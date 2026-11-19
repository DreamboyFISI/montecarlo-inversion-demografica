// nucleo_cuda.hpp
// Nucleo del escenario Monte Carlo para la version CUDA: un escenario completo en una sola funcion,
// sin memoria dinamica, excepciones ni biblioteca estandar, para que pueda ejecutarla un hilo de GPU.
// Las funciones son __host__ __device__: el mismo codigo corre en la GPU (gpu.cu) y en la CPU
// (main_cuda.cpp lo usa para comprobar que la GPU calcula lo mismo que la CPU).
//
// Es el mismo modelo de modelo.cpp / escenario.cpp en su modo de muestreo rapido:
//   - binomial por inversion (n*p < 10) o rechazo transformado BTRS (Hormann, 1993), con las
//     propuestas en precision simple y la funcion de masa en doble precision;
//   - Poisson exacta por rechazo transformado PTRS (Hormann, 1993);
//   - el escenario termina en su primera inversion (salvo cuando se pide la trayectoria).
// Diferencia con la CPU: el generador. std::mt19937_64 no existe en la GPU (y sus 2,5 KiB de estado
// por hilo serian un desperdicio), asi que cada escenario usa un xoroshiro128++ (16 bytes de estado)
// sembrado con splitmix64(semilla + r). Por eso los resultados son estadisticamente equivalentes a
// los de la CPU, no identicos escenario a escenario.
#pragma once

#include <cmath>
#include <cstdint>

#ifdef __CUDACC__
#define MC_HD __host__ __device__
#else
#define MC_HD
#endif

constexpr int MC_EDADES = 101;  // edades 0..99 y grupo abierto 100+
constexpr int MC_HOMBRES = 0;
constexpr int MC_MUJERES = 1;

// Datos de solo lectura compartidos por todos los escenarios (se copian una vez a la GPU).
// La fecundidad va aparte: f[t * MC_EDADES + a], una fila por paso t = 0..horizonte-1.
struct DatosGpu {
    int N0[2][MC_EDADES];     // poblacion inicial (cabe en 32 bits: se comprueba al cargar)
    double q[2][MC_EDADES];   // probabilidad anual de muerte
    double p_femenino;
    double u_recien_nacido[2];
    double sigma_fecundidad;
    double sigma_mortalidad;
    std::uint64_t semilla;
    int horizonte;
};

// Una fila de trayectoria_escenario_1.csv.
struct FilaTraza {
    long long antes, nacimientos, defunciones, despues, menores15, mayores65, balance;
    double lambda;
};

// ---------------------------------------------------------------------------------------------
// Generador: xoroshiro128++ (Blackman y Vigna, 2019), periodo 2^128 - 1.
// ---------------------------------------------------------------------------------------------
struct McGenerador {
    std::uint64_t s0, s1;
};

MC_HD inline std::uint64_t mc_splitmix64(std::uint64_t& x) {
    x += 0x9e3779b97f4a7c15ULL;
    std::uint64_t z = x;
    z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
    z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
    return z ^ (z >> 31);
}

// Semilla del escenario r: se mezcla semilla + r y de ahi salen las dos palabras de estado.
MC_HD inline McGenerador mc_sembrar(std::uint64_t semilla, std::uint64_t r) {
    std::uint64_t x = semilla + r;
    x = mc_splitmix64(x);
    McGenerador g;
    g.s0 = mc_splitmix64(x);
    g.s1 = mc_splitmix64(x);
    if ((g.s0 | g.s1) == 0) g.s0 = 1;  // el estado nulo es el unico no valido
    return g;
}

MC_HD inline std::uint64_t mc_rotl(std::uint64_t x, int k) { return (x << k) | (x >> (64 - k)); }

MC_HD inline std::uint64_t mc_siguiente(McGenerador& g) {
    const std::uint64_t s0 = g.s0;
    std::uint64_t s1 = g.s1;
    const std::uint64_t salida = mc_rotl(s0 + s1, 17) + s0;
    s1 ^= s0;
    g.s0 = mc_rotl(s0, 49) ^ s1 ^ (s1 << 21);
    g.s1 = mc_rotl(s1, 28);
    return salida;
}

