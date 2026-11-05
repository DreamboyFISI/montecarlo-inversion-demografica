// main.cpp
// Simulacion Monte Carlo de la inversion demografica del Peru. Version SECUENCIAL:
// un proceso, un hilo; recorre un escenario completo y luego el siguiente.
// Es la linea base T1 de las versiones OpenMP y MPI (carpeta MonteCarlo_Paralelo).
//
// Uso:
//   ./simulador --config config_demostracion.ini [--datos datos] [--salida resultados] [--escenarios N]
//   ./simulador --self-test [--datos datos]
#include <chrono>
#include <iomanip>
#include <iostream>

#include "escenario.hpp"
#include "pruebas.hpp"
#include "salida.hpp"

using Reloj = std::chrono::steady_clock;

int main(int argc, char** argv) {
    try {
        const Argumentos args = leer_argumentos(argc, argv);
        if (args.ayuda) {
            imprimir_ayuda("simulador");
            return 0;
        }
        if (args.pruebas) {
            ejecutar_pruebas(args.datos);
            return 0;
        }

        // ---------------- 1. Configuracion y datos ----------------
        const Configuracion c = configuracion_efectiva(args);
        Metricas metricas;
        metricas.escenarios = c.escenarios;
        metricas.horizonte = c.horizonte;
        const auto inicio_total = Reloj::now();
        const DatosModelo datos = cargar_datos_modelo(args.datos, c);
        metricas.segundos_carga = std::chrono::duration<double>(Reloj::now() - inicio_total).count();
        preparar_salida(args, c);

        std::ofstream trayectoria_csv(args.salida / "trayectoria_escenario_1.csv");
        exigir(bool(trayectoria_csv), "No se puede escribir salida");
        trayectoria_csv << ENCABEZADO_TRAYECTORIA << std::setprecision(15);
        EscritorEscenarios escritor(args.salida, c);

        // ---------------- 2. Bucle Monte Carlo ----------------
        // Cada resultado se escribe en cuanto se obtiene: la memoria no crece con R.
        const auto inicio_simulacion = Reloj::now();
        for (Conteo r = 0; r < c.escenarios; ++r)
            escritor.agregar(r, simular_escenario(r, datos, c, r == 0 ? &trayectoria_csv : nullptr));
        escritor.cerrar();
        trayectoria_csv.close();
        exigir(!trayectoria_csv.fail(), "Fallo al terminar escritura");
        metricas.segundos_simulacion = std::chrono::duration<double>(Reloj::now() - inicio_simulacion).count();

        // ---------------- 3. Metricas y resultados ----------------
        metricas.segundos_total = std::chrono::duration<double>(Reloj::now() - inicio_total).count();
        metricas.segundos_cpu = segundos_cpu_proceso();
        metricas.memoria_pico_mb = memoria_pico_mib();
        escribir_resultados(args.salida, c, datos.N0, escritor, metricas, "C++17 secuencial, un proceso, un hilo.",
                            "secuencial");
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << '\n';
        return 1;
    }
    return 0;
}
