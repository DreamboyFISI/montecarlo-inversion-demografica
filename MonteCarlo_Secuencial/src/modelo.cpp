// modelo.cpp
#include "modelo.hpp"

#include <algorithm>
#include <cmath>

Conteo poblacion_total(const Poblacion& N) {
    Conteo total = 0;
    for (const auto& sexo : N)
        for (const Conteo n : sexo) total += n;
    return total;
}

Conteo poblacion_entre(const Poblacion& N, int desde, int hasta) {
    Conteo total = 0;
    for (const auto& sexo : N)
        for (int a = desde; a <= hasta; ++a) total += sexo[a];
    return total;
}

std::uint64_t mezclar_semilla(std::uint64_t x) {
    x += 0x9e3779b97f4a7c15ULL;
    x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
    x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
    return x ^ (x >> 31);
}

Conteo sorteo_binomial(Conteo n, double p, std::mt19937_64& generador) {
    if (n == 0 || p == 0) return 0;
    if (p == 1) return n;
    return std::binomial_distribution<Conteo>(n, p)(generador);
}

PasoAnual simular_anio(const Poblacion& N, const Tasas& q, const TasaFecundidad& f, const Configuracion& c,
                       std::mt19937_64& generador) {
    PasoAnual paso{};

    // 1. Nacimientos esperados y simulados (exposicion: mujeres al inicio del anio).
    for (int a = 15; a <= 49; ++a) paso.lambda += N[MUJERES][a] * f[a];
    exigir(std::isfinite(paso.lambda) && paso.lambda <= 1e12, "Lambda no valida");
    paso.nacimientos = paso.lambda == 0 ? 0 : std::poisson_distribution<Conteo>(paso.lambda)(generador);

    // 2. Sexo de los nacimientos.
    const Conteo nacidas = sorteo_binomial(paso.nacimientos, c.p_femenino, generador);
    const Conteo nacidos[2] = {paso.nacimientos - nacidas, nacidas};

    // 3. Defunciones, envejecimiento y supervivencia de los nacidos, por sexo.
    //    (El orden de los sorteos se mantiene fijo para que la ejecucion sea reproducible.)
    for (int s = 0; s < 2; ++s) {
        for (int a = 0; a <= 100; ++a) {
            const Conteo muertes = sorteo_binomial(N[s][a], q[s][a], generador);
            paso.defunciones += muertes;
            // Los supervivientes de edad a pasan a a+1; los de 99 y 100+ quedan en 100+.
            paso.poblacion[s][std::min(a + 1, 100)] += N[s][a] - muertes;
        }
        const Conteo vivos_al_cierre = sorteo_binomial(nacidos[s], c.u_recien_nacido[s], generador);
        paso.poblacion[s][0] = vivos_al_cierre;
        paso.defunciones += nacidos[s] - vivos_al_cierre;
    }

    // 4. Controles: balance exacto y conteos no negativos.
    exigir(poblacion_total(paso.poblacion) == poblacion_total(N) + paso.nacimientos - paso.defunciones,
           "Balance poblacional inconsistente");
    for (const auto& sexo : paso.poblacion)
        for (const Conteo n : sexo) exigir(n >= 0, "Poblacion negativa");
    return paso;
}
