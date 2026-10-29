#!/usr/bin/env python3
"""Linea base secuencial: ejecuta el simulador varias veces y agrega las metricas.

Uso:
    python3 scripts/linea_base.py [--escenarios 1000 10000 100000] [--repeticiones 3]
                                  [--salida linea_base] [--ejecutable ./simulador]

Para cada R ejecuta el simulador `repeticiones` veces (misma semilla, resultados identicos),
lee el metricas.csv de cada corrida y produce en la carpeta de salida:
    metricas_crudas.csv       una fila por corrida
    metricas_secuencial.csv   media y desviacion estandar por R  (T1 de referencia para el Sprint 3)
    linea_base.md             tabla lista para el informe
    linea_base_tiempos.png    tiempo total y escenarios/s frente a R

El T1 que se use para el speedup en el Sprint 3 es la MEDIA de `segundos_total` para el mismo R,
en la misma maquina y con el mismo compilador y banderas.
"""
import argparse
import csv
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path


def ejecutar(ejecutable, config, datos, R, carpeta):
    subprocess.run([str(ejecutable), "--config", str(config), "--datos", str(datos),
                    "--salida", str(carpeta), "--escenarios", str(R)],
                   check=True, stdout=subprocess.DEVNULL)
    with open(carpeta / "metricas.csv", newline="") as f:
        fila = next(csv.DictReader(f))
    return {k: (float(v) if k not in ("version",) else v) for k, v in fila.items()}


def media_sd(valores):
    m = statistics.fmean(valores)
    sd = statistics.stdev(valores) if len(valores) > 1 else 0.0
    return m, sd


