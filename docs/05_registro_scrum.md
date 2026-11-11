# Registro de ceremonias Scrum (S4–S12)

Calendario según el cronograma (`docs/cronograma.png`): Sprint 1 = S4–S6; Sprint 2 = S7–S9, con pausa en S8 por exámenes parciales; Sprint 3 = S10–S12; Sprint 4 = S13–S14; presentación en S15. El Daily Scrum es una reunión breve en días de trabajo; no hay reuniones en S8.

> Las secciones **[completar por el equipo]** recogen lo que se dijo en cada reunión (asistentes, impedimentos, acuerdos de la retrospectiva). Este registro solo documenta lo verificable en el repositorio: objetivos, ítems e incrementos.

---

## Sprint 1 (S4–S6): datos y modelo

### Sprint Planning (S4)

- **Objetivo del sprint:** tener datos de entrada confiables y un modelo probabilístico explícito y verificable.
- **Sprint backlog:** PB-01 Product Backlog (S4), PB-02 Recopilación y limpieza de datos (S4–S5), PB-03 Diseño del modelo probabilístico (S5–S6).
- Asistentes y capacidad: **[completar por el equipo]**

### Sprint Review y Retrospectiva (S6)

**Incremento demostrado:**

- `docs/01_product_backlog.md`: backlog priorizado con criterios de aceptación y Definición de Hecho.
- `scripts/limpieza_datos.py` → `datos_procesados/`: 28 comprobaciones (27 OK, 1 aviso, 0 fallas) y desagregación a edades simples que conserva el total.
- `docs/02_diseno_modelo_probabilistico.md`: estado, transiciones Poisson/binomiales, evento A > J, estimadores y estrategia de semillas por escenario.

**Retrospectiva:** qué salió bien / qué mejorar / acciones: **[completar por el equipo]**

---

## Sprint 2 (S7–S9): implementación secuencial y línea base

### Sprint Planning (S7)

- **Objetivo del sprint:** contar con una implementación secuencial correcta y medida, que sirva de referencia (T1) para la paralelización.
- **Sprint backlog:** PB-04 Implementación secuencial (S7) y PB-05 Validación y línea base (S9). En S8 no hubo actividades (exámenes parciales).
- Asistentes y capacidad: **[completar por el equipo]**

### Sprint Review y Retrospectiva (S9)

**Incremento demostrado:**

- `MonteCarlo_Secuencial/`: simulador C++17 modular, 12 pruebas controladas, salida CSV/SVG y métricas de rendimiento.
- Incertidumbre macro opcional (`config_incertidumbre.ini`): distribución del año de inversión con media 2054,5 y desviación de 2,3 años.
- `linea_base/`: T1 para R = 10³, 10⁴ y 10⁵ (≈ 3,1 ms por escenario; escalado lineal; 14 MiB).
- `docs/03_validacion_linea_base.md`: verificación, coherencia estadística y convergencia Monte Carlo.
- Extras: interfaz gráfica (`interfaz.py`) y versión en Go.

**Retrospectiva:** **[completar por el equipo]**

---

## Sprint 3 (S10–S12): paralelización

### Sprint Planning (S10)

- **Objetivo del sprint:** ejecutar 10 millones de escenarios en un tiempo razonable con MPI + OpenMP, sin cambiar los resultados.
- **Sprint backlog:**
  - S10: PB-06 Paralelización con OpenMP y PB-07 MPI y contenedores Docker.
  - S11: PB-08 Integración MPI + OpenMP.
  - S11–S12: PB-15 Clustering de escenarios (agregado al cronograma durante el sprint).
  - S12: PB-09 Ejecución de 10 millones de escenarios.
- **Criterio transversal:** la salida debe ser idéntica byte a byte a la secuencial con la misma semilla.
- Asistentes y capacidad: **[completar por el equipo]**

### Avance al cierre de S11

- PB-06 (OpenMP), PB-07 (MPI + Docker) y PB-08 (Híbrido MPI + OpenMP) **hechos**. El detalle está en `docs/04_sprint3_paralelizacion.md`.
- PB-15 (Clustering de escenarios, S11–S12): implementado; el detalle está en `docs/06_clustering.md`.
- Sprint Review y Retrospectiva del Sprint 3: en S12 (tras la ejecución masiva de 10 millones de escenarios).

### Sprint Review y Retrospectiva (S12)

**Incremento demostrado:**

- `MonteCarlo_Paralelo/src/main_openmp.cpp`, `main_mpi.cpp` y `main_hibrido.cpp`: las tres versiones paralelas. `make verificar` confirma que sus CSV son idénticos byte a byte a los del secuencial (20 de 20 comparaciones OK, ejecutado en el clúster el 11/11/2026).
- Clúster MPI de 4 nodos con Docker Compose; `docker/ejecutar_cluster.sh` acepta ahora un cuarto argumento (hilos por proceso) para lanzar la versión híbrida.
- **PB-09, 10 millones de escenarios** (`MonteCarlo_Paralelo/resultados_10000000/`): híbrido con 4 procesos × 2 hilos sobre los 4 nodos, `config_incertidumbre.ini`, semilla 12345.
  - Tiempo de pared: 2 188 s (36,5 min); 4 570 escenarios/s; CPU/pared = 7,90 de 8 núcleos; memoria pico 254 MiB; espera + comunicación 12,2 s (0,56 %).
  - Año de inversión: media 2054,504, desviación 2,304 años, rango 2043–2065; error estándar de la media 0,00073 años (IC 95 %: 2054,5027–2054,5056).
  - Sin inversión en el horizonte: 65 230 de 10 000 000 (0,652 %).
  - El primer millón de escenarios coincide byte a byte con la corrida de 1 000 000 hecha con OpenMP.
- PB-15, clustering de escenarios (`MonteCarlo_Clustering/`, `docs/06_clustering.md`).
- Objetivo del sprint (10 millones de escenarios con MPI + OpenMP sin cambiar los resultados): **cumplido**.

**Pasa al Sprint 4:** PB-10 (análisis de resultados y rendimiento), PB-11 (informe final) y PB-12 (diapositivas y ensayo).

**Retrospectiva:** **[completar por el equipo]**
