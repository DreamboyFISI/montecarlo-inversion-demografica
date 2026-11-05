// escenario.cpp
#include "escenario.hpp"

#include <algorithm>
#include <iomanip>
#include <random>

#include "modelo.hpp"

const char* const ENCABEZADO_TRAYECTORIA =
    "anio,poblacion_inicial,nacimientos,defunciones,poblacion_final,menores15,mayores65,lambda,balance\n";

DatosModelo cargar_datos_modelo(const std::filesystem::path& carpeta, const Configuracion& c) {
    DatosModelo d;
    d.N0 = cargar_poblacion_inicial(carpeta);
    d.q = cargar_mortalidad(carpeta, c);
    d.fecundidad = cargar_fecundidad(carpeta, c);
    return d;
}

bool hay_incertidumbre_macro(const Configuracion& c) {
    return c.sigma_fecundidad > 0.0 || c.sigma_mortalidad > 0.0;
}

ResultadoEscenario simular_escenario(Conteo r, const DatosModelo& d, const Configuracion& c, std::ostream* trayectoria) {
    ResultadoEscenario e;
    Poblacion N = d.N0;  // cada escenario parte de la misma poblacion inicial
    std::mt19937_64 generador(mezclar_semilla(c.semilla + std::uint64_t(r)));
    if (hay_inversion(N)) e.primer_paso = 0;  // tambien se revisa el estado inicial

    // Incertidumbre macro: dos multiplicadores por escenario (no por persona ni por anio).
    // Con sigma = 0 no se consume ningun numero aleatorio: la ejecucion es identica a la de referencia.
    const Tasas* q_r = &d.q;
    const std::vector<TasaFecundidad>* fecundidad_r = &d.fecundidad;
    Tasas q_esc;
    std::vector<TasaFecundidad> fecundidad_esc;
    if (hay_incertidumbre_macro(c)) {
        if (c.sigma_fecundidad > 0.0)
            e.factor_fecundidad = std::max(0.0, std::normal_distribution<double>(1.0, c.sigma_fecundidad)(generador));
        if (c.sigma_mortalidad > 0.0)
            e.factor_mortalidad = std::max(0.0, std::normal_distribution<double>(1.0, c.sigma_mortalidad)(generador));
        fecundidad_esc = d.fecundidad;
        for (auto& f : fecundidad_esc)
            for (double& v : f) v *= e.factor_fecundidad;
        q_esc = d.q;
        for (auto& sexo : q_esc)
            for (double& v : sexo) v = std::clamp(v * e.factor_mortalidad, 0.0, 1.0);
        q_r = &q_esc;
        fecundidad_r = &fecundidad_esc;
    }

    for (int t = 0; t < c.horizonte; ++t) {
        const Conteo antes = poblacion_total(N);
        const PasoAnual paso = simular_anio(N, *q_r, (*fecundidad_r)[t], c, generador);
        N = paso.poblacion;
        if (e.primer_paso < 0 && hay_inversion(N)) e.primer_paso = t + 1;
        // Se completa el horizonte aunque ya haya inversion: misma carga por escenario.

        if (trayectoria)
            *trayectoria << c.anio_base + t + 1 << ',' << antes << ',' << paso.nacimientos << ','
                         << paso.defunciones << ',' << poblacion_total(N) << ',' << menores_15(N) << ','
                         << mayores_65(N) << ',' << paso.lambda << ','
                         << (poblacion_total(N) - antes - paso.nacimientos + paso.defunciones) << '\n';
    }
    return e;
}

EscritorEscenarios::EscritorEscenarios(const std::filesystem::path& salida, const Configuracion& c)
    : c_(c), macro_(hay_incertidumbre_macro(c)), histograma_(c.horizonte + 1, 0) {
    escenarios_csv_.open(salida / "escenarios.csv");
    exigir(bool(escenarios_csv_), "No se puede escribir escenarios.csv");
    escenarios_csv_ << "escenario,ocurrio_inversion,primer_anio_inversion\n";
    if (macro_) {
        factores_csv_.open(salida / "factores_escenarios.csv");
        exigir(bool(factores_csv_), "No se puede escribir factores_escenarios.csv");
        factores_csv_ << "escenario,factor_fecundidad,factor_mortalidad\n" << std::setprecision(10);
    }
}

void EscritorEscenarios::agregar(Conteo r, const ResultadoEscenario& e) {
    if (macro_) factores_csv_ << r + 1 << ',' << e.factor_fecundidad << ',' << e.factor_mortalidad << '\n';
    escenarios_csv_ << r + 1 << ',' << (e.primer_paso >= 0 ? 1 : 0) << ',';
    if (e.primer_paso >= 0) {
        escenarios_csv_ << c_.anio_base + e.primer_paso;
        ++con_inversion_;
        ++histograma_[e.primer_paso];
    }
    escenarios_csv_ << '\n';
}

void EscritorEscenarios::cerrar() {
    escenarios_csv_.close();
    exigir(!escenarios_csv_.fail(), "Fallo al terminar escritura");
    if (macro_) {
        factores_csv_.close();
        exigir(!factores_csv_.fail(), "Fallo al escribir factores");
    }
}
