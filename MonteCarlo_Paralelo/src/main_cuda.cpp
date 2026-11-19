// main_cuda.cpp
// Simulacion Monte Carlo de la inversion demografica del Peru. Version CUDA: un hilo de GPU por escenario.
//
// Descomposicion: la misma paralelizacion de datos de OpenMP y MPI. Los R escenarios se envian a la GPU
// en lotes; dentro de un lote cada hilo simula un escenario completo (nucleo_cuda.hpp) con su propio
// generador, sin comunicarse con los demas. El anfitrion reune los resultados de cada lote y, al final,
// escribe los CSV en orden r = 0..R-1 con el mismo codigo que las demas versiones.
//
// Resultados: mismo modelo y mismos algoritmos de sorteo que --muestreo rapido, pero con otro generador
// (xoroshiro128++ en lugar de mt19937_64). Son estadisticamente equivalentes a los de la CPU, no identicos
// escenario a escenario; por eso esta version no entra en make verificar.
//
// Uso:
//   ./simulador_cuda --config config.ini [--datos d] [--salida s] [--escenarios N]
//   ./simulador_cuda --self-test --config config.ini [--datos d]   # pruebas del modelo, de los sorteos y GPU = CPU
//   Variable opcional MC_LOTE: escenarios por lote (por defecto 262144).
#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <string>
#include <vector>

#include "cuda_comun.hpp"
#include "escenario.hpp"
#include "gpu.hpp"
#include "pruebas.hpp"
#include "salida.hpp"

using Reloj = std::chrono::steady_clock;

