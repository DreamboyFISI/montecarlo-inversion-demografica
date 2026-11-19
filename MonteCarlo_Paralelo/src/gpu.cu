// gpu.cu
// Parte CUDA del simulador: un hilo de GPU por escenario. Los escenarios son independientes (cada uno
// tiene su generador, sembrado con su indice), asi que no hay comunicacion entre hilos: es la misma
// descomposicion de datos de OpenMP y MPI, con miles de hilos en lugar de 8 o 16.
#include "gpu.hpp"

#include <cuda_runtime.h>

#include <cstring>

namespace {

constexpr int HILOS_POR_BLOQUE = 128;

DatosGpu* d_datos = nullptr;      // memoria de la GPU
double* d_fecundidad = nullptr;
int* d_pasos = nullptr;
double* d_factores = nullptr;
FilaTraza* d_traza = nullptr;
int lote_reservado = 0;
int horizonte = 0;

__global__ void kernel_lote(const DatosGpu* datos, const double* fecundidad, unsigned long long inicio, int n,
                            int* pasos, double* factores) {
    const int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= n) return;
    double ff, fm;
    pasos[i] = mc_simular_escenario(*datos, fecundidad, inicio + i, &ff, &fm, nullptr);
    factores[2 * i] = ff;
    factores[2 * i + 1] = fm;
}

__global__ void kernel_trayectoria(const DatosGpu* datos, const double* fecundidad, unsigned long long r,
                                   FilaTraza* filas, int* paso) {
    double ff, fm;
    *paso = mc_simular_escenario(*datos, fecundidad, r, &ff, &fm, filas);
}

const char* error(cudaError_t codigo) { return codigo == cudaSuccess ? nullptr : cudaGetErrorString(codigo); }

#define INTENTAR(llamada)                                 \
    do {                                                  \
        if (const char* e = error(llamada)) return e;     \
    } while (0)

}  // namespace

const char* gpu_iniciar(const DatosGpu& datos, const double* fecundidad, int lote_max, char* nombre_gpu, int largo) {
    int dispositivos = 0;
    INTENTAR(cudaGetDeviceCount(&dispositivos));
    if (dispositivos == 0) return "No hay ninguna GPU con CUDA disponible";
    cudaDeviceProp propiedades;
    INTENTAR(cudaGetDeviceProperties(&propiedades, 0));
    std::strncpy(nombre_gpu, propiedades.name, std::size_t(largo) - 1);
    nombre_gpu[largo - 1] = '\0';

    horizonte = datos.horizonte;
    lote_reservado = lote_max;
    const std::size_t celdas = std::size_t(horizonte) * MC_EDADES;
    INTENTAR(cudaMalloc(&d_datos, sizeof(DatosGpu)));
    INTENTAR(cudaMalloc(&d_fecundidad, celdas * sizeof(double)));
    INTENTAR(cudaMalloc(&d_pasos, std::size_t(lote_max) * sizeof(int)));
    INTENTAR(cudaMalloc(&d_factores, 2 * std::size_t(lote_max) * sizeof(double)));
    INTENTAR(cudaMalloc(&d_traza, std::size_t(horizonte) * sizeof(FilaTraza)));
    INTENTAR(cudaMemcpy(d_datos, &datos, sizeof(DatosGpu), cudaMemcpyHostToDevice));
    INTENTAR(cudaMemcpy(d_fecundidad, fecundidad, celdas * sizeof(double), cudaMemcpyHostToDevice));
    return nullptr;
}

const char* gpu_simular_lote(unsigned long long inicio, int n, int* pasos, double* factores) {
    if (n > lote_reservado) return "Lote mayor que el reservado";
    const int bloques = (n + HILOS_POR_BLOQUE - 1) / HILOS_POR_BLOQUE;
    kernel_lote<<<bloques, HILOS_POR_BLOQUE>>>(d_datos, d_fecundidad, inicio, n, d_pasos, d_factores);
    INTENTAR(cudaGetLastError());
    // cudaMemcpy espera a que termine el kernel antes de copiar.
    INTENTAR(cudaMemcpy(pasos, d_pasos, std::size_t(n) * sizeof(int), cudaMemcpyDeviceToHost));
    INTENTAR(cudaMemcpy(factores, d_factores, 2 * std::size_t(n) * sizeof(double), cudaMemcpyDeviceToHost));
    return nullptr;
}

const char* gpu_trayectoria(unsigned long long r, FilaTraza* filas, int* paso) {
    kernel_trayectoria<<<1, 1>>>(d_datos, d_fecundidad, r, d_traza, d_pasos);
    INTENTAR(cudaGetLastError());
    INTENTAR(cudaMemcpy(filas, d_traza, std::size_t(horizonte) * sizeof(FilaTraza), cudaMemcpyDeviceToHost));
    INTENTAR(cudaMemcpy(paso, d_pasos, sizeof(int), cudaMemcpyDeviceToHost));
    return nullptr;
}

void gpu_liberar() {
    cudaFree(d_datos);
    cudaFree(d_fecundidad);
    cudaFree(d_pasos);
    cudaFree(d_factores);
    cudaFree(d_traza);
    d_datos = nullptr;
    d_fecundidad = nullptr;
    d_pasos = nullptr;
    d_factores = nullptr;
    d_traza = nullptr;
}
