# Sprint 3 (S10–S12): paralelización con OpenMP, MPI y contenedores Docker

Código en `MonteCarlo_Paralelo/`; instrucciones de compilación y ejecución en el `README.md` de la raíz.

## 1. Análisis del paralelismo (metodología de Foster)

| Etapa | Decisión |
|---|---|
| **Particionamiento** | Descomposición de dominio sobre los R escenarios. Un escenario (40 años, ≈ 8 240 sorteos, ≈ 3 ms) es la tarea mínima. No se paraleliza dentro de un año: los sorteos de un escenario usan un único generador en orden fijo, y partirlo rompería la reproducibilidad sin aportar trabajo suficiente. |
| **Comunicación** | Ninguna durante la simulación. Los escenarios son independientes porque cada uno tiene su generador `mt19937_64` sembrado con `splitmix64(semilla + r)`. Al final se reúnen R enteros (primer año), más 2R reales si hay incertidumbre macro. |
| **Aglomeración** | OpenMP: bloques de 16 escenarios por pedido (`schedule(dynamic, 16)`, ≈ 50 ms de trabajo). MPI: un bloque contiguo por proceso. |
| **Mapeo** | OpenMP: un hilo por CPU lógica. MPI: un proceso por slot del `hostfile`; en el clúster, `--map-by node` reparte los procesos en round-robin entre los nodos. |

**Partes secuenciales que quedan (Amdahl):**

- lectura de los CSV (≈ 1 ms);
- escritura ordenada de `escenarios.csv` (R líneas) en un solo hilo o proceso;
- en MPI, el `MPI_Gatherv`.

Todas son O(R) muy baratas frente a la simulación, que es O(R·H) con ≈ 3 ms por escenario.

## 2. Refactorización previa (sin cambiar resultados)

Para que las tres versiones compartan exactamente el mismo modelo, se extrajeron dos módulos de `MonteCarlo_Secuencial/src/main.cpp`:

- `escenario.hpp/.cpp`: `simular_escenario(r, datos, config, trayectoria*)` devuelve el primer año de inversión y los factores macro del escenario r. `EscritorEscenarios` escribe `escenarios.csv` y `factores_escenarios.csv` en orden y acumula el histograma.
- `salida.hpp/.cpp`: argumentos, carpeta de salida, `distribucion.csv`, `resumen.txt`, SVG y `metricas.csv`.

`main.cpp` (secuencial) queda en ≈ 60 líneas y sigue escribiendo cada escenario apenas termina, así que su memoria no crece con R.

**Verificación del refactor:** se regeneraron `resultados_demo` (R = 1 000) y `resultados_incertidumbre` (R = 10 000) y se compararon con los committeados antes del cambio. Todos los CSV, el SVG y el resumen sin tiempos son **idénticos byte a byte**.

## 3. Versión OpenMP (`src/main_openmp.cpp`)

```cpp
std::vector<ResultadoEscenario> resultados(R);
#pragma omp parallel for schedule(dynamic, 16)
for (Conteo r = 0; r < R; ++r)
    resultados[r] = simular_escenario(r, datos, c, r == 0 ? &trayectoria : nullptr);
// despues, un hilo escribe los CSV en orden r = 0..R-1
```

- **Sin condiciones de carrera.** `datos` (población, tasas) es compartido y de solo lectura. El generador, la población del escenario y las tasas escaladas son locales de cada iteración. Cada hilo escribe solo en `resultados[r]`. La trayectoria del escenario 1 la escribe únicamente el hilo que ejecuta r = 0.
- **Excepciones.** No pueden salir de una región paralela, así que cada iteración las captura. La primera se guarda en una sección `critical` y se relanza al terminar el bucle.
- **Memoria.** 24 bytes por escenario (240 MB con R = 10⁷). Es el precio de escribir en orden y producir CSV idénticos al secuencial.
- **Planificación `dynamic`.** El costo por escenario es casi uniforme, pero `dynamic` absorbe la variación de los sorteos y la interferencia del sistema operativo (y del Hyper-Threading) sin un costo apreciable con bloques de 16.

## 4. Versión MPI (`src/main_mpi.cpp`)