namespace {

// Ji-cuadrado de M sorteos contra una funcion de masa; agrupa las clases con esperado < 10.
// Devuelve true si el estadistico queda bajo la media + 6 desviaciones de su distribucion.
template <typename Sorteo, typename LogMasa>
bool ajuste_ji_cuadrado(Sorteo sorteo, LogMasa log_masa, long long lo, long long hi, int M) {
    std::vector<double> observado(std::size_t(hi - lo + 1), 0.0);
    for (int i = 0; i < M; ++i) ++observado[std::size_t(std::clamp<long long>(sorteo(), lo, hi) - lo)];
    double ji = 0, esperado = 0, visto = 0, masa = 0;
    int grupos = 0;
    for (long long k = lo; k <= hi; ++k) {
        const double p = std::exp(log_masa(double(k)));
        masa += p;
        esperado += M * p;
        visto += observado[std::size_t(k - lo)];
        if (esperado >= 10) {
            ji += (visto - esperado) * (visto - esperado) / esperado;
            esperado = visto = 0;
            ++grupos;
        }
    }
    return masa > 0.999999 && ji < grupos + 6 * std::sqrt(2.0 * grupos);
}

int aprobadas = 0;
void comprobar(bool condicion, const std::string& nombre) {
    exigir(condicion, "PRUEBA FALLIDA: " + nombre);
    ++aprobadas;
    std::cout << "  [OK] " << nombre << '\n';
}

// Pruebas propias de la version CUDA: sorteos del nucleo (en la CPU) y GPU = CPU con el mismo codigo.
void pruebas_cuda(const Argumentos& args) {
    std::cout << "Pruebas de la version CUDA\n";
    const int M = 400000;
    McGenerador g = mc_sembrar(1, 0);

    bool ok = true;
    const struct { int n; double p; } binomiales[] = {{30, 0.2}, {60, 0.3}, {400, 0.9}, {250000, 0.004}, {5000, 0.35}};
    for (const auto& b : binomiales) {
        const double media = b.n * b.p, desv = std::sqrt(media * (1 - b.p));
        ok = ok && ajuste_ji_cuadrado(
                       [&] { return (long long)mc_binomial(b.n, b.p, g); },
                       [&](double k) {
                           return std::lgamma(b.n + 1.0) - std::lgamma(k + 1) - std::lgamma(b.n - k + 1) +
                                  k * std::log(b.p) + (b.n - k) * std::log1p(-b.p);
                       },
                       std::max(0LL, (long long)(media - 8 * desv)), std::min<long long>(b.n, (long long)(media + 8 * desv) + 1), M);
    }
    comprobar(ok, "C1 binomial del nucleo: ji-cuadrado contra la masa exacta (5 casos)");

    ok = true;
    for (const double lambda : {4.0, 30.0, 512939.0}) {
        const double desv = std::sqrt(lambda);
        ok = ok && ajuste_ji_cuadrado([&] { return (long long)mc_poisson(lambda, g); },
                                      [&](double k) { return -lambda + k * std::log(lambda) - std::lgamma(k + 1); },
                                      std::max(0LL, (long long)(lambda - 8 * desv)), (long long)(lambda + 8 * desv) + 1, M);
    }
    comprobar(ok, "C2 Poisson del nucleo: ji-cuadrado contra la masa exacta (lambda = 4, 30 y 512 939)");

    double suma = 0, suma2 = 0;
    for (int i = 0; i < M; ++i) {
        const double z = mc_normal(g);
        suma += z;
        suma2 += z * z;
    }
    comprobar(std::fabs(suma / M) < 0.01 && std::fabs(suma2 / M - 1.0) < 0.02, "C3 normal del nucleo: media 0 y varianza 1");

    // GPU = CPU: los mismos escenarios, simulados con el mismo codigo en la GPU y en el anfitrion.
    exigir(!args.config.empty(), "Las pruebas de GPU necesitan --config");
    const Configuracion c = configuracion_efectiva(args);
    const DatosModelo datos = cargar_datos_modelo(args.datos, c);
    std::vector<double> fecundidad;
    const DatosGpu dg = a_datos_gpu(datos, c, fecundidad);
    const int n = 4096;
    char nombre[256];
    exigir_gpu(gpu_iniciar(dg, fecundidad.data(), n, nombre, sizeof(nombre)));
    std::vector<int> pasos(n);
    std::vector<double> factores(2 * std::size_t(n));
    exigir_gpu(gpu_simular_lote(0, n, pasos.data(), factores.data()));
    int pasos_iguales = 0, factores_iguales = 0, con_inversion = 0;
    double error_factor = 0.0;
    for (int i = 0; i < n; ++i) {
        double ff, fm;
        const int paso = mc_simular_escenario(dg, fecundidad.data(), std::uint64_t(i), &ff, &fm, nullptr);
        if (paso == pasos[i]) ++pasos_iguales;
        if (ff == factores[2 * std::size_t(i)] && fm == factores[2 * std::size_t(i) + 1]) ++factores_iguales;
        error_factor = std::max({error_factor, std::fabs(ff - factores[2 * std::size_t(i)]),
                                 std::fabs(fm - factores[2 * std::size_t(i) + 1])});
        if (pasos[i] >= 0) ++con_inversion;
    }
    std::cout << "  GPU: " << nombre << "; de " << n << " escenarios, mismo anio de inversion GPU/CPU: " << pasos_iguales
              << "; factores identicos bit a bit: " << factores_iguales << " (diferencia maxima " << error_factor << ")\n";
    // Las funciones matematicas de la GPU y de la CPU pueden diferir en el ultimo bit: los factores macro
    // (logaritmo y coseno de Box-Muller) no siempre coinciden bit a bit, y en teoria podria cambiar algun
    // sorteo aislado. Se exige diferencia despreciable en los factores y coincidencia casi total (99 %) en
    // el resultado.
    comprobar(pasos_iguales >= n - n / 100 && error_factor < 1e-12 && con_inversion > n / 2,
              "C4 la GPU reproduce los escenarios calculados en la CPU");

    std::vector<FilaTraza> filas(std::size_t(c.horizonte));
    int paso_traza = 0;
    exigir_gpu(gpu_trayectoria(0, filas.data(), &paso_traza));
    bool balance = paso_traza == pasos[0];
    for (const FilaTraza& fila : filas) balance = balance && fila.balance == 0 && fila.despues > 0;
    comprobar(balance, "C5 trayectoria en GPU: balance exacto cada anio y misma inversion que en el lote");
    gpu_liberar();
    std::cout << "Pruebas de la version CUDA: OK (" << aprobadas << " de " << aprobadas << ")\n";
}

}  // namespace

