// configuracion.cpp
#include "configuracion.hpp"

#include <fstream>
#include <map>
#include <set>

Configuracion leer_configuracion(const std::filesystem::path& archivo) {
    std::ifstream entrada(archivo);
    exigir(bool(entrada), "No se puede leer configuracion");

    // 1. Leer pares clave=valor, ignorando lineas vacias y comentarios (#).
    std::map<std::string, std::string> valores;
    std::string linea;
    while (std::getline(entrada, linea)) {
        linea = recortar(linea);
        if (linea.empty() || linea[0] == '#') continue;
        const auto igual = linea.find('=');
        exigir(igual != std::string::npos, "Se espera clave=valor");
        const std::string clave = recortar(linea.substr(0, igual));
        exigir(valores.emplace(clave, recortar(linea.substr(igual + 1))).second,
               "Clave duplicada: " + clave);
    }

    // 2. Comprobar que estan exactamente las claves esperadas.
    const std::set<std::string> claves = {
        "anio_base", "horizonte", "escenarios", "semilla", "estado_datos", "tipo_mortalidad",
        "unidad_fecundidad", "p_femenino", "u_recien_nacido_h", "u_recien_nacido_f",
        "q_100_h", "q_100_f"};
    // Claves opcionales (si faltan valen 0: tasas fijas).
    const std::set<std::string> opcionales = {"sigma_fecundidad", "sigma_mortalidad"};
    for (const auto& [clave, valor] : valores)
        exigir(claves.count(clave) > 0 || opcionales.count(clave) > 0, "Clave desconocida: " + clave);
    for (const auto& clave : claves)
        exigir(valores.count(clave) > 0 && !valores[clave].empty(), "Falta parametro: " + clave);

    // 3. Convertir y validar rangos.
    const Conteo anio = leer_entero(valores.at("anio_base"));
    const Conteo horizonte = leer_entero(valores.at("horizonte"));
    const Conteo escenarios = leer_entero(valores.at("escenarios"));
    const Conteo semilla = leer_entero(valores.at("semilla"));
    exigir(anio >= 1900 && anio <= 2100 && horizonte >= 1 && horizonte <= 150 &&
               escenarios >= 1 && escenarios <= 1000000000LL && semilla >= 0,
           "Configuracion fuera de limites");
    exigir(valores.at("unidad_fecundidad") == "anual_por_mujer",
           "Esta version requiere fecundidad anual por mujer");

    Configuracion c;
    c.anio_base = int(anio);
    c.horizonte = int(horizonte);
    c.escenarios = escenarios;
    c.semilla = std::uint64_t(semilla);
    c.estado_datos = valores.at("estado_datos");
    c.tipo_mortalidad = valores.at("tipo_mortalidad");
    c.p_femenino = leer_probabilidad(valores.at("p_femenino"));
    c.u_recien_nacido[0] = leer_probabilidad(valores.at("u_recien_nacido_h"));
    c.u_recien_nacido[1] = leer_probabilidad(valores.at("u_recien_nacido_f"));
    c.q_100[0] = leer_probabilidad(valores.at("q_100_h"));
    c.q_100[1] = leer_probabilidad(valores.at("q_100_f"));
    for (const auto& [clave, destino] : {std::pair<const char*, double*>{"sigma_fecundidad", &c.sigma_fecundidad},
                                         std::pair<const char*, double*>{"sigma_mortalidad", &c.sigma_mortalidad}}) {
        if (valores.count(clave) && !valores.at(clave).empty()) {
            *destino = leer_real(valores.at(clave));
            exigir(*destino >= 0.0 && *destino <= 0.5, std::string(clave) + " debe estar en [0, 0.5]");
        }
    }
    c.archivo = archivo;

    exigir(c.estado_datos == "DEMO_NO_VALIDADO" || c.estado_datos == "PARAMETROS_DOCUMENTADOS",
           "estado_datos no reconocido");
    exigir(c.tipo_mortalidad == "supervivencia_intervalo" || c.tipo_mortalidad == "supervivencia_anual" ||
               c.tipo_mortalidad == "muerte_anual",
           "tipo_mortalidad no reconocido");
    return c;
}
