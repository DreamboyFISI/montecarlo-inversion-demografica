#!/usr/bin/env python3
"""Rendimiento de las versiones OpenMP y MPI frente a la linea base secuencial (Sprint 3, S10).

Uso (desde MonteCarlo_Paralelo, con los tres ejecutables compilados):
    python3 scripts/rendimiento.py [--escenarios 10000] [--repeticiones 3] [--p 1 2 4 8]
                                   [--salida rendimiento] [--mpirun-opciones "--use-hwthread-cpus --bind-to none"]
    python3 scripts/rendimiento.py --solo-informe --salida rendimiento

En cada repeticion ejecuta, intercalados, el secuencial (T1), OpenMP con p hilos y MPI con p procesos
(Tp), todos con el mismo R, la misma semilla y en la misma maquina. Produce en la carpeta de salida:
    metricas_crudas.csv   una fila por corrida (metricas.csv de cada ejecucion)
    rendimiento.csv       media y sd de Tp por version y p, con S(p), E(p), C(p) y Karp-Flatt
    rendimiento.md        tabla lista para el informe
    rendimiento.png       speedup y eficiencia frente a p

Definiciones (T = segundos_total medio):
    S(p) = T1 / Tp      E(p) = S(p) / p      C(p) = p * Tp
    Karp-Flatt  f(p) = (1/S - 1/p) / (1 - 1/p)   (p > 1)      Cota de Amdahl S_max = 1/f
"""
import argparse
import csv
import os
import platform
import shlex
import shutil
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

SEC = Path("../MonteCarlo_Secuencial")


def ejecutar(comando, carpeta):
    subprocess.run(comando, check=True, stdout=subprocess.DEVNULL)
    with open(carpeta / "metricas.csv", newline="") as f:
        fila = next(csv.DictReader(f))
    return {k: (float(v) if k != "version" else v) for k, v in fila.items()}


def comando(version, p, R, carpeta, config, mpirun_opciones):
    comunes = ["--config", str(config), "--datos", str(SEC / "datos"), "--salida", str(carpeta), "--escenarios", str(R)]
    if version == "secuencial":
        return [str((SEC / "simulador").resolve())] + comunes
    if version == "openmp":
        return [str(Path("simulador_omp").resolve())] + comunes + ["--hilos", str(p)]
    return ["mpirun", *mpirun_opciones, "-np", str(p), str(Path("simulador_mpi").resolve())] + comunes


