#!/usr/bin/env bash
# Construye la imagen CUDA y ejecuta simulador_cuda en la GPU del equipo.
# Uso (desde MonteCarlo_Paralelo):
#   ./docker/ejecutar_cuda.sh [escenarios=1000] [config=config_incertidumbre.ini] [procesos=1] [hilos=4]
# Con procesos = 1 se usa simulador_cuda (solo GPU). Con procesos > 1 se usa simulador_mpi_cuda: el
# proceso 0 simula en la GPU y los otros procesos-1 en la CPU, cada uno con esa cantidad de hilos OpenMP.
#   ./docker/ejecutar_cuda.sh 10000000 config_incertidumbre.ini 4 5   # GPU + 3 procesos x 5 hilos
# Variables opcionales: MC_LOTE y MC_PESO_GPU (ver main_mpi_cuda.cpp).
#   ./docker/ejecutar_cuda.sh pruebas            # pruebas del modelo, de los sorteos y GPU = CPU
#   ./docker/ejecutar_cuda.sh 10000000           # 10 millones de escenarios
# Los resultados quedan en ./resultados_cuda/<carpeta> del anfitrion.
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1   # Git Bash en Windows: no convertir las rutas del contenedor

R="${1:-1000}"
CONFIG="${2:-config_incertidumbre.ini}"
P="${3:-1}"
H="${4:-4}"
SEC=../MonteCarlo_Secuencial

docker build -q -f docker/Dockerfile.cuda -t montecarlo-cuda:latest .. > /dev/null

if [[ "$R" == pruebas ]]; then
    docker run --rm --gpus all montecarlo-cuda:latest \
        ./simulador_cuda --self-test --config "$SEC/$CONFIG" --datos "$SEC/datos"
    exit 0
fi

if [[ "$P" -gt 1 ]]; then
    CARPETA="mpi_cuda_np${P}_h${H}_R${R}_$(date +%Y%m%d_%H%M%S)"
    PROGRAMA=(mpirun -np "$P" --bind-to none --oversubscribe ./simulador_mpi_cuda --hilos "$H")
else
    CARPETA="cuda_R${R}_$(date +%Y%m%d_%H%M%S)"
    PROGRAMA=(./simulador_cuda)
fi
mkdir -p resultados_cuda
if [[ "$(uname -s)" == MINGW* || "$(uname -s)" == MSYS* ]]; then VOLUMEN="$(pwd -W)/resultados_cuda"; else VOLUMEN="$(pwd)/resultados_cuda"; fi
docker run --rm --gpus all -e MC_LOTE -e MC_PESO_GPU -v "$VOLUMEN:/resultados" montecarlo-cuda:latest \
    "${PROGRAMA[@]}" --config "$SEC/$CONFIG" --datos "$SEC/datos" --salida "/resultados/$CARPETA" --escenarios "$R"
echo "Resultados en: resultados_cuda/$CARPETA"
