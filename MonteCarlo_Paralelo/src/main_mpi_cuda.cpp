// main_mpi_cuda.cpp
// Simulacion Monte Carlo de la inversion demografica del Peru. Version heterogenea MPI + CUDA + OpenMP:
// el proceso 0 simula su bloque en la GPU y los procesos 1..P-1 simulan los suyos en la CPU con H hilos
// OpenMP cada uno.
//
// 1. Todos los procesos ejecutan el MISMO nucleo (nucleo_cuda.hpp, funciones __host__ __device__): el
//    escenario r usa el generador xoroshiro128++ sembrado con splitmix64(semilla + r) lo simule quien
//    lo simule. La GPU y la CPU solo difieren en el redondeo del ultimo bit de algunas funciones
//    matematicas (prueba C4 de simulador_cuda: mismo anio de inversion en todos los escenarios probados),
//    asi que el resultado no depende de como se repartan los escenarios.
// 2. Balanceo de carga: los recursos no son iguales, asi que los bloques tampoco. Cada proceso mide su
//    velocidad con una calibracion corta (escenarios por segundo) y los R escenarios se reparten en
//    bloques contiguos proporcionales a esas velocidades. MC_PESO_GPU fija el reparto a mano.
// 3. MPI_Gatherv reune los resultados en el proceso 0, que escribe los CSV en orden r = 0..R-1.
//
// Uso:
//   mpirun -np P --bind-to none ./simulador_mpi_cuda --config config.ini [--datos d] [--salida s]
//          [--escenarios N] [--hilos H]
//   Variables opcionales: MC_LOTE (escenarios por lote de GPU, por defecto 262144) y MC_PESO_GPU
//   (velocidad de la GPU relativa a la de UN proceso de CPU; sin ella se calibra). Con calibracion el
//   tamano de los bloques varia un poco de una corrida a otra; con MC_PESO_GPU es fijo.
#include <mpi.h>
#include <omp.h>

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "cuda_comun.hpp"
#include "escenario.hpp"
#include "gpu.hpp"
#include "pruebas.hpp"
#include "salida.hpp"

namespace {

// Limites de los bloques contiguos: el proceso k simula [limites[k], limites[k+1]).
// Reparto proporcional a las velocidades, redondeando los limites acumulados.
std::vector<Conteo> repartir(Conteo R, const std::vector<double>& velocidad) {
    double total = 0;
    for (const double v : velocidad) total += v;
    std::vector<Conteo> limites(velocidad.size() + 1, 0);
    double acumulada = 0;
    for (std::size_t k = 0; k < velocidad.size(); ++k) {
        acumulada += velocidad[k];
        limites[k + 1] = std::max(limites[k], Conteo(std::llround(double(R) * acumulada / total)));
    }
    limites.back() = R;
    return limites;
}

// Reune en el proceso 0 los bloques de todos; cada escenario ocupa por_escenario elementos.
template <typename T>
std::vector<T> reunir(const std::vector<T>& local, MPI_Datatype tipo, int por_escenario,
                      const std::vector<Conteo>& limites, int rango) {
    const int p = int(limites.size()) - 1;
    std::vector<int> conteos, desplazamientos;
    std::vector<T> total;
    if (rango == 0) {
        conteos.resize(p);
        desplazamientos.resize(p);
        for (int k = 0; k < p; ++k) {
            conteos[k] = int((limites[k + 1] - limites[k]) * por_escenario);
            desplazamientos[k] = int(limites[k] * por_escenario);
        }
        total.resize(std::size_t(limites.back()) * std::size_t(por_escenario));
    }
    MPI_Gatherv(local.data(), int(local.size()), tipo, total.data(), conteos.data(), desplazamientos.data(), tipo, 0,
                MPI_COMM_WORLD);
    return total;
}

// Simula en la CPU (OpenMP) los escenarios [inicio, inicio + n) con el nucleo comun.
void simular_cpu(const DatosGpu& d, const std::vector<double>& f, Conteo inicio, Conteo n, int* pasos, double* factores) {
#pragma omp parallel for schedule(dynamic, 64)
    for (Conteo i = 0; i < n; ++i)
        pasos[i] = mc_simular_escenario(d, f.data(), std::uint64_t(inicio + i), &factores[2 * i], &factores[2 * i + 1],
                                        nullptr);
}

// Simula en la GPU, por lotes, los escenarios [inicio, inicio + n).
void simular_gpu(Conteo inicio, Conteo n, int lote, int* pasos, double* factores) {
    for (Conteo hecho = 0; hecho < n; hecho += lote) {
        const int m = int(std::min<Conteo>(lote, n - hecho));
        exigir_gpu(gpu_simular_lote(static_cast<unsigned long long>(inicio + hecho), m, pasos + hecho,
                                    factores + 2 * hecho));
    }
}

}  // namespace