// Uniforme en [0, 1) con 53 bits.
MC_HD inline double mc_uniforme(McGenerador& g) { return double(mc_siguiente(g) >> 11) * 0x1.0p-53; }

// Normal estandar (Box-Muller; se usa solo dos veces por escenario).
MC_HD inline double mc_normal(McGenerador& g) {
    const double u1 = 1.0 - mc_uniforme(g);  // (0, 1]: el logaritmo es finito
    const double u2 = mc_uniforme(g);
    return std::sqrt(-2.0 * std::log(u1)) * std::cos(6.283185307179586 * u2);
}

// ---------------------------------------------------------------------------------------------
// Binomial(n, p). Mismos algoritmos que sorteo_binomial_rapido (modelo.cpp): inversion si n*p < 10
// y rechazo transformado BTRS (Hormann, 1993) en otro caso, pero organizados para la GPU:
//
//   - Las GPU de consumo rinden muy poco en doble precision. La propuesta de BTRS y su aceptacion
//     inmediata (~86 % de los sorteos) se calculan en precision simple, con 24 bits por uniforme.
//   - La comparacion con la funcion de masa (camino lento, ~14 %) necesita doble precision. Se separa
//     en mc_btrs_aceptar para que el escenario pueda aplazarla y evaluarla agrupada (ver
//     mc_simular_escenario): los 32 hilos de un "warp" ejecutan la misma instruccion, asi que una rama
//     lenta dentro del bucle de edades la pagarian los 32 en cada sorteo.
//
// Precision: la funcion de masa se evalua en doble precision; las propuestas se generan en precision
// simple, lo que limita la resolucion de cada clase a ~1e-4 relativo (en la CPU es ~1e-13).
// ---------------------------------------------------------------------------------------------
// Correccion de Stirling: log(k!) - [log(sqrt(2 pi)) + (k + 1/2) log(k + 1) - (k + 1)].
MC_HD inline double mc_cola_stirling(double k) {
    if (k <= 9) {
        switch (int(k)) {
            case 0: return 0.08106146679532726;
            case 1: return 0.04134069595540929;
            case 2: return 0.02767792568499834;
            case 3: return 0.02079067210376509;
            case 4: return 0.01664469118982119;
            case 5: return 0.01387612882307075;
            case 6: return 0.01189670994589177;
            case 7: return 0.01041126526197209;
            case 8: return 0.009255462182712733;
            default: return 0.008330563433362871;
        }
    }
    const double k1 = (k + 1) * (k + 1);
    return (1.0 / 12 - (1.0 / 360 - 1.0 / 1260 / k1) / k1) / (k + 1);
}

// Inversion secuencial. Requiere p <= 0.5 y n*p < 10.
MC_HD inline int mc_binomial_inversion(int n, double p, McGenerador& g) {
    const double s = p / (1 - p), a = double(n + 1) * s;
    double r = std::exp(double(n) * std::log1p(-p));  // P(X = 0)
    double u = mc_uniforme(g);
    int x = 0;
    while (u > r && x < n) {
        u -= r;
        ++x;
        r *= a / double(x) - s;
    }
    return x;
}

// Constantes de BTRS en precision simple. La propuesta y la aceptacion las calculan igual.
struct McBtrs {
    float desv, b, a;
};
MC_HD inline McBtrs mc_btrs_constantes(int n, float p) {
    McBtrs c;
    c.desv = std::sqrt(float(n) * p * (1.0f - p));
    c.b = 1.15f + 2.53f * c.desv;
    c.a = -0.0873f + 0.0248f * c.b + 0.01f * p;
    return c;
}

// Candidato de BTRS pendiente de comparar con la funcion de masa.
struct McCandidato {
    float us, v;
    int k;
};

