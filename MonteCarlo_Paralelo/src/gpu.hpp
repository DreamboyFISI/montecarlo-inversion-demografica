// gpu.hpp
// Interfaz entre main_cuda.cpp (compilado con g++) y gpu.cu (compilado con nvcc). Solo usa tipos
// simples para que el codigo de CUDA no dependa de las cabeceras del resto del simulador.
// Todas las funciones devuelven nullptr si no hubo error, o un mensaje que describe el fallo.
#pragma once

#include "nucleo_cuda.hpp"

// Copia los datos a la GPU y reserva memoria para lotes de hasta lote_max escenarios.
// Deja en nombre_gpu (de tamano largo) el modelo de la tarjeta.
const char* gpu_iniciar(const DatosGpu& datos, const double* fecundidad, int lote_max, char* nombre_gpu, int largo);

// Simula los escenarios [inicio, inicio + n), uno por hilo de GPU, y copia los resultados al anfitrion:
// pasos[i] = paso de la primera inversion (-1 si no ocurre); factores[2i], factores[2i+1] = factores macro.
const char* gpu_simular_lote(unsigned long long inicio, int n, int* pasos, double* factores);

// Simula el escenario r con el horizonte completo y devuelve su trayectoria (una fila por anio).
const char* gpu_trayectoria(unsigned long long r, FilaTraza* filas, int* paso);

void gpu_liberar();
