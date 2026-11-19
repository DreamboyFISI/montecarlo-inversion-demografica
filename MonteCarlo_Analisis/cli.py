"""Entrada por consola, utilizable tambien desde Windows a traves de WSL."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from MonteCarlo_Analisis.ejecucion import ejecutar, ejecutar_campana
from MonteCarlo_Analisis.informes import (exportar_comparacion, exportar_ejecucion,
                                        informe_comparacion, informe_ejecucion)
from MonteCarlo_Analisis.procedencia import ROOT
from MonteCarlo_Analisis.rendimiento import comparar_ejecuciones, descubrir_ejecuciones
from MonteCarlo_Analisis.resultados import analizar_ejecucion


def pareja(texto: str) -> tuple[int, int]:
    try:
        p, h = (int(n) for n in texto.lower().split("x"))
        if min(p, h) < 1:
            raise ValueError
        return p, h
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use procesosxhilos positivos, por ejemplo 2x2") from exc


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Analisis de resultados y rendimiento S13 (sin datos inventados)")
    sub = ap.add_subparsers(dest="accion", required=True)
    analizar = sub.add_parser("analizar", help="Analizar una carpeta de salida (incluidas salidas antiguas)")
    analizar.add_argument("carpeta", type=Path)
    comparar = sub.add_parser("comparar", help="Comparar una campana o carpetas explicitas")
    comparar.add_argument("carpetas", nargs="+", type=Path)
    for comando in (analizar, comparar):
        comando.add_argument("--salida", type=Path, help="Carpeta nueva para exportar Markdown, CSV, JSON y PNG")
        comando.add_argument("--sin-graficos", action="store_true")
    lanzar = sub.add_parser("ejecutar", help="Ejecutar un motor y registrar su procedencia real")
    lanzar.add_argument("--version", required=True, choices=["secuencial", "openmp", "mpi", "hibrido", "go"])
    lanzar.add_argument("--procesos", type=int, default=1)
    lanzar.add_argument("--hilos", type=int, default=1)
    campana = sub.add_parser("campana", help="Campana local secuencial/OpenMP/MPI/hibrido, nunca simultaneas")
    campana.add_argument("--repeticiones", type=int, default=3)
    campana.add_argument("--versiones", nargs="+", choices=["openmp", "mpi", "hibrido"],
                         default=["openmp", "mpi", "hibrido"])
    campana.add_argument("--p", nargs="+", type=int, default=[1, 2])
    campana.add_argument("--hibridos", nargs="+", type=pareja, default=[(1, 2)])
    for comando in (lanzar, campana):
        comando.add_argument("--config", type=Path, default=ROOT / "MonteCarlo_Secuencial/config_incertidumbre.ini")
        comando.add_argument("--datos", type=Path, default=ROOT / "MonteCarlo_Secuencial/datos")
        comando.add_argument("--escenarios", type=int, default=1000)
        comando.add_argument("--salida", required=True, type=Path)
        comando.add_argument("--permitir-sobresuscripcion", action="store_true",
                             help="Permitir mas trabajadores que CPU; se advierte en el analisis")
    return ap


def main(argv=None) -> int:
    a = parser().parse_args(argv)
    try:
        if a.accion == "analizar":
            e = analizar_ejecucion(a.carpeta)
            print(informe_ejecucion(e))
            if a.salida:
                exportar_ejecucion(e, a.salida, not a.sin_graficos)
        elif a.accion == "comparar":
            carpetas = [p for carpeta in a.carpetas for p in descubrir_ejecuciones(carpeta)]
            if not carpetas:
                raise ValueError("No se encontraron carpetas con metricas.csv")
            c = comparar_ejecuciones(carpetas)
            print(informe_comparacion(c))
            if a.salida:
                exportar_comparacion(c, a.salida, not a.sin_graficos)
        elif a.accion == "ejecutar":
            salida = ejecutar(a.version, a.config, a.datos, a.salida, a.escenarios, a.procesos,
                              a.hilos, a.permitir_sobresuscripcion)
            print(informe_ejecucion(analizar_ejecucion(salida)))
        else:
            salida = ejecutar_campana(a.config, a.datos, a.salida, a.escenarios, a.repeticiones,
                                      a.versiones, a.p, a.hibridos, a.permitir_sobresuscripcion)
            c = comparar_ejecuciones(descubrir_ejecuciones(salida))
            exportar_comparacion(c, salida / "analisis")
            print(informe_comparacion(c))
            if c.excluidas or len(c.filas) < 2:
                raise ValueError("La campana termino con exclusiones o sin comparacion valida; revise el informe.")
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Error S13: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
