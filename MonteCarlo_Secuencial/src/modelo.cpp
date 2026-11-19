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

namespace {

// Uniforme en [0, 1) con 53 bits.
inline double uniforme(std::mt19937_64& generador) { return double(generador() >> 11) * 0x1.0p-53; }

// Correccion de Stirling: log(k!) - [log(sqrt(2 pi)) + (k + 1/2) log(k + 1) - (k + 1)].
inline double cola_stirling(double k) {
    static const double tabla[10] = {0.08106146679532726, 0.04134069595540929, 0.02767792568499834,
                                     0.02079067210376509, 0.01664469118982119, 0.01387612882307075,
                                     0.01189670994589177, 0.01041126526197209, 0.009255462182712733,
                                     0.008330563433362871};
    if (k <= 9) return tabla[int(k)];
    const double k1 = (k + 1) * (k + 1);
    return (1.0 / 12 - (1.0 / 360 - 1.0 / 1260 / k1) / k1) / (k + 1);
}

// Inversion secuencial de la funcion de distribucion. Requiere p <= 0.5 y n*p < 10 (q^n no desborda).
Conteo binomial_inversion(Conteo n, double p, std::mt19937_64& generador) {
    const double s = p / (1 - p), a = double(n + 1) * s;
    double r = std::exp(double(n) * std::log1p(-p));  // P(X = 0)
    double u = uniforme(generador);
    Conteo x = 0;
    while (u > r && x < n) {
        u -= r;
        ++x;
        r *= a / double(x) - s;  // P(X = x) = P(X = x-1) * (n-x+1)/x * p/q
    }
    return x;
}

// BTRS: rechazo transformado con "squeeze" (Hormann, 1993). Requiere p <= 0.5 y n*p >= 10.
// En ~86 % de los sorteos acepta con dos uniformes y sin evaluar logaritmos.
Conteo binomial_btrs(Conteo n, double p, std::mt19937_64& generador) {
    const double N = double(n);
    const double desv = std::sqrt(N * p * (1 - p));
    const double b = 1.15 + 2.53 * desv;
    const double a = -0.0873 + 0.0248 * b + 0.01 * p;
    const double c = N * p + 0.5;
    const double v_r = 0.92 - 4.2 / b;
    for (;;) {
        const double u = uniforme(generador) - 0.5;
        double v = uniforme(generador);
        const double us = 0.5 - std::fabs(u);
        const double k = std::floor((2 * a / us + b) * u + c);
        if (us >= 0.07 && v <= v_r) return Conteo(k);  // region central: aceptacion inmediata
        if (!(k >= 0 && k <= N)) continue;
        // Camino lento (~14 % de los sorteos): comparacion con la funcion de masa.
        const double r = p / (1 - p);
        const double alfa = (2.83 + 5.1 / b) * desv;
        const double m = std::floor((N + 1) * p);
        v = std::log(v * alfa / (a / (us * us) + b));
        const double cota = (m + 0.5) * std::log((m + 1) / (r * (N - m + 1))) +
                            (N + 1) * std::log((N - m + 1) / (N - k + 1)) +
                            (k + 0.5) * std::log(r * (N - k + 1) / (k + 1)) + cola_stirling(m) +
                            cola_stirling(N - m) - cola_stirling(k) - cola_stirling(N - k);
        if (v <= cota) return Conteo(k);
    }
}

}  // namespace

Conteo sorteo_binomial_rapido(Conteo n, double p, std::mt19937_64& generador) {
    if (n == 0 || p == 0) return 0;
    if (p == 1) return n;
    if (p > 0.5) return n - sorteo_binomial_rapido(n, 1 - p, generador);
    return double(n) * p < 10.0 ? binomial_inversion(n, p, generador) : binomial_btrs(n, p, generador);
}

PasoAnual simular_anio(const Poblacion& N, const Tasas& q, const TasaFecundidad& f, const Configuracion& c,
                       std::mt19937_64& generador) {
    PasoAnual paso{};
    const auto binomial = c.muestreo_rapido ? sorteo_binomial_rapido : sorteo_binomial;

    // 1. Nacimientos esperados y simulados (exposicion: mujeres al inicio del anio).
    for (int a = 15; a <= 49; ++a) paso.lambda += N[MUJERES][a] * f[a];
    exigir(std::isfinite(paso.lambda) && paso.lambda <= 1e12, "Lambda no valida");
    paso.nacimientos = paso.lambda == 0 ? 0 : std::poisson_distribution<Conteo>(paso.lambda)(generador);

    // 2. Sexo de los nacimientos.
    const Conteo nacidas = binomial(paso.nacimientos, c.p_femenino, generador);
    const Conteo nacidos[2] = {paso.nacimientos - nacidas, nacidas};

    // 3. Defunciones, envejecimiento y supervivencia de los nacidos, por sexo.
    //    (El orden de los sorteos se mantiene fijo para que la ejecucion sea reproducible.)
    for (int s = 0; s < 2; ++s) {
        for (int a = 0; a <= 100; ++a) {
            const Conteo muertes = binomial(N[s][a], q[s][a], generador);
            paso.defunciones += muertes;
            // Los supervivientes de edad a pasan a a+1; los de 99 y 100+ quedan en 100+.
            paso.poblacion[s][std::min(a + 1, 100)] += N[s][a] - muertes;
        }
        const Conteo vivos_al_cierre = binomial(nacidos[s], c.u_recien_nacido[s], generador);
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
