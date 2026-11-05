#!/usr/bin/env bash
# Verifica que OpenMP (1, 2, 3 y 8 hilos), MPI (1, 2, 3 y 4 procesos) e Hibrido (2 procesos x 2 y 4 hilos)
# producen exactamente los mismos CSV de resultados que la version secuencial, con tasas fijas y con incertidumbre macro.
# Se ejecuta desde MonteCarlo_Paralelo:  ./scripts/verificar_equivalencia.sh [escenarios]
# Variable opcional MPIRUN_OPCIONES (p. ej. "--oversubscribe --allow-run-as-root").
set -euo pipefail

R="${1:-200}"
SEC=../MonteCarlo_Secuencial
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
ARCHIVOS="escenarios.csv distribucion.csv trayectoria_escenario_1.csv"
fallos=0

comparar() {  # comparar <referencia> <candidata> <nombre> <archivos...>
    local ref=$1 cand=$2 nombre=$3; shift 3
    for f in "$@"; do
        if cmp -s "$ref/$f" "$cand/$f"; then :; else
            echo "  [FALLA] $nombre: $f difiere de la version secuencial"
            fallos=$((fallos + 1))
            return
        fi
    done
    echo "  [OK] $nombre: $* identicos"
}

for config in config_demostracion.ini config_incertidumbre.ini; do
    archivos=$ARCHIVOS
    [[ $config == config_incertidumbre.ini ]] && archivos="$ARCHIVOS factores_escenarios.csv"
    echo "== $config, $R escenarios =="
    ref="$TMP/sec_$config"
    "$SEC/simulador" --config "$SEC/$config" --datos "$SEC/datos" --salida "$ref" --escenarios "$R" > /dev/null
    for p in 1 2 3 8; do
        out="$TMP/omp_${p}_$config"
        ./simulador_omp --config "$SEC/$config" --datos "$SEC/datos" --salida "$out" --escenarios "$R" --hilos "$p" > /dev/null
        # shellcheck disable=SC2086
        comparar "$ref" "$out" "OpenMP $p hilos" $archivos
    done
    for p in 1 2 3 4; do
        out="$TMP/mpi_${p}_$config"
        # shellcheck disable=SC2086
        mpirun ${MPIRUN_OPCIONES:-} -np "$p" ./simulador_mpi --config "$SEC/$config" --datos "$SEC/datos" \
            --salida "$out" --escenarios "$R" > /dev/null
        # shellcheck disable=SC2086
        comparar "$ref" "$out" "MPI $p procesos" $archivos
    done
    if [[ -f ./simulador_hibrido ]]; then
        for p in 2; do
            for h in 2 4; do
                out="$TMP/hibrido_${p}x${h}_$config"
                # shellcheck disable=SC2086
                mpirun ${MPIRUN_OPCIONES:-} -np "$p" ./simulador_hibrido --config "$SEC/$config" --datos "$SEC/datos" \
                    --salida "$out" --escenarios "$R" --hilos "$h" > /dev/null
                # shellcheck disable=SC2086
                comparar "$ref" "$out" "Hibrido $p proc x $h hilos" $archivos
            done
        done
    fi
done

if [[ $fallos -eq 0 ]]; then
    echo "Equivalencia: OK (OpenMP, MPI e Hibrido reproducen exactamente la version secuencial)"
else
    echo "Equivalencia: $fallos FALLA(S)"
    exit 1
fi
