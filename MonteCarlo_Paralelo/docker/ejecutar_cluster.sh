#!/usr/bin/env bash
# Ejecuta el simulador MPI o el hibrido MPI + OpenMP en el cluster de docker-compose.yml.
# Uso (desde MonteCarlo_Paralelo):
#   ./docker/ejecutar_cluster.sh [procesos=8] [escenarios=1000] [config=config_incertidumbre.ini] [hilos=0]
# Con hilos = 0 se usa simulador_mpi (un hilo por proceso). Con hilos > 0 se usa simulador_hibrido:
# los procesos se reparten uno a uno entre los nodos y cada uno abre esa cantidad de hilos OpenMP.
#   ./docker/ejecutar_cluster.sh 4 10000000 config_incertidumbre.ini 2   # 4 nodos x 2 hilos (PB-09)
# Los resultados quedan en ./resultados_cluster/<carpeta> del anfitrion.
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1   # Git Bash en Windows: no convertir las rutas del contenedor

P="${1:-8}"
R="${2:-1000}"
CONFIG="${3:-config_incertidumbre.ini}"
H="${4:-0}"

if [[ "$H" -gt 0 ]]; then
    PROGRAMA=./simulador_hibrido
    CARPETA="hibrido_np${P}_h${H}_R${R}_$(date +%Y%m%d_%H%M%S)"
    OPCIONES_MPI=(--bind-to none)   # sin esto los hilos OpenMP quedan fijados a un solo nucleo
    OPCIONES_SIM=(--hilos "$H")
else
    PROGRAMA=./simulador_mpi
    CARPETA="mpi_np${P}_R${R}_$(date +%Y%m%d_%H%M%S)"
    OPCIONES_MPI=()
    OPCIONES_SIM=()
fi

# Si Docker creo la carpeta del volumen, es de root: se le asigna al usuario mpi (UID 1000).
docker compose exec -T nodo1 chown mpi:mpi /home/mpi/resultados
docker compose exec -T -u mpi nodo1     mpirun --hostfile hostfile -np "$P" --map-by node "${OPCIONES_MPI[@]}"         "$PROGRAMA" --config "../MonteCarlo_Secuencial/$CONFIG" --datos ../MonteCarlo_Secuencial/datos         --salida "/home/mpi/resultados/$CARPETA" --escenarios "$R" "${OPCIONES_SIM[@]}"
echo "Resultados en: resultados_cluster/$CARPETA"
