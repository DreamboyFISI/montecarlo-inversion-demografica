// salida.hpp
// Partes comunes a los ejecutables secuencial, OpenMP y MPI: argumentos de linea de comandos,
// preparacion de la carpeta de salida y escritura de distribucion, resumen, grafico y metricas.
#pragma once

#include <filesystem>
#include <string>

#include "configuracion.hpp"
#include "datos.hpp"
#include "escenario.hpp"
#include "metricas.hpp"

struct Argumentos {
    std::filesystem::path config;
    std::filesystem::path datos = "datos";
    std::filesystem::path salida = "resultados";
    Conteo escenarios = 0;  // 0 = usar el valor del .ini
    int hilos = 0;          // solo OpenMP; 0 = valor por defecto (OMP_NUM_THREADS o nucleos)
    bool pruebas = false;
    bool ayuda = false;
};

// acepta_hilos: si es false, --hilos se rechaza como opcion desconocida.
Argumentos leer_argumentos(int argc, char** argv, bool acepta_hilos = false);

void imprimir_ayuda(const std::string& programa, bool acepta_hilos = false);

// Lee la configuracion y aplica --escenarios.
Configuracion configuracion_efectiva(const Argumentos& a);

// Crea la carpeta de salida (debe ser nueva) y guarda config_usada.ini y parametros_efectivos.txt.
void preparar_salida(const Argumentos& a, const Configuracion& c);

// Escribe distribucion.csv, resumen.txt, distribucion_anio.svg y metricas.csv, e imprime el resumen
// en pantalla. m debe tener ya todos los tiempos, la CPU y la memoria.
//   version_texto: linea "Version: ..." del resumen
//   version_csv:   columna version de metricas.csv (secuencial, openmp, mpi)
void escribir_resultados(const std::filesystem::path& salida, const Configuracion& c, const Poblacion& N0,
                         const EscritorEscenarios& escritor, const Metricas& m, const std::string& version_texto,
                         const std::string& version_csv);
