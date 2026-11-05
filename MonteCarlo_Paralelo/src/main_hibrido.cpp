// main_hibrido.cpp
// Simulacion Monte Carlo de la inversion demografica del Peru. Version Hibrida MPI + OpenMP (Sprint 3, S11):
// P procesos MPI (memoria distribuida entre nodos/contenedores) x H hilos OpenMP (memoria compartida
// dentro de cada proceso).
//
// Descomposicion jerarquica:
// 1. MPI reparte los R escenarios en P bloques contiguos balanceados (bloque_de).
// 2. OpenMP reparte dinamicamente los escenarios del bloque local entre H hilos
//    con #pragma omp parallel for schedule(dynamic, 16).
// 3. Los escenarios son mutuamente independientes (cada uno con semilla splitmix64(semilla + r)).
// 4. Al terminar el computo local, un MPI_Gatherv reune los resultados en el proceso 0.
// 5. El proceso 0 escribe los CSV en orden estricto r = 0..R-1.
//
// Resultado: identico byte a byte a las versiones secuencial, OpenMP y MPI pura para la misma semilla.
//
// Uso:
//   mpirun -np P ./simulador_hibrido --config config.ini [--datos d] [--salida s] [--escenarios N] [--hilos H]
//   (sin --hilos se usa OMP_NUM_THREADS o el numero de nucleos disponibles en el nodo)
#include <mpi.h>
#include <omp.h>

#include <algorithm>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "escenario.hpp"
#include "pruebas.hpp"
#include "salida.hpp"

namespace {

struct Bloque {
    Conteo inicio = 0, fin = 0;
    Conteo tamano() const { return fin - inicio; }
};

// Bloque del proceso k entre p: los primeros R % p procesos reciben un escenario mas.
Bloque bloque_de(Conteo R, int p, int k) {
    const Conteo base = R / p, resto = R % p;
    Bloque b;
    b.inicio = k * base + std::min<Conteo>(k, resto);
    b.fin = b.inicio + base + (k < resto ? 1 : 0);
    return b;
}

// Reune en el proceso 0 los bloques de todos (en orden de rango); cada escenario ocupa
// por_escenario elementos. Devuelve el vector completo en el proceso 0 y vacio en los demas.
template <typename T>
std::vector<T> reunir(const std::vector<T>& local, MPI_Datatype tipo, int por_escenario, Conteo R, int p, int rango) {
    std::vector<int> conteos, desplazamientos;
    std::vector<T> total;
    if (rango == 0) {
        conteos.resize(p);
        desplazamientos.resize(p);
        for (int k = 0; k < p; ++k) {
            const Bloque b = bloque_de(R, p, k);
            conteos[k] = int(b.tamano() * por_escenario);
            desplazamientos[k] = int(b.inicio * por_escenario);
        }
        total.resize(std::size_t(R) * std::size_t(por_escenario));
    }
    MPI_Gatherv(local.data(), int(local.size()), tipo, total.data(), conteos.data(), desplazamientos.data(), tipo, 0,
                MPI_COMM_WORLD);
    return total;
}

}  // namespace

