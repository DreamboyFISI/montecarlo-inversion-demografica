# Monte Carlo de la inversión demográfica del Perú: implementación secuencial (semana 7)

Programa en C++17 que estima en qué año la población de 65 o más años supera a la de menores de 15. Usa un proceso y un hilo, sin MPI ni OpenMP. Es la línea base que se paralelizará en el Sprint 3.

**Estado de los datos: DEMO_NO_VALIDADO.** Faltan la ficha técnica de los CSV y la confirmación de algunos supuestos. Los resultados dependen de esos supuestos y no son un pronóstico oficial.

## Contenido

| Carpeta / archivo | Qué contiene |
|---|---|
| `src/utilidades.hpp` | Validación y conversión de texto |
| `src/configuracion.*` | Lectura del archivo `.ini` |
| `src/datos.*` | Lectura de los CSV, reparto en edades simples, q anual y fecundidad por año |
| `src/modelo.*` | Núcleo: `simular_anio` (Poisson, binomiales, envejecimiento, balance) |
| `src/pruebas.*` | 12 pruebas controladas con resultado conocido |
| `src/grafico.hpp` | Gráfico generado por el ejecutable: histograma del año de inversión en SVG (`distribucion_anio.svg`) y en texto (pantalla y `resumen.txt`) |
| `src/metricas.hpp` | Métricas de rendimiento: tiempo de pared por fase, tiempo de CPU, memoria pico, ms/escenario, escenarios/s → `metricas.csv` |
| `src/main.cpp` | Bucle Monte Carlo y escritura de resultados |
| `datos/` | Los tres CSV originales, sin modificar |
| `config_demostracion.ini` | Parámetros y supuestos de la demostración (tasas fijas) |
| `config_incertidumbre.ini` | Igual, con `sigma_fecundidad=0.05` y `sigma_mortalidad=0.015`: distribución del año de inversión |
| `resultados_incertidumbre/`, `graficos_incertidumbre/` | Ejecución de 10 000 escenarios con incertidumbre macro y sus gráficos (`06_distribucion_anio.png`) |
| `scripts/limpieza_datos.py` | Validación de datos (Sprint 1) → `datos_procesados/` |
| `scripts/graficos.py` | Gráficos de una ejecución → `graficos/` |
| `scripts/linea_base.py` | Línea base secuencial (T1): ejecuta R = 1 000, 10 000 y 100 000 × 3 repeticiones y agrega las métricas → `linea_base/` |
| `datos_procesados/` | Tablas en edades simples y `reporte_calidad_datos.md` |
| `resultados_demo/` | Ejecución de referencia: 1 000 escenarios, semilla 12345 |
| `graficos/` | Cinco gráficos PNG de la ejecución de referencia |
| `linea_base/` | Métricas de rendimiento medidas: `metricas_secuencial.csv` (media ± sd por R), `metricas_crudas.csv` (una fila por corrida), `linea_base.md` y `linea_base_tiempos.png` |

## 1. Compilar

Linux, macOS o WSL (se necesita g++ con C++17):

```bash
make
```

Equivale a `g++ -std=c++17 -O2 -Wall -Wextra -Wpedantic src/*.cpp -o simulador`.

En Windows con MinGW: `g++ -std=c++17 -O2 src/*.cpp -o simulador.exe`.
En Visual Studio (Developer Command Prompt): `cl /EHsc /std:c++17 /O2 src\*.cpp /Fe:simulador.exe`.

## 2. Ejecutar las pruebas

```bash
./simulador --self-test --datos datos
```

Debe mostrar las 12 pruebas con `[OK]` y la línea `Pruebas controladas: OK (12 de 12)`.

## 3. Ejecutar la simulación

```bash
./simulador --config config_demostracion.ini --datos datos --salida resultados_1000
```

- `--escenarios N` cambia el número de escenarios sin editar el `.ini`.
- La carpeta de salida debe ser nueva; el programa no sobrescribe resultados.
- En PowerShell usa `.\simulador.exe`.

## 4. Validar datos y generar gráficos (Python 3 y matplotlib)

```bash
python3 scripts/limpieza_datos.py datos datos_procesados
python3 scripts/graficos.py resultados_1000 datos_procesados graficos_1000
```

## 5. Archivos de salida