1. `MPI_Init`. Cada proceso lee la configuración y los CSV: son pocos KB y así se evita un broadcast.
2. El proceso 0 crea la carpeta de salida y comunica el éxito o fracaso con `MPI_Bcast`, para que todos se detengan juntos si la carpeta ya existe.
3. **Reparto por bloques.** El proceso k simula [inicio_k, fin_k), con tamaños ⌊R/p⌋ o ⌈R/p⌉. El escenario 1 siempre cae en el proceso 0, que es el que escribe la trayectoria.
4. **Sin comunicación durante la simulación.**
5. Un `MPI_Gatherv` lleva el primer año de cada escenario (`MPI_INT`) y, con incertidumbre macro, otro lleva 2 `MPI_DOUBLE` por escenario. Ambos usan la misma función `reunir()`, con conteos y desplazamientos por bloque.
6. Con `MPI_Reduce` se agregan la CPU (suma), la memoria pico (máximo) y el tiempo de espera + comunicación (máximo).
7. El proceso 0 escribe los CSV en orden, con el mismo `EscritorEscenarios` que el secuencial.

**Errores:** una excepción en cualquier proceso llama a `MPI_Abort`, para que los demás no queden bloqueados en el `Gatherv`. Se probó con una carpeta de datos inexistente y con una carpeta de salida repetida.

**Tiempos:** se miden con `MPI_Wtime` en el proceso 0, después de un `MPI_Barrier`, para que todos partan a la vez. No incluyen el arranque de `mpirun`.

## 5. Contenedores Docker y clúster

- **`docker/Dockerfile`** (Ubuntu 24.04, g++ 13, OpenMPI 4.1.6, OpenSSH). Compila las tres versiones y **corre las 14 pruebas durante la construcción**: si fallan, no hay imagen. El usuario `mpi` tiene UID 1000 para escribir en el volumen de resultados.
- **`docker-compose.yml`**: 4 nodos (`nodo1` … `nodo4`) en la red `cluster`, con 2 CPU cada uno y SSH sin contraseña entre ellos. `nodo1` es el maestro y monta `./resultados_cluster`.
- **Ajustes de OpenMPI dentro de contenedores:**
  - `btl_vader_single_copy_mechanism=none`: Docker restringe `ptrace`, que necesita CMA;
  - `btl_tcp_if_include=eth0` y `oob_tcp_if_include=eth0`: la comunicación va solo por la red del clúster.
- **Ejecución:** `./docker/ejecutar_cluster.sh 8 10000` lanza `mpirun --hostfile hostfile -np 8 --map-by node`, con 2 procesos en cada uno de los 4 nodos.

## 6. Verificación de correctitud

`scripts/verificar_equivalencia.sh` corre el secuencial y luego OpenMP con 1, 2, 3 y 8 hilos y MPI con 1, 2, 3 y 4 procesos. Se usan tanto tasas fijas como incertidumbre macro, y se comparan con `cmp` `escenarios.csv`, `distribucion.csv`, `trayectoria_escenario_1.csv` y `factores_escenarios.csv`:

```
== config_demostracion.ini, 300 escenarios ==
  [OK] OpenMP 1/2/3/8 hilos ... identicos
  [OK] MPI 1/2/3/4 procesos ... identicos
== config_incertidumbre.ini, 300 escenarios ==
  [OK] OpenMP 1/2/3/8 hilos ... identicos
  [OK] MPI 1/2/3/4 procesos ... identicos
Equivalencia: OK (OpenMP y MPI reproducen exactamente la version secuencial)
```

Los conteos 3 (hilos) y 3 (procesos) prueban repartos desiguales, porque R no es múltiplo de p. También se probaron:

- **Clúster Docker** (8 procesos en 4 nodos, R = 2 000, con incertidumbre): los 4 CSV son idénticos a los del secuencial.
- **R < p** (R = 1, 2 procesos): el proceso 1 queda con un bloque vacío y el resultado es correcto.

## 7. Rendimiento