// Genera propuestas hasta que una se acepta de inmediato (devuelve true y deja el valor en cand.k) o
// hasta que una necesita la comparacion con la funcion de masa (devuelve false y deja el candidato).
// Requiere p <= 0.5 y n*p >= 10.
MC_HD inline bool mc_btrs_proponer(int n, float p, McGenerador& g, McCandidato& cand) {
    const McBtrs c = mc_btrs_constantes(n, p);
    const float centro = float(n) * p + 0.5f;
    const float v_r = 0.92f - 4.2f / c.b;
    for (;;) {
        // Un solo numero de 64 bits da los dos uniformes de 24 bits.
        const std::uint64_t bits = mc_siguiente(g);
        const float u = float(bits >> 40) * 0x1.0p-24f - 0.5f;
        const float v = float((bits >> 16) & 0xFFFFFFu) * 0x1.0p-24f;
        const float us = 0.5f - std::fabs(u);
        const float k = std::floor((2.0f * c.a / us + c.b) * u + centro);
        if (!(k >= 0.0f && k <= float(n))) continue;
        cand.k = int(k);
        if (us >= 0.07f && v <= v_r) return true;  // region central: aceptacion inmediata
        cand.us = us;
        cand.v = v;
        return false;
    }
}

// Comparacion con la funcion de masa (doble precision). p es la probabilidad exacta, p <= 0.5.
MC_HD inline bool mc_btrs_aceptar(int n, double p, const McCandidato& cand) {
    const McBtrs c = mc_btrs_constantes(n, float(p));
    const double N = double(n), k = double(cand.k), us = double(cand.us);
    const double b = double(c.b), a = double(c.a);
    const double r = p / (1 - p);
    const double alfa = (2.83 + 5.1 / b) * double(c.desv);
    const double m = std::floor((N + 1) * p);
    const double v = std::log(double(cand.v) * alfa / (a / (us * us) + b));
    const double cota = (m + 0.5) * std::log((m + 1) / (r * (N - m + 1))) +
                        (N + 1) * std::log((N - m + 1) / (N - k + 1)) +
                        (k + 0.5) * std::log(r * (N - k + 1) / (k + 1)) + mc_cola_stirling(m) +
                        mc_cola_stirling(N - m) - mc_cola_stirling(k) - mc_cola_stirling(N - k);
    return v <= cota;
}

// Clasificacion de un sorteo Binomial(n, p) y reduccion a p <= 0.5.
//   TRIVIAL: el resultado ya esta en `valor` (n = 0, p = 0 o p = 1).
//   INVERSION / BTRS: sortear X ~ Binomial(n, p_min); el resultado es X, o n - X si `reflejado`.
enum McCaso { MC_TRIVIAL, MC_INVERSION, MC_BTRS };
struct McSorteo {
    McCaso caso;
    bool reflejado;
    double p_min;
    int valor;
};
MC_HD inline McSorteo mc_clasificar(int n, double p) {
    McSorteo s;
    s.reflejado = false;
    s.p_min = p;
    s.valor = 0;
    s.caso = MC_TRIVIAL;
    if (n == 0 || p <= 0) return s;
    if (p >= 1) {
        s.valor = n;
        return s;
    }
    if (p > 0.5) {
        s.reflejado = true;
        s.p_min = 1 - p;
    }
    s.caso = double(n) * s.p_min < 10.0 ? MC_INVERSION : MC_BTRS;
    return s;
}

// Binomial(n, p) completa, sin aplazar nada (sexo de los nacimientos y pruebas).
MC_HD inline int mc_binomial(int n, double p, McGenerador& g) {
    const McSorteo s = mc_clasificar(n, p);
    if (s.caso == MC_TRIVIAL) return s.valor;
    int x;
    if (s.caso == MC_INVERSION) {
        x = mc_binomial_inversion(n, s.p_min, g);
    } else {
        McCandidato cand;
        while (!mc_btrs_proponer(n, float(s.p_min), g, cand) && !mc_btrs_aceptar(n, s.p_min, cand)) {
        }
        x = cand.k;
    }
    return s.reflejado ? n - x : x;
}

