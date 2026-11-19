"""Contexto capturado por el lanzador; nunca reconstruido para resultados antiguos."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath

ROOT = Path(__file__).resolve().parent.parent
CRITERIO = "cpp_segundos_total_desde_carga_hasta_antes_resumen_v1"
DATOS = ("poblacion_inicial_peru.csv", "fecundidad_peru.csv", "mortalidad_peru.csv")
PROTEGIDOS = ("metricas.csv", "distribucion.csv", "config_usada.ini", "parametros_efectivos.txt")


def ruta_visible(ruta: Path | str) -> str:
    """Mostrar ubicaciones sin exponer el prefijo personal del sistema de archivos."""
    texto = str(ruta)
    windows = PureWindowsPath(texto)
    # Un informe de Windows puede abrirse en Linux: sus barras no deben tratarse
    # como parte de un nombre relativo y terminar exponiendo la ruta completa.
    if windows.is_absolute() and os.name != "nt":
        return windows.name or "carpeta externa"
    p = Path(ruta)
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return p.name or "carpeta externa"


def ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def huella(archivo: Path) -> str:
    h = hashlib.sha256()
    with archivo.open("rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def firma(objeto: object) -> str:
    return hashlib.sha256(json.dumps(objeto, sort_keys=True, ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def guardar_json(archivo: Path, objeto: object) -> None:
    archivo.write_text(json.dumps(objeto, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def salida_herramienta(comando: list[str]) -> str | None:
    try:
        p = subprocess.run(comando, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=5, check=False)
        return p.stdout.strip() if p.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def cpus_disponibles() -> int:
    if hasattr(os, "sched_getaffinity"):
        return len(os.sched_getaffinity(0))
    return (getattr(os, "process_cpu_count", os.cpu_count)() or 1)


def rutas_binarios() -> dict[str, Path]:
    ext = ".exe" if sys.platform == "win32" else ""
    return {
        "secuencial": ROOT / "MonteCarlo_Secuencial" / f"simulador{ext}",
        "openmp": ROOT / "MonteCarlo_Paralelo" / f"simulador_omp{ext}",
        "mpi": ROOT / "MonteCarlo_Paralelo" / f"simulador_mpi{ext}",
        "hibrido": ROOT / "MonteCarlo_Paralelo" / f"simulador_hibrido{ext}",
        "go": ROOT / "MonteCarlo_Go" / f"simulador_go{ext}",
    }


def capturar_contexto(datos: Path, config: Path, variables: dict | None = None) -> dict:
    cpu = platform.processor() or "no disponible"
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for linea in cpuinfo.read_text().splitlines():
            if linea.startswith("model name"):
                cpu = linea.split(":", 1)[1].strip()
                break
    identidad = [platform.node(), str(uuid.getnode()), platform.system()]
    machine_id = Path("/etc/machine-id")
    if machine_id.is_file():
        identidad.append(machine_id.read_text().strip())
    fuentes = {}
    for carpeta in ("MonteCarlo_Secuencial", "MonteCarlo_Paralelo", "MonteCarlo_Go"):
        for patron in ("src/*.cpp", "src/*.hpp", "cmd/simulador/*.go", "Makefile", "go.mod", "go.sum"):
            for archivo in sorted((ROOT / carpeta).glob(patron)):
                fuentes[archivo.relative_to(ROOT).as_posix()] = huella(archivo)
    binarios = {v: huella(p) for v, p in rutas_binarios().items() if p.is_file()}
    herramientas = {nombre: salida_herramienta(cmd) for nombre, cmd in {
        "g++": ["g++", "--version"], "mpirun": ["mpirun", "--version"],
        "mpicxx": ["mpicxx", "--showme"], "go": ["go", "version"],
    }.items()}
    entorno = {k: v for k, v in (variables if variables is not None else os.environ).items()
               if k.startswith(("OMP_", "OMPI_", "PRTE_", "GOMP_", "KMP_"))}
    return dict(
        maquina=dict(id=firma(identidad), cpu=cpu, cpus_logicas=os.cpu_count(),
                     cpus_disponibles=cpus_disponibles()),
        entorno=dict(sistema=platform.platform(), python=platform.python_version(),
                     afinidad=sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
                     variables=entorno, herramientas=herramientas),
        fuentes_sha256=firma(fuentes), binarios_sha256=binarios,
        datos_sha256={nombre: huella(datos / nombre) for nombre in DATOS},
        config_sha256=huella(config),
        # Mantener el mismo entorno de archivos en una campaña; no mezclar /mnt/c y ext4.
        proyecto=str(ROOT), datos=str(datos.resolve()),
    )


def validar_procedencia(carpeta: Path, p: dict, metricas: dict) -> None:
    if not isinstance(p, dict) or p.get("esquema") != 1 or p.get("estado") != "completada":
        raise ValueError("esquema desconocido o ejecucion incompleta")
    if not p.get("ejecucion_id") or not isinstance(p.get("contexto"), dict):
        raise ValueError("faltan identidad/contexto")
    contexto = p["contexto"]
    for clave in ("maquina", "entorno", "fuentes_sha256", "binarios_sha256",
                  "datos_sha256", "config_sha256", "proyecto", "datos"):
        if not contexto.get(clave):
            raise ValueError(f"contexto incompleto: {clave}")
    for clave in ("maquina", "entorno", "binarios_sha256", "datos_sha256"):
        if not isinstance(contexto[clave], dict):
            raise ValueError(f"contexto invalido: {clave}")
    maquina = contexto["maquina"]
    if (not maquina.get("id") or not isinstance(maquina.get("cpu"), str)
            or type(maquina.get("cpus_disponibles")) is not int or maquina["cpus_disponibles"] < 1):
        raise ValueError("identidad/capacidad de maquina ausente")
    if not isinstance(contexto["entorno"].get("sistema"), str) or not isinstance(p.get("inicio_utc"), str):
        raise ValueError("sistema o fecha de ejecucion ausente")
    if p.get("firma_contexto") != firma(contexto):
        raise ValueError("la firma del contexto no coincide")
    ejecucion = p.get("ejecucion")
    if not isinstance(ejecucion, dict):
        raise ValueError("faltan los parametros de ejecucion")
    for clave in ("version", "procesos", "hilos", "escenarios", "horizonte"):
        if ejecucion.get(clave) != metricas[clave]:
            raise ValueError(f"procedencia y metricas no coinciden: {clave}")
    archivos = p.get("archivos_sha256", {})
    if not isinstance(archivos, dict):
        raise ValueError("lista de archivos invalida")
    for nombre in PROTEGIDOS:
        if not archivos.get(nombre) or archivos[nombre] != huella(carpeta / nombre):
            raise ValueError(f"{nombre} cambio o no tiene huella")
    if p.get("criterio") not in (CRITERIO, "go_tiempo_total_v1"):
        raise ValueError("criterio de tiempo desconocido")
