// main.cpp
// Simulacion Monte Carlo de la inversion demografica del Peru. Version SECUENCIAL:
// un proceso, un hilo; recorre un escenario completo y luego el siguiente.
//
// Uso:
//   ./simulador --config config_demostracion.ini [--datos datos] [--salida resultados] [--escenarios N]
//   ./simulador --self-test [--datos datos]
#include <algorithm>
#include <chrono>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <vector>

#include "configuracion.hpp"
#include "datos.hpp"
#include "grafico.hpp"
#include "metricas.hpp"
#include "modelo.hpp"
#include "pruebas.hpp"

namespace fs = std::filesystem;
using Reloj = std::chrono::steady_clock;

namespace {

struct Argumentos {
    fs::path config;
    fs::path datos = "datos";
    fs::path salida = "resultados";
    Conteo escenarios = 0;  // 0 = usar el valor del .ini
    bool pruebas = false;
    bool ayuda = false;
};

Argumentos leer_argumentos(int argc, char** argv) {
    Argumentos a;
    for (int i = 1; i < argc; ++i) {
        const std::string opcion = argv[i];
        if (opcion == "--self-test") { a.pruebas = true; continue; }
        if (opcion == "--help") { a.ayuda = true; continue; }
        exigir(i + 1 < argc, "Falta valor para " + opcion);
        const std::string valor = argv[++i];
        if (opcion == "--config") a.config = valor;
        else if (opcion == "--datos") a.datos = valor;
        else if (opcion == "--salida") a.salida = valor;
        else if (opcion == "--escenarios") {
            a.escenarios = leer_entero(valor);
            exigir(a.escenarios >= 1 && a.escenarios <= 1000000000LL, "Escenarios fuera de limites");
        } else
            throw std::runtime_error("Opcion desconocida: " + opcion);
    }
    return a;
}

void escribir_parametros(const fs::path& archivo, const Configuracion& c) {
    std::ofstream m(archivo);
    m << "estado_datos=" << c.estado_datos << "\nanio_base=" << c.anio_base << "\nhorizonte=" << c.horizonte
      << "\nescenarios=" << c.escenarios << "\nsemilla=" << c.semilla << "\ntipo_mortalidad=" << c.tipo_mortalidad
      << "\nsigma_fecundidad=" << c.sigma_fecundidad << "\nsigma_mortalidad=" << c.sigma_mortalidad
      << "\nq100 desde configuracion; fila100 del CSV no aplicada"
         "\nDesagregacion uniforme entera; mortalidad constante en el tiempo"
         "\nBiblioteca C++: reproducibilidad exacta solo con mismo ejecutable/entorno\n";
}

}  // namespace

