// main_mpi.cpp
// Simulacion Monte Carlo de la inversion demografica del Peru. Version MPI (Sprint 3, S10):
// p procesos de memoria distribuida, un hilo por proceso. Se ejecuta en una maquina o en el
// cluster de contenedores Docker (ver docker/).
//
// Descomposicion: reparto por bloques contiguos de los R escenarios. El proceso k simula
// [inicio_k, fin_k), con bloques que difieren a lo sumo en un escenario. Como todos los escenarios
// simulan el horizonte completo, cuestan lo mismo y el reparto estatico queda balanceado.
// Cada proceso lee los CSV por su cuenta (son pocos KB) y no hay comunicacion durante la simulacion;
// al final un MPI_Gatherv lleva al proceso 0 el primer anio de inversion (y los factores macro)
// de cada escenario, y el proceso 0 escribe los CSV en orden. Los CSV de resultados son identicos
// byte a byte a los de la version secuencial con la misma semilla, sea cual sea p.
//
// Uso:
//   mpirun -np 4 ./simulador_mpi --config config.ini [--datos d] [--salida s] [--escenarios N]
#include <mpi.h>

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
    MPI_Init(&argc, &argv);
    int rango = 0, procesos = 1;
    MPI_Comm_rank(MPI_COMM_WORLD, &rango);
    MPI_Comm_size(MPI_COMM_WORLD, &procesos);
    const bool raiz = rango == 0;

    try {
        const Argumentos args = leer_argumentos(argc, argv);
        if (args.ayuda || args.pruebas) {
            if (raiz) {
                if (args.ayuda) imprimir_ayuda("mpirun -np P simulador_mpi");
                else ejecutar_pruebas(args.datos);
            }
            MPI_Finalize();
            return 0;
        }

        // ---------------- 1. Configuracion y datos (cada proceso) ----------------
        const Configuracion c = configuracion_efectiva(args);
        // Los conteos y desplazamientos de MPI_Gatherv son int (2 double por escenario con factores).
        exigir(c.escenarios <= 1000000000LL, "MPI: escenarios debe ser <= 10^9");
        Metricas metricas;
        metricas.escenarios = c.escenarios;
        metricas.horizonte = c.horizonte;
        metricas.procesos = procesos;
        metricas.etiqueta = "MPI, Tp";

        MPI_Barrier(MPI_COMM_WORLD);  // todos empiezan a medir a la vez
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

        // ---------------- 2. Bloque local de escenarios ----------------
        MPI_Barrier(MPI_COMM_WORLD);
        const double inicio_simulacion = MPI_Wtime();
        const Bloque b = bloque_de(c.escenarios, procesos, rango);
        const bool macro = hay_incertidumbre_macro(c);
        std::vector<int> primer_paso(std::size_t(b.tamano()));
        std::vector<double> factores;  // pares (fecundidad, mortalidad), solo con incertidumbre macro
        if (macro) factores.resize(2 * std::size_t(b.tamano()));
        std::ostringstream trayectoria;  // escenario 1: siempre esta en el bloque del proceso 0
        trayectoria << std::setprecision(15);
        for (Conteo r = b.inicio; r < b.fin; ++r) {
            const std::size_t i = std::size_t(r - b.inicio);
            const ResultadoEscenario e = simular_escenario(r, datos, c, r == 0 ? &trayectoria : nullptr);
            primer_paso[i] = e.primer_paso;
            if (macro) {
                factores[2 * i] = e.factor_fecundidad;
                factores[2 * i + 1] = e.factor_mortalidad;
            }
        }
        const double fin_computo = MPI_Wtime();

        // ---------------- 3. Comunicacion: resultados al proceso 0 ----------------
        const std::vector<int> todos_pasos = reunir(primer_paso, MPI_INT, 1, c.escenarios, procesos, rango);
        std::vector<double> todos_factores;
        if (macro) todos_factores = reunir(factores, MPI_DOUBLE, 2, c.escenarios, procesos, rango);
        const double fin_comunicacion = MPI_Wtime();

        // Metricas agregadas: CPU sumada y memoria maxima por proceso; tiempo de comunicacion maximo.
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
                                "C++17 + MPI, " + std::to_string(procesos) + " procesos, un hilo por proceso.", "mpi");
        }
    } catch (const std::exception& e) {
        // Un error en cualquier proceso detiene a todos: si no, los demas quedarian bloqueados en el Gatherv.
        std::cerr << "Error (proceso " << rango << "): " << e.what() << '\n';
        MPI_Abort(MPI_COMM_WORLD, 1);
    }
    MPI_Finalize();
    return 0;
}
