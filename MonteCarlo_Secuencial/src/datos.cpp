// datos.cpp
#include "datos.hpp"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <set>
#include <sstream>
#include <utility>

FilasCsv leer_csv(const std::filesystem::path& archivo) {
    std::ifstream entrada(archivo);
    exigir(bool(entrada), "No se puede leer " + archivo.string());
    FilasCsv filas;
    std::string linea;
    while (std::getline(entrada, linea)) {
        linea = recortar(linea);
        if (linea.empty()) continue;
        std::vector<std::string> fila;
        std::stringstream partes(linea);
        std::string celda;
        while (std::getline(partes, celda, ',')) fila.push_back(recortar(celda));
        exigir(!fila.empty(), "Fila vacia");
        filas.push_back(fila);
    }
    exigir(!filas.empty(), "CSV vacio: " + archivo.string());
    for (const auto& fila : filas)
        exigir(fila.size() == filas.front().size(), "Columnas inconsistentes en " + archivo.string());
    return filas;
}

Poblacion cargar_poblacion_inicial(const std::filesystem::path& carpeta) {
    const auto filas = leer_csv(carpeta / "poblacion_inicial_peru.csv");
    exigir(filas[0] == std::vector<std::string>{"grupo_edad", "poblacion_hombres", "poblacion_mujeres"},
           "Encabezado poblacion incorrecto");
    exigir(filas.size() == 22, "Se requieren 21 grupos de poblacion");

    Poblacion N{};
    std::set<int> vistos;
    for (std::size_t i = 1; i < filas.size(); ++i) {
        const auto& fila = filas[i];
        // "0-4" -> 0, "5-9" -> 5, ..., "100+" -> 100
        const int inicio = fila[0] == "100+" ? 100 : int(leer_entero(fila[0].substr(0, fila[0].find('-'))));
        exigir(inicio >= 0 && inicio <= 100 && inicio % 5 == 0 && vistos.insert(inicio).second,
               "Grupo poblacion invalido o duplicado");
        exigir(fila[0] == (inicio == 100 ? "100+" : std::to_string(inicio) + "-" + std::to_string(inicio + 4)),
               "Etiqueta grupo invalida");

        for (int s = 0; s < 2; ++s) {
            const Conteo G = leer_entero(fila[s + 1]);
            exigir(G >= 0 && G <= 1000000000LL, "Poblacion fuera de limites");
            if (inicio == 100) {
                N[s][100] = G;  // grupo abierto, no se reparte
            } else {
                // Reparto uniforme entero: k = G/5, resto r = G%5 a las primeras r edades.
                for (int j = 0; j < 5; ++j) N[s][inicio + j] = G / 5 + (j < G % 5);
            }
        }
    }
    return N;
}

Tasas cargar_mortalidad(const std::filesystem::path& carpeta, const Configuracion& c) {
    const auto filas = leer_csv(carpeta / "mortalidad_peru.csv");
    exigir(filas[0] == std::vector<std::string>{"rango_edad", "mortalidad_hombres", "mortalidad_mujeres"},
           "Encabezado mortalidad incorrecto");
    exigir(filas.size() == 23, "Se requieren 22 filas de mortalidad");

    Tasas q{};
    std::set<int> vistos;
    for (std::size_t i = 1; i < filas.size(); ++i) {
        const int clave = int(leer_entero(filas[i][0]));
        exigir((clave == 0 || clave == 1 || (clave >= 5 && clave <= 100 && clave % 5 == 0)) &&
                   vistos.insert(clave).second,
               "Edad de mortalidad invalida o duplicada");

        for (int s = 0; s < 2; ++s) {
            const double valor = leer_probabilidad(filas[i][s + 1]);
            if (clave == 100) {  // 100+: no hay intervalo finito; se usa la configuracion
                q[s][100] = c.q_100[s];
                continue;
            }
            // Duracion del intervalo: clave 0 -> 1 anio, clave 1 -> edades 1-4, resto -> 5 anios.
            const int n = clave == 0 ? 1 : clave == 1 ? 4 : 5;
            double q_anual;
            if (c.tipo_mortalidad == "muerte_anual")
                q_anual = valor;
            else if (c.tipo_mortalidad == "supervivencia_anual")
                q_anual = 1 - valor;
            else  // supervivencia_intervalo: q = 1 - p^(1/n)
                q_anual = 1 - std::pow(valor, 1.0 / n);
            for (int edad = clave; edad < clave + n; ++edad) q[s][edad] = std::clamp(q_anual, 0.0, 1.0);
        }
    }
    return q;
}

std::vector<TasaFecundidad> cargar_fecundidad(const std::filesystem::path& carpeta, const Configuracion& c) {
    const auto filas = leer_csv(carpeta / "fecundidad_peru.csv");
    exigir(filas.size() == 8 && filas[0].size() == 11 && filas[0][0] == "rango_edad",
           "Se requieren 7 grupos y 10 periodos de fecundidad");

    // Encabezados "poblacion_2025_2030" -> periodo [2025, 2030)
    std::vector<std::pair<int, int>> periodos;
    std::set<std::string> encabezados;
    for (std::size_t j = 1; j < filas[0].size(); ++j) {
        const auto& h = filas[0][j];
        exigir(encabezados.insert(h).second && h.rfind("poblacion_", 0) == 0 && h.size() == 19 && h[14] == '_',
               "Periodo invalido");
        const int desde = int(leer_entero(h.substr(10, 4)));
        const int hasta = int(leer_entero(h.substr(15, 4)));
        exigir(hasta == desde + 5, "Periodo no quinquenal");
        periodos.push_back({desde, hasta});
    }

    // Validar grupos de edad 15-19 ... 45-49 y tasas en [0, 1].
    std::set<int> vistos;
    for (std::size_t i = 1; i < filas.size(); ++i) {
        const int edad = int(leer_entero(filas[i][0].substr(0, 2)));
        exigir(edad >= 15 && edad <= 45 && edad % 5 == 0 &&
                   filas[i][0] == std::to_string(edad) + "-" + std::to_string(edad + 4) &&
                   vistos.insert(edad).second,
               "Grupo fecundidad invalido");
        for (std::size_t j = 1; j < filas[i].size(); ++j)
            exigir(leer_real(filas[i][j]) >= 0 && leer_real(filas[i][j]) <= 1,
                   "Tasa anual por mujer fuera de [0,1]");
    }

    // Para cada anio del horizonte elegir la unica columna con desde <= anio < hasta.
    std::vector<TasaFecundidad> por_anio(c.horizonte);
    for (int t = 0; t < c.horizonte; ++t) {
        const int anio = c.anio_base + t;
        int columna = -1, coincidencias = 0;
        for (std::size_t j = 0; j < periodos.size(); ++j)
            if (anio >= periodos[j].first && anio < periodos[j].second) {
                columna = int(j) + 1;
                ++coincidencias;
            }
        exigir(coincidencias == 1, "Fecundidad sin cobertura unica para " + std::to_string(anio));
        por_anio[t].fill(0);
        for (std::size_t i = 1; i < filas.size(); ++i) {
            const int edad = int(leer_entero(filas[i][0].substr(0, 2)));
            for (int j = 0; j < 5; ++j) por_anio[t][edad + j] = leer_real(filas[i][columna]);
        }
    }
    return por_anio;
}