int main(int argc, char** argv) {
    try {
        const Argumentos args = leer_argumentos(argc, argv);
        if (args.ayuda) {
            std::cout << "Uso: simulador --config config_demostracion.ini [--datos datos] [--salida resultados] "
                         "[--escenarios N]\nPruebas: simulador --self-test [--datos datos]\n";
            return 0;
        }
        if (args.pruebas) {
            ejecutar_pruebas(args.datos);
            return 0;
        }
        exigir(!args.config.empty(), "Indique --config. Use --help para instrucciones.");

        // ---------------- 1. Configuracion y datos ----------------
        Configuracion c = leer_configuracion(args.config);
        if (args.escenarios) c.escenarios = args.escenarios;

        Metricas metricas;
        metricas.escenarios = c.escenarios;
        metricas.horizonte = c.horizonte;
        const auto inicio_total = Reloj::now();
        const Poblacion N0 = cargar_poblacion_inicial(args.datos);
        const Tasas q = cargar_mortalidad(args.datos, c);
        const auto fecundidad = cargar_fecundidad(args.datos, c);
        metricas.segundos_carga = std::chrono::duration<double>(Reloj::now() - inicio_total).count();

        exigir(!fs::exists(args.salida), "La carpeta de salida ya existe. Elija otra con --salida.");
        fs::create_directories(args.salida);
        fs::copy_file(args.config, args.salida / "config_usada.ini");
        escribir_parametros(args.salida / "parametros_efectivos.txt", c);

        std::ofstream escenarios_csv(args.salida / "escenarios.csv");
        std::ofstream trayectoria_csv(args.salida / "trayectoria_escenario_1.csv");
        exigir(bool(escenarios_csv) && bool(trayectoria_csv), "No se puede escribir salida");
        escenarios_csv << "escenario,ocurrio_inversion,primer_anio_inversion\n";
        trayectoria_csv << "anio,poblacion_inicial,nacimientos,defunciones,poblacion_final,menores15,mayores65,"
                           "lambda,balance\n"
                        << std::setprecision(15);

        // ---------------- 2. Bucle Monte Carlo ----------------
        // histograma[t] = escenarios cuya primera inversion ocurre en anio_base + t
        std::vector<Conteo> histograma(c.horizonte + 1, 0);
        Conteo con_inversion = 0;
        const bool macro = c.sigma_fecundidad > 0.0 || c.sigma_mortalidad > 0.0;
        std::ofstream factores_csv;
        if (macro) {
            factores_csv.open(args.salida / "factores_escenarios.csv");
            exigir(bool(factores_csv), "No se puede escribir factores_escenarios.csv");
            factores_csv << "escenario,factor_fecundidad,factor_mortalidad\n" << std::setprecision(10);
        }
        const auto inicio_simulacion = Reloj::now();

        for (Conteo r = 0; r < c.escenarios; ++r) {
            Poblacion N = N0;  // cada escenario parte de la misma poblacion inicial
            std::mt19937_64 generador(mezclar_semilla(c.semilla + std::uint64_t(r)));
            int primer_paso = hay_inversion(N) ? 0 : -1;  // tambien se revisa el estado inicial

            // Incertidumbre macro: dos multiplicadores por escenario (no por persona ni por anio).
            // Con sigma = 0 no se consume ningun numero aleatorio: la ejecucion es identica a la de referencia.
            const Tasas* q_r = &q;
            const std::vector<TasaFecundidad>* fecundidad_r = &fecundidad;
            Tasas q_esc;
            std::vector<TasaFecundidad> fecundidad_esc;
            if (macro) {
                double factor_fec = 1.0, factor_mort = 1.0;
                if (c.sigma_fecundidad > 0.0)
                    factor_fec = std::max(0.0, std::normal_distribution<double>(1.0, c.sigma_fecundidad)(generador));
                if (c.sigma_mortalidad > 0.0)
                    factor_mort = std::max(0.0, std::normal_distribution<double>(1.0, c.sigma_mortalidad)(generador));
                fecundidad_esc = fecundidad;
                for (auto& f : fecundidad_esc)
                    for (double& v : f) v *= factor_fec;
                q_esc = q;
                for (auto& sexo : q_esc)
                    for (double& v : sexo) v = std::clamp(v * factor_mort, 0.0, 1.0);
                q_r = &q_esc;
                fecundidad_r = &fecundidad_esc;
                factores_csv << r + 1 << ',' << factor_fec << ',' << factor_mort << '\n';
            }

            for (int t = 0; t < c.horizonte; ++t) {
                const Conteo antes = poblacion_total(N);
                const PasoAnual paso = simular_anio(N, *q_r, (*fecundidad_r)[t], c, generador);
                N = paso.poblacion;
                if (primer_paso < 0 && hay_inversion(N)) primer_paso = t + 1;
                // Se completa el horizonte aunque ya haya inversion: misma carga por escenario.

                if (r == 0)
                    trayectoria_csv << c.anio_base + t + 1 << ',' << antes << ',' << paso.nacimientos << ','
                                    << paso.defunciones << ',' << poblacion_total(N) << ',' << menores_15(N) << ','
                                    << mayores_65(N) << ',' << paso.lambda << ','
                                    << (poblacion_total(N) - antes - paso.nacimientos + paso.defunciones) << '\n';
            }

            escenarios_csv << r + 1 << ',' << (primer_paso >= 0 ? 1 : 0) << ',';
            if (primer_paso >= 0) {
                escenarios_csv << c.anio_base + primer_paso;
                ++con_inversion;
                ++histograma[primer_paso];
            }
            escenarios_csv << '\n';
        }
        escenarios_csv.close();
        trayectoria_csv.close();
        if (macro) { factores_csv.close(); exigir(!factores_csv.fail(), "Fallo al escribir factores"); }
        exigir(!escenarios_csv.fail() && !trayectoria_csv.fail(), "Fallo al terminar escritura");
        const double segundos = std::chrono::duration<double>(Reloj::now() - inicio_simulacion).count();
        metricas.segundos_simulacion = segundos;

        // ---------------- 3. Estimacion Monte Carlo ----------------
        // p(T = y) = frecuencia / R;  F(y) = acumulada / R  (R incluye escenarios sin inversion)
        std::ofstream dist(args.salida / "distribucion.csv");
        dist << "anio,primeras_inversiones,probabilidad_anual,probabilidad_acumulada\n" << std::setprecision(15);
        Conteo acumulado = 0, suma_anios = 0;
        int anio_min = 0, anio_max = 0;
        for (int t = 0; t <= c.horizonte; ++t) {
            acumulado += histograma[t];
            suma_anios += histograma[t] * Conteo(c.anio_base + t);
            if (histograma[t] > 0) {
                if (anio_min == 0) anio_min = c.anio_base + t;
                anio_max = c.anio_base + t;
            }
            dist << c.anio_base + t << ',' << histograma[t] << ',' << double(histograma[t]) / c.escenarios << ','
                 << double(acumulado) / c.escenarios << '\n';
        }
        dist.close();
        exigir(!dist.fail(), "Error guardando histograma");
        exigir(acumulado == con_inversion, "Conteo inconsistente");

        // ---------------- 4. Resumen ----------------
        std::ofstream res(args.salida / "resumen.txt");
        res << std::setprecision(12) << "ESTADO: " << c.estado_datos << "\n";
        if (c.estado_datos == "DEMO_NO_VALIDADO")
            res << "Ejecucion ilustrativa con supuestos no confirmados. No es una prediccion validada del Peru.\n";
        res << "Version: C++17 secuencial, un proceso, un hilo.\n"
            << "Poblacion inicial: " << poblacion_total(N0) << "\nMenores de 15: " << menores_15(N0)
            << "\n65 o mas: " << mayores_65(N0) << "\nEscenarios completados: " << c.escenarios
            << "\nHorizonte: " << c.horizonte << "\nCon inversion: " << con_inversion
            << "\nSin inversion: " << c.escenarios - con_inversion
            << "\nProbabilidad de inversion: " << double(con_inversion) / c.escenarios
            << "\nProbabilidad sin inversion: " << double(c.escenarios - con_inversion) / c.escenarios << "\n";
        if (con_inversion > 0)
            res << "Primer anio de inversion (escenarios con inversion): minimo " << anio_min << ", media "
                << double(suma_anios) / con_inversion << ", maximo " << anio_max << "\n";
        // ---------------- 5. Metricas de rendimiento (linea base T1) ----------------
        metricas.segundos_total = std::chrono::duration<double>(Reloj::now() - inicio_total).count();
        metricas.segundos_cpu = segundos_cpu_proceso();
        metricas.memoria_pico_mb = memoria_pico_mib();
        res << "Segundos simulacion y escritura de escenarios: " << segundos
            << "\nSegundos hasta resumen: " << metricas.segundos_total << "\n";
        escribir_metricas_texto(res, metricas);
        histograma_texto(res, c.anio_base, histograma, c.escenarios);
        res.close();
        exigir(!res.fail(), "Error guardando resumen");

        // ---------------- 6. Grafico generado por el ejecutable ----------------
        {
            std::ostringstream sub;
            sub << c.escenarios << " escenarios, horizonte " << c.horizonte << " anios, semilla " << c.semilla;
            if (macro) sub << ", sigma_fec " << c.sigma_fecundidad << ", sigma_mort " << c.sigma_mortalidad;
            else sub << ", tasas fijas";
            histograma_svg(args.salida / "distribucion_anio.svg", c.anio_base, histograma, c.escenarios, sub.str());
        }
        escribir_metricas_csv(args.salida / "metricas.csv", metricas, "secuencial");

        std::cout << "Completado: " << c.escenarios << " escenarios. Estado: " << c.estado_datos
                  << "\nResultados en: " << args.salida.string() << "\nTiempo simulacion + escritura: " << segundos
                  << " s\n";
        escribir_metricas_texto(std::cout, metricas);
        histograma_texto(std::cout, c.anio_base, histograma, c.escenarios);
        std::cout << "Grafico: " << (args.salida / "distribucion_anio.svg").string() << "\n";
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << '\n';
        return 1;
    }
    return 0;
}
