// pruebas.cpp
// Pruebas controladas con resultado conocido. Se ejecutan con: ./simulador --self-test [--datos datos]
#include "pruebas.hpp"

#include <cmath>
#include <iomanip>
#include <iostream>
#include <string>

#include "modelo.hpp"

namespace {

int aprobadas = 0;

void comprobar(bool condicion, const std::string& nombre) {
    exigir(condicion, "PRUEBA FALLIDA: " + nombre);
    ++aprobadas;
    std::cout << "  [OK] " << nombre << '\n';
}

// Configuracion minima para pruebas sinteticas (sin nacimientos, supervivencia total de nacidos).
Configuracion configuracion_de_prueba() {
    Configuracion c;
    c.anio_base = 2025;
    c.horizonte = 40;
    c.p_femenino = 0.5;
    c.u_recien_nacido[0] = c.u_recien_nacido[1] = 1.0;
    c.tipo_mortalidad = "supervivencia_intervalo";
    c.q_100[0] = c.q_100[1] = 0.35;
    return c;
}

}  // namespace

void ejecutar_pruebas(const std::filesystem::path& carpeta_datos) {
    std::cout << "Pruebas controladas\n";
    const Configuracion c = configuracion_de_prueba();
    std::mt19937_64 generador(9);

    // --- P1-P3: transicion con mortalidad cero y sin fecundidad --------------------------
    Poblacion N{};
    N[HOMBRES][14] = 10;
    N[MUJERES][64] = 20;
    N[HOMBRES][99] = 3;
    N[MUJERES][100] = 4;
    Tasas q{};
    TasaFecundidad sin_fecundidad{};
    auto paso = simular_anio(N, q, sin_fecundidad, c, generador);
    comprobar(paso.poblacion[HOMBRES][15] == 10 && paso.poblacion[MUJERES][65] == 20,
              "P1 envejecimiento 14->15 y 64->65");
    comprobar(paso.poblacion[HOMBRES][100] == 3 && paso.poblacion[MUJERES][100] == 4,
              "P2 grupo abierto: 99->100+ y 100+ permanece");
    comprobar(poblacion_total(paso.poblacion) == 37 && paso.nacimientos == 0 && paso.defunciones == 0,
              "P3 mortalidad cero conserva la poblacion (37)");

    // --- P4: mortalidad uno extingue -----------------------------------------------------
    for (auto& sexo : q) sexo.fill(1.0);
    paso = simular_anio(N, q, sin_fecundidad, c, generador);
    comprobar(poblacion_total(paso.poblacion) == 0 && paso.defunciones == 37, "P4 mortalidad uno extingue (37 muertes)");

    // --- P5: evento de inversion; el empate no cuenta -------------------------------------
    Poblacion E{};
    E[HOMBRES][10] = 5;
    E[MUJERES][70] = 5;
    const bool empate = hay_inversion(E);
    E[MUJERES][80] = 1;
    comprobar(!empate && hay_inversion(E), "P5 inversion solo si A > J (empate no cuenta)");

    // --- P6: binomial en casos limite no consume aleatorios -------------------------------
    std::mt19937_64 g1(1), g2(1);
    sorteo_binomial(0, 0.3, g1);
    sorteo_binomial(100, 0.0, g1);
    sorteo_binomial(100, 1.0, g1);
    comprobar(g1() == g2(), "P6 binomial trivial no altera la secuencia aleatoria");

    // --- P7-P10: datos reales ------------------------------------------------------------
    const Poblacion N0 = cargar_poblacion_inicial(carpeta_datos);
    comprobar(poblacion_total(N0) == 32706028 && menores_15(N0) == 7429471 && mayores_65(N0) == 3440272,
              "P7 desagregacion conserva totales del CSV (32 706 028; 7 429 471; 3 440 272)");
    comprobar(N0[HOMBRES][0] == 205318 && N0[HOMBRES][1] == 205317 && N0[HOMBRES][4] == 205317,
              "P8 reparto uniforme entero 0-4 hombres (205 318 + 4 x 205 317)");

    const Tasas qr = cargar_mortalidad(carpeta_datos, c);
    comprobar(std::fabs(qr[HOMBRES][20] - (1 - std::pow(0.9907, 0.2))) < 1e-15 &&
                  std::fabs(qr[HOMBRES][22] - 0.001867) < 5e-7 && qr[MUJERES][100] == 0.35,
              "P9 q anual H 20-24 = 1 - 0,9907^(1/5) ~ 0,001867 y q(100+) de configuracion");

    const auto f = cargar_fecundidad(carpeta_datos, c);
    double lambda = 0;
    for (int a = 15; a <= 49; ++a) lambda += N0[MUJERES][a] * f[0][a];
    comprobar(std::fabs(lambda - 512939.1415) < 1e-6, "P10 lambda inicial = 512 939,1415");

    // --- P11: seleccion de columna de fecundidad (2029 -> 2025_2030, 2030 -> 2030_2035) ----
    comprobar(f[4][15] == 0.0467 && f[5][15] == 0.0422, "P11 cambio de quinquenio de fecundidad en 2030");

    // --- P12: un anio real cumple balance y es reproducible con la misma semilla ----------
    std::mt19937_64 a(mezclar_semilla(12345)), b(mezclar_semilla(12345));
    const auto pa = simular_anio(N0, qr, f[0], c, a);
    const auto pb = simular_anio(N0, qr, f[0], c, b);
    comprobar(pa.poblacion == pb.poblacion && pa.nacimientos == pb.nacimientos &&
                  poblacion_total(pa.poblacion) == poblacion_total(N0) + pa.nacimientos - pa.defunciones,
              "P12 balance exacto y reproducibilidad con la misma semilla");

    std::cout << "Pruebas controladas: OK (" << aprobadas << " de " << aprobadas << ")\n";
}