int main(int argc, char** argv) {
    int proporcionado = 0;
    MPI_Init_thread(&argc, &argv, MPI_THREAD_FUNNELED, &proporcionado);
    int rango = 0, procesos = 1;
    MPI_Comm_rank(MPI_COMM_WORLD, &rango);
    MPI_Comm_size(MPI_COMM_WORLD, &procesos);
    const bool raiz = rango == 0;  // el proceso 0 es el unico que usa la GPU y el unico que escribe

    try {
        const Argumentos args = leer_argumentos(argc, argv, true);
        if (args.ayuda || args.pruebas) {
            if (raiz) {
                if (args.ayuda) imprimir_ayuda("mpirun -np P simulador_mpi_cuda", true);
                else ejecutar_pruebas(args.datos);
            }
            MPI_Finalize();
            return 0;
        }
        if (args.hilos > 0) omp_set_num_threads(args.hilos);
        const int hilos = omp_get_max_threads();

        // ---------------- 1. Configuracion, datos y GPU ----------------
        Configuracion c = configuracion_efectiva(args);
        c.muestreo_rapido = true;  // el nucleo comun solo existe con muestreo rapido
        Metricas metricas;
        metricas.escenarios = c.escenarios;
        metricas.horizonte = c.horizonte;
        metricas.procesos = procesos;
        metricas.hilos = hilos;
        metricas.etiqueta = "MPI + CUDA + OpenMP, Tp";

        MPI_Barrier(MPI_COMM_WORLD);
        const double inicio_total = MPI_Wtime();
        const DatosModelo datos = cargar_datos_modelo(args.datos, c);
        std::vector<double> fecundidad;
        const DatosGpu dg = a_datos_gpu(datos, c, fecundidad);
        const int lote = tamano_lote();
        char nombre_gpu[256] = "";
        if (raiz) exigir_gpu(gpu_iniciar(dg, fecundidad.data(), lote, nombre_gpu, sizeof(nombre_gpu)));
        metricas.segundos_carga = MPI_Wtime() - inicio_total;

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

        // ---------------- 2. Calibracion y reparto proporcional ----------------
        MPI_Barrier(MPI_COMM_WORLD);
        const double inicio_simulacion = MPI_Wtime();
        double mi_velocidad = 1.0;  // escenarios por segundo de este proceso
        const char* peso_fijo = std::getenv("MC_PESO_GPU");
        if (peso_fijo) {
            const double peso = leer_real(peso_fijo);
            exigir(peso > 0.0 && peso <= 1e6, "MC_PESO_GPU fuera de limites");
            mi_velocidad = raiz ? peso : 1.0;
        } else {
            // Todos calibran a la vez, como trabajaran despues: la medida incluye la competencia por la CPU.
            const Conteo n = raiz ? std::min<Conteo>(lote, 131072) : Conteo(2500) * hilos;
            std::vector<int> pasos(static_cast<std::size_t>(n));
            std::vector<double> factores(2 * static_cast<std::size_t>(n));
            // Calentamiento, que no se mide: primer lanzamiento del kernel y arranque de los hilos OpenMP.
            if (raiz) simular_gpu(0, 4096, lote, pasos.data(), factores.data());
            else simular_cpu(dg, fecundidad, 0, Conteo(100) * hilos, pasos.data(), factores.data());
            const double t0 = MPI_Wtime();
            if (raiz) simular_gpu(0, n, lote, pasos.data(), factores.data());
            else simular_cpu(dg, fecundidad, 0, n, pasos.data(), factores.data());
            mi_velocidad = double(n) / std::max(MPI_Wtime() - t0, 1e-9);
        }
        std::vector<double> velocidad(static_cast<std::size_t>(procesos));
        MPI_Allgather(&mi_velocidad, 1, MPI_DOUBLE, velocidad.data(), 1, MPI_DOUBLE, MPI_COMM_WORLD);
        const std::vector<Conteo> limites = repartir(c.escenarios, velocidad);
        const Conteo inicio = limites[std::size_t(rango)], n_local = limites[std::size_t(rango) + 1] - inicio;
        const double fin_calibracion = MPI_Wtime();

        // ---------------- 3. Bucle Monte Carlo: GPU en el proceso 0, OpenMP en los demas ----------------
        std::vector<int> pasos(static_cast<std::size_t>(n_local));
        std::vector<double> factores(2 * static_cast<std::size_t>(n_local));
        if (raiz) simular_gpu(inicio, n_local, lote, pasos.data(), factores.data());
        else simular_cpu(dg, fecundidad, inicio, n_local, pasos.data(), factores.data());
        const double fin_computo = MPI_Wtime();

        // ---------------- 4. Comunicacion: resultados al proceso 0 ----------------
        const std::vector<int> todos_pasos = reunir(pasos, MPI_INT, 1, limites, rango);
        const std::vector<double> todos_factores = reunir(factores, MPI_DOUBLE, 2, limites, rango);
        const double fin_comunicacion = MPI_Wtime();

        const double cpu_local = segundos_cpu_proceso(), memoria_local = memoria_pico_mib();
        const double comunicacion_local = fin_comunicacion - fin_computo, computo_local = fin_computo - fin_calibracion;
        double cpu_total = 0, memoria_max = 0, comunicacion_max = 0;
        std::vector<double> computo(static_cast<std::size_t>(procesos));
        MPI_Reduce(&cpu_local, &cpu_total, 1, MPI_DOUBLE, MPI_SUM, 0, MPI_COMM_WORLD);
        MPI_Reduce(&memoria_local, &memoria_max, 1, MPI_DOUBLE, MPI_MAX, 0, MPI_COMM_WORLD);
        MPI_Reduce(&comunicacion_local, &comunicacion_max, 1, MPI_DOUBLE, MPI_MAX, 0, MPI_COMM_WORLD);
        MPI_Gather(&computo_local, 1, MPI_DOUBLE, computo.data(), 1, MPI_DOUBLE, 0, MPI_COMM_WORLD);

        // ---------------- 5. Escritura ordenada (proceso 0) ----------------
        if (raiz) {
            std::vector<FilaTraza> filas(std::size_t(c.horizonte));
            int paso_traza = 0;
            exigir_gpu(gpu_trayectoria(0, filas.data(), &paso_traza));
            gpu_liberar();
            std::ofstream trayectoria_csv(args.salida / "trayectoria_escenario_1.csv");
            exigir(bool(trayectoria_csv), "No se puede escribir salida");
            trayectoria_csv << ENCABEZADO_TRAYECTORIA << std::setprecision(15);
            for (int t = 0; t < c.horizonte; ++t) {
                const FilaTraza& fila = filas[std::size_t(t)];
                exigir(fila.balance == 0, "Balance poblacional inconsistente");
                trayectoria_csv << c.anio_base + t + 1 << ',' << fila.antes << ',' << fila.nacimientos << ','
                                << fila.defunciones << ',' << fila.despues << ',' << fila.menores15 << ','
                                << fila.mayores65 << ',' << fila.lambda << ',' << fila.balance << '\n';
            }
            trayectoria_csv.close();
            exigir(!trayectoria_csv.fail(), "Fallo al terminar escritura");

            const bool macro = hay_incertidumbre_macro(c);
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
            const double parte_gpu = 100.0 * double(limites[1]) / double(c.escenarios);
            std::ostringstream version;
            version << std::fixed << std::setprecision(1) << "C++17 + MPI + CUDA + OpenMP, " << procesos
                    << " procesos: el 0 en GPU (" << nombre_gpu << ", " << parte_gpu << " % de los escenarios)"
                    << (procesos > 1 ? " y los demas en CPU con " + std::to_string(hilos) + " hilos" : std::string())
                    << ", generador xoroshiro128++.";
            escribir_resultados(args.salida, c, datos.N0, escritor, metricas, version.str(), "mpi_cuda");

            // Reparto y balance: si la calibracion fue buena, todos los procesos terminan a la vez.
            std::cout << std::fixed << std::setprecision(2) << "--- Reparto (" << (peso_fijo ? "MC_PESO_GPU" : "calibracion")
                      << ", " << fin_calibracion - inicio_simulacion << " s) ---\n";
            for (int k = 0; k < procesos; ++k)
                std::cout << "Proceso " << k << (k == 0 ? " (GPU)" : " (CPU)") << ": " << limites[std::size_t(k) + 1] - limites[std::size_t(k)]
                          << " escenarios (" << 100.0 * double(limites[std::size_t(k) + 1] - limites[std::size_t(k)]) / double(c.escenarios)
                          << " %), velocidad medida " << velocidad[std::size_t(k)] << " esc/s, computo "
                          << computo[std::size_t(k)] << " s\n";
        }
    } catch (const std::exception& e) {
        std::cerr << "Error (proceso " << rango << "): " << e.what() << '\n';
        MPI_Abort(MPI_COMM_WORLD, 1);
    }
    MPI_Finalize();
    return 0;
}
