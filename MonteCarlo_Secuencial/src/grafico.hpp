// grafico.hpp
// Graficos generados por el propio ejecutable, sin dependencias externas:
//   - histograma_svg: distribucion del primer anio de inversion p(T = y) en SVG (se abre en cualquier navegador
//     y se inserta en Word / PowerPoint);
//   - histograma_texto: la misma distribucion en texto, para la pantalla y resumen.txt.
#pragma once

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <ostream>
#include <sstream>
#include <string>
#include <vector>

#include "utilidades.hpp"

struct ResumenDistribucion {
    Conteo escenarios = 0;      // R
    Conteo con_inversion = 0;   // escenarios con inversion en el horizonte
    double media = 0.0;         // media del primer anio (sobre los que tienen inversion)
    double desviacion = 0.0;    // desviacion estandar del primer anio
    int anio_min = 0, anio_max = 0;
};

inline ResumenDistribucion resumir_distribucion(int anio_base, const std::vector<Conteo>& histograma, Conteo R) {
    ResumenDistribucion s;
    s.escenarios = R;
    double suma = 0.0, suma2 = 0.0;
    for (std::size_t t = 0; t < histograma.size(); ++t) {
        const Conteo n = histograma[t];
        if (n == 0) continue;
        const double y = double(anio_base + int(t));
        s.con_inversion += n;
        suma += n * y;
        suma2 += n * y * y;
        if (s.anio_min == 0) s.anio_min = anio_base + int(t);
        s.anio_max = anio_base + int(t);
    }
    if (s.con_inversion > 0) {
        s.media = suma / double(s.con_inversion);
        s.desviacion = std::sqrt(std::max(0.0, suma2 / double(s.con_inversion) - s.media * s.media));
    }
    return s;
}

// Histograma en texto: una fila por anio con masa, barra proporcional a p(T = y).
inline void histograma_texto(std::ostream& out, int anio_base, const std::vector<Conteo>& histograma, Conteo R) {
    const ResumenDistribucion s = resumir_distribucion(anio_base, histograma, R);
    const Conteo maximo = *std::max_element(histograma.begin(), histograma.end());
    out << "--- Distribucion del primer anio de inversion p(T = y) ---\n";
    if (s.con_inversion == 0) {
        out << "Ningun escenario presenta inversion en el horizonte.\n";
        return;
    }
    out << std::fixed << std::setprecision(4);
    for (std::size_t t = 0; t < histograma.size(); ++t) {
        if (histograma[t] == 0) continue;
        const double p = double(histograma[t]) / double(R);
        const int largo = maximo > 0 ? int(std::lround(40.0 * double(histograma[t]) / double(maximo))) : 0;
        out << anio_base + int(t) << "  " << std::setw(8) << histograma[t] << "  " << std::setw(6) << p << "  "
            << std::string(std::size_t(largo), '#') << '\n';
    }
    out << std::setprecision(2) << "Media " << s.media << ", desviacion " << s.desviacion << " anios, rango "
        << s.anio_min << "-" << s.anio_max << "; sin inversion: " << R - s.con_inversion << " de " << R << " ("
        << std::setprecision(2) << 100.0 * double(R - s.con_inversion) / double(R) << " %)\n";
}

