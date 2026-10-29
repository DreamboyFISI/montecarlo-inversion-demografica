// datos.hpp
// Lectura de los tres CSV y su conversion a las estructuras del modelo.
#pragma once

#include <array>
#include <filesystem>
#include <string>
#include <vector>

#include "configuracion.hpp"

constexpr int EDADES = 101;  // edades 0..99 y grupo abierto 100+ (indice 100)
constexpr int HOMBRES = 0;
constexpr int MUJERES = 1;

// N[s][a]: personas de sexo s y edad a al inicio del anio.
using Poblacion = std::array<std::array<Conteo, EDADES>, 2>;
// q[s][a]: probabilidad anual de muerte.
using Tasas = std::array<std::array<double, EDADES>, 2>;
// f[a]: nacimientos esperados por mujer de edad a en un anio calendario.
using TasaFecundidad = std::array<double, EDADES>;

using FilasCsv = std::vector<std::vector<std::string>>;

// Lee un CSV separado por comas; exige el mismo numero de columnas en todas las filas.
FilasCsv leer_csv(const std::filesystem::path& archivo);

// Carga poblacion_inicial_peru.csv y reparte cada grupo quinquenal en 5 edades simples
// (reparto uniforme entero: G/5 a cada edad y el resto a las primeras). 100+ queda abierto.
Poblacion cargar_poblacion_inicial(const std::filesystem::path& carpeta);

// Carga mortalidad_peru.csv y obtiene q anual segun c.tipo_mortalidad.
// La fila 100 del CSV no se usa: q(100+) viene de la configuracion.
Tasas cargar_mortalidad(const std::filesystem::path& carpeta, const Configuracion& c);

// Carga fecundidad_peru.csv y devuelve, para cada paso t = 0..horizonte-1,
// las tasas del quinquenio que contiene al anio anio_base + t.
std::vector<TasaFecundidad> cargar_fecundidad(const std::filesystem::path& carpeta, const Configuracion& c);
