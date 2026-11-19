"""Informes calculados, exportacion no destructiva y graficos opcionales."""

from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path

from .procedencia import guardar_json, ruta_visible
from .rendimiento import Comparacion
from .resultados import Ejecucion


def numero(valor, decimales: int = 6) -> str:
    return "N/D" if valor is None else f"{valor:.{decimales}f}"


def porcentaje_ic(valores) -> str:
    return f"[{100 * valores[0]:.4f} %, {100 * valores[1]:.4f} %]"


def informe_ejecucion(e: Ejecucion) -> str:
    s, m = e.estadisticas, e.metricas
    texto = [
        "# Analisis de resultados y rendimiento — S13",
        "",
        f"Origen: `{ruta_visible(e.carpeta)}`",
        f"Version: **{m['version']}**; procesos x hilos: **{m['procesos']} x {m['hilos']}**.",
        f"R = {s['escenarios']:,}; estados observados: {s['anio_inicial']}–{s['anio_final']}; "
        f"{m['horizonte']} transiciones anuales. Evento: **A > J**, el empate no cuenta.",
        "",
        "## Resultados demograficos",
        "",
        f"- Con inversion dentro del horizonte: **{s['con_inversion']:,}** "
        f"({s['probabilidad_inversion']:.4%}); IC Wilson 95 %: "
        f"{porcentaje_ic(s['ic95_probabilidad_inversion'])}.",
        f"- Sin inversion observada: **{s['sin_inversion']:,}** "
        f"({s['probabilidad_sin_inversion']:.4%}); IC Wilson 95 %: "
        f"{porcentaje_ic(s['ic95_sin_inversion'])}.",
    ]
    if s["con_inversion"]:
        texto += [
            f"- Media **condicional a la inversion en el horizonte**: **{s['media_condicional']:.6f}**.",
            f"- Mediana condicional (cuantil empirico): {s['mediana_condicional']}; "
            f"rango observado: {s['minimo']}–{s['maximo']}.",
            f"- Desviacion empirica entre anios: **{s['desviacion_condicional']:.6f} anios** "
            "(denominador: escenarios con inversion).",
            f"- Cuantiles empiricos 2,5 % y 97,5 % del anio, condicionales al cruce: "
            f"**{s['p025_condicional']}–{s['p975_condicional']}**. "
            "Describen dispersion; no son un IC de la media.",
            f"- Error estandar Monte Carlo de la media: **{numero(s['error_estandar_media'], 8)} anios** "
            "(desviacion muestral / raiz del numero de escenarios con inversion).",
        ]
        ic = s["ic95_media_condicional"]
        texto.append("- IC normal aproximado 95 % de la media condicional: "
                     + (f"**[{ic[0]:.8f}, {ic[1]:.8f}]**." if ic else "**N/D** (muestra insuficiente "
                        "o sin dispersion observada)."))
        if s["desviacion_condicional"] == 0:
            texto.append(f"- Todos los cruces observados se concentran en **{s['minimo']}**. "
                         "Esto describe esta muestra, no demuestra que el anio sea determinista.")
    else:
        texto.append("- No hay cruces observados: media, dispersion, cuantiles condicionales e IC de la media "
                     "no estan definidos. No se sustituyen los casos censurados por otro anio.")
    for nombre, clave in (("Mediana", "mediana_no_condicional"), ("Cuantil 95 %", "p95_no_condicional")):
        anio = s[clave]
        texto.append(f"- {nombre} **no condicional**, considerando todos los escenarios: "
                     + (str(anio) if anio is not None else f"no alcanzado hasta {s['anio_final']}") + ".")
    texto += [
        "",
        "## Rendimiento de esta ejecucion",
        "",
        f"- Tiempo total del simulador hasta antes del resumen: **{m['segundos_total']:.6f} s**.",
        f"- Tiempo de simulacion y escritura de escenarios: **{m['segundos_simulacion']:.6f} s**.",
        f"- Rendimiento de esa fase: **{m['escenarios_por_segundo']:.3f} escenarios/s**; "
        f"**{m['ms_por_escenario']:.6f} ms/escenario**.",
    ]
    if m["version"] != "go_secuencial":
        texto.append(f"- CPU/pared informado: **{m['segundos_cpu'] / m['segundos_total']:.3f}**. "
                     "No es speedup ni porcentaje de eficiencia.")
    else:
        texto.append("- CPU/pared: **N/D**; esta implementacion Go no mide tiempo de CPU.")
    memoria = m["memoria_pico_mib"]
    alcance = ("memoria informada por Go (alcance dependiente de plataforma)" if m["version"] == "go_secuencial"
               else "RSS pico maximo por proceso" if m["version"] in {"mpi", "hibrido", "mpi_cuda"} else "RSS pico del proceso")
    texto.append(f"- {alcance}: **{numero(memoria if memoria > 0 else None, 3)} MiB**. "
                 "Cero en el archivo significa medicion no disponible, no consumo nulo.")
    if m["version"] in {"mpi", "hibrido", "mpi_cuda"}:
        texto.append(f"- Espera + comunicacion informada: **{numero(m['segundos_comunicacion'])} s**; "
                     "incluye espera/desbalance y no permite aislar solo transferencia de datos.")
    if e.procedencia:
        p = e.procedencia
        maquina = p["contexto"]["maquina"]
        texto += [
            f"- Procedencia registrada al ejecutar: {p['inicio_utc']}; CPU: {maquina['cpu']}; "
            f"CPU logicas disponibles: {maquina['cpus_disponibles']}.",
            f"- ID de ejecucion: `{p['ejecucion_id']}`; ID de equipo (SHA-256): `{maquina['id']}`.",
        ]
    texto += [
        "- **Speedup individual: N/D.** Use una campana con linea base comparable; nunca se toma T1 "
        "de otra computadora o de un valor fijo.",
        "",
        "## Configuracion efectiva disponible",
        "",
        *[f"- `{k}={v}`" for k, v in sorted(e.configuracion.items())],
        "",
        "## Interpretacion y limites",
        "",
        *[f"- {aviso}" for aviso in e.avisos],
        "- La trayectoria del escenario 1, si existe, es una realizacion y no el promedio de la poblacion.",
    ]
    return "\n".join(texto) + "\n"