// ---------------------------------------------------------------------------------------------
// Poisson(lambda) exacta: producto de uniformes si lambda < 10, PTRS (Hormann, 1993) en otro caso.
// ---------------------------------------------------------------------------------------------
MC_HD inline int mc_poisson(double lambda, McGenerador& g) {
    if (lambda <= 0) return 0;
    if (lambda < 10.0) {
        const double limite = std::exp(-lambda);
        double producto = mc_uniforme(g);
        int k = 0;
        while (producto > limite) {
            ++k;
            producto *= mc_uniforme(g);
        }
        return k;
    }
    const double raiz = std::sqrt(lambda), log_lambda = std::log(lambda);
    const double b = 0.931 + 2.53 * raiz;
    const double a = -0.059 + 0.02483 * b;
    const double inv_alfa = 1.1239 + 1.1328 / (b - 3.4);
    const double v_r = 0.9277 - 3.6224 / (b - 2);
    for (;;) {
        const double u = mc_uniforme(g) - 0.5;
        const double v = mc_uniforme(g);
        const double us = 0.5 - std::fabs(u);
        const double k = std::floor((2 * a / us + b) * u + lambda + 0.43);
        if (us >= 0.07 && v <= v_r) return int(k);
        if (!(k >= 0) || (us < 0.013 && v > us)) continue;
        if (std::log(v) + std::log(inv_alfa) - std::log(a / (us * us) + b) <=
            -lambda + k * log_lambda - std::lgamma(k + 1))
            return int(k);
    }
}

// ---------------------------------------------------------------------------------------------
// Escenario completo.
// ---------------------------------------------------------------------------------------------
MC_HD inline long long mc_suma(const int (*N)[MC_EDADES], int desde, int hasta) {
    long long total = 0;
    for (int s = 0; s < 2; ++s)
        for (int a = desde; a <= hasta; ++a) total += N[s][a];
    return total;
}

// Sorteos binomiales de un anio: 2 x 101 celdas de defunciones y la supervivencia de los nacidos
// de cada sexo.
constexpr int MC_SORTEOS = 2 * MC_EDADES + 2;

