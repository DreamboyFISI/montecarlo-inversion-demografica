// metricas.hpp
// Metricas de rendimiento de una ejecucion. En la version secuencial son la LINEA BASE (T1):
// con ellas se calcula en el Sprint 3 el speedup S(p) = T1 / Tp, la eficiencia E(p) = S(p) / p
// y el costo C(p) = p * Tp de las versiones OpenMP, MPI y MPI + OpenMP.
//
// Se miden:
//   - tiempo de pared (wall clock) con std::chrono::steady_clock, separado en carga de datos,
//     simulacion + escritura de escenarios, y total;
//   - tiempo de CPU del proceso (std::clock); en la version secuencial debe ser ~ igual al de pared
//     (con OpenMP suma todos los hilos; con MPI se suma la de todos los procesos);
//   - memoria residente maxima (RSS) del proceso, con getrusage en Linux/macOS;
//   - metricas derivadas: tiempo por escenario, escenarios por segundo y escenario-anios por segundo.
#pragma once

#include <chrono>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <ostream>
#include <string>

#if defined(__unix__) || defined(__APPLE__)
#include <sys/resource.h>
#elif defined(_WIN32)
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <psapi.h>
#endif

#include "utilidades.hpp"

struct Metricas {
    Conteo escenarios = 0;          // R
    int horizonte = 0;              // H (anios por escenario)
    int procesos = 1;               // version secuencial: 1 proceso
    int hilos = 1;                  // version secuencial: 1 hilo
    double segundos_carga = 0.0;    // lectura de configuracion y CSV
    double segundos_simulacion = 0; // bucle Monte Carlo + escritura de escenarios.csv
    double segundos_total = 0.0;    // desde el inicio hasta escribir el resumen
    double segundos_cpu = 0.0;      // tiempo de CPU del proceso (usuario + sistema)
    double memoria_pico_mb = 0.0;   // RSS maxima en MiB (0 si la plataforma no la expone); en MPI, maximo por proceso
    // Solo MPI: maximo entre procesos del tiempo desde que terminan su bloque hasta que concluye el
    // MPI_Gatherv hacia el proceso 0 (incluye la espera al proceso mas lento: mide el desbalance).
    double segundos_comunicacion = 0.0;
    std::string etiqueta = "linea base secuencial, T1";  // titulo del bloque de metricas

    double segundos_por_escenario() const { return escenarios ? segundos_simulacion / double(escenarios) : 0.0; }
    double escenarios_por_segundo() const { return segundos_simulacion > 0 ? double(escenarios) / segundos_simulacion : 0.0; }
    double escenario_anios_por_segundo() const { return escenarios_por_segundo() * horizonte; }
};

// Tiempo de CPU consumido por el proceso hasta ahora, en segundos.
inline double segundos_cpu_proceso() { return double(std::clock()) / double(CLOCKS_PER_SEC); }

// Memoria residente maxima del proceso, en MiB. Devuelve 0 si no esta disponible.
inline double memoria_pico_mib() {
#if defined(__APPLE__)
    rusage uso{};
    if (getrusage(RUSAGE_SELF, &uso) == 0) return double(uso.ru_maxrss) / (1024.0 * 1024.0);  // bytes
    return 0.0;
#elif defined(__unix__)
    rusage uso{};
    if (getrusage(RUSAGE_SELF, &uso) == 0) return double(uso.ru_maxrss) / 1024.0;  // kibibytes
    return 0.0;
#elif defined(_WIN32)
    PROCESS_MEMORY_COUNTERS uso{};
    uso.cb = sizeof(uso);
    if (GetProcessMemoryInfo(GetCurrentProcess(), &uso, sizeof(uso)) != 0)
        return double(uso.PeakWorkingSetSize) / (1024.0 * 1024.0);
    return 0.0;
#else
    return 0.0;
#endif
}

// Escribe las metricas en formato clave: valor (para resumen.txt y pantalla).
inline void escribir_metricas_texto(std::ostream& out, const Metricas& m) {
    out << std::setprecision(6) << std::fixed
        << "--- Metricas de rendimiento (" << m.etiqueta << ") ---\n"
        << "Procesos x hilos: " << m.procesos << " x " << m.hilos << "\n"
        << "Segundos carga de datos: " << m.segundos_carga << "\n"
        << "Segundos simulacion y escritura de escenarios: " << m.segundos_simulacion << "\n"
        << "Segundos hasta resumen (" << (m.procesos * m.hilos == 1 ? "T1" : "Tp") << " total): " << m.segundos_total
        << "\n"
        << "Segundos de CPU del proceso: " << m.segundos_cpu << "\n"
        << "Milisegundos por escenario: " << m.segundos_por_escenario() * 1000.0 << "\n"
        << "Escenarios por segundo: " << m.escenarios_por_segundo() << "\n"
        << "Escenario-anios por segundo: " << m.escenario_anios_por_segundo() << "\n"
        << "Memoria pico (MiB): " << m.memoria_pico_mb << "\n";
    if (m.procesos > 1)
        out << "Segundos de espera + comunicacion (MPI_Gatherv): " << m.segundos_comunicacion << "\n";
}

// Escribe metricas.csv (una fila) para que scripts/linea_base.py pueda agregar varias ejecuciones.
inline void escribir_metricas_csv(const std::filesystem::path& archivo, const Metricas& m, const std::string& version) {
    std::ofstream f(archivo);
    exigir(bool(f), "No se puede escribir metricas.csv");
    f << std::setprecision(9)
      << "version,procesos,hilos,escenarios,horizonte,segundos_carga,segundos_simulacion,segundos_total,"
         "segundos_cpu,ms_por_escenario,escenarios_por_segundo,escenario_anios_por_segundo,memoria_pico_mib,"
         "segundos_comunicacion\n"
      << version << ',' << m.procesos << ',' << m.hilos << ',' << m.escenarios << ',' << m.horizonte << ','
      << m.segundos_carga << ',' << m.segundos_simulacion << ',' << m.segundos_total << ',' << m.segundos_cpu << ','
      << m.segundos_por_escenario() * 1000.0 << ',' << m.escenarios_por_segundo() << ','
      << m.escenario_anios_por_segundo() << ',' << m.memoria_pico_mb << ',' << m.segundos_comunicacion << '\n';
    f.close();
    exigir(!f.fail(), "Error guardando metricas.csv");
}