def informe_comparacion(c: Comparacion) -> str:
    texto = ["# Comparacion de rendimiento — S13", ""]
    if c.contexto:
        maquina = c.contexto["maquina"]
        texto += [f"CPU: {maquina['cpu']}; CPU disponibles: {maquina['cpus_disponibles']}.",
                  f"Entorno: {c.contexto['entorno']['sistema']}.",
                  f"Firma de fuentes: `{c.contexto['fuentes_sha256']}`.", ""]
    if c.campana_id:
        texto += [f"Campana: `{c.campana_id}`.",
                  f"Origen de las mediciones: "
                  f"`{ruta_visible(c.contexto.get('almacenamiento', 'ver metricas_crudas.csv'))}`.",
                  "Parametros disponibles: " + "; ".join(f"`{k}={v}`" for k, v in sorted(c.parametros.items())),
                  ""]
    if c.filas:
        texto += [
            "| Version | P x H | R | Reps | T media ± sd (s) | Speedup | Eficiencia | Costo (s) | "
            "Karp-Flatt | Amdahl 1/f |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for f in c.filas:
            texto.append(
                f"| {f['version']} | {f['procesos']} x {f['hilos']} | {f['escenarios']} | {f['repeticiones']} | "
                f"{f['segundos_total_media']:.6f} ± {numero(f['segundos_total_sd'])} | "
                f"{f['speedup']:.3f} | {f['eficiencia']:.2%} | {f['costo']:.6f} | "
                f"{numero(f['karp_flatt'])} | {numero(f['amdahl_smax'], 3)} |"
            )
    texto += ["", "## Lectura de esta comparacion", "", *[f"- {s}" for s in c.conclusiones]]
    if c.excluidas:
        texto += ["", "## Ejecuciones excluidas", ""]
        texto += [f"- `{ruta_visible(e['carpeta'])}`: {e['motivo']}" for e in c.excluidas]
    return "\n".join(texto) + "\n"


def escribir_csv(archivo: Path, filas: list[dict]) -> None:
    if not filas:
        return
    with archivo.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)


def figura_ejecucion(e: Ejecucion):
    from matplotlib.figure import Figure
    fig = Figure(figsize=(11, 4.3), dpi=110)
    ax, ac = fig.subplots(1, 2)
    xs = [f["anio"] for f in e.distribucion]
    ax.bar(xs, [f["probabilidad_anual"] for f in e.distribucion], color="#1E5F8A")
    ax.set(xlabel="Primer anio T (A > J)", ylabel="P(T = y)", title="Distribucion: todos los escenarios")
    ac.step(xs, [f["probabilidad_acumulada"] for f in e.distribucion], where="post", label="F empirica")
    ac.fill_between(xs, [f["acumulada_ic95_inferior"] for f in e.distribucion],
                    [f["acumulada_ic95_superior"] for f in e.distribucion], step="post", alpha=.2,
                    label="IC Wilson 95 % puntual")
    ac.set(xlabel="Anio", ylabel="P(T <= y)", ylim=(0, 1.02), title="Acumulada (no condicional)")
    ac.legend(fontsize=8)
    for eje in (ax, ac):
        eje.grid(axis="y", alpha=.2)
    fig.suptitle(f"{e.metricas['version']}; R={e.metricas['escenarios']:,}; "
                 f"sin cruce en horizonte: {e.estadisticas['probabilidad_sin_inversion']:.3%}")
    fig.tight_layout()
    return fig


