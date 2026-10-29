// pruebas.hpp
#pragma once

#include <filesystem>

// Ejecuta las pruebas controladas. Lanza una excepcion en la primera que falle.
void ejecutar_pruebas(const std::filesystem::path& carpeta_datos);
