// configuracion.hpp
// Parametros de la simulacion leidos desde un archivo clave=valor (.ini).
#pragma once

#include <cstdint>
#include <filesystem>
#include <string>

#include "utilidades.hpp"

struct Configuracion {
    int anio_base = 0;              // anio del estado inicial (supuesto: el CSV no lo indica)
    int horizonte = 0;              // numero de pasos anuales a simular
    Conteo escenarios = 0;          // R: numero de trayectorias Monte Carlo
    std::uint64_t semilla = 0;      // semilla maestra
    std::string estado_datos;       // DEMO_NO_VALIDADO o PARAMETROS_DOCUMENTADOS
    std::string tipo_mortalidad;    // como interpretar mortalidad_peru.csv
    double p_femenino = 0.0;        // pF: proporcion femenina al nacer
    double u_recien_nacido[2] = {0.0, 0.0};  // u[s]: supervivencia de nacidos hasta el cierre del anio
    double q_100[2] = {0.0, 0.0};   // probabilidad anual de muerte del grupo abierto 100+
    // Incertidumbre macro por escenario (opcional; 0 = tasas fijas, ejecucion identica a la de referencia).
    // En cada escenario se sortea factor_fec ~ N(1, sigma_fecundidad) y factor_mort ~ N(1, sigma_mortalidad)
    // y se multiplican f(a,y) y q(a,s) por ellos durante los 40 anios.
    double sigma_fecundidad = 0.0;
    double sigma_mortalidad = 0.0;
    std::filesystem::path archivo;  // ruta del .ini leido
};

// Lee y valida el archivo. Rechaza claves desconocidas, duplicadas o faltantes.
Configuracion leer_configuracion(const std::filesystem::path& archivo);
