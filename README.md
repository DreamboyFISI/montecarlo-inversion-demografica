# montecarlo-inversion-demografica

Proyecto del curso Programación Paralela y Concurrente. Abordamos la paralelización de una simulación Monte Carlo de la inversión demográfica del Perú: el año en que la población de 65 o más años (A) supera a la de menores de 15 (J).

**Estado de los datos: DEMO_NO_VALIDADO.** Falta la ficha técnica de los CSV y la confirmación de algunos supuestos. Los resultados dependen de esos supuestos y no son un pronóstico oficial.

## Contenido

1. [Estructura del repositorio](#estructura-del-repositorio)
2. [Inicio rápido con Docker](#inicio-rápido-con-docker)
3. [Versión secuencial (S7–S9)](#versión-secuencial-s7s9)
4. [Versiones paralelas: OpenMP y MPI (S10)](#versiones-paralelas-openmp-y-mpi-s10)
5. [Clúster MPI con Docker Compose (S10)](#clúster-mpi-con-docker-compose-s10)
6. [Archivos de salida](#archivos-de-salida)
7. [Incertidumbre macro por escenario](#incertidumbre-macro-por-escenario)
8. [Métricas de rendimiento](#métricas-de-rendimiento)
9. [Versión Go](#versión-go)
10. [Documentación Scrum](#documentación-scrum)

## Estructura del repositorio

| Carpeta / archivo | Qué contiene | Semana |
|---|---|---|
| `docs/` | Product Backlog, diseño del modelo probabilístico, validación y línea base, paralelización y registro Scrum | S4–S10 |
| `MonteCarlo_Secuencial/src/utilidades.hpp` | Validación y conversión de texto | S7 |
| `MonteCarlo_Secuencial/src/configuracion.*` | Lectura del archivo `.ini` | S7 |
| `MonteCarlo_Secuencial/src/datos.*` | Lectura de los CSV, reparto en edades simples, q anual y fecundidad por año | S7 |
| `MonteCarlo_Secuencial/src/modelo.*` | Núcleo: `simular_anio` (Poisson, binomiales, envejecimiento, balance) | S7 |
| `MonteCarlo_Secuencial/src/escenario.*` | Un escenario completo (`simular_escenario`) y escritura ordenada de `escenarios.csv` / `factores_escenarios.csv`; lo comparten las tres versiones | S10 |
| `MonteCarlo_Secuencial/src/salida.*` | Argumentos, carpeta de salida, distribución, resumen, SVG y métricas; lo comparten las tres versiones | S10 |
| `MonteCarlo_Secuencial/src/pruebas.*` | 12 pruebas controladas con resultado conocido | S9 |
| `MonteCarlo_Secuencial/src/grafico.hpp` | Histograma del año de inversión en SVG (`distribucion_anio.svg`) y en texto | S9 |
| `MonteCarlo_Secuencial/src/metricas.hpp` | Tiempo de pared por fase, CPU, memoria pico, ms/escenario, escenarios/s → `metricas.csv` | S9 |
| `MonteCarlo_Secuencial/src/main.cpp` | Bucle Monte Carlo secuencial | S7 |
| `MonteCarlo_Secuencial/datos/` | Los tres CSV originales, sin modificar | S4 |
| `MonteCarlo_Secuencial/config_demostracion.ini` | Parámetros y supuestos de la demostración (tasas fijas) | S7 |
| `MonteCarlo_Secuencial/config_incertidumbre.ini` | Igual, con `sigma_fecundidad=0.05` y `sigma_mortalidad=0.015` | S9 |
| `MonteCarlo_Secuencial/scripts/limpieza_datos.py` | Validación de datos → `datos_procesados/` | S4–S5 |
| `MonteCarlo_Secuencial/scripts/graficos.py` | Gráficos PNG de una ejecución | S7 |
| `MonteCarlo_Secuencial/scripts/linea_base.py` | Línea base secuencial T1 (R = 10³, 10⁴, 10⁵ × 3 repeticiones) → `linea_base/` | S9 |
| `MonteCarlo_Secuencial/datos_procesados/` | Tablas en edades simples y `reporte_calidad_datos.md` | S5 |
| `MonteCarlo_Secuencial/resultados_demo/`, `graficos/` | Ejecución de referencia (1 000 escenarios, semilla 12345) y sus gráficos | S7 |
| `MonteCarlo_Secuencial/resultados_incertidumbre/`, `graficos_incertidumbre/` | 10 000 escenarios con incertidumbre macro y sus gráficos | S9 |
| `MonteCarlo_Secuencial/linea_base/` | T1 medido: `metricas_secuencial.csv`, `metricas_crudas.csv`, `linea_base.md`, `linea_base_tiempos.png` | S9 |
| `MonteCarlo_Secuencial/interfaz.py` | Interfaz gráfica (Tkinter) que ejecuta el simulador C++ o Go y muestra los resultados | extra |
| `MonteCarlo_Paralelo/src/main_openmp.cpp` | Bucle Monte Carlo con OpenMP | S10 |
| `MonteCarlo_Paralelo/src/main_mpi.cpp` | Bucle Monte Carlo con MPI | S10 |
| `MonteCarlo_Paralelo/Makefile` | Compila ambas versiones con los fuentes de `MonteCarlo_Secuencial/src` | S10 |
| `MonteCarlo_Paralelo/scripts/verificar_equivalencia.sh` | Compara los CSV de OpenMP (1, 2, 3, 8 hilos) y MPI (1, 2, 3, 4 procesos) con los del secuencial | S10 |
| `MonteCarlo_Paralelo/scripts/rendimiento.py` | Speedup, eficiencia, costo, Karp-Flatt y Amdahl → `rendimiento/` | S10 |
| `MonteCarlo_Paralelo/docker/Dockerfile` | Imagen Ubuntu 24.04 con g++, OpenMPI y SSH; compila las tres versiones y corre las pruebas | S10 |
| `MonteCarlo_Paralelo/docker-compose.yml`, `hostfile` | Clúster MPI de 4 nodos (contenedores) con 2 CPU cada uno | S10 |
| `MonteCarlo_Paralelo/docker/ejecutar_cluster.sh` | Lanza `mpirun` en el clúster; resultados en `resultados_cluster/` | S10 |
| `MonteCarlo_Go/` | Implementación secuencial alternativa en Go | extra |

## Inicio rápido con Docker

No hace falta instalar compiladores. Desde la raíz del repositorio:

```bash
docker build -f MonteCarlo_Paralelo/docker/Dockerfile -t montecarlo-demografia .
```

La construcción compila el secuencial, OpenMP y MPI y corre las 12 pruebas controladas. Si alguna falla, la imagen no se construye.

```bash
# Verificar que OpenMP y MPI reproducen exactamente al secuencial
docker run --rm -u mpi montecarlo-demografia bash -c 'MPIRUN_OPCIONES=--oversubscribe ./scripts/verificar_equivalencia.sh'

# Secuencial
docker run --rm -u mpi montecarlo-demografia ../MonteCarlo_Secuencial/simulador \
    --config ../MonteCarlo_Secuencial/config_incertidumbre.ini --datos ../MonteCarlo_Secuencial/datos --salida /tmp/sec --escenarios 2000

# OpenMP con 8 hilos
docker run --rm -u mpi montecarlo-demografia ./simulador_omp \
    --config ../MonteCarlo_Secuencial/config_incertidumbre.ini --datos ../MonteCarlo_Secuencial/datos --salida /tmp/omp --escenarios 10000 --hilos 8

# MPI con 4 procesos en un solo contenedor
docker run --rm -u mpi montecarlo-demografia mpirun -np 4 ./simulador_mpi \
    --config ../MonteCarlo_Secuencial/config_incertidumbre.ini --datos ../MonteCarlo_Secuencial/datos --salida /tmp/mpi --escenarios 10000
```

Para conservar los resultados, monta una carpeta del anfitrión con `-v "$PWD/salidas:/salidas:z"` y usa `--salida /salidas/<nombre>`.

## Versión secuencial (S7–S9)

Programa en C++17 que usa un proceso y un hilo, sin MPI ni OpenMP. Es la línea base T1 de las versiones paralelas. Los comandos de esta sección se ejecutan desde `MonteCarlo_Secuencial/`.

### Compilar

En Linux, macOS o WSL (se necesita g++ con C++17):

```bash
make
```

Equivale a `g++ -std=c++17 -O2 -Wall -Wextra -Wpedantic src/*.cpp -o simulador`. Otras plataformas:

- Windows con MinGW: `g++ -std=c++17 -O2 src/*.cpp -o simulador.exe`.
- Visual Studio (Developer Command Prompt): `cl /EHsc /std:c++17 /O2 src\*.cpp /Fe:simulador.exe`.

### Pruebas

```bash
./simulador --self-test --datos datos
```

Deben aparecer las 12 pruebas con `[OK]` y la línea `Pruebas controladas: OK (12 de 12)`.

### Simulación

```bash
./simulador --config config_demostracion.ini --datos datos --salida resultados_1000
```

- `--escenarios N` cambia el número de escenarios sin editar el `.ini`.
- La carpeta de salida debe ser nueva: el programa no sobrescribe resultados.
- En PowerShell usa `.\simulador.exe`.
- Otros objetivos del Makefile: `make test`, `make demo` (1 000 escenarios en `resultados_demo/`) y `make campana` (10 000 escenarios con incertidumbre en `resultados_incertidumbre/`).

### Validar datos y generar gráficos (Python 3 y matplotlib)

```bash
python3 scripts/limpieza_datos.py datos datos_procesados
python3 scripts/graficos.py resultados_1000 datos_procesados graficos_1000
```

### Interfaz gráfica

```bash
python interfaz.py
```

Ejecuta `simulador.exe` (Windows) o `simulador` (Linux/macOS), o bien la versión Go, y presenta los CSV producidos.

### Resultado de la ejecución de referencia

Con 1 000 escenarios, 40 años, semilla 12345 y los supuestos de demostración:

- Hubo inversión en los 1 000 escenarios, en el año 2054.
- El balance fue 0 en los 40 años.
- Tardó unos 3 s en un Intel Xeon de 2,8 GHz con g++ 13.3 y -O2 (≈ 3 ms por escenario y 14 MiB de memoria; detalle en `linea_base/`).

## Versiones paralelas: OpenMP y MPI (S10)

Las versiones paralelas usan **el mismo modelo y los mismos fuentes** que la secuencial. Solo cambia cómo se reparten los R escenarios:

| Ejecutable | Paralelismo | Reparto de escenarios |
|---|---|---|
| `simulador_omp` | 1 proceso, P hilos (memoria compartida) | `#pragma omp parallel for schedule(dynamic, 16)` |
| `simulador_mpi` | P procesos, 1 hilo cada uno (memoria distribuida) | Bloques contiguos; `MPI_Gatherv` de los resultados al proceso 0 |

Cada escenario r tiene su propio generador con semilla `splitmix64(semilla + r)`, así que su resultado no depende de quién lo calcule. Por eso **los CSV de resultados son idénticos byte a byte a los del secuencial** con cualquier número de hilos o procesos, y así se verifica que la paralelización es correcta. El diseño completo está en `docs/04_sprint3_paralelizacion.md`.

### Compilar en Linux / WSL

Se necesitan g++ con OpenMP y OpenMPI:

- Ubuntu / WSL: `sudo apt install g++ make openmpi-bin libopenmpi-dev`
- Fedora: `sudo dnf install gcc-c++ make openmpi-devel`

Desde `MonteCarlo_Paralelo/`:

```bash
make all secuencial      # simulador_omp, simulador_mpi y ../MonteCarlo_Secuencial/simulador
make verificar           # CSV de OpenMP y MPI idénticos a los del secuencial
./simulador_omp --config ../MonteCarlo_Secuencial/config_demostracion.ini --datos ../MonteCarlo_Secuencial/datos \
    --salida resultados_omp --hilos 4
mpirun -np 4 ./simulador_mpi --config ../MonteCarlo_Secuencial/config_demostracion.ini --datos ../MonteCarlo_Secuencial/datos \
    --salida resultados_mpi
```

- Sin `--hilos`, OpenMP usa `OMP_NUM_THREADS` o el número de CPU lógicas.
- OpenMPI solo ofrece por defecto un slot por núcleo físico. Para usar todas las CPU lógicas agrega `--use-hwthread-cpus --bind-to none`. Sin `--bind-to none`, los procesos 0 y 1 quedan fijados a los dos hilos de hardware del mismo núcleo y MPI con 2 procesos rinde como con 1.

## Clúster MPI con Docker Compose (S10)

Desde `MonteCarlo_Paralelo/`:

```bash
docker compose up -d --build              # nodo1 (maestro) ... nodo4, red "cluster", SSH sin contraseña
./docker/ejecutar_cluster.sh 8 10000      # mpirun -np 8 --map-by node: 2 procesos por nodo
docker compose down
```

Los resultados aparecen en `MonteCarlo_Paralelo/resultados_cluster/mpi_np8_R10000_<fecha>/` del anfitrión. El tercer argumento opcional es el `.ini` (por defecto `config_incertidumbre.ini`).

Detalles del clúster:

- Los 4 contenedores salen de la misma imagen y comparten la clave SSH del usuario `mpi`. Es adecuado para un laboratorio, no para producción.
- `OMPI_MCA_btl_vader_single_copy_mechanism=none` es necesario porque Docker restringe `ptrace`, que usa el mecanismo CMA de memoria compartida de OpenMPI.
- `btl_tcp_if_include=eth0` hace que la comunicación entre nodos use la red del clúster.
- Cada nodo tiene `cpus: 2` y el `hostfile` declara `slots=2`.

## Archivos de salida

Las tres versiones escriben los mismos archivos:

| Archivo | Contenido |
|---|---|
| `resumen.txt` | Conteos, probabilidades, año mínimo, medio y máximo de inversión, tiempos, métricas e histograma en texto |
| `distribucion_anio.svg` | Gráfico de barras de p(T = y) con media y desviación (se abre en el navegador o se inserta en Word/PowerPoint) |
| `escenarios.csv` | Un registro por escenario con su primer año de inversión (vacío si no ocurrió) |
| `distribucion.csv` | Frecuencia, probabilidad anual y acumulada por año |
| `factores_escenarios.csv` | Solo con sigma > 0: factor de fecundidad y de mortalidad sorteados en cada escenario |
| `trayectoria_escenario_1.csv` | Año a año del escenario 1: población, nacimientos, defunciones, J, A, λ y balance |
| `metricas.csv` | Una fila con las métricas de rendimiento (ver más abajo) |
| `config_usada.ini`, `parametros_efectivos.txt` | Configuración usada y parámetros efectivos |

## Incertidumbre macro por escenario

Con las tasas fijas de los CSV, el único azar son los sorteos Poisson y binomiales. Sobre 33 millones de personas ese azar es tan pequeño que el año de inversión cae siempre en 2054. Para obtener una distribución del año, el `.ini` admite dos claves opcionales (por defecto 0):

```ini
sigma_fecundidad=0.05    # factor_fec  ~ N(1, 0.05)  multiplica f(a, y) durante todo el escenario
sigma_mortalidad=0.015   # factor_mort ~ N(1, 0.015) multiplica q(a, s), acotado a [0, 1]
```

Los dos factores se sortean una vez por escenario, antes de los 40 años, con el generador de ese escenario, y quedan registrados en `factores_escenarios.csv`. Con sigma = 0 no se consume ningún número aleatorio y la ejecución es idéntica byte a byte a la de referencia.

Ejemplo con `config_incertidumbre.ini` y 10 000 escenarios:

- media 2054,5 y desviación de 2,3 años;
- rango 2046–2065;
- 0,75 % de escenarios sin inversión en el horizonte;
- gráfico en `graficos_incertidumbre/06_distribucion_anio.png`.

Los sigmas son supuestos didácticos.

## Métricas de rendimiento

Cada ejecución mide y guarda en `resumen.txt` y `metricas.csv`:

| Métrica | Cómo se mide | Para qué sirve |
|---|---|---|
| Tiempo de pared (total y por fases) | `std::chrono::steady_clock`; en MPI, `MPI_Wtime` en el proceso 0 tras un `MPI_Barrier` | T1 y Tp del speedup S(p) = T1 / Tp |
| Tiempo de CPU | `std::clock`; suma todos los hilos en OpenMP y todos los procesos en MPI | CPU/pared ≈ P indica que todos trabajaron |
| Tiempo por escenario | T_simulación / R (ms) | Costo unitario; permite estimar Tp para cualquier R |
| Rendimiento (throughput) | R / T_simulación (escenarios/s) | Comparar ejecuciones con distinto R |
| Memoria pico (RSS) | `getrusage`; en MPI, el máximo por proceso | Comprobar que no crece con R y dimensionar los procesos MPI |
| Espera + comunicación (solo MPI) | Máximo, entre procesos, del tiempo desde que terminan su bloque hasta que concluye el `MPI_Gatherv` | Mide el desbalance más la comunicación |

En `metricas.csv`, la columna `version` vale `secuencial`, `openmp` o `mpi`, y `procesos`/`hilos` registran P.

### Línea base secuencial T1 (S9)

Desde `MonteCarlo_Secuencial/` (3 tamaños × 3 corridas, unos 17 minutos):

```bash
python3 scripts/linea_base.py --salida linea_base
python3 scripts/linea_base.py --solo-informe --salida linea_base   # rehace tabla y gráfico sin ejecutar
```

El resultado medido (Intel Xeon 2,8 GHz, g++ 13.3 -O2) está en `linea_base/linea_base.md`.

### Speedup de OpenMP y MPI (S10)

Desde `MonteCarlo_Paralelo/`. El script vuelve a medir T1 junto a cada Tp, intercalando las corridas en la misma máquina:

```bash
python3 scripts/rendimiento.py --escenarios 10000 --repeticiones 3 --salida rendimiento
# o en Docker:
docker run --rm -u mpi -v "$PWD/rendimiento:/out:z" montecarlo-demografia \
    python3 scripts/rendimiento.py --escenarios 10000 --repeticiones 3 --salida /out
```

Calcula:

- speedup S(p) = T1/Tp;
- eficiencia E(p) = S(p)/p;
- costo C(p) = p·Tp;
- fracción secuencial de Karp–Flatt f = (1/S − 1/p)/(1 − 1/p);
- cota de Amdahl S_máx = 1/f.

La medición de S10 está en `MonteCarlo_Paralelo/rendimiento/rendimiento.md` y se analiza en `docs/04_sprint3_paralelizacion.md`.

## Versión Go

`MonteCarlo_Go/` es una implementación secuencial en Go del mismo modelo. Se mantiene separada para comparar lenguaje, tiempo y memoria sin mezclar fuentes:

- `cmd/simulador/`: configuración, carga de datos, modelo y ejecutable;
- `datos/`: copia de los tres CSV de entrada;
- `config_demostracion.ini` y `config_incertidumbre.ini`: configuraciones equivalentes a las de C++.

Desde `MonteCarlo_Go/`, en Windows:

```powershell
go build -o simulador_go.exe ./cmd/simulador
.\simulador_go.exe --config config_incertidumbre.ini --datos datos --salida resultados_go --escenarios 10000
```

Usa las mismas ecuaciones demográficas, distribuciones Poisson y binomial exactas y formatos de salida. Go y C++ usan generadores y algoritmos aleatorios diferentes, así que los escenarios individuales no coinciden byte a byte. La comparación debe hacerse sobre la distribución agregada.

## Documentación Scrum

| Documento | Semana |
|---|---|
| `docs/01_product_backlog.md`: visión, roles, Definición de Hecho, backlog priorizado y criterios de aceptación | S4 |
| `docs/02_diseno_modelo_probabilistico.md`: estado, transiciones, incertidumbre macro, estimadores, semillas y supuestos | S5–S6 |
| `docs/03_validacion_linea_base.md`: verificación, coherencia estadística, convergencia Monte Carlo y T1 | S9 |
| `docs/04_sprint3_paralelizacion.md`: análisis de Foster, OpenMP, MPI, Docker, verificación y rendimiento | S10 |
| `docs/05_registro_scrum.md`: Sprint Planning y Review de los sprints 1–3 | S4–S10 |
