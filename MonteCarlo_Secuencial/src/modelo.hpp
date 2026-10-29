// modelo.hpp
// Nucleo demografico: un paso anual estocastico y funciones de resumen.
// Es la parte que se paralelizara en el Sprint 3 (OpenMP / MPI).
#pragma once

#include <cstdint>
#include <random>

#include "datos.hpp"

// Resultado de un anio simulado.
struct PasoAnual {
    Poblacion poblacion{};   // N(t+1)
    Conteo nacimientos = 0;  // B(t)
    Conteo defunciones = 0;  // D(t), incluye muertes de nacidos en el anio
    double lambda = 0.0;     // nacimientos esperados
};

// Suma de todas las edades y ambos sexos: P(t).
Conteo poblacion_total(const Poblacion& N);

// Suma de las edades [desde, hasta] de ambos sexos.
Conteo poblacion_entre(const Poblacion& N, int desde, int hasta);

// Menores de 15 (J) y personas de 65 o mas (A).
inline Conteo menores_15(const Poblacion& N) { return poblacion_entre(N, 0, 14); }
inline Conteo mayores_65(const Poblacion& N) { return poblacion_entre(N, 65, 100); }

// Evento de inversion: A > J. El empate no cuenta.
inline bool hay_inversion(const Poblacion& N) { return mayores_65(N) > menores_15(N); }

// Semilla reproducible por escenario (mezcla splitmix64).
std::uint64_t mezclar_semilla(std::uint64_t x);

// Binomial(n, p). No consume numeros aleatorios en los casos triviales n=0, p=0 o p=1.
Conteo sorteo_binomial(Conteo n, double p, std::mt19937_64& generador);

// Un anio completo:
//   lambda = sum_{a=15..49} N[F][a] * f[a]
//   B ~ Poisson(lambda);  B_F ~ Binomial(B, pF);  B_H = B - B_F
//   D[s][a] ~ Binomial(N[s][a], q[s][a]);  S = N - D;  envejecer S un anio (99 y 100+ -> 100+)
//   U[s] ~ Binomial(B_s, u[s]) pasan a edad 0
// Verifica P(t+1) = P(t) + B - D y que no haya conteos negativos.
PasoAnual simular_anio(const Poblacion& N, const Tasas& q, const TasaFecundidad& f, const Configuracion& c,
                       std::mt19937_64& generador);
