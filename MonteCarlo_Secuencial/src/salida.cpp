// salida.cpp
#include "salida.hpp"

#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>

#include "grafico.hpp"
#include "modelo.hpp"

namespace fs = std::filesystem;

Argumentos leer_argumentos(int argc, char** argv, bool acepta_hilos) {
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
        } else if (acepta_hilos && opcion == "--hilos") {
            const Conteo hilos = leer_entero(valor);
            exigir(hilos >= 1 && hilos <= 4096, "Hilos fuera de limites");
            a.hilos = int(hilos);
        } else
            throw std::runtime_error("Opcion desconocida: " + opcion);
    }
    return a;
}

void imprimir_ayuda(const std::string& programa, bool acepta_hilos) {
    std::cout << "Uso: " << programa << " --config config_demostracion.ini [--datos datos] [--salida resultados] "
              << "[--escenarios N]" << (acepta_hilos ? " [--hilos P]" : "") << "\nPruebas: " << programa
              << " --self-test [--datos datos]\n";
}

Configuracion configuracion_efectiva(const Argumentos& a) {
    exigir(!a.config.empty(), "Indique --config. Use --help para instrucciones.");
    Configuracion c = leer_configuracion(a.config);
    if (a.escenarios) c.escenarios = a.escenarios;
    return c;
}

void preparar_salida(const Argumentos& a, const Configuracion& c) {
    exigir(!fs::exists(a.salida), "La carpeta de salida ya existe. Elija otra con --salida.");
    fs::create_directories(a.salida);
    fs::copy_file(a.config, a.salida / "config_usada.ini");
    std::ofstream m(a.salida / "parametros_efectivos.txt");
    m << "estado_datos=" << c.estado_datos << "\nanio_base=" << c.anio_base << "\nhorizonte=" << c.horizonte
      << "\nescenarios=" << c.escenarios << "\nsemilla=" << c.semilla << "\ntipo_mortalidad=" << c.tipo_mortalidad
      << "\nsigma_fecundidad=" << c.sigma_fecundidad << "\nsigma_mortalidad=" << c.sigma_mortalidad
      << "\nq100 desde configuracion; fila100 del CSV no aplicada"
         "\nDesagregacion uniforme entera; mortalidad constante en el tiempo"
         "\nBiblioteca C++: reproducibilidad exacta solo con mismo ejecutable/entorno\n";
}

void escribir_resultados(const fs::path& salida, const Configuracion& c, const Poblacion& N0,
                         const EscritorEscenarios& escritor, const Metricas& m, const std::string& version_texto,
                         const std::string& version_csv) {
    const std::vector<Conteo>& histograma = escritor.histograma();
    const Conteo con_inversion = escritor.con_inversion();

    // ---------------- Estimacion Monte Carlo ----------------
    // p(T = y) = frecuencia / R;  F(y) = acumulada / R  (R incluye escenarios sin inversion)
    std::ofstream dist(salida / "distribucion.csv");
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

    // ---------------- Resumen ----------------
    std::ofstream res(salida / "resumen.txt");
    res << std::setprecision(12) << "ESTADO: " << c.estado_datos << "\n";
    if (c.estado_datos == "DEMO_NO_VALIDADO")
        res << "Ejecucion ilustrativa con supuestos no confirmados. No es una prediccion validada del Peru.\n";
    res << "Version: " << version_texto << "\n"
        << "Poblacion inicial: " << poblacion_total(N0) << "\nMenores de 15: " << menores_15(N0)
        << "\n65 o mas: " << mayores_65(N0) << "\nEscenarios completados: " << c.escenarios
        << "\nHorizonte: " << c.horizonte << "\nCon inversion: " << con_inversion
        << "\nSin inversion: " << c.escenarios - con_inversion
        << "\nProbabilidad de inversion: " << double(con_inversion) / c.escenarios
        << "\nProbabilidad sin inversion: " << double(c.escenarios - con_inversion) / c.escenarios << "\n";
    if (con_inversion > 0)
        res << "Primer anio de inversion (escenarios con inversion): minimo " << anio_min << ", media "
            << double(suma_anios) / con_inversion << ", maximo " << anio_max << "\n";
    res << "Segundos simulacion y escritura de escenarios: " << m.segundos_simulacion
        << "\nSegundos hasta resumen: " << m.segundos_total << "\n";
    escribir_metricas_texto(res, m);
    histograma_texto(res, c.anio_base, histograma, c.escenarios);
    res.close();
    exigir(!res.fail(), "Error guardando resumen");

    // ---------------- Grafico generado por el ejecutable ----------------
    {
        std::ostringstream sub;
        sub << c.escenarios << " escenarios, horizonte " << c.horizonte << " anios, semilla " << c.semilla;
        if (hay_incertidumbre_macro(c)) sub << ", sigma_fec " << c.sigma_fecundidad << ", sigma_mort " << c.sigma_mortalidad;
        else sub << ", tasas fijas";
        histograma_svg(salida / "distribucion_anio.svg", c.anio_base, histograma, c.escenarios, sub.str());
    }
    escribir_metricas_csv(salida / "metricas.csv", m, version_csv);

    std::cout << "Completado: " << c.escenarios << " escenarios. Estado: " << c.estado_datos
              << "\nResultados en: " << salida.string() << "\nTiempo simulacion + escritura: " << m.segundos_simulacion
              << " s\n";
    escribir_metricas_texto(std::cout, m);
    histograma_texto(std::cout, c.anio_base, histograma, c.escenarios);
    std::cout << "Grafico: " << (salida / "distribucion_anio.svg").string() << "\n";
}