// Simula el escenario r (0-based). Devuelve el paso t de la primera inversion (0 = estado inicial)
// o -1 si no ocurre en el horizonte, y deja en factor_fec / factor_mort los multiplicadores sorteados.
// Si traza no es nulo, simula el horizonte completo y escribe ahi una fila por anio.
MC_HD inline int mc_simular_escenario(const DatosGpu& d, const double* f, std::uint64_t r, double* factor_fec,
                                      double* factor_mort, FilaTraza* traza) {
    McGenerador g = mc_sembrar(d.semilla, r);
    int N[2][MC_EDADES];
    for (int s = 0; s < 2; ++s)
        for (int a = 0; a < MC_EDADES; ++a) N[s][a] = d.N0[s][a];

    // Incertidumbre macro: dos multiplicadores por escenario.
    double ff = 1.0, fm = 1.0;
    if (d.sigma_fecundidad > 0.0) ff = std::fmax(0.0, 1.0 + d.sigma_fecundidad * mc_normal(g));
    if (d.sigma_mortalidad > 0.0) fm = std::fmax(0.0, 1.0 + d.sigma_mortalidad * mc_normal(g));
    *factor_fec = ff;
    *factor_mort = fm;

    int primer_paso = mc_suma(N, 65, 100) > mc_suma(N, 0, 14) ? 0 : -1;
    for (int t = 0; t < d.horizonte; ++t) {
        if (!traza && primer_paso >= 0) break;  // el resultado no depende de los anios posteriores
        const long long antes = traza ? mc_suma(N, 0, 100) : 0;

        // 1. Nacimientos (exposicion: mujeres al inicio del anio) y su sexo.
        const double* ft = f + std::size_t(t) * MC_EDADES;
        double lambda = 0.0;
        for (int a = 15; a <= 49; ++a) lambda += N[MC_MUJERES][a] * (ft[a] * ff);
        const int nacimientos = mc_poisson(lambda, g);
        const int nacidas = mc_binomial(nacimientos, d.p_femenino, g);
        const int nacidos[2] = {nacimientos - nacidas, nacidas};

        // 2. Los 204 sorteos binomiales del anio. Sorteo i < 202: defunciones de la celda (sexo, edad);
        //    i = 202, 203: nacidos de cada sexo que NO llegan vivos al cierre del anio.
        //    Primera pasada: cada sorteo se resuelve si su propuesta se acepta de inmediato; si no,
        //    el candidato queda pendiente. Segunda pasada: se resuelven los pendientes, una comparacion
        //    en doble precision por vuelta. Asi la rama lenta se ejecuta agrupada (~30 a 50 vueltas por
        //    anio) en vez de interrumpir cada uno de los 204 sorteos.
        int resultado[MC_SORTEOS];
        unsigned char pendiente[MC_SORTEOS];
        McCandidato candidato[MC_SORTEOS];
        int pendientes = 0;
        for (int i = 0; i < MC_SORTEOS; ++i) {
            const bool celda = i < 2 * MC_EDADES;
            const int s = celda ? i / MC_EDADES : i - 2 * MC_EDADES;
            const int n = celda ? N[s][i - s * MC_EDADES] : nacidos[s];
            const double p = celda ? std::fmin(d.q[s][i - s * MC_EDADES] * fm, 1.0) : 1.0 - d.u_recien_nacido[s];
            const McSorteo caso = mc_clasificar(n, p);
            if (caso.caso == MC_TRIVIAL) {
                resultado[i] = caso.valor;
            } else if (caso.caso == MC_INVERSION) {
                const int x = mc_binomial_inversion(n, caso.p_min, g);
                resultado[i] = caso.reflejado ? n - x : x;
            } else {
                McCandidato cand;
                if (mc_btrs_proponer(n, float(caso.p_min), g, cand)) {
                    resultado[i] = caso.reflejado ? n - cand.k : cand.k;
                } else {
                    pendiente[pendientes] = (unsigned char)i;
                    candidato[pendientes] = cand;
                    ++pendientes;
                }
            }
        }
        for (int j = 0; j < pendientes;) {
            const int i = pendiente[j];
            const bool celda = i < 2 * MC_EDADES;
            const int s = celda ? i / MC_EDADES : i - 2 * MC_EDADES;
            const int n = celda ? N[s][i - s * MC_EDADES] : nacidos[s];
            const double p = celda ? std::fmin(d.q[s][i - s * MC_EDADES] * fm, 1.0) : 1.0 - d.u_recien_nacido[s];
            const McSorteo caso = mc_clasificar(n, p);
            // Si el candidato se rechaza se propone otro: o se acepta de inmediato o queda para la
            // vuelta siguiente en la misma posicion j.
            if (mc_btrs_aceptar(n, caso.p_min, candidato[j]) ||
                mc_btrs_proponer(n, float(caso.p_min), g, candidato[j])) {
                resultado[i] = caso.reflejado ? n - candidato[j].k : candidato[j].k;
                ++j;
            }
        }

        // 3. Envejecimiento: los supervivientes de edad a pasan a a+1; 99 y 100+ quedan en 100+.
        long long defunciones = 0;
        for (int s = 0; s < 2; ++s) {
            const int* muertes = resultado + s * MC_EDADES;
            const int abierto = (N[s][MC_EDADES - 1] - muertes[MC_EDADES - 1]) +
                                (N[s][MC_EDADES - 2] - muertes[MC_EDADES - 2]);
            defunciones += muertes[MC_EDADES - 1] + muertes[MC_EDADES - 2];
            for (int a = MC_EDADES - 3; a >= 0; --a) {
                N[s][a + 1] = N[s][a] - muertes[a];
                defunciones += muertes[a];
            }
            N[s][MC_EDADES - 1] = abierto;
            const int no_sobreviven = resultado[2 * MC_EDADES + s];
            N[s][0] = nacidos[s] - no_sobreviven;
            defunciones += no_sobreviven;
        }

        // 4. Evento de inversion: A > J (el empate no cuenta).
        const long long menores = mc_suma(N, 0, 14), mayores = mc_suma(N, 65, 100);
        if (primer_paso < 0 && mayores > menores) primer_paso = t + 1;

        if (traza) {
            const long long despues = mc_suma(N, 0, 100);
            traza[t].antes = antes;
            traza[t].nacimientos = nacimientos;
            traza[t].defunciones = defunciones;
            traza[t].despues = despues;
            traza[t].menores15 = menores;
            traza[t].mayores65 = mayores;
            traza[t].balance = despues - antes - nacimientos + defunciones;
            traza[t].lambda = lambda;
        }
    }
    return primer_paso;
}