int main(int argc, char** argv) {
    try {
        const Argumentos args = leer_argumentos(argc, argv);
        if (args.ayuda) {
            imprimir_ayuda("simulador_cuda");
            return 0;
        }
        if (args.pruebas) {
            ejecutar_pruebas(args.datos);
            pruebas_cuda(args);
            return 0;
        }

        // ---------------- 1. Configuracion, datos y GPU ----------------
        Configuracion c = configuracion_efectiva(args);
        c.muestreo_rapido = true;  // la version CUDA solo existe con muestreo rapido (queda anotado en la salida)
        Metricas metricas;
        metricas.escenarios = c.escenarios;
        metricas.horizonte = c.horizonte;
        metricas.etiqueta = "CUDA, Tp";
        const auto inicio_total = Reloj::now();
        const DatosModelo datos = cargar_datos_modelo(args.datos, c);
        std::vector<double> fecundidad;
        const DatosGpu datos_gpu = a_datos_gpu(datos, c, fecundidad);
        const int lote = int(std::min<Conteo>(tamano_lote(), c.escenarios));
        char nombre_gpu[256];
        exigir_gpu(gpu_iniciar(datos_gpu, fecundidad.data(), lote, nombre_gpu, sizeof(nombre_gpu)));
        metricas.segundos_carga = std::chrono::duration<double>(Reloj::now() - inicio_total).count();
        preparar_salida(args, c);

        // ---------------- 2. Bucle Monte Carlo en la GPU, por lotes ----------------
        const auto inicio_simulacion = Reloj::now();
        const bool macro = hay_incertidumbre_macro(c);
        std::vector<int> pasos(static_cast<std::size_t>(c.escenarios));
        std::vector<double> factores(2 * static_cast<std::size_t>(c.escenarios));
        for (Conteo inicio = 0; inicio < c.escenarios; inicio += lote) {
            const int n = int(std::min<Conteo>(lote, c.escenarios - inicio));
            exigir_gpu(gpu_simular_lote(static_cast<unsigned long long>(inicio), n, pasos.data() + inicio,
                                        factores.data() + 2 * inicio));
        }
        // Trayectoria completa del escenario 1 (r = 0), calculada tambien en la GPU.
        std::vector<FilaTraza> filas(std::size_t(c.horizonte));
        int paso_traza = 0;
        exigir_gpu(gpu_trayectoria(0, filas.data(), &paso_traza));
        gpu_liberar();
        const double segundos_gpu = std::chrono::duration<double>(Reloj::now() - inicio_simulacion).count();

        // ---------------- 3. Escritura ordenada (anfitrion) ----------------
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

        EscritorEscenarios escritor(args.salida, c);
        for (Conteo r = 0; r < c.escenarios; ++r) {
            ResultadoEscenario e;
            e.primer_paso = pasos[std::size_t(r)];
            if (macro) {
                e.factor_fecundidad = factores[2 * std::size_t(r)];
                e.factor_mortalidad = factores[2 * std::size_t(r) + 1];
            }
            escritor.agregar(r, e);
        }
        escritor.cerrar();
        metricas.segundos_simulacion = std::chrono::duration<double>(Reloj::now() - inicio_simulacion).count();

        // ---------------- 4. Metricas y resultados ----------------
        metricas.segundos_total = std::chrono::duration<double>(Reloj::now() - inicio_total).count();
        metricas.segundos_cpu = segundos_cpu_proceso();
        metricas.memoria_pico_mb = memoria_pico_mib();
        escribir_resultados(args.salida, c, datos.N0, escritor, metricas,
                            std::string("C++17 + CUDA, un hilo de GPU por escenario (") + nombre_gpu +
                                "), generador xoroshiro128++.",
                            "cuda");
        std::cout << "Segundos en GPU (lotes + trayectoria, sin escritura): " << segundos_gpu << "\n"
                  << "Escenarios por lote: " << lote << "\n";
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << '\n';
        return 1;
    }
    return 0;
}