// Grafico de barras SVG (900 x 480 px) de p(T = y) con media y desviacion.
inline void histograma_svg(const std::filesystem::path& archivo, int anio_base, const std::vector<Conteo>& histograma,
                           Conteo R, const std::string& subtitulo) {
    const ResumenDistribucion s = resumir_distribucion(anio_base, histograma, R);
    const int W = 900, H = 480, izq = 70, der = 30, arriba = 70, abajo = 60;
    const int ancho = W - izq - der, alto = H - arriba - abajo;

    int y0 = s.anio_min, y1 = s.anio_max;
    if (s.con_inversion == 0) { y0 = anio_base; y1 = anio_base + int(histograma.size()) - 1; }
    y0 -= 1; y1 += 1;  // un anio de margen a cada lado
    const int n_anios = y1 - y0 + 1;
    double p_max = 0.0;
    for (const Conteo n : histograma) p_max = std::max(p_max, double(n) / double(R));
    if (p_max <= 0.0) p_max = 1.0;
    const double escala_y = alto / (p_max * 1.15);
    const double paso_x = double(ancho) / n_anios;

    std::ofstream f(archivo);
    exigir(bool(f), "No se puede escribir el grafico SVG");
    f << std::fixed << std::setprecision(1);
    f << "<svg xmlns='http://www.w3.org/2000/svg' width='" << W << "' height='" << H << "' viewBox='0 0 " << W
      << ' ' << H << "' font-family='Arial, Helvetica, sans-serif' font-size='13'>\n"
      << "<rect width='" << W << "' height='" << H << "' fill='#ffffff'/>\n"
      << "<text x='" << W / 2 << "' y='28' text-anchor='middle' font-size='18' fill='#14213d'>"
      << "Distribucion del primer anio de inversion p(T = y)</text>\n"
      << "<text x='" << W / 2 << "' y='50' text-anchor='middle' fill='#5a6270'>" << subtitulo << "</text>\n";

    // Ejes y rejilla horizontal
    for (int k = 0; k <= 4; ++k) {
        const double p = p_max * 1.15 * k / 4.0;
        const double y = arriba + alto - p * escala_y;
        f << "<line x1='" << izq << "' y1='" << y << "' x2='" << izq + ancho << "' y2='" << y
          << "' stroke='#e5e7eb'/>\n<text x='" << izq - 8 << "' y='" << y + 4 << "' text-anchor='end' fill='#5a6270'>"
          << std::setprecision(3) << p << std::setprecision(1) << "</text>\n";
    }
    f << "<line x1='" << izq << "' y1='" << arriba + alto << "' x2='" << izq + ancho << "' y2='" << arriba + alto
      << "' stroke='#9aa3b2'/>\n";

    // Barras
    for (std::size_t t = 0; t < histograma.size(); ++t) {
        if (histograma[t] == 0) continue;
        const int anio = anio_base + int(t);
        if (anio < y0 || anio > y1) continue;
        const double p = double(histograma[t]) / double(R);
        const double x = izq + (anio - y0) * paso_x + paso_x * 0.1;
        const double h = p * escala_y;
        f << "<rect x='" << x << "' y='" << arriba + alto - h << "' width='" << paso_x * 0.8 << "' height='" << h
          << "' fill='#1f4e79'><title>" << anio << ": " << histograma[t] << " escenarios (p = "
          << std::setprecision(4) << p << std::setprecision(1) << ")</title></rect>\n";
    }
    // Etiquetas del eje x (cada 1, 2 o 5 anios segun el rango)
    const int salto = n_anios <= 16 ? 1 : (n_anios <= 32 ? 2 : 5);
    for (int anio = y0; anio <= y1; ++anio) {
        if ((anio - y0) % salto != 0) continue;
        const double x = izq + (anio - y0 + 0.5) * paso_x;
        f << "<text x='" << x << "' y='" << arriba + alto + 20 << "' text-anchor='middle' fill='#3e4a5c'>" << anio
          << "</text>\n";
    }
    f << "<text x='" << izq + ancho / 2 << "' y='" << H - 14 << "' text-anchor='middle' fill='#3e4a5c'>"
      << "Primer anio de inversion T</text>\n";

    // Media y leyenda
    if (s.con_inversion > 0) {
        const double xm = izq + (s.media - y0 + 0.5) * paso_x;
        f << "<line x1='" << xm << "' y1='" << arriba << "' x2='" << xm << "' y2='" << arriba + alto
          << "' stroke='#a04a0c' stroke-width='2' stroke-dasharray='6 4'/>\n"
          << "<text x='" << xm + 8 << "' y='" << arriba + 18 << "' fill='#a04a0c'>media " << std::setprecision(1)
          << s.media << ", sd " << s.desviacion << " anios</text>\n";
    }
    f << "<text x='" << izq + ancho << "' y='" << arriba + 18 << "' text-anchor='end' fill='#5a6270'>"
      << s.con_inversion << " de " << R << " escenarios con inversion</text>\n</svg>\n";
    f.close();
    exigir(!f.fail(), "Error guardando el grafico SVG");
}