int main(int argc, char** argv) {
    int proporcionado = 0;
    // Solo el hilo maestro llama a MPI: MPI_THREAD_FUNNELED es el nivel necesario y suficiente.
    MPI_Init_thread(&argc, &argv, MPI_THREAD_FUNNELED, &proporcionado);

    int rango = 0, procesos = 1;
    MPI_Comm_rank(MPI_COMM_WORLD, &rango);
    MPI_Comm_size(MPI_COMM_WORLD, &procesos);
    const bool raiz = rango == 0;

    try {
        const Argumentos args = leer_argumentos(argc, argv, true);
        if (args.ayuda || args.pruebas) {
            if (raiz) {
                if (args.ayuda) imprimir_ayuda("mpirun -np P simulador_hibrido", true);
                else ejecutar_pruebas(args.datos);
            }
            MPI_Finalize();
            return 0;
        }

        if (args.hilos > 0) omp_set_num_threads(args.hilos);
        const int hilos = omp_get_max_threads();

        // ---------------- 1. Configuracion y datos (cada proceso) ----------------
        const Configuracion c = configuracion_efectiva(args);
        exigir(c.escenarios <= 1000000000LL, "Hibrido: escenarios debe ser <= 10^9");
        Metricas metricas;
        metricas.escenarios = c.escenarios;
        metricas.horizonte = c.horizonte;
        metricas.procesos = procesos;
        metricas.hilos = hilos;
        metricas.etiqueta = "Hibrido MPI+OpenMP, Tp";

        MPI_Barrier(MPI_COMM_WORLD);  // Sincronizacion inicial para medicion limpia
        const double inicio_total = MPI_Wtime();
        const DatosModelo datos = cargar_datos_modelo(args.datos, c);
        metricas.segundos_carga = MPI_Wtime() - inicio_total;

        // Solo el proceso 0 escribe. Si la carpeta ya existe, todos deben detenerse.
        int salida_ok = 1;
        std::string error_salida;
        if (raiz) {
            try {
                preparar_salida(args, c);
            } catch (const std::exception& e) {
                salida_ok = 0;
                error_salida = e.what();
            }
        }
        MPI_Bcast(&salida_ok, 1, MPI_INT, 0, MPI_COMM_WORLD);
        if (!salida_ok) {
            if (raiz) std::cerr << "Error: " << error_salida << '\n';
            MPI_Finalize();
            return 1;
        }

        // ---------------- 2. Bucle Monte Carlo hibrido (MPI + OpenMP) ----------------
        MPI_Barrier(MPI_COMM_WORLD);
        const double inicio_simulacion = MPI_Wtime();
        const Bloque b = bloque_de(c.escenarios, procesos, rango);
        const bool macro = hay_incertidumbre_macro(c);
        std::vector<int> primer_paso(std::size_t(b.tamano()));
        std::vector<double> factores;
        if (macro) factores.resize(2 * std::size_t(b.tamano()));
        std::ostringstream trayectoria;  // Escenario 1: procesado solo por rango 0, hilo correspondiente
        trayectoria << std::setprecision(15);

        bool fallo_local = false;
        std::string mensaje_fallo_local;

#pragma omp parallel for schedule(dynamic, 16)
        for (Conteo r = b.inicio; r < b.fin; ++r) {
            const std::size_t i = std::size_t(r - b.inicio);
            try {
                const ResultadoEscenario e = simular_escenario(r, datos, c, r == 0 ? &trayectoria : nullptr);
                primer_paso[i] = e.primer_paso;
                if (macro) {
                    factores[2 * i] = e.factor_fecundidad;
                    factores[2 * i + 1] = e.factor_mortalidad;
                }
            } catch (const std::exception& exc) {
#pragma omp critical(fallo_hibrido_escenario)
                if (!fallo_local) {
                    fallo_local = true;
                    mensaje_fallo_local = "Proceso " + std::to_string(rango) + ", Escenario " +
                                          std::to_string(r + 1) + ": " + exc.what();
                }
            }
        }
        exigir(!fallo_local, mensaje_fallo_local);
        const double fin_computo = MPI_Wtime();

        // ---------------- 3. Comunicacion: resultados al proceso 0 ----------------
        const std::vector<int> todos_pasos = reunir(primer_paso, MPI_INT, 1, c.escenarios, procesos, rango);
        std::vector<double> todos_factores;
        if (macro) todos_factores = reunir(factores, MPI_DOUBLE, 2, c.escenarios, procesos, rango);
        const double fin_comunicacion = MPI_Wtime();

        // Metricas agregadas: CPU sumada (cada proceso suma sus hilos OpenMP), memoria maxima y comunicacion
        const double cpu_local = segundos_cpu_proceso(), memoria_local = memoria_pico_mib();
        const double comunicacion_local = fin_comunicacion - fin_computo;
        double cpu_total = 0, memoria_max = 0, comunicacion_max = 0;
        MPI_Reduce(&cpu_local, &cpu_total, 1, MPI_DOUBLE, MPI_SUM, 0, MPI_COMM_WORLD);
        MPI_Reduce(&memoria_local, &memoria_max, 1, MPI_DOUBLE, MPI_MAX, 0, MPI_COMM_WORLD);
        MPI_Reduce(&comunicacion_local, &comunicacion_max, 1, MPI_DOUBLE, MPI_MAX, 0, MPI_COMM_WORLD);

        // ---------------- 4. Escritura ordenada (proceso 0) ----------------
        if (raiz) {
            std::ofstream trayectoria_csv(args.salida / "trayectoria_escenario_1.csv");
            exigir(bool(trayectoria_csv), "No se puede escribir salida");
            trayectoria_csv << ENCABEZADO_TRAYECTORIA << trayectoria.str();
            trayectoria_csv.close();
            exigir(!trayectoria_csv.fail(), "Fallo al terminar escritura");

            EscritorEscenarios escritor(args.salida, c);
            for (Conteo r = 0; r < c.escenarios; ++r) {
                ResultadoEscenario e;
                e.primer_paso = todos_pasos[std::size_t(r)];
                if (macro) {
                    e.factor_fecundidad = todos_factores[2 * std::size_t(r)];
                    e.factor_mortalidad = todos_factores[2 * std::size_t(r) + 1];
                }
                escritor.agregar(r, e);
            }
            escritor.cerrar();

            metricas.segundos_simulacion = MPI_Wtime() - inicio_simulacion;
            metricas.segundos_total = MPI_Wtime() - inicio_total;
            metricas.segundos_cpu = cpu_total;
            metricas.memoria_pico_mb = memoria_max;
            metricas.segundos_comunicacion = comunicacion_max;
            escribir_resultados(args.salida, c, datos.N0, escritor, metricas,
                                "C++17 + Hibrido (MPI + OpenMP), " + std::to_string(procesos) +
                                    " procesos x " + std::to_string(hilos) + " hilos.",
                                "hibrido");
        }
    } catch (const std::exception& e) {
        std::cerr << "Error (proceso " << rango << "): " << e.what() << '\n';
        MPI_Abort(MPI_COMM_WORLD, 1);
    }
    MPI_Finalize();
    return 0;
}

