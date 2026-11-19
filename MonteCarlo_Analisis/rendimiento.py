"""Comparaciones conservadoras: sin T1 comparable no hay speedup."""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .procedencia import CRITERIO, huella
from .resultados import Ejecucion, analizar_ejecucion


@dataclass
class Comparacion:
    filas: list[dict]
    excluidas: list[dict]
    conclusiones: list[str]
    contexto: dict | None
    campana_id: str | None = None
    parametros: dict = field(default_factory=dict)
    usadas: list[dict] = field(default_factory=list)


def descubrir_ejecuciones(carpeta: Path | str) -> list[Path]:
    carpeta = Path(carpeta).resolve()
    if (carpeta / "metricas.csv").is_file():
        return [carpeta]
    # Solo el nivel inmediato de la carpeta elegida, sin recorrer todo el repositorio.
    return sorted(p.parent for p in carpeta.glob("*/metricas.csv"))


def media_sd(valores: list[float]) -> tuple[float, float | None]:
    return statistics.fmean(valores), statistics.stdev(valores) if len(valores) > 1 else None


def comparar_ejecuciones(carpetas: list[Path | str]) -> Comparacion:
    ejecuciones: list[Ejecucion] = []
    excluidas = []
    identidades = set()
    for carpeta in carpetas:
        try:
            e = analizar_ejecucion(carpeta)
        except (ValueError, OSError) as exc:
            excluidas.append(dict(carpeta=str(carpeta), motivo=f"Salida invalida: {exc}"))
            continue
        p = e.procedencia
        motivo = None
        if p is None:
            motivo = "Sin procedencia verificable; no se infiere el equipo actual para una salida antigua."
        elif p.get("criterio") != CRITERIO or e.metricas["version"] == "go_secuencial":
            motivo = "Go es una comparacion de lenguaje, no speedup paralelo del mismo ejecutable/modelo C++."
        elif not p.get("campana_id") or not isinstance(p.get("equivalencia_sha256"), dict):
            motivo = "Falta una campana controlada con comprobacion de equivalencia."
        elif p["ejecucion_id"] in identidades:
            motivo = "Ejecucion duplicada (mismo ID); una copia no es una repeticion independiente."
        if motivo:
            excluidas.append(dict(carpeta=str(e.carpeta), motivo=motivo))
        else:
            try:
                archivos = p["equivalencia_sha256"]
                if not {"escenarios.csv", "trayectoria_escenario_1.csv"} <= archivos.keys():
                    raise ValueError("faltan escenarios/trayectoria")
                for nombre, esperado in archivos.items():
                    if nombre not in {"escenarios.csv", "trayectoria_escenario_1.csv", "factores_escenarios.csv"}:
                        raise ValueError("nombre de archivo no reconocido")
                    if huella(e.carpeta / nombre) != esperado:
                        raise ValueError(f"{nombre} cambio despues de medir")
            except (ValueError, OSError) as exc:
                excluidas.append(dict(carpeta=str(e.carpeta), motivo=f"Equivalencia no verificable: {exc}"))
                continue
            identidades.add(p["ejecucion_id"])
            ejecuciones.append(e)
    bases = [e for e in ejecuciones if e.metricas["version"] == "secuencial"]
    if not bases:
        return Comparacion([], excluidas, [
            "Speedup no disponible: falta una linea base secuencial C++ de una campana verificable.",
            "Los tiempos individuales pueden analizarse sin calcular una aceleracion.",
        ], None)
    # No elegir silenciosamente una de varias maquinas/campanas/entradas.
    firmas = {(e.procedencia["campana_id"], e.procedencia["firma_contexto"]) for e in bases}
    if len(firmas) != 1:
        return Comparacion([], excluidas, [
            "Hay lineas base de distintas campanas o contextos. Seleccione una sola campana; no se mezclan sus tiempos.",
        ], None)
    base = bases[0]
    bp = base.procedencia
    declaradas = None
    manifiesto = base.carpeta.parent / "campana.json"
    if manifiesto.is_file():
        try:
            datos = json.loads(manifiesto.read_text(encoding="utf-8"))
            if not isinstance(datos, dict):
                raise ValueError("estructura invalida")
            if datos.get("estado") != "completada" or datos.get("campana_id") != bp["campana_id"]:
                raise ValueError("campana incompleta o identidad distinta")
            declaradas = datos["repeticiones"]
            if type(declaradas) is not int or declaradas < 1:
                raise ValueError("numero de repeticiones invalido")
            nombres = datos.get("ejecuciones")
            if (not isinstance(nombres, list) or not nombres
                    or any(not isinstance(n, str) or not n or n in {".", ".."} or "/" in n or "\\" in n
                           for n in nombres) or len(set(nombres)) != len(nombres)):
                raise ValueError("lista de ejecuciones invalida")
            seleccionadas = {Path(c).resolve() for c in carpetas}
            if any(base.carpeta.parent / n not in seleccionadas for n in nombres):
                raise ValueError("faltan ejecuciones declaradas; seleccione la campana completa")
        except (ValueError, KeyError, TypeError) as exc:
            return Comparacion([], excluidas, [f"Speedup no disponible: manifiesto de {exc}."], bp["contexto"])
    grupos: dict[tuple, list[Ejecucion]] = defaultdict(list)
    for e in ejecuciones:
        p, m = e.procedencia, e.metricas
        motivo = None
        if p["campana_id"] != bp["campana_id"]:
            motivo = "Distinta campana: no se mezclan sesiones de medicion."
        elif p["firma_contexto"] != bp["firma_contexto"]:
            motivo = "Distinto equipo/entorno, datos, configuracion, fuentes, binarios o almacenamiento."
        elif any(m[k] != base.metricas[k] for k in ("escenarios", "horizonte")):
            motivo = "Distinta carga: numero de escenarios u horizonte."
        elif e.configuracion != base.configuracion:
            motivo = "Distintos parametros efectivos."
        elif p["equivalencia_sha256"] != bp["equivalencia_sha256"]:
            motivo = "Los CSV de resultados no coinciden byte a byte con la linea base."
        elif e.distribucion != base.distribucion:
            motivo = "La distribucion no coincide con la linea base."
        if motivo:
            excluidas.append(dict(carpeta=str(e.carpeta), motivo=motivo))
        else:
            grupos[(m["version"], m["procesos"], m["hilos"])].append(e)
    basereps = grupos.get(("secuencial", 1, 1), [])
    repeticiones = [e.procedencia.get("repeticion") for e in basereps]
    if (not repeticiones or any(type(n) is not int or n < 1 for n in repeticiones)
            or len(set(repeticiones)) != len(repeticiones)):
        return Comparacion([], excluidas, ["Linea base sin repeticiones unicas validas."], bp["contexto"])
    if declaradas is not None and set(repeticiones) != set(range(1, declaradas + 1)):
        return Comparacion([], excluidas, ["Speedup no disponible: faltan repeticiones declaradas de T1."],
                           bp["contexto"])
    t1, _ = media_sd([e.metricas["segundos_total"] for e in basereps])
    filas = []
    usadas = []
    conclusiones = [
        "T = segundos_total del simulador: desde la carga hasta antes de escribir resumen/distribucion/SVG/metricas. "
        "MPI excluye MPI_Init y MPI_Finalize. El arranque externo y el analisis no forman parte de T.",
        "p cuenta trabajadores solicitados (hilos o procesos x hilos), no nucleos fisicos.",
        "Karp-Flatt es una fraccion serial efectiva con sobrecostos; no identifica por si sola sus causas. "
        "1/f es una extrapolacion de Amdahl, no un maximo de aceleracion demostrado.",
        "CPU/pared no es speedup. La memoria MPI es maxima por proceso, no memoria total del trabajo.",
        "Las herramientas registradas son las detectadas al ejecutar; no certifican las banderas con que se "
        "compilo cada binario. Sus huellas permiten identificar los binarios utilizados.",
    ]
    for (version, procesos, hilos), grupo in sorted(grupos.items()):
        reps = [e.procedencia.get("repeticion") for e in grupo]
        if len(set(reps)) != len(reps) or set(reps) != set(repeticiones):
            for e in grupo:
                excluidas.append(dict(carpeta=str(e.carpeta),
                                       motivo="Repeticiones duplicadas o incompletas respecto de T1."))
            continue
        media, sd = media_sd([e.metricas["segundos_total"] for e in grupo])
        p = procesos * hilos
        speedup = t1 / media
        f = (1 / speedup - 1 / p) / (1 - 1 / p) if p > 1 else None
        simulacion = statistics.fmean(e.metricas["segundos_simulacion"] for e in grupo)
        fila = dict(version=version, procesos=procesos, hilos=hilos, p=p, repeticiones=len(grupo),
                    escenarios=base.metricas["escenarios"], horizonte=base.metricas["horizonte"],
                    segundos_total_media=media, segundos_total_sd=sd,
                    speedup=speedup, eficiencia=speedup / p, costo=p * media,
                    karp_flatt=f, amdahl_smax=1 / f if f is not None and 0 < f <= 1 else None,
                    escenarios_por_segundo=base.metricas["escenarios"] / simulacion,
                    memoria_max_por_proceso_mib=max(e.metricas["memoria_pico_mib"] for e in grupo) or None,
                    comunicacion_media=(
                        statistics.fmean(e.metricas["segundos_comunicacion"] for e in grupo)
                        if version in {"mpi", "hibrido"}
                        and all(e.metricas["segundos_comunicacion"] is not None for e in grupo) else None),
                    cpu_pared=statistics.fmean(e.metricas["segundos_cpu"] for e in grupo) / media)
        filas.append(fila)
        for e in grupo:
            usadas.append(dict(
                carpeta=str(e.carpeta), ejecucion_id=e.procedencia["ejecucion_id"],
                repeticion=e.procedencia["repeticion"], inicio_utc=e.procedencia["inicio_utc"],
                **{k: e.metricas[k] for k in (
                    "version", "procesos", "hilos", "escenarios", "horizonte",
                    "segundos_carga", "segundos_simulacion", "segundos_total", "segundos_cpu",
                    "memoria_pico_mib", "segundos_comunicacion", "ms_por_escenario", "escenarios_por_segundo")},
            ))
        if version != "secuencial":
            descripcion = f"{version}, {procesos} proceso(s) x {hilos} hilo(s)"
            conclusiones.append(
                f"{descripcion}: S={speedup:.3f}, E={speedup / p:.1%}; "
                + ("menor tiempo medio que T1." if speedup > 1 else
                   "no mejora el tiempo medio de T1 en esta campana.")
            )
            if f is not None and not 0 < f <= 1:
                conclusiones.append(f"{descripcion}: f fuera de (0,1]; no se extrapola 1/f.")
    paralelas = [f for f in filas if f["version"] != "secuencial"]
    if paralelas:
        mejor = min(filas, key=lambda f: f["segundos_total_media"])
        conclusiones.append(
            f"Menor tiempo medio observado entre las configuraciones evaluadas: {mejor['version']} "
            f"{mejor['procesos']}x{mejor['hilos']} ({mejor['segundos_total_media']:.6f} s). "
            "Es una comparacion descriptiva de medias, no prueba de significacion ni garantia para otro equipo."
        )
    if len(repeticiones) < 3:
        conclusiones.append("Menos de 3 repeticiones: resultado preliminar; no ocultar la variabilidad.")
    if any(f["segundos_total_media"] < 1 for f in filas):
        conclusiones.append("Hay tiempos medios inferiores a 1 segundo: diagnostico de ejecucion corta, "
                            "muy sensible al arranque de hilos, E/S y ruido. Aumente R para el estudio final.")
    if bp.get("sobresuscripcion"):
        conclusiones.append("Se permitio sobresuscripcion: los trabajadores pueden competir por las mismas CPU.")
    if any(f["p"] > bp["contexto"]["maquina"]["cpus_disponibles"] for f in filas):
        conclusiones.append("Hay configuraciones con mas trabajadores que CPU disponibles.")
    if excluidas:
        conclusiones.append("Existen ejecuciones excluidas; revise sus motivos antes de usar la comparacion.")
    conclusiones.append("Frecuencia, temperatura y carga ajena no estan controladas/medidas por este modulo; "
                        "no se atribuyen cuellos de botella sin evidencia adicional.")
    return Comparacion(filas, excluidas, conclusiones, bp["contexto"],
                       campana_id=bp["campana_id"], parametros=base.configuracion, usadas=usadas)
