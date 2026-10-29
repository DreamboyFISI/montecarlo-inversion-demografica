#!/usr/bin/env bash
# Ejecuta el simulador MPI en el cluster de docker-compose.yml.
# Uso (desde MonteCarlo_Paralelo):  ./docker/ejecutar_cluster.sh [procesos=8] [escenarios=1000] [config=config_incertidumbre.ini]
# Los resultados quedan en ./resultados_cluster/<carpeta> del anfitrion.
set -euo pipefail
cd "$(dirname "$0")/.."

P="${1:-8}"
R="${2:-1000}"
CONFIG="${3:-config_incertidumbre.ini}"
CARPETA="mpi_np${P}_R${R}_$(date +%Y%m%d_%H%M%S)"

# Si Docker creo la carpeta del volumen, es de root: se le asigna al usuario mpi (UID 1000).
docker compose exec -T nodo1 chown mpi:mpi /home/mpi/resultados
docker compose exec -T -u mpi nodo1 \
    mpirun --hostfile hostfile -np "$P" --map-by node \
        ./simulador_mpi --config "../MonteCarlo_Secuencial/$CONFIG" --datos ../MonteCarlo_Secuencial/datos \
        --salida "/home/mpi/resultados/$CARPETA" --escenarios "$R"
echo "Resultados en: resultados_cluster/$CARPETA"