| Archivo | Contenido |
|---|---|
| `resumen.txt` | Conteos, probabilidades, año mínimo, medio y máximo de inversión, tiempos y métricas de rendimiento |
| `distribucion_anio.svg` | Gráfico de barras de p(T = y) con media y desviación, generado por el ejecutable (se abre en el navegador o se inserta en Word/PowerPoint) |
| `factores_escenarios.csv` | Solo con sigma > 0: factor de fecundidad y mortalidad sorteado en cada escenario |
| `metricas.csv` | Una fila con las métricas de rendimiento de la ejecución (procesos, hilos, R, H, tiempos, ms/escenario, escenarios/s, memoria pico) |
| `escenarios.csv` | Un registro por escenario con su primer año de inversión (vacío si no ocurrió) |
| `distribucion.csv` | Frecuencia, probabilidad anual y acumulada por año |
| `trayectoria_escenario_1.csv` | Año a año del escenario 1: población, nacimientos, defunciones, J, A, λ y balance |
| `config_usada.ini`, `parametros_efectivos.txt` | Configuración usada y parámetros efectivos |

## 6. Incertidumbre macro por escenario (campana del año de inversión)

Con las tasas fijas de los CSV, el único azar son los sorteos Poisson y binomiales, y sobre 33 millones de
personas ese azar es tan pequeño que el año de inversión cae siempre en 2054. Para obtener una distribución
del año, el `.ini` admite dos claves opcionales (por defecto 0):

```ini
sigma_fecundidad=0.05    # factor_fec  ~ N(1, 0.05)  multiplica f(a, y) durante todo el escenario
sigma_mortalidad=0.015   # factor_mort ~ N(1, 0.015) multiplica q(a, s), acotado a [0, 1]
```

Los dos factores se sortean una vez por escenario, antes de los 40 años, con el generador de ese escenario;
quedan registrados en `factores_escenarios.csv`. Con sigma = 0 no se consume ningún número aleatorio y la
ejecución es idéntica byte a byte a la de referencia. Ejemplo (`config_incertidumbre.ini`, 10 000 escenarios):
media 2054,5, desviación 2,3 años, rango 2046–2065, 0,75 % sin inversión en el horizonte; gráfico
`06_distribucion_anio.png`. Los sigmas son supuestos didácticos; se calibran en S9.

```bash
make campana      # = ./simulador --config config_incertidumbre.ini --datos datos --salida resultados_incertidumbre --escenarios 10000
```

El ejecutable imprime el histograma en pantalla, lo guarda en `resumen.txt` y escribe `distribucion_anio.svg`
en la carpeta de salida (no hace falta Python). `scripts/graficos.py` sigue disponible para los gráficos PNG.

## 7. Métricas de rendimiento (línea base T1)

Cada ejecución mide y guarda en `resumen.txt` y `metricas.csv`:

| Métrica | Cómo se mide | Para qué sirve |
|---|---|---|
| Tiempo de ejecución T1 (pared) | `std::chrono::steady_clock`; total y por fases (carga de datos, simulación + escritura) | Numerador del speedup S(p) = T1 / Tp |
| Tiempo de CPU | `std::clock` del proceso | En un hilo ≈ T1; en paralelo revela esperas |
| Tiempo por escenario | T_simulación / R (ms) | Costo unitario; estimar Tp para cualquier R |
| Rendimiento (throughput) | R / T_simulación (escenarios/s) y R·H / T_simulación (escenario-años/s) | Comparar versiones con distinto R |
| Memoria pico (RSS) | `getrusage(RUSAGE_SELF)` | Comprobar que no crece con R; dimensionar procesos MPI |

Para medir la línea base con repeticiones (3 tamaños × 3 corridas, unos 17 minutos):

```bash
python3 scripts/linea_base.py --salida linea_base
python3 scripts/linea_base.py --solo-informe --salida linea_base   # rehace tabla y gráfico sin ejecutar
```

Con el T1 de `linea_base/metricas_secuencial.csv` se calcularán en el Sprint 3, para el mismo R y la misma máquina:
speedup S(p) = T1/Tp, eficiencia E(p) = S(p)/p, costo C(p) = p·Tp, fracción secuencial de Karp–Flatt
f = (1/S − 1/p)/(1 − 1/p) y la cota de Amdahl S_máx = 1/f.

Resultado medido (Intel Xeon 2,8 GHz, g++ 13.3 -O2, 1 proceso × 1 hilo): ver `linea_base/linea_base.md`.

## 8. Resultado de la ejecución de referencia

Se usaron 1 000 escenarios, 40 años y la semilla 12345, con los supuestos de demostración:

- Hubo inversión en los 1 000 escenarios, en el año 2054.
- El balance fue 0 en los 40 años.
- El tiempo fue de unos 3 s en un Intel Xeon de 2,8 GHz con g++ 13.3 y -O2 (≈ 3 ms por escenario, 14 MiB de memoria; detalle en `linea_base/`).
- Los CSV coinciden byte a byte con los del programa secuencial original (`simulador.cpp` de una sola pieza) usando la misma semilla.
