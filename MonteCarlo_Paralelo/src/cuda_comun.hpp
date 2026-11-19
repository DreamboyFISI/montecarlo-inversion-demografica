// cuda_comun.hpp
// Utilidades compartidas por simulador_cuda y simulador_mpi_cuda (lado del anfitrion).
#pragma once

#include <cstdlib>
#include <stdexcept>
#include <string>
#include <vector>

#include "escenario.hpp"
#include "gpu.hpp"

inline void exigir_gpu(const char* error) {
    if (error) throw std::runtime_error(std::string("CUDA: ") + error);
}

// Convierte los datos del modelo a la estructura plana que se copia a la GPU.
inline DatosGpu a_datos_gpu(const DatosModelo& datos, const Configuracion& c, std::vector<double>& fecundidad) {
    DatosGpu g{};
    Conteo total = 0;
    for (int s = 0; s < 2; ++s)
        for (int a = 0; a < EDADES; ++a) {
            total += datos.N0[s][a];
            g.N0[s][a] = int(datos.N0[s][a]);
            g.q[s][a] = datos.q[s][a];
        }
    // Los conteos por celda viajan en 32 bits: ninguna celda puede superar a la poblacion total mas
    // los nacimientos del horizonte, que con este margen quedan muy por debajo de 2^31.
    exigir(total < 500000000LL, "CUDA: la poblacion inicial no cabe en conteos de 32 bits");
    g.p_femenino = c.p_femenino;
    g.u_recien_nacido[0] = c.u_recien_nacido[0];
    g.u_recien_nacido[1] = c.u_recien_nacido[1];
    g.sigma_fecundidad = c.sigma_fecundidad;
    g.sigma_mortalidad = c.sigma_mortalidad;
    g.semilla = c.semilla;
    g.horizonte = c.horizonte;
    fecundidad.resize(std::size_t(c.horizonte) * EDADES);
    for (int t = 0; t < c.horizonte; ++t)
        for (int a = 0; a < EDADES; ++a) fecundidad[std::size_t(t) * EDADES + a] = datos.fecundidad[t][a];
    return g;
}

inline int tamano_lote() {
    const char* texto = std::getenv("MC_LOTE");
    const Conteo lote = texto ? leer_entero(texto) : 262144;
    exigir(lote >= 1 && lote <= 16777216, "MC_LOTE fuera de limites");
    return int(lote);
}