def media_sd(valores):
    return statistics.fmean(valores), (statistics.stdev(valores) if len(valores) > 1 else 0.0)


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
        mpi = subprocess.run(["mpirun", "--version"], capture_output=True, text=True).stdout.splitlines()[0]
    except (OSError, IndexError):
        gxx, mpi = "g++ (version desconocida)", "MPI (version desconocida)"
    return f"{cpu} · {os.cpu_count()} CPU logicas · {platform.system()} {platform.release()} · {gxx} · {mpi} · -O2"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--escenarios", type=int, default=10000)
    ap.add_argument("--repeticiones", type=int, default=3)
    ap.add_argument("--p", type=int, nargs="+", default=[1, 2, 4, 8], help="hilos (OpenMP) y procesos (MPI)")
    ap.add_argument("--config", type=Path, default=SEC / "config_demostracion.ini")
    ap.add_argument("--salida", type=Path, default=Path("rendimiento"))
    # Por defecto OpenMPI ofrece un slot por nucleo fisico y fija cada proceso a una CPU. Con
    # --use-hwthread-cpus ve las mismas CPU logicas que OpenMP, pero fijaria los rangos 0 y 1 a los dos hilos
    # de hardware del MISMO nucleo; --bind-to none deja la ubicacion al sistema operativo, como en OpenMP.
    ap.add_argument("--mpirun-opciones", default="--use-hwthread-cpus --bind-to none")
    ap.add_argument("--solo-informe", action="store_true",
                    help="no ejecuta nada: rehace tablas y grafico a partir de metricas_crudas.csv")
    a = ap.parse_args()
    a.salida.mkdir(parents=True, exist_ok=True)

    crudas = []
    if a.solo_informe:
        with open(a.salida / "metricas_crudas.csv", newline="") as f:
            for fila in csv.DictReader(f):
                crudas.append({k: (float(v) if k != "version" else v) for k, v in fila.items()})
    else:
        for ejecutable in (SEC / "simulador", Path("simulador_omp"), Path("simulador_mpi")):
            if not ejecutable.exists():
                sys.exit(f"No existe {ejecutable}. Compile primero con `make all secuencial`.")
        corridas = [("secuencial", 1)] + [(v, p) for v in ("openmp", "mpi") for p in a.p]
        with tempfile.TemporaryDirectory() as tmp:
            for rep in range(1, a.repeticiones + 1):
                for version, p in corridas:  # intercaladas: la deriva termica afecta a todas por igual
                    carpeta = Path(tmp) / f"{version}_p{p}_rep{rep}"
                    m = ejecutar(comando(version, p, a.escenarios, carpeta, a.config,
                                         shlex.split(a.mpirun_opciones)), carpeta)
                    m["p"] = p
                    m["repeticion"] = rep
                    crudas.append(m)
                    print(f"rep {rep}  {version:<10} p={p:<2}  total {m['segundos_total']:8.3f} s  "
                          f"CPU {m['segundos_cpu']:8.3f} s  RSS {m['memoria_pico_mib']:.1f} MiB", flush=True)
                    shutil.rmtree(carpeta, ignore_errors=True)

    columnas = ["version", "p", "procesos", "hilos", "escenarios", "horizonte", "repeticion", "segundos_carga",
                "segundos_simulacion", "segundos_total", "segundos_cpu", "ms_por_escenario", "escenarios_por_segundo",
                "memoria_pico_mib", "segundos_comunicacion"]
    with open(a.salida / "metricas_crudas.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columnas)
        w.writeheader()
        w.writerows({k: m[k] for k in columnas} for m in crudas)

    # ---------------- Agregacion ----------------
    R = int(crudas[0]["escenarios"])
    T1, T1_sd = media_sd([m["segundos_total"] for m in crudas if m["version"] == "secuencial"])
    filas = [dict(version="secuencial", p=1, Tp_media=T1, Tp_sd=T1_sd, speedup=1.0, eficiencia=1.0, costo=T1,
                  karp_flatt="", amdahl_smax="",
                  cpu_pared=statistics.fmean(m["segundos_cpu"] for m in crudas if m["version"] == "secuencial") / T1,
                  memoria_pico_mib=max(m["memoria_pico_mib"] for m in crudas if m["version"] == "secuencial"),
                  comunicacion_media="")]
    ps = sorted({int(m["p"]) for m in crudas if m["version"] != "secuencial"})
    for version in ("openmp", "mpi"):
        for p in ps:
            sel = [m for m in crudas if m["version"] == version and int(m["p"]) == p]
            if not sel:
                continue
            Tp, Tp_sd = media_sd([m["segundos_total"] for m in sel])
            S = T1 / Tp
            f = (1 / S - 1 / p) / (1 - 1 / p) if p > 1 else None
            filas.append(dict(version=version, p=p, Tp_media=Tp, Tp_sd=Tp_sd, speedup=S, eficiencia=S / p,
                              costo=p * Tp, karp_flatt=f if f is not None else "",
                              amdahl_smax=(1 / f if f and f > 0 else "") if f is not None else "",
                              cpu_pared=statistics.fmean(m["segundos_cpu"] for m in sel) / Tp,
                              memoria_pico_mib=max(m["memoria_pico_mib"] for m in sel),
                              comunicacion_media=(statistics.fmean(m["segundos_comunicacion"] for m in sel)
                                                  if version == "mpi" else "")))
    with open(a.salida / "rendimiento.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)

    # ---------------- Tabla markdown ----------------
    reps = int(max(m["repeticion"] for m in crudas))

    def num(v, fmt):
        return format(v, fmt) if v != "" else "—"

    md = ["# Rendimiento de OpenMP y MPI frente a la linea base (S10)\n",
          f"Maquina: {info_maquina()}\n",
          f"R = {R:,} escenarios, horizonte {int(crudas[0]['horizonte'])} anios, {reps} repeticiones intercaladas "
          "por configuracion. T = tiempo total de pared (carga + simulacion + escritura), media ± sd.\n",
          "| Version | p | Tp (s) | S(p) = T1/Tp | E(p) = S/p | C(p) = p·Tp (s) | Karp-Flatt f | Amdahl S_max | "
          "CPU/pared | RSS max (MiB) | Espera+Gatherv (s) |",
          "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for g in filas:
        md.append(f"| {g['version']} | {g['p']} | {g['Tp_media']:.3f} ± {g['Tp_sd']:.3f} | {g['speedup']:.2f} | "
                  f"{g['eficiencia']:.2f} | {g['costo']:.2f} | {num(g['karp_flatt'], '.4f')} | "
                  f"{num(g['amdahl_smax'], '.1f')} | {g['cpu_pared']:.2f} | {g['memoria_pico_mib']:.1f} | "
                  f"{num(g['comunicacion_media'], '.3f')} |")
    md.append("\nLectura: S(p) cercano a p y E(p) cercano a 1 indican escalado lineal; un f de Karp-Flatt que crece "
              "con p indica sobrecosto paralelo (sincronizacion, comunicacion), y uno constante, una parte "
              "secuencial fija (escritura ordenada de los CSV en un solo hilo/proceso).")
    (a.salida / "rendimiento.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))

    # ---------------- Grafico ----------------
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib no disponible; no se genera el grafico.")
        return
    colores = {"openmp": "#1f4e79", "mpi": "#a04a0c"}
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    ax1.plot(ps, ps, "--", color="#888888", label="ideal S = p")
    for version in ("openmp", "mpi"):
        g = [x for x in filas if x["version"] == version]
        ax1.plot([x["p"] for x in g], [x["speedup"] for x in g], "o-", color=colores[version], label=version)
        ax2.plot([x["p"] for x in g], [x["eficiencia"] for x in g], "o-", color=colores[version], label=version)
    ax2.axhline(1.0, ls="--", color="#888888", label="ideal E = 1")
    for ax, titulo, ylabel in ((ax1, "Speedup S(p) = T1 / Tp", "S(p)"), (ax2, "Eficiencia E(p) = S(p) / p", "E(p)")):
        ax.set_xticks(ps)
        ax.set_xlabel("p (hilos OpenMP / procesos MPI)")
        ax.set_ylabel(ylabel)
        ax.set_title(titulo)
        ax.grid(True, alpha=0.3)
        ax.legend()
    ax2.set_ylim(0, 1.1)
    fig.suptitle(f"R = {R:,} escenarios; T1 = {T1:.2f} s (secuencial)".replace(",", " "), fontsize=11)
    fig.tight_layout()
    fig.savefig(a.salida / "rendimiento.png", dpi=150)
    print(f"Grafico: {a.salida / 'rendimiento.png'}")


if __name__ == "__main__":
    main()
