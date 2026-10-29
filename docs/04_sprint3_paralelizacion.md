# Sprint 3, semana 10: paralelización con OpenMP, MPI y contenedores Docker

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

- **`docker/Dockerfile`** (Ubuntu 24.04, g++ 13, OpenMPI 4.1.6, OpenSSH). Compila las tres versiones y **corre las 12 pruebas durante la construcción**: si fallan, no hay imagen. El usuario `mpi` tiene UID 1000 para escribir en el volumen de resultados.
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

## 8. Pendiente para S11–S12

- **S11, híbrido MPI + OpenMP.** Dentro del bloque de cada proceso, el bucle se reparte con el mismo `#pragma omp parallel for` (`MPI_Init_thread` con `MPI_THREAD_FUNNELED`, porque solo el hilo maestro llama a MPI). Habrá que comparar p × h frente a MPI puro con los mismos núcleos.
- **S12, R = 10⁷.** Con 10⁷ escenarios, `escenarios.csv` ocupa ≈ 190 MB. Hay que evaluar si se escribe completo o solo el histograma, para que la parte secuencial no limite el speedup (Amdahl).