def figura_comparacion(c: Comparacion):
    from matplotlib.figure import Figure
    fig = Figure(figsize=(11, 4.3), dpi=110)
    ax, ae = fig.subplots(1, 2)
    if not c.filas:
        for eje in (ax, ae):
            eje.text(.5, .5, "Sin T1/campana comparable", ha="center", va="center", transform=eje.transAxes)
    else:
        max_p = max(f["p"] for f in c.filas)
        ax.plot([1, max_p], [1, max_p], "--", color="gray", label="Ideal S=p")
        ae.axhline(1, ls="--", color="gray", label="Ideal E=1")
        for version in ("openmp", "mpi", "hibrido"):
            filas = sorted((f for f in c.filas if f["version"] == version), key=lambda f: f["p"])
            if not filas:
                continue
            for eje, clave in ((ax, "speedup"), (ae, "eficiencia")):
                eje.plot([f["p"] for f in filas], [f[clave] for f in filas],
                         "o" if version == "hibrido" else "o-", label=version)
                if version == "hibrido":
                    for f in filas:
                        eje.annotate(f"{f['procesos']}x{f['hilos']}", (f["p"], f[clave]), xytext=(4, 4),
                                     textcoords="offset points", fontsize=8)
        for eje in (ax, ae):
            eje.legend(fontsize=8)
    ax.set(xlabel="Trabajadores solicitados p", ylabel="T1/Tp", title="Speedup")
    ae.set(xlabel="Trabajadores solicitados p", ylabel="S/p", title="Eficiencia relativa")
    for eje in (ax, ae):
        eje.grid(alpha=.2)
    fig.tight_layout()
    return fig


def exportar_ejecucion(e: Ejecucion, salida: Path | str, graficos: bool = True) -> Path:
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=False)
    (salida / "informe.md").write_text(informe_ejecucion(e), encoding="utf-8")
    contenido = asdict(e)
    contenido["carpeta"] = str(e.carpeta)
    guardar_json(salida / "analisis.json", contenido)
    escribir_csv(salida / "distribucion_analizada.csv", e.distribucion)
    escribir_csv(salida / "estadisticas.csv", [dict(metrica=k, valor=v) for k, v in e.estadisticas.items()])
    if graficos:
        try:
            from matplotlib.backends.backend_agg import FigureCanvasAgg
        except ImportError:
            (salida / "graficos_no_disponibles.txt").write_text(
                "Instale matplotlib para generar PNG. El informe numerico esta completo.\n", encoding="utf-8")
        else:
            fig = figura_ejecucion(e)
            FigureCanvasAgg(fig).print_png(str(salida / "resultados.png"))
    return salida


def exportar_comparacion(c: Comparacion, salida: Path | str, graficos: bool = True) -> Path:
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=False)
    (salida / "informe.md").write_text(informe_comparacion(c), encoding="utf-8")
    guardar_json(salida / "comparacion.json", asdict(c))
    escribir_csv(salida / "rendimiento.csv", c.filas)
    escribir_csv(salida / "metricas_crudas.csv", c.usadas)
    escribir_csv(salida / "excluidas.csv", c.excluidas)
    if graficos:
        try:
            from matplotlib.backends.backend_agg import FigureCanvasAgg
        except ImportError:
            (salida / "graficos_no_disponibles.txt").write_text("Instale matplotlib para generar PNG.\n",
                                                             encoding="utf-8")
        else:
            fig = figura_comparacion(c)
            FigureCanvasAgg(fig).print_png(str(salida / "rendimiento.png"))
            if c.filas:
                from matplotlib.figure import Figure
                tiempos = Figure(figsize=(10, 4), dpi=110)
                ax = tiempos.subplots()
                ax.bar(range(len(c.filas)), [f["segundos_total_media"] for f in c.filas],
                       yerr=[f["segundos_total_sd"] or 0 for f in c.filas], capsize=4)
                ax.set_xticks(range(len(c.filas)), [f"{f['version']}\n{f['procesos']}x{f['hilos']}"
                                                   for f in c.filas])
                ax.set(ylabel="Segundos", title="Tiempo total: media y desviacion muestral (no IC)")
                tiempos.tight_layout()
                FigureCanvasAgg(tiempos).print_png(str(salida / "tiempos.png"))
    return salida