Medido con `scripts/rendimiento.py` dentro del contenedor (sin límite de CPU). Los datos crudos, la tabla y el gráfico están en `MonteCarlo_Paralelo/rendimiento/` (`rendimiento.png` muestra el speedup y la eficiencia).

- **Equipo:** Intel Core i5-9300H (4 núcleos físicos, 8 hilos con Hyper-Threading, turbo hasta 4,1 GHz), g++ 13.3 -O2, Open MPI 4.1.6.
- **Ejecución:** R = 10 000 escenarios con tasas fijas y 3 repeticiones intercaladas. T es el tiempo total de pared (media ± sd).

| Versión | p | Tp (s) | S(p) | E(p) | C(p) (s) | Karp-Flatt f | CPU/pared | Espera+Gatherv (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| secuencial | 1 | 25,25 ± 0,22 | 1,00 | 1,00 | 25,3 | — | 1,00 | — |
| OpenMP | 1 | 25,58 ± 0,38 | 0,99 | 0,99 | 25,6 | — | 1,00 | — |
| OpenMP | 2 | 13,17 ± 0,16 | 1,92 | 0,96 | 26,3 | 0,043 | 1,99 | — |
| OpenMP | 4 | 7,78 ± 0,43 | 3,25 | 0,81 | 31,1 | 0,077 | 3,97 | — |
| OpenMP | 8 | 6,82 ± 0,42 | 3,70 | 0,46 | 54,6 | 0,166 | 7,16 | — |
| MPI | 1 | 25,96 ± 0,37 | 0,97 | 0,97 | 26,0 | — | 1,00 | 0,000 |
| MPI | 2 | 13,67 ± 0,31 | 1,85 | 0,92 | 27,3 | 0,082 | 2,00 | 0,093 |
| MPI | 4 | 9,06 ± 0,62 | 2,79 | 0,70 | 36,3 | 0,145 | 3,97 | 0,249 |
| MPI | 8 | 9,23 ± 0,48 | 2,73 | 0,34 | 73,9 | 0,275 | 6,98 | 0,398 |

**Interpretación**

1. **El costo de paralelizar con un solo trabajador es mínimo.** OpenMP y MPI con p = 1 tardan entre 1 % y 3 % más que el secuencial: el vector de resultados y la escritura al final (OpenMP) y la inicialización de MPI.
2. **Hasta 2 hilos o procesos el escalado es casi lineal** (E ≈ 0,92–0,96).
3. **Con 4, la pérdida de eficiencia no se debe a código secuencial ni a esperas.** CPU/pared ≈ 3,97 indica que los 4 trabajadores estuvieron ocupados todo el tiempo. Además, la parte secuencial real (leer los CSV, ≈ 1 ms, y escribir 10 000 líneas, unos ms) es mucho menor que el f ≈ 0,08 de Karp-Flatt. Lo que baja es la velocidad de cada núcleo cuando trabajan todos: el turbo del i5-9300H baja de frecuencia con más núcleos activos y la L3 es compartida. Por eso el f de Karp-Flatt crece con p sin que haya comunicación.
4. **Con p = 8 se pasa del número de núcleos físicos (4).** El Hyper-Threading le aporta solo un 14 % más a OpenMP (3,25 → 3,70) y nada a MPI. E(8) = 0,46 es esperable. Respecto de los 4 núcleos físicos, OpenMP con 8 hilos rinde S/4 = 0,93.
5. **MPI rinde menos que OpenMP con p = 4 (2,79 frente a 3,25).**
   - La espera + Gatherv (0,25 s, ≈ 3 % de Tp) refleja el desbalance del reparto estático: el proceso más lento fija el tiempo. OpenMP no lo sufre gracias a `schedule(dynamic)`. Mover 10 000 enteros cuesta microsegundos, así que ese tiempo es casi todo espera.
   - Eso no explica toda la diferencia (≈ 1,3 s). Se probó fijar cada proceso a un núcleo (`--map-by core --bind-to core`) y no mejoró: hubo corridas de 9,4–11,2 s con y sin binding.
   - La dispersión entre corridas de MPI (sd ≈ 0,6 s) es alta en este portátil. Queda como pregunta abierta para el análisis de S13, en un equipo sin turbo variable.
6. **Advertencia sobre el clúster Docker.** Los 4 nodos de `docker-compose.yml` comparten las mismas 8 CPU del anfitrión. El clúster demuestra la ejecución distribuida (SSH, hostfile, comunicación TCP entre contenedores) y su correctitud, pero **no** sirve para medir speedup entre máquinas. Las cifras de esta sección son de un solo contenedor.
7. **Proyección a R = 10⁷ (S12) en este equipo:** ≈ 7 h en secuencial (2,5 ms por escenario) y ≈ 1,9 h con OpenMP de 8 hilos. Reducir más el tiempo exige más núcleos físicos (varios nodos con la versión híbrida de S11).

> T1 de este equipo (25,25 s para R = 10⁴) no es comparable con el T1 del Xeon de `linea_base/` (32,94 s). Cada speedup se calcula con T1 y Tp medidos en la misma máquina.

## 8. Versión Híbrida MPI + OpenMP (S11)

Implementada en `MonteCarlo_Paralelo/src/main_hibrido.cpp` (`simulador_hibrido`):

- **Arquitectura jerárquica:**
  1. $P$ procesos MPI para memoria distribuida (entre nodos del clúster o contenedores).
  2. Dentro de cada proceso, $H$ hilos OpenMP de memoria compartida procesan los escenarios del bloque local mediante `#pragma omp parallel for schedule(dynamic, 16)`.
- **Inicialización de hilos en MPI:**  
  Usa `MPI_Init_thread(&argc, &argv, MPI_THREAD_FUNNELED, &proporcionado)`, garantizando que el proceso es multihilo pero solo el hilo maestro efectúa llamadas MPI (`MPI_Barrier`, `MPI_Gatherv`, `MPI_Reduce`, etc.).
- **Mapeo y paso de argumentos:**  
  Admite `--hilos H` para dimensionar el pool de hilos dentro de cada proceso MPI (por defecto toma `OMP_NUM_THREADS` o los cores asignados).
- **Correctitud y reproducibilidad:**  
  Al compartir la misma fórmula de semillas `splitmix64(semilla + r)`, `simulador_hibrido` produce resultados byte a byte idénticos a los del secuencial, OpenMP y MPI puro para cualquier combinación $P \times H$.

## 9. Ejecución de 10 millones de escenarios (S12)

Corrida de PB-09 en el clúster Docker de 4 nodos (2 CPU por nodo), con un proceso MPI por nodo y 2 hilos OpenMP por proceso:

```bash
cd MonteCarlo_Paralelo
docker compose up -d --build
./docker/ejecutar_cluster.sh 4 10000000 config_incertidumbre.ini 2   # procesos, escenarios, config, hilos
```

El cuarto argumento hace que el script use `simulador_hibrido` con `--bind-to none` y `--hilos`. Los archivos pequeños de la corrida están en `MonteCarlo_Paralelo/resultados_10000000/`.

| Métrica | Valor |
|---|---|
| Procesos × hilos | 4 × 2 (8 núcleos) |
| Tiempo de pared (Tp) | 2 188,1 s (36,5 min) |
| Tiempo de CPU | 17 280,7 s (CPU/pared = 7,90) |
| Rendimiento | 4 570 escenarios/s (0,219 ms por escenario) |
| Memoria pico por proceso | 254 MiB |
| Espera + comunicación (`MPI_Gatherv`) | 12,2 s (0,56 % de Tp) |

Resultado estadístico (9 934 770 escenarios con inversión):

- media del año de inversión 2054,504, desviación 2,304 años, rango 2043–2065;
- error estándar de la media 0,00073 años; IC 95 %: 2054,5027–2054,5056;
- sin inversión en el horizonte: 65 230 de 10 000 000 (0,652 %; error estándar 0,0025 puntos porcentuales);
- probabilidad acumulada: 2,5 % a 2050, 52,4 % a 2054, 89,9 % a 2057 y 98,3 % a 2060.

Observaciones:

1. **Correctitud.** El primer millón de filas de `escenarios.csv` y `factores_escenarios.csv` es idéntico byte a byte al de la corrida de 1 000 000 hecha con OpenMP (`MonteCarlo_Secuencial/resultados_1000000/`), y `make verificar` pasa 20 de 20 comparaciones en el clúster.
2. **Escritura completa.** Se escribieron los CSV completos: `escenarios.csv` (149 MB) y `factores_escenarios.csv` (327 MB). No se versionan porque superan el límite de 100 MB por archivo de GitHub; quedan en `resultados_cluster/` (ignorada por git) y se regeneran con el comando de arriba.
3. **Memoria.** El pico sube de ≈ 15 MiB a 254 MiB porque el proceso 0 reúne los 10⁷ resultados antes de escribirlos; sigue siendo holgado para este equipo.
4. **Speedup.** No se midió T1 con R = 10⁷ (serían varias horas), así que no se reporta un speedup directo de esta corrida. El dato medido es CPU/pared = 7,90: los 8 núcleos trabajaron casi todo el tiempo. El análisis de speedup y eficiencia queda para PB-10 (S13).
5. **Finales de línea.** En Windows, `hostfile` se extraía con CRLF y OpenMPI no podía leerlo dentro del contenedor. `.gitattributes` fija ahora LF para `hostfile`, `Makefile`, `Dockerfile` y `*.ini`.
6. **Muestreo rápido.** La misma corrida con `--muestreo rapido` tarda 6,4 min en lugar de 36,5 (sección 9.1).

### 9.1. Modo de muestreo rápido (`--muestreo rapido`)

El perfil de la corrida anterior muestra que casi todo el tiempo se va en los ≈ 8 000 sorteos binomiales por escenario hechos con `std::binomial_distribution`, que recalcula sus constantes (logaritmos y `lgamma`) en cada sorteo. La opción `--muestreo rapido`, disponible en los cuatro ejecutables, cambia tres cosas:

1. **Binomial exacta de bajo costo** (`sorteo_binomial_rapido` en `modelo.cpp`): inversión secuencial si $n \cdot \min(p, 1-p) < 10$ y rechazo transformado BTRS (Hörmann, 1993) en otro caso. BTRS acepta ≈ 86 % de los sorteos con dos uniformes y sin evaluar logaritmos. No es una aproximación normal: la distribución es la misma binomial.
2. **Corte en la primera inversión.** El resultado de un escenario no depende de los años posteriores a su primera inversión, así que el escenario termina ahí (salvo el escenario 1, que escribe la trayectoria completa).
3. **Controles sin asignación de memoria.** `exigir` tiene una variante para mensajes literales que no construye un `std::string` cuando la condición se cumple. Este cambio aplica también al modo estándar y no altera sus resultados.

El modo estándar sigue siendo el predeterminado y **no cambia**: reproduce byte a byte los CSV publicados (comprobado con los 10 000 escenarios de `MonteCarlo_Secuencial/resultados_incertidumbre/`) y `make verificar` pasa 20 de 20. El modo rápido consume otra secuencia de números aleatorios: sus resultados son estadísticamente equivalentes, no idénticos escenario a escenario. Dentro del modo rápido, secuencial, OpenMP, MPI e híbrido siguen siendo idénticos entre sí.

```bash
./docker/ejecutar_cluster.sh 4 10000000 config_incertidumbre.ini 2 rapido   # quinto argumento: muestreo
```

Misma máquina y mismo clúster (4 nodos × 2 CPU) que la corrida estándar; archivos pequeños en `MonteCarlo_Paralelo/resultados_10000000_rapido/`:

| Métrica | Estándar | Rápido |
|---|---:|---:|
| Tiempo de pared (Tp) | 2 188,1 s (36,5 min) | 383,7 s (6,4 min) |
| Tiempo de CPU | 17 280,7 s | 2 763,8 s |
| Rendimiento | 4 570 escenarios/s | 26 064 escenarios/s |
| Un hilo, 20 000 escenarios | 1,64 ms por escenario | 0,21 ms por escenario |
| Media del año de inversión | 2054,5041 | 2054,5041 |
| Desviación | 2,3038 | 2,3040 |
| Sin inversión | 65 230 (0,652 %) | 65 172 (0,652 %) |

La mayor diferencia de probabilidad anual entre ambas distribuciones es 4,9 × 10⁻⁵. Las dos corridas no son muestras independientes: comparten la semilla y, por tanto, los factores macro de cada escenario, que explican la mayor parte del año de inversión; por eso coinciden más de lo que cabría esperar por azar. La validación de la binomial rápida contra la función de masa exacta está en las pruebas P13 y P14 de `--self-test`.

De los 383,7 s, cerca de un minuto es la escritura ordenada de los CSV por el proceso 0, que ahora pesa proporcionalmente más.

**Con todos los hilos del equipo y `-O3`.** `docker-compose.yml` y el `Dockerfile` aceptan dos variables opcionales, `CPUS_POR_NODO` (por defecto 2) y `OPTIMIZACION` (por defecto `-O2`); los valores por defecto son los de las mediciones publicadas. En un equipo de 8 núcleos y 16 hilos (Ryzen 7 7735HS):

```bash
CPUS_POR_NODO=4 OPTIMIZACION="-O3 -march=native -ffp-contract=off" docker compose up -d --build
./docker/ejecutar_cluster.sh 4 10000000 config_incertidumbre.ini 4 rapido   # 4 nodos x 4 hilos
```

| Configuración (muestreo rápido, R = 10⁷) | Tp | CPU | Escenarios/s |
|---|---:|---:|---:|
| 4 × 2 hilos, `-O2` | 383,7 s (6,4 min) | 2 763,8 s | 26 064 |
| 4 × 4 hilos, `-O3 -march=native` | 243,1 s (4,1 min) | 3 297,5 s | 41 130 |

Los CSV de las dos corridas rápidas son idénticos byte a byte entre sí, y con estos flags el modo estándar sigue reproduciendo los CSV publicados (`make verificar`, 20 de 20). `-ffp-contract=off` impide que el compilador fusione multiplicación y suma (FMA), que podría alterar el redondeo; `-march=native` ata el binario al procesador donde se construye la imagen. Pasar de 8 a 16 hilos rinde 1,6× y no 2× porque los 16 hilos lógicos comparten 8 núcleos físicos y la escritura de los CSV sigue siendo secuencial.

## 10. Versiones CUDA y MPI + CUDA (extra)

`simulador_cuda` ejecuta **un hilo de GPU por escenario**. Es la misma descomposición de datos de OpenMP y MPI (los escenarios son independientes y cada uno tiene su generador), con miles de hilos en lugar de 8 o 16. No forma parte de `make all` ni de `make verificar`.

| Archivo | Contenido |
|---|---|
| `MonteCarlo_Paralelo/src/nucleo_cuda.hpp` | Escenario completo en funciones `__host__ __device__`, sin memoria dinámica ni biblioteca estándar: el mismo código corre en la GPU y en la CPU |
| `MonteCarlo_Paralelo/src/gpu.cu` | Kernels (`kernel_lote`, `kernel_trayectoria`), memoria de la GPU y copias; se compila con `nvcc` |
| `MonteCarlo_Paralelo/src/main_cuda.cpp` | Lotes, escritura ordenada de los CSV con el código común y pruebas; se compila con `g++` |
| `MonteCarlo_Paralelo/src/main_mpi_cuda.cpp` | Versión heterogénea MPI + CUDA + OpenMP (sección 10.5) |
| `MonteCarlo_Paralelo/docker/Dockerfile.cuda`, `docker/ejecutar_cuda.sh` | Imagen `nvidia/cuda:12.6.3-devel-ubuntu24.04` con OpenMPI y ejecución con `--gpus all` |

```bash
cd MonteCarlo_Paralelo
./docker/ejecutar_cuda.sh pruebas      # pruebas del modelo, de los sorteos y GPU = CPU
./docker/ejecutar_cuda.sh 10000000     # solo GPU; resultados en resultados_cuda/
./docker/ejecutar_cuda.sh 10000000 config_incertidumbre.ini 4 5   # MPI + CUDA: GPU + 3 procesos x 5 hilos
```

### 10.1. Diferencias con las versiones de CPU

1. **Generador.** `std::mt19937_64` no existe en la GPU y su estado ocupa 2,5 KiB por hilo. Cada escenario usa un xoroshiro128++ (16 bytes) sembrado con `splitmix64(semilla + r)`. Por eso los resultados son **estadísticamente equivalentes** a los de la CPU, no idénticos escenario a escenario.
2. **Sorteos.** Mismo modelo y mismos algoritmos que `--muestreo rapido` (binomial por inversión/BTRS, corte en la primera inversión), más una Poisson por rechazo transformado PTRS (Hörmann, 1993) para los nacimientos.
3. **Precisión.** La función de masa se evalúa en doble precisión, pero las propuestas de BTRS se generan en precisión simple (24 bits por uniforme), lo que limita la resolución de cada clase a ≈ 10⁻⁴ relativo. En la CPU todo es doble precisión.
4. **Trayectoria.** `trayectoria_escenario_1.csv` se calcula también en la GPU, con un kernel de un solo hilo que simula el horizonte completo.

### 10.2. Por qué hubo que reorganizar el sorteo

La primera versión, que trasladaba el código de la CPU tal cual, rendía 20 500 escenarios/s: la mitad que la CPU con 16 hilos. Dos causas, las dos propias de la GPU:

- **Doble precisión.** Las tarjetas de consumo tienen muy poca capacidad de cómputo en 64 bits frente a la de 32 bits.
- **Divergencia de ramas.** Los 32 hilos de un *warp* ejecutan la misma instrucción. BTRS acepta ≈ 86 % de los sorteos sin logaritmos, pero la probabilidad de que los 32 hilos acepten a la vez es 0,86³² ≈ 0,8 %: casi todos los sorteos pagaban la rama lenta completa.

La versión final calcula la propuesta y la aceptación inmediata en precisión simple y **aplaza** la comparación con la función de masa: en cada año, una primera pasada resuelve los 204 sorteos que se aceptan de inmediato y deja pendientes los demás; una segunda pasada resuelve los pendientes, una comparación en doble precisión por vuelta. La rama lenta se ejecuta así unas 30 a 50 veces por año en lugar de interrumpir cada uno de los 204 sorteos. Resultado: 78 000 escenarios/s en la GPU (3,8× sobre la primera versión).

### 10.3. Resultados (R = 10⁷, RTX 4050 Laptop de 6 GB)

Archivos pequeños en `MonteCarlo_Paralelo/resultados_10000000_cuda/`.

| Versión | Tp | Escenarios/s |
|---|---:|---:|
| Híbrido 4 × 2, estándar (sección 9) | 2 188,1 s (36,5 min) | 4 570 |
| Híbrido 4 × 4, rápido, `-O3 -march=native` (sección 9.1) | 243,1 s (4,1 min) | 41 130 |
| CUDA | 158,2 s (2,6 min) | 63 227 |
| MPI + CUDA + OpenMP, 4 procesos × 5 hilos (sección 10.5) | 123,1 s (2,1 min) | 81 223 |

De los 158,2 s, 116,9 s son cómputo en la GPU (lotes de 262 144 escenarios) y el resto es la escritura ordenada de los CSV en el anfitrión, igual que en las demás versiones. Memoria pico del proceso: 374 MiB.

Comparación con la corrida estándar de la sección 9. A diferencia de la corrida rápida de CPU, aquí las dos muestras **sí son independientes** (otro generador, otros factores macro), así que las pruebas son informativas:

| Estadístico | CPU estándar | CUDA | Contraste |
|---|---:|---:|---|
| Media del año de inversión | 2054,5041 | 2054,5043 | z = +0,12 |
| Desviación | 2,3038 | 2,3039 | — |
| Sin inversión | 65 230 | 64 483 | z = −2,08 |
| Distribución por año | — | — | χ² = 19,9 con 22 g. l. |

La distribución completa y la media son compatibles. El conteo de escenarios sin inversión queda en el límite (z = −2,08, p ≈ 0,04 en una prueba aislada de tres); se reporta tal cual y conviene repetir la corrida con otra semilla antes de darlo por descartado.

### 10.4. Pruebas

`./simulador_cuda --self-test --config ...` ejecuta las 14 pruebas del modelo y cinco propias:

- **C1–C3:** binomial, Poisson (λ = 4, 30 y 512 939) y normal del núcleo contra su distribución exacta (ji-cuadrado, 400 000 sorteos por caso), ejecutadas en la CPU.
- **C4:** 4 096 escenarios simulados con el mismo código en la GPU y en la CPU. Los 4 096 dan el mismo año de inversión. Los factores macro coinciden bit a bit en 4 069; en los otros 27 difieren en el último bit (2,2 × 10⁻¹⁶), porque el logaritmo y el coseno de la GPU y de la CPU no redondean igual. Esa diferencia no llega a los CSV, que se escriben con 10 cifras. Se exige ≥ 99 % de años iguales y diferencia de factores < 10⁻¹².
- **C5:** la trayectoria calculada en la GPU cumple el balance exacto cada año.

### 10.5. MPI + CUDA + OpenMP: reparto heterogéneo

`simulador_mpi_cuda` combina los tres modelos: el proceso 0 simula su bloque en la GPU y los procesos 1..P−1 simulan los suyos en la CPU con H hilos OpenMP cada uno. Solo el proceso 0 toca la GPU y solo él escribe.

1. **Mismo núcleo en todos los procesos.** Todos ejecutan `nucleo_cuda.hpp`; el escenario r usa el generador sembrado con `splitmix64(semilla + r)` lo simule quien lo simule. Por eso el resultado no depende del reparto: los CSV de la corrida MPI + CUDA de 10⁷ escenarios (2,8 millones simulados en CPU) son idénticos byte a byte a los de la corrida solo-GPU.
2. **Balanceo por calibración.** Los recursos no son iguales, así que los bloques tampoco. Cada proceso mide su velocidad en una calibración corta (131 072 escenarios la GPU, 2 500 por hilo la CPU, todos a la vez) y los R escenarios se reparten en bloques contiguos proporcionales, con `MPI_Allgather` para compartir las velocidades. `MC_PESO_GPU` fija el reparto a mano.
3. **Comunicación.** `MPI_Gatherv` con conteos distintos por proceso reúne los resultados en el proceso 0, como en la versión híbrida.

Corrida de 10⁷ escenarios con 4 procesos × 5 hilos (archivos en `MonteCarlo_Paralelo/resultados_10000000_mpi_cuda/`):

| Proceso | Escenarios | Velocidad calibrada | Cómputo |
|---|---:|---:|---:|
| 0 (GPU) | 7 171 384 (71,7 %) | 83 346 esc/s | 83,1 s |
| 1 (CPU, 5 hilos) | 927 218 (9,3 %) | 10 776 esc/s | 67,4 s |
| 2 (CPU, 5 hilos) | 953 513 (9,5 %) | 11 082 esc/s | 69,2 s |
| 3 (CPU, 5 hilos) | 947 885 (9,5 %) | 11 016 esc/s | 67,4 s |

Tiempo total 123,1 s (calibración 4,1 s, espera + `MPI_Gatherv` 15,9 s, memoria pico 490 MiB), 1,28× sobre la GPU sola. El balance no es perfecto: la calibración subestima a la CPU (rindió ≈ 13 800 esc/s en la corrida frente a ≈ 11 000 calibrados), de modo que los procesos de CPU terminan unos 15 s antes y esperan a la GPU. Con el reparto ideal el cómputo bajaría de ≈ 83 s a ≈ 78 s; un reparto dinámico (el proceso 0 entrega bloques pequeños bajo demanda) lo corregiría a costa de más comunicación.

### 10.6. Limitaciones

- Los procesos MPI de `simulador_mpi_cuda` corren en un solo contenedor con una sola GPU. No se probó en el clúster de 4 contenedores ni con varias GPU; con más tarjetas, cada proceso con GPU tomaría la suya con el mismo esquema de reparto.
- Con calibración, el tamaño de los bloques varía un poco de una corrida a otra; los resultados no, porque no dependen del reparto.
- La imagen de desarrollo de CUDA pesa varios GB y requiere una GPU NVIDIA con Docker configurado para usarla.
