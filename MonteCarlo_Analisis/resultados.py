"""Lectura validada de las salidas existentes, sin cargar millones de escenarios."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

VERSIONES = {"secuencial", "openmp", "mpi", "hibrido", "go_secuencial", "cuda", "mpi_cuda"}
VERSIONES_GPU = {"cuda", "mpi_cuda"}
Z95 = 1.959963984540054


def entero(valor: object, nombre: str, minimo: int = 0) -> int:
    """No redondear conteos ni aceptar NaN, infinitos o valores fraccionarios."""
    try:
        n = int(str(valor))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{nombre}: se esperaba un entero, no {valor!r}") from exc
    if n < minimo:
        raise ValueError(f"{nombre}: debe ser >= {minimo}")
    return n


def real(valor: object, nombre: str, minimo: float = 0) -> float:
    try:
        n = float(valor)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{nombre}: numero invalido") from exc
    if not math.isfinite(n) or n < minimo:
        raise ValueError(f"{nombre}: debe ser finito y >= {minimo}")
    return n


def leer_pares(archivo: Path, estricto: bool = False) -> dict[str, str]:
    valores: dict[str, str] = {}
    if not archivo.is_file():
        return valores
    for linea in archivo.read_text(encoding="utf-8-sig").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        if "=" not in linea:
            if estricto:
                raise ValueError(f"{archivo.name}: se esperaba clave=valor")
            continue  # parametros_efectivos.txt tambien contiene comentarios libres
        clave, valor = (p.strip() for p in linea.split("=", 1))
        if clave in valores:
            raise ValueError(f"{archivo.name}: clave duplicada {clave}")
        valores[clave] = valor
    return valores


def leer_csv(archivo: Path) -> list[dict[str, str]]:
    with archivo.open(newline="", encoding="utf-8-sig") as f:
        lector = csv.DictReader(f)
        if not lector.fieldnames or len(set(lector.fieldnames)) != len(lector.fieldnames):
            raise ValueError(f"{archivo.name}: cabecera ausente o duplicada")
        filas = list(lector)
    if not filas or any(None in fila or None in fila.values() for fila in filas):
        raise ValueError(f"{archivo.name}: CSV vacio o fila incompleta")
    return filas


def leer_metricas(carpeta: Path) -> dict:
    filas = leer_csv(carpeta / "metricas.csv")
    if len(filas) != 1:
        raise ValueError("metricas.csv debe contener exactamente una ejecucion")
    m = dict(filas[0])
    if m.get("version") not in VERSIONES:
        raise ValueError(f"Version no reconocida: {m.get('version')!r}")
    for k in ("procesos", "hilos", "escenarios", "horizonte"):
        m[k] = entero(m.get(k), k, 1)
    for k in ("segundos_total", "segundos_simulacion", "segundos_carga", "segundos_cpu",
              "memoria_pico_mib", "ms_por_escenario", "escenarios_por_segundo"):
        m[k] = real(m.get(k), k)
    if m["segundos_total"] <= 0 or m["segundos_simulacion"] <= 0:
        raise ValueError("Los tiempos total y de simulacion deben ser positivos")
    if m["segundos_simulacion"] > m["segundos_total"] + 1e-6:
        raise ValueError("El tiempo de simulacion supera al tiempo total")
    if m["segundos_carga"] > m["segundos_total"] + 1e-6:
        raise ValueError("El tiempo de carga supera al tiempo total")
    for k, esperado in (
        ("ms_por_escenario", 1000 * m["segundos_simulacion"] / m["escenarios"]),
        ("escenarios_por_segundo", m["escenarios"] / m["segundos_simulacion"]),
    ):
        if not math.isclose(m[k], esperado, rel_tol=1e-5, abs_tol=1e-6):
            raise ValueError(f"metricas.csv: {k} no coincide con escenarios/tiempo")
    m["segundos_comunicacion"] = (
        real(m["segundos_comunicacion"], "segundos_comunicacion")
        if m.get("segundos_comunicacion", "") != "" else None
    )
    p, h, v = m["procesos"], m["hilos"], m["version"]
    if ((v in {"secuencial", "go_secuencial", "cuda"} and (p, h) != (1, 1))
            or (v == "openmp" and p != 1) or (v == "mpi" and h != 1)):
        raise ValueError("Procesos/hilos incompatibles con la version declarada")
    return m


def wilson(exitos: int, total: int) -> tuple[float, float]:
    """IC binomial Wilson 95%; no degenera a [0,0] ni [1,1] en los extremos."""
    if total < 1 or not 0 <= exitos <= total:
        raise ValueError("Conteos invalidos para Wilson")
    p, z2 = exitos / total, Z95 ** 2
    centro = (p + z2 / (2 * total)) / (1 + z2 / total)
    radio = Z95 * math.sqrt(p * (1 - p) / total + z2 / (4 * total ** 2)) / (1 + z2 / total)
    return max(0.0, centro - radio), min(1.0, centro + radio)


@dataclass
class Ejecucion:
    carpeta: Path
    metricas: dict
    configuracion: dict[str, str]
    distribucion: list[dict]
    estadisticas: dict
    avisos: list[str]
    procedencia: dict | None


def analizar_ejecucion(carpeta: Path | str) -> Ejecucion:
    carpeta = Path(carpeta).resolve()
    m = leer_metricas(carpeta)
    r = m["escenarios"]
    config = leer_pares(carpeta / "config_usada.ini", estricto=True)
    efectivos = leer_pares(carpeta / "parametros_efectivos.txt")
    # --escenarios sustituye al .ini. Nunca usar el R original de config_usada.ini.
    config.update(efectivos)
    for clave in ("escenarios", "horizonte"):
        if clave in efectivos and entero(efectivos[clave], clave, 1) != m[clave]:
            raise ValueError(f"{clave}: parametros efectivos y metricas no coinciden")
    if "horizonte" in config and entero(config["horizonte"], "horizonte", 1) != m["horizonte"]:
        raise ValueError("El horizonte de configuracion no coincide con metricas.csv")
    config["escenarios"] = str(r)
    config["horizonte"] = str(m["horizonte"])

    filas = leer_csv(carpeta / "distribucion.csv")
    distribucion = []
    acumulado = 0
    for fila in filas:
        anio = entero(fila.get("anio"), "anio")
        n = entero(fila.get("primeras_inversiones"), "primeras_inversiones")
        acumulado += n
        if acumulado > r:
            raise ValueError("La distribucion contiene mas inversiones que escenarios")
        pa = real(fila.get("probabilidad_anual"), "probabilidad_anual")
        pc = real(fila.get("probabilidad_acumulada"), "probabilidad_acumulada")
        if not math.isclose(pa, n / r, abs_tol=1e-10, rel_tol=1e-9):
            raise ValueError(f"Probabilidad anual inconsistente en {anio}")
        if not math.isclose(pc, acumulado / r, abs_tol=1e-10, rel_tol=1e-9):
            raise ValueError(f"Probabilidad acumulada inconsistente en {anio}")
        if distribucion and anio != distribucion[-1]["anio"] + 1:
            raise ValueError("Los anios deben ser consecutivos y estar ordenados")
        inferior, superior = wilson(acumulado, r)
        distribucion.append(dict(anio=anio, primeras_inversiones=n, probabilidad_anual=n / r,
                                 probabilidad_acumulada=acumulado / r,
                                 acumulada_ic95_inferior=inferior, acumulada_ic95_superior=superior))
    if len(distribucion) != m["horizonte"] + 1:
        raise ValueError("La distribucion debe incluir el estado inicial y todo el horizonte")
    if "anio_base" in config and entero(config["anio_base"], "anio_base") != distribucion[0]["anio"]:
        raise ValueError("El anio base no coincide con la distribucion")

    masa = [(f["anio"], f["primeras_inversiones"]) for f in distribucion if f["primeras_inversiones"]]
    con = acumulado
    media = sum(a * n for a, n in masa) / con if con else None
    suma_cuadrados = sum(n * (a - media) ** 2 for a, n in masa) if con else 0
    desviacion = math.sqrt(suma_cuadrados / con) if con else None
    sd_muestral = math.sqrt(suma_cuadrados / (con - 1)) if con > 1 else None
    error_media = sd_muestral / math.sqrt(con) if con > 1 else None

    def cuantil(q: float, denominador: int) -> int | None:
        # Los niveles decimales (p. ej. 0.025) son racionales exactos; evitar que
        # un redondeo flotante eleve accidentalmente el rango al siguiente entero.
        objetivo = math.ceil(Fraction(str(q)) * denominador)
        conteo = 0
        for anio, n in masa:
            conteo += n
            if conteo >= objetivo:
                return anio
        return None  # No observado dentro del horizonte; no imputar horizonte+1

    e = dict(escenarios=r, con_inversion=con, sin_inversion=r - con,
             anio_inicial=distribucion[0]["anio"], anio_final=distribucion[-1]["anio"],
             probabilidad_inversion=con / r, ic95_probabilidad_inversion=wilson(con, r),
             probabilidad_sin_inversion=(r - con) / r, ic95_sin_inversion=wilson(r - con, r),
             media_condicional=media, desviacion_condicional=desviacion,
             error_estandar_media=error_media,
             ic95_media_condicional=(
                 (media - Z95 * error_media, media + Z95 * error_media)
                 if con > 1 and error_media > 0 else None),
             minimo=masa[0][0] if con else None, maximo=masa[-1][0] if con else None,
             mediana_condicional=cuantil(.5, con) if con else None,
             p025_condicional=cuantil(.025, con) if con else None,
             p975_condicional=cuantil(.975, con) if con else None,
             mediana_no_condicional=cuantil(.5, r),
             p95_no_condicional=cuantil(.95, r))
    avisos = [
        "Resultados condicionados a los datos y supuestos del modelo; no son un pronostico oficial.",
        "Sin inversion significa no observada hasta el fin del horizonte, no que nunca ocurrira.",
        "Mas escenarios reducen el error Monte Carlo; no validan las fuentes ni eliminan la incertidumbre del modelo.",
    ]
    if not (carpeta / "config_usada.ini").is_file():
        avisos.append("Falta config_usada.ini: no se pueden identificar todos los supuestos.")
    if m["version"] == "go_secuencial":
        avisos.append("Go asigna CPU = tiempo total en main.go: no es CPU medida. Fuera de Windows, "
                      "la memoria informada es runtime.MemStats.Sys, no RSS pico.")
    if m["version"] in VERSIONES_GPU:
        avisos.append("Version con GPU: mismo modelo, pero otro generador aleatorio (xoroshiro128++) y muestreo "
                      "rapido. Sus resultados son estadisticamente equivalentes a los de CPU, no identicos "
                      "escenario a escenario, y no entran en las campanas de speedup.")
    elif config.get("muestreo", "").startswith("rapido"):
        avisos.append("Muestreo rapido: binomial por inversion/BTRS y corte en la primera inversion. Resultados "
                      "estadisticamente equivalentes a los del muestreo estandar, no identicos escenario a "
                      "escenario; su tiempo no es comparable con el de una ejecucion estandar.")
    if m["version"] in {"mpi", "hibrido", "mpi_cuda"}:
        avisos.append("MPI/hibrido: memoria es el maximo por proceso, no la suma. CPU se suma antes "
                      "de la escritura final: CPU/pared es descriptivo, no una eficiencia ni un speedup.")
    if con == 1:
        avisos.append("Solo un escenario con inversion: no se estima el error estandar de la media.")
    elif con > 1 and desviacion == 0:
        avisos.append("No se observo dispersion del anio. Un error muestral cero no prueba ausencia de incertidumbre; "
                      "no se presenta un IC normal degenerado de la media.")
    elif con > 1:
        avisos.append("El IC de la media es una aproximacion normal Monte Carlo, condicional al cruce en "
                      "el horizonte; no es un intervalo predictivo del anio real. Con pocas observaciones "
                      "su aproximacion puede ser inadecuada.")
    procedencia = None
    archivo = carpeta / "procedencia.json"
    if archivo.exists():
        try:
            from .procedencia import validar_procedencia
            procedencia = json.loads(archivo.read_text(encoding="utf-8"))
            validar_procedencia(carpeta, procedencia, m)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            avisos.append(f"Procedencia no valida para comparar rendimiento: {exc}")
            procedencia = None
    if procedencia is None:
        avisos.append("Sin procedencia verificable: metricas descriptivas disponibles, speedup no disponible.")
    return Ejecucion(carpeta, m, config, distribucion, e, avisos, procedencia)
