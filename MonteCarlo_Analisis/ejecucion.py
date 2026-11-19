"""Lanzamiento local auditable, sin modificar los simuladores ni sus sorteos."""

from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from .procedencia import (CRITERIO, PROTEGIDOS, ROOT, ahora, capturar_contexto, cpus_disponibles,
                          firma, guardar_json, huella, rutas_binarios)
from .resultados import analizar_ejecucion, entero, leer_metricas


def validar_recursos(version: str, procesos: int, hilos: int, sobresuscripcion: bool) -> None:
    entero(procesos, "procesos", 1)
    entero(hilos, "hilos", 1)
    if hilos > 4096:
        raise ValueError("El simulador admite como maximo 4096 hilos por proceso")
    if version in {"secuencial", "go"} and (procesos, hilos) != (1, 1):
        raise ValueError("Las versiones secuenciales usan 1 proceso x 1 hilo")
    if version == "cuda" and (procesos, hilos) != (1, 1):
        raise ValueError("CUDA usa un proceso; el paralelismo esta en la GPU")
    if version == "openmp" and procesos != 1:
        raise ValueError("OpenMP usa un solo proceso")
    if version == "mpi" and hilos != 1:
        raise ValueError("MPI puro usa un hilo por proceso")
    # En MPI + CUDA el proceso 0 atiende a la GPU con un solo hilo; los demas usan `hilos` cada uno.
    trabajadores = (procesos - 1) * hilos + 1 if version == "mpi_cuda" else procesos * hilos
    if trabajadores > cpus_disponibles() and not sobresuscripcion:
        raise ValueError(f"Se solicitaron {trabajadores} trabajadores, pero hay {cpus_disponibles()} CPU "
                         "disponibles. Reduzca procesos/hilos o permita sobresuscripcion explicitamente.")


GPU = {"cuda", "mpi_cuda"}
MUESTREOS = {"estandar", "rapido"}


def muestreo_efectivo(version: str, muestreo: str) -> str:
    """Las versiones con GPU solo existen con muestreo rapido; Go solo con el estandar."""
    if muestreo not in MUESTREOS:
        raise ValueError(f"Muestreo desconocido: {muestreo}")
    if version in GPU:
        return "rapido"
    if version == "go" and muestreo == "rapido":
        raise ValueError("El muestreo rapido solo existe en las versiones C++")
    return muestreo


def construir_comando(version: str, config: Path, datos: Path, salida: Path, escenarios: int,
                      procesos: int, hilos: int, sobresuscripcion: bool, muestreo: str = "estandar") -> list[str]:
    if version not in rutas_binarios():
        raise ValueError(f"Motor desconocido: {version}")
    muestreo = muestreo_efectivo(version, muestreo)
    binario = rutas_binarios()[version]
    if not binario.is_file():
        ayuda = (" Las versiones con GPU se compilan aparte: make -C MonteCarlo_Paralelo simulador_cuda "
                 "simulador_mpi_cuda (requiere nvcc y una GPU NVIDIA)." if version in GPU else "")
        raise FileNotFoundError(f"Falta {binario}. Compile los ejecutables antes de ejecutar.{ayuda}")
    if version in {"mpi", "hibrido", "mpi_cuda"} and sys.platform == "win32":
        raise ValueError("Las campanas MPI deben lanzarse dentro de Linux/WSL, no con Python de Windows.")
    comunes = ["--config", str(config), "--datos", str(datos), "--salida", str(salida),
               "--escenarios", str(escenarios)]
    if version in {"openmp", "hibrido", "mpi_cuda"}:
        comunes += ["--hilos", str(hilos)]
    if muestreo == "rapido" and version not in GPU:  # en las versiones con GPU es el unico modo
        comunes += ["--muestreo", "rapido"]
    comando = [str(binario), *comunes]
    if version in {"mpi", "hibrido", "mpi_cuda"}:
        opciones = ["--use-hwthread-cpus", "--bind-to", "none"]
        if sobresuscripcion:
            opciones.append("--oversubscribe")
        comando = ["mpirun", *opciones, "-np", str(procesos), *comando]
    return comando


