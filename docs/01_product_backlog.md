# Product Backlog

**Proyecto:** Inversión demográfica del Perú · Monte Carlo con MPI y OpenMP
**Curso:** Programación Paralela y Concurrente
**Producto:** simulador que estima la distribución de probabilidad del primer año en que la población de 65 años o más (A) supera a la de menores de 15 (J), y que escala a 10 millones de escenarios con MPI + OpenMP.

## Visión

Responder con una distribución, no con un año único: *¿con qué probabilidad ocurre la inversión demográfica antes de cada año?* El volumen de cálculo, del orden de 10⁷ escenarios × 40 años × 202 celdas edad-sexo, justifica la paralelización. El producto incluye la medición rigurosa del speedup conseguido.

## Roles

| Rol | Responsabilidad |
|---|---|
| Product Owner | Prioriza el backlog y acepta los incrementos (criterios de aceptación) |
| Scrum Master | Facilita Planning, Daily, Review y Retrospectiva; elimina impedimentos |
| Equipo de desarrollo | Datos, modelo, implementación, paralelización, pruebas e informe |

## Definición de Hecho (DoD)

Un ítem está **hecho** cuando:

1. Compila sin advertencias con `-Wall -Wextra -Wpedantic`.
2. Pasan las 12 pruebas controladas (`--self-test`).
3. Con la misma semilla, los CSV de resultados son reproducibles (y, desde S10, idénticos byte a byte entre las versiones secuencial, OpenMP y MPI).
4. Está documentado en el `README.md` de la raíz y, si cambia el diseño, en `docs/`.
5. Está versionado en git.

## Backlog priorizado

Prioridad: 1 = más alta. Estimación en puntos de historia (Fibonacci). El estado corresponde al cierre de la semana 10.

| ID | Historia de usuario | Prioridad | Puntos | Sprint | Semana | Estado |
|---|---|:-:|:-:|:-:|:-:|---|
| PB-01 | Como equipo, quiero un Product Backlog priorizado con criterios de aceptación para planificar los sprints | 1 | 2 | 1 | S4 | Hecho (este documento) |
| PB-02 | Como analista, quiero los CSV de población, fecundidad y mortalidad validados y convertidos a edades simples para alimentar el modelo | 1 | 5 | 1 | S4–S5 | Hecho |
| PB-03 | Como analista, quiero un modelo probabilístico explícito (variables, distribuciones, supuestos) para que la simulación sea verificable | 1 | 8 | 1 | S5–S6 | Hecho |
| PB-04 | Como usuario, quiero una implementación secuencial en C++17 que simule R escenarios y estime p(T = y) | 1 | 8 | 2 | S7 | Hecho |
| PB-05 | Como evaluador, quiero pruebas con resultado conocido y una línea base T1 medida para validar el modelo y comparar el speedup | 1 | 5 | 2 | S9 | Hecho |
| PB-06 | Como usuario, quiero una versión OpenMP que reparta los escenarios entre hilos con los mismos resultados que la secuencial | 1 | 5 | 3 | S10 | Hecho |
| PB-07 | Como usuario, quiero una versión MPI ejecutable en un clúster de contenedores Docker con los mismos resultados que la secuencial | 1 | 8 | 3 | S10 | Hecho |
| PB-08 | Como usuario, quiero una versión híbrida MPI + OpenMP (procesos entre nodos, hilos dentro de cada nodo) | 1 | 5 | 3 | S11 | Pendiente |
| PB-09 | Como investigador, quiero ejecutar 10 millones de escenarios y obtener la distribución del año de inversión | 1 | 5 | 3 | S12 | Pendiente |
| PB-10 | Como evaluador, quiero un análisis de resultados y de rendimiento (speedup, eficiencia, Karp-Flatt, Amdahl) | 2 | 5 | 4 | S13 | Pendiente (S10 deja el script y la primera medición) |
| PB-11 | Como docente, quiero un informe final con correcciones | 2 | 5 | 4 | S13–S14 | Pendiente |
| PB-12 | Como equipo, quiero diapositivas y un ensayo de la presentación | 3 | 3 | 4 | S14 | Pendiente |
| PB-13 | Como usuario, quiero una interfaz gráfica para lanzar simulaciones y ver la distribución | 3 | 3 | — | — | Hecho (extra: `interfaz.py`) |
| PB-14 | Como equipo, quiero una implementación alternativa en Go para contrastar lenguaje, tiempo y memoria | 4 | 3 | — | — | Hecho (extra: `MonteCarlo_Go`) |

## Criterios de aceptación

**PB-02 Datos.** `scripts/limpieza_datos.py` produce `datos_procesados/` y un reporte sin fallas. La desagregación a edades simples conserva el total exacto (32 706 028). Los supuestos sin ficha técnica quedan listados como pendientes.

**PB-03 Modelo.** Cada variable aleatoria tiene una distribución y parámetros documentados (`docs/02_diseno_modelo_probabilistico.md`). El balance P(t+1) = P(t) + B − D se cumple de forma exacta. El evento de inversión está definido sin ambigüedad (A > J; el empate no cuenta).

**PB-04 Secuencial.** Un solo ejecutable lee `.ini` + CSV y escribe `escenarios.csv`, `distribucion.csv`, `resumen.txt`, `metricas.csv` y el gráfico SVG. La misma semilla da la misma salida.

**PB-05 Validación y línea base.** Pasan 12 de 12 pruebas controladas. T1 está medido con 3 repeticiones para R = 10³, 10⁴ y 10⁵ y documentado (`docs/03_validacion_linea_base.md`).

**PB-06 OpenMP.** `simulador_omp --hilos P` reproduce byte a byte los CSV del secuencial para P = 1, 2, 3 y 8. Se reportan S(p) y E(p).

**PB-07 MPI + Docker.** `mpirun -np P simulador_mpi` reproduce byte a byte los CSV del secuencial para P = 1, 2, 3 y 4. `docker compose up` levanta un clúster de 4 nodos y `docker/ejecutar_cluster.sh` corre el simulador repartido entre ellos.

**PB-08 Híbrido.** Con p procesos × h hilos se obtienen CSV idénticos al secuencial y se compara contra MPI puro con el mismo total de núcleos.

**PB-09 10⁷ escenarios.** La corrida termina, `metricas.csv` registra el tiempo y la memoria, y se reporta el error estándar de la media del año de inversión.
