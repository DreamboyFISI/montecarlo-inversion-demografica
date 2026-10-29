// utilidades.hpp
// Funciones pequenas de validacion y conversion de texto usadas en todo el programa.
#pragma once

#include <cmath>
#include <stdexcept>
#include <string>

using Conteo = long long;  // conteos enteros de personas, nacimientos y defunciones

// Detiene el programa con un mensaje claro si la condicion no se cumple.
inline void exigir(bool condicion, const std::string& mensaje) {
    if (!condicion) throw std::runtime_error(mensaje);
}

// Quita espacios, tabuladores y saltos de linea al inicio y al final.
inline std::string recortar(const std::string& texto) {
    const auto inicio = texto.find_first_not_of(" \t\r\n");
    if (inicio == std::string::npos) return "";
    const auto fin = texto.find_last_not_of(" \t\r\n");
    return texto.substr(inicio, fin - inicio + 1);
}

// Convierte texto a entero. Rechaza restos como "12abc".
inline Conteo leer_entero(const std::string& texto) {
    std::size_t usados = 0;
    const Conteo valor = std::stoll(texto, &usados);
    exigir(usados == texto.size(), "Entero invalido: " + texto);
    return valor;
}

// Convierte texto a real finito. Rechaza restos, infinito y NaN.
inline double leer_real(const std::string& texto) {
    std::size_t usados = 0;
    const double valor = std::stod(texto, &usados);
    exigir(usados == texto.size() && std::isfinite(valor), "Numero invalido: " + texto);
    return valor;
}

// Convierte texto a probabilidad y exige que este en [0, 1].
inline double leer_probabilidad(const std::string& texto) {
    const double valor = leer_real(texto);
    exigir(valor >= 0.0 && valor <= 1.0, "Probabilidad fuera de [0,1]: " + texto);
    return valor;
}