def ejecutar(version: str, config: Path | str, datos: Path | str, salida: Path | str,
             escenarios: int, procesos: int = 1, hilos: int = 1, sobresuscripcion: bool = False,
             campana_id: str | None = None, repeticion: int = 1, muestreo: str = "estandar") -> Path:
    escenarios = entero(escenarios, "escenarios", 1)
    if escenarios > 1_000_000_000:
        raise ValueError("El simulador admite hasta 10^9 escenarios")
    validar_recursos(version, procesos, hilos, sobresuscripcion)
    muestreo = muestreo_efectivo(version, muestreo)
    if campana_id and muestreo != "estandar":
        raise ValueError("Las campanas de speedup solo admiten el muestreo estandar")
    config, datos, salida = Path(config).resolve(), Path(datos).resolve(), Path(salida).resolve()
    if salida.exists():
        raise ValueError(f"La salida ya existe: {salida}. Elija una carpeta nueva.")
    comando = construir_comando(version, config, datos, salida, escenarios, procesos, hilos, sobresuscripcion,
                                muestreo)
    entorno = dict(os.environ, OMP_DYNAMIC="FALSE", OMP_THREAD_LIMIT="4096", OMP_PROC_BIND="FALSE")
    contexto = capturar_contexto(datos, config, entorno)
    contexto["almacenamiento"] = str(salida.parent)
    inicio = ahora()
    salida.parent.mkdir(parents=True, exist_ok=True)
    t = time.perf_counter()
    completado = subprocess.run(comando, cwd=ROOT, env=entorno, capture_output=True,
                               text=True, encoding="utf-8", errors="replace", check=False)
    externo = time.perf_counter() - t
    if salida.is_dir():
        (salida / "ejecucion.log").write_text(completado.stdout + "\n" + completado.stderr, encoding="utf-8")
    if completado.returncode != 0:
        raise RuntimeError(f"Fallo {version} (codigo {completado.returncode}):\n"
                           f"{completado.stderr.strip() or completado.stdout.strip()}")
    despues = capturar_contexto(datos, config, entorno)
    despues["almacenamiento"] = str(salida.parent)
    if despues != contexto:
        raise RuntimeError("Los datos, configuracion, fuentes, binarios o contexto cambiaron durante la ejecucion. "
                           "La salida se conserva, pero no se certifica para comparar.")
    e = analizar_ejecucion(salida)
    m = e.metricas
    esperado = "go_secuencial" if version == "go" else version
    if (m["version"], m["procesos"], m["hilos"], m["escenarios"]) != (esperado, procesos, hilos, escenarios):
        raise ValueError("El ejecutable no produjo la version/carga/paralelismo solicitado")
    equivalencia = {}
    if campana_id:
        # Comprobacion fuera de T; lectura por bloques, no guardar todos los escenarios en memoria.
        for nombre in ("escenarios.csv", "trayectoria_escenario_1.csv", "factores_escenarios.csv"):
            if (salida / nombre).is_file():
                equivalencia[nombre] = huella(salida / nombre)
        if not {"escenarios.csv", "trayectoria_escenario_1.csv"} <= equivalencia.keys():
            raise ValueError("Faltan CSV necesarios para verificar equivalencia")
        if any(float(e.configuracion.get(k, 0)) > 0 for k in ("sigma_fecundidad", "sigma_mortalidad")):
            if "factores_escenarios.csv" not in equivalencia:
                raise ValueError("Falta factores_escenarios.csv con incertidumbre macro")
    p = dict(esquema=1, estado="completada", ejecucion_id=uuid.uuid4().hex,
             campana_id=campana_id, repeticion=repeticion, inicio_utc=inicio, fin_utc=ahora(),
             contexto=contexto, firma_contexto=firma(contexto),
             criterio=CRITERIO if version != "go" else "go_tiempo_total_v1",
             ejecucion={k: m[k] for k in ("version", "procesos", "hilos", "escenarios", "horizonte")},
             comando=comando, segundos_externos=externo, sobresuscripcion=sobresuscripcion, muestreo=muestreo,
             equivalencia_sha256=equivalencia,
             archivos_sha256={nombre: huella(salida / nombre) for nombre in PROTEGIDOS})
    guardar_json(salida / "procedencia.json", p)
    return salida


def ejecutar_campana(config: Path, datos: Path, salida: Path, escenarios: int, repeticiones: int,
                     versiones: list[str], trabajadores: list[int], hibridos: list[tuple[int, int]],
                     sobresuscripcion: bool = False, notificar=print) -> Path:
    entero(repeticiones, "repeticiones", 1)
    if not versiones or any(v not in {"openmp", "mpi", "hibrido"} for v in versiones):
        raise ValueError("Seleccione openmp, mpi y/o hibrido para comparar con C++ secuencial")
    plan = [("secuencial", 1, 1)]
    for v in dict.fromkeys(versiones):
        if v == "hibrido":
            plan += [(v, p, h) for p, h in dict.fromkeys(hibridos)]
        else:
            plan += [(v, 1 if v == "openmp" else p, p if v == "openmp" else 1)
                     for p in dict.fromkeys(trabajadores)]
    if len(plan) < 2 or ("hibrido" in versiones and not hibridos):
        raise ValueError("Faltan configuraciones paralelas para la campana")
    if any(v in versiones for v in ("openmp", "mpi")) and not trabajadores:
        raise ValueError("Indique al menos un numero de trabajadores")
    salida = Path(salida).resolve()
    if salida.exists():
        raise ValueError("La carpeta de campana debe ser nueva")
    # Preflight de todo el plan antes de empezar una medicion larga.
    for v, p, h in plan:
        validar_recursos(v, p, h, sobresuscripcion)
        construir_comando(v, Path(config).resolve(), Path(datos).resolve(), salida / "preflight",
                          escenarios, p, h, sobresuscripcion)
    campana_id = uuid.uuid4().hex
    manifiesto = dict(esquema=1, campana_id=campana_id, estado="en_curso", inicio_utc=ahora(),
                      repeticiones=repeticiones, escenarios=escenarios, plan=plan, ejecuciones=[])
    salida.mkdir(parents=True)
    guardar_json(salida / "campana.json", manifiesto)
    try:
        for rep in range(1, repeticiones + 1):
            # Rotar el orden para no favorecer siempre a la misma version. Nunca simultaneas.
            orden = plan[(rep - 1) % len(plan):] + plan[:(rep - 1) % len(plan)]
            for v, p, h in orden:
                nombre = f"{v}_p{p}_h{h}_rep{rep}"
                notificar(f"Repeticion {rep}/{repeticiones}: {v} {p}x{h}", flush=True)
                carpeta = ejecutar(v, config, datos, salida / nombre, escenarios, p, h,
                                   sobresuscripcion, campana_id, rep)
                manifiesto["ejecuciones"].append(carpeta.name)
                guardar_json(salida / "campana.json", manifiesto)
                m = leer_metricas(carpeta)
                notificar(f"  Tiempo del simulador: {m['segundos_total']:.6f} s", flush=True)
        manifiesto["estado"] = "completada"
    except BaseException as exc:
        manifiesto["estado"] = "incompleta"
        manifiesto["error"] = str(exc)
        raise
    finally:
        manifiesto["fin_utc"] = ahora()
        guardar_json(salida / "campana.json", manifiesto)
    return salida
