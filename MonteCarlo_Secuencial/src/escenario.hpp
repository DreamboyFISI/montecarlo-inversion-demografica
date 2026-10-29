// escenario.hpp
// Un escenario Monte Carlo completo (H anios) y la escritura ordenada de sus resultados.
// Es la unidad de trabajo que reparten las versiones paralelas: cada escenario r usa su propio
// generador con semilla mezclar_semilla(semilla + r), asi que su resultado no depende de que hilo
// o proceso lo ejecute ni en que orden. Por eso secuencial, OpenMP y MPI producen los mismos CSV.
#pragma once

#include <filesystem>
#include <fstream>
#include <ostream>
#include <vector>

#include "datos.hpp"

// Datos de entrada compartidos (solo lectura) por todos los escenarios.
struct DatosModelo {
    Poblacion N0{};                           // poblacion inicial
    Tasas q{};                                // probabilidad anual de muerte
    std::vector<TasaFecundidad> fecundidad;   // una fila por paso t = 0..H-1
};

DatosModelo cargar_datos_modelo(const std::filesystem::path& carpeta, const Configuracion& c);

struct ResultadoEscenario {
    int primer_paso = -1;            // t del primer anio con A > J (0 = estado inicial); -1 si no ocurrio
    double factor_fecundidad = 1.0;  // multiplicadores macro sorteados (1 si sigma = 0)
    double factor_mortalidad = 1.0;
};

// true si la configuracion pide incertidumbre macro (sigma_fecundidad > 0 o sigma_mortalidad > 0).
bool hay_incertidumbre_macro(const Configuracion& c);

// Simula el escenario r (0-based). Si trayectoria no es nulo, escribe ahi una fila CSV por anio
// (columnas de trayectoria_escenario_1.csv, sin encabezado).
ResultadoEscenario simular_escenario(Conteo r, const DatosModelo& d, const Configuracion& c, std::ostream* trayectoria);

// Encabezado de trayectoria_escenario_1.csv.
extern const char* const ENCABEZADO_TRAYECTORIA;

// Escribe escenarios.csv (y factores_escenarios.csv si hay incertidumbre macro) y acumula el
// histograma. Los resultados deben agregarse en orden r = 0, 1, 2, ...
class EscritorEscenarios {
public:
    EscritorEscenarios(const std::filesystem::path& salida, const Configuracion& c);
    void agregar(Conteo r, const ResultadoEscenario& e);
    void cerrar();  // cierra los archivos y verifica que la escritura no fallo

    // histograma[t] = escenarios cuya primera inversion ocurre en anio_base + t
    const std::vector<Conteo>& histograma() const { return histograma_; }
    Conteo con_inversion() const { return con_inversion_; }

private:
    const Configuracion& c_;
    bool macro_;
    std::ofstream escenarios_csv_;
    std::ofstream factores_csv_;
    std::vector<Conteo> histograma_;
    Conteo con_inversion_ = 0;
};