def info_maquina():
    cpu = platform.processor() or ""
    try:
        for linea in open("/proc/cpuinfo"):
            if linea.startswith("model name"):
                cpu = linea.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    try:
        gxx = subprocess.run(["g++", "--version"], capture_output=True, text=True).stdout.splitlines()[0]
    except (OSError, IndexError):
        gxx = "g++ (version desconocida)"
    return f"{cpu} · {platform.system()} {platform.release()} · {gxx} · -O2"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--escenarios", type=int, nargs="+", default=[1000, 10000, 100000])
    ap.add_argument("--repeticiones", type=int, default=3)
    ap.add_argument("--salida", type=Path, default=Path("linea_base"))
    ap.add_argument("--ejecutable", type=Path, default=Path("./simulador"))
    ap.add_argument("--config", type=Path, default=Path("config_demostracion.ini"))
    ap.add_argument("--datos", type=Path, default=Path("datos"))
    ap.add_argument("--solo-informe", action="store_true",
                    help="no ejecuta nada: rehace la tabla y el grafico a partir de metricas_crudas.csv")
    a = ap.parse_args()

    if not a.solo_informe and not a.ejecutable.exists():
        sys.exit(f"No existe {a.ejecutable}. Compile primero con `make`.")
    a.ejecutable = a.ejecutable.resolve()  # Path("./simulador") perderia el "./" al pasar a subprocess
    a.salida.mkdir(parents=True, exist_ok=True)

    crudas = []
    if a.solo_informe:
        with open(a.salida / "metricas_crudas.csv", newline="") as f:
            for fila in csv.DictReader(f):
                crudas.append({k: (float(v) if k != "version" else v) for k, v in fila.items()})
        a.escenarios = sorted({int(m["escenarios"]) for m in crudas})
        a.repeticiones = max(int(m["repeticion"]) for m in crudas)
    with tempfile.TemporaryDirectory() as tmp:
        if a.solo_informe:
            a.escenarios_a_ejecutar = []
        else:
            a.escenarios_a_ejecutar = a.escenarios
        for R in a.escenarios_a_ejecutar:
            for rep in range(1, a.repeticiones + 1):
                carpeta = Path(tmp) / f"R{R}_rep{rep}"
                m = ejecutar(a.ejecutable, a.config, a.datos, R, carpeta)
                m["repeticion"] = rep
                crudas.append(m)
                print(f"R={R:>8}  rep {rep}: total {m['segundos_total']:8.3f} s  "
                      f"{m['escenarios_por_segundo']:7.1f} esc/s  RSS {m['memoria_pico_mib']:.1f} MiB", flush=True)
                shutil.rmtree(carpeta, ignore_errors=True)

    columnas = ["version", "procesos", "hilos", "escenarios", "horizonte", "repeticion", "segundos_carga",
                "segundos_simulacion", "segundos_total", "segundos_cpu", "ms_por_escenario",
                "escenarios_por_segundo", "escenario_anios_por_segundo", "memoria_pico_mib"]
    with open(a.salida / "metricas_crudas.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columnas)
        w.writeheader()
        w.writerows({k: m[k] for k in columnas} for m in crudas)

    # Agregacion por R
    agregadas = []
    for R in a.escenarios:
        filas = [m for m in crudas if int(m["escenarios"]) == R]
        t_m, t_sd = media_sd([m["segundos_total"] for m in filas])
        s_m, s_sd = media_sd([m["segundos_simulacion"] for m in filas])
        c_m, _ = media_sd([m["segundos_cpu"] for m in filas])
        ms_m, ms_sd = media_sd([m["ms_por_escenario"] for m in filas])
        th_m, th_sd = media_sd([m["escenarios_por_segundo"] for m in filas])
        mem_m = max(m["memoria_pico_mib"] for m in filas)
        agregadas.append(dict(escenarios=R, repeticiones=len(filas), horizonte=int(filas[0]["horizonte"]),
                              T1_segundos_media=t_m, T1_segundos_sd=t_sd, cv_porcentaje=100 * t_sd / t_m,
                              simulacion_segundos_media=s_m, simulacion_segundos_sd=s_sd,
                              cpu_segundos_media=c_m, uso_cpu_porcentaje=100 * c_m / t_m,
                              ms_por_escenario_media=ms_m, ms_por_escenario_sd=ms_sd,
                              escenarios_por_segundo_media=th_m, escenarios_por_segundo_sd=th_sd,
                              escenario_anios_por_segundo=th_m * int(filas[0]["horizonte"]),
                              memoria_pico_mib_max=mem_m))
    with open(a.salida / "metricas_secuencial.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(agregadas[0].keys()))
        w.writeheader()
        w.writerows(agregadas)

    # Tabla markdown
    maquina = info_maquina()
    md = [f"# Linea base secuencial (T1)\n", f"Maquina: {maquina}\n",
          f"Repeticiones por R: {a.repeticiones}. Misma semilla en todas: los CSV de resultados son identicos; "
          "solo varia el tiempo.\n",
          "| R (escenarios) | T1 total (s) media ± sd | CV (%) | CPU/pared (%) | ms / escenario | escenarios/s | "
          "escenario-anios/s | RSS pico (MiB) |", "|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for g in agregadas:
        md.append(f"| {g['escenarios']:,} | {g['T1_segundos_media']:.3f} ± {g['T1_segundos_sd']:.3f} | "
                  f"{g['cv_porcentaje']:.1f} | {g['uso_cpu_porcentaje']:.1f} | {g['ms_por_escenario_media']:.3f} | "
                  f"{g['escenarios_por_segundo_media']:.1f} | {g['escenario_anios_por_segundo']:,.0f} | "
                  f"{g['memoria_pico_mib_max']:.1f} |")
    if len(agregadas) >= 2:
        r0, r1 = agregadas[0], agregadas[-1]
        factor_R = r1["escenarios"] / r0["escenarios"]
        factor_T = r1["T1_segundos_media"] / r0["T1_segundos_media"]
        md.append(f"\nEscalado con R: al multiplicar R por {factor_R:,.0f} el tiempo se multiplica por "
                  f"{factor_T:,.1f} (lineal: O(R·H), sin crecimiento de memoria).")
    md.append("\nMetricas del Sprint 3 que se calcularan con este T1 (mismo R, misma maquina):\n"
              "- Speedup S(p) = T1 / Tp\n- Eficiencia E(p) = S(p) / p\n- Costo C(p) = p · Tp\n"
              "- Fraccion secuencial (Karp-Flatt) f = (1/S(p) − 1/p) / (1 − 1/p)\n"
              "- Cota de Amdahl S_max = 1 / f\n")
    (a.salida / "linea_base.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))

    # Grafico
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib no disponible; no se genera el grafico.")
        return
    Rs = [g["escenarios"] for g in agregadas]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    ax1.errorbar(Rs, [g["T1_segundos_media"] for g in agregadas], yerr=[g["T1_segundos_sd"] for g in agregadas],
                 marker="o", capsize=4, color="#1f4e79")
    ax1.set_xscale("log"); ax1.set_yscale("log")
    ax1.set_xlabel("R (escenarios)"); ax1.set_ylabel("T1 total (s)")
    ax1.set_title("Tiempo secuencial frente a R (media ± sd)")
    ax1.set_xticks(Rs); ax1.set_xticklabels([f"{r:,}".replace(",", " ") for r in Rs])
    ax1.grid(True, which="both", alpha=0.3)
    ax2.bar([f"{r:,}".replace(",", " ") for r in Rs], [g["escenarios_por_segundo_media"] for g in agregadas], color="#a04a0c")
    ax2.set_xlabel("R (escenarios)"); ax2.set_ylabel("escenarios / s")
    ax2.set_title("Rendimiento (throughput) secuencial")
    ax2.grid(True, axis="y", alpha=0.3)
    fig.suptitle("Linea base secuencial: 1 proceso, 1 hilo", fontsize=11)
    fig.tight_layout()
    fig.savefig(a.salida / "linea_base_tiempos.png", dpi=150)
    print(f"Grafico: {a.salida / 'linea_base_tiempos.png'}")


if __name__ == "__main__":
    main()
