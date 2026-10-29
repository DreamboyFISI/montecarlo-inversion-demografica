// main_openmp.cpp
// Simulacion Monte Carlo de la inversion demografica del Peru. Version OpenMP (Sprint 3, S10):
// un proceso, P hilos de memoria compartida.
//
// Descomposicion: paralelismo de datos sobre los R escenarios. Los escenarios son independientes
// (cada uno tiene su generador mt19937_64 con semilla mezclar_semilla(semilla + r)), asi que el
// bucle se reparte sin sincronizacion; cada hilo guarda el resultado del escenario r en la posicion r
// de un vector y, al final, un solo hilo escribe los CSV en orden. Los CSV de resultados son
// identicos byte a byte a los de la version secuencial con la misma semilla, sea cual sea P.
//
// Uso:
//   ./simulador_omp --config config.ini [--datos d] [--salida s] [--escenarios N] [--hilos P]
//   (sin --hilos se usa OMP_NUM_THREADS o el numero de nucleos)
#include <omp.h>

#include <chrono>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "escenario.hpp"
#include "pruebas.hpp"
#include "salida.hpp"

using Reloj = std::chrono::steady_clock;

int main(int argc, char** argv) {
    try {
        const Argumentos args = leer_argumentos(argc, argv, true);
        if (args.ayuda) {
            imprimir_ayuda("simulador_omp", true);
            return 0;
        }
        if (args.pruebas) {
            ejecutar_pruebas(args.datos);
            return 0;
        }
        if (args.hilos > 0) omp_set_num_threads(args.hilos);
        const int hilos = omp_get_max_threads();

        // ---------------- 1. Configuracion y datos ----------------
        const Configuracion c = configuracion_efectiva(args);
        Metricas metricas;
        metricas.escenarios = c.escenarios;
        metricas.horizonte = c.horizonte;
        metricas.hilos = hilos;
        metricas.etiqueta = "OpenMP, Tp";
        const auto inicio_total = Reloj::now();
        const DatosModelo datos = cargar_datos_modelo(args.datos, c);  // compartido, solo lectura
        metricas.segundos_carga = std::chrono::duration<double>(Reloj::now() - inicio_total).count();
        preparar_salida(args, c);

        // ---------------- 2. Bucle Monte Carlo paralelo ----------------
        const auto inicio_simulacion = Reloj::now();
        std::vector<ResultadoEscenario> resultados(static_cast<std::size_t>(c.escenarios));
        std::ostringstream trayectoria;  // la escribe solo el hilo que ejecuta r = 0
        trayectoria << std::setprecision(15);
        bool fallo = false;
        std::string mensaje_fallo;

        // schedule(dynamic): todos los escenarios cuestan lo mismo, pero dynamic absorbe la variacion
        // de los sorteos y la interferencia del sistema; bloques de 16 escenarios (~50 ms) hacen
        // despreciable el costo de pedir trabajo.
#pragma omp parallel for schedule(dynamic, 16)
        for (Conteo r = 0; r < c.escenarios; ++r) {
            // Una excepcion no puede salir de una region paralela: se registra y se relanza despues.
            try {
                resultados[std::size_t(r)] = simular_escenario(r, datos, c, r == 0 ? &trayectoria : nullptr);
            } catch (const std::exception& e) {
#pragma omp critical(fallo_escenario)
                if (!fallo) {
                    fallo = true;
                    mensaje_fallo = "Escenario " + std::to_string(r + 1) + ": " + e.what();
                }
            }
        }
        exigir(!fallo, mensaje_fallo);

        // ---------------- 3. Escritura ordenada (un hilo) ----------------
        std::ofstream trayectoria_csv(args.salida / "trayectoria_escenario_1.csv");
        exigir(bool(trayectoria_csv), "No se puede escribir salida");
        trayectoria_csv << ENCABEZADO_TRAYECTORIA << trayectoria.str();
        trayectoria_csv.close();
        exigir(!trayectoria_csv.fail(), "Fallo al terminar escritura");
        EscritorEscenarios escritor(args.salida, c);
        for (Conteo r = 0; r < c.escenarios; ++r) escritor.agregar(r, resultados[std::size_t(r)]);
        escritor.cerrar();
        metricas.segundos_simulacion = std::chrono::duration<double>(Reloj::now() - inicio_simulacion).count();

        // ---------------- 4. Metricas y resultados ----------------
        metricas.segundos_total = std::chrono::duration<double>(Reloj::now() - inicio_total).count();
        metricas.segundos_cpu = segundos_cpu_proceso();  // suma de todos los hilos
        metricas.memoria_pico_mb = memoria_pico_mib();
        escribir_resultados(args.salida, c, datos.N0, escritor, metricas,
                            "C++17 + OpenMP, un proceso, " + std::to_string(hilos) + " hilos.", "openmp");
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << '\n';
        return 1;
    }
    return 0;
}
