# Registro de ceremonias Scrum (S4–S10)

Calendario según el cronograma: Sprint 1 = S4–S6; Sprint 2 = S7–S9, con pausa en S8 por exámenes parciales; Sprint 3 = S10–S12; Sprint 4 = S13–S14; presentación en S15. El Daily Scrum es una reunión breve en días de trabajo; no hay reuniones en S8.

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
  - S12: PB-09 Ejecución de 10 millones de escenarios.
- **Criterio transversal:** la salida debe ser idéntica byte a byte a la secuencial con la misma semilla.
- Asistentes y capacidad: **[completar por el equipo]**

### Avance al cierre de S10

- PB-06 y PB-07 **hechos**. El detalle está en `docs/04_sprint3_paralelizacion.md`.
- Sprint Review y Retrospectiva del Sprint 3: en S12.
