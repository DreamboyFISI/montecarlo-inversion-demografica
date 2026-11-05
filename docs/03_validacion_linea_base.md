# Validación y línea base (S9)

Cierre del Sprint 2. Se comprueba que la implementación secuencial hace lo que dice el modelo (`02_diseno_modelo_probabilistico.md`) y se fija el tiempo T1 con el que se mide el speedup del Sprint 3.

## 1. Verificación: ¿el programa implementa bien el modelo?

| # | Comprobación | Evidencia | Resultado |
|---|---|---|---|
| V1 | Calidad de los datos de entrada: 28 comprobaciones de formato, rangos, totales y plausibilidad | `MonteCarlo_Secuencial/datos_procesados/reporte_calidad_datos.md` | 27 OK, 1 aviso, 0 fallas |
| V2 | 12 pruebas controladas con resultado conocido: envejecimiento, grupo abierto, mortalidad 0 y 1, empate, binomial trivial, totales, reparto, q anual, λ inicial, cambio de quinquenio, balance + reproducibilidad | `./simulador --self-test` | 12 de 12 |
| V3 | Balance P(t+1) = P(t) + B − D exacto en cada año | `exigir(...)` en `simular_anio`; columna `balance` de `trayectoria_escenario_1.csv` | 0 en los 40 años |
| V4 | Reproducibilidad: misma semilla → mismos CSV | Prueba P12 y 3 repeticiones de la línea base | CSV idénticos |
| V5 | Refactor de S10: los módulos compartidos `escenario.*` y `salida.*` no cambian la salida | Se regeneraron `resultados_demo` (R = 1 000) y `resultados_incertidumbre` (R = 10 000) y se compararon con `cmp` contra los committeados | Idénticos byte a byte (CSV, SVG, resumen sin tiempos) |

### Coherencia estadística del muestreo (V6)

En la trayectoria del escenario 1 (`resultados_demo/trayectoria_escenario_1.csv`, 40 años), los nacimientos simulados deben comportarse como Poisson(λ_t). La variable z_t = (B_t − λ_t)/√λ_t debe seguir aproximadamente N(0, 1):

| Estadístico | Esperado | Obtenido |
|---|---|---|
| media de z | 0 | −0,100 |
| desviación de z | 1 | 1,083 |
| años con \|z\| > 1,96 | ≈ 2 de 40 (5 %) | 3 de 40 |

Es compatible con una Poisson bien muestreada.

## 2. Validación: ¿el resultado es razonable?

- Con tasas fijas, el ruido demográfico sobre 33 millones de personas es despreciable: la inversión ocurre en **2054** en los 1 000 escenarios. En ese año, J = 6 244 851 y A = 6 267 718.
- Con incertidumbre macro (σ_f = 0,05 y σ_m = 0,015) aparece una distribución unimodal centrada en 2054.
- El aviso de V1 (cohorte 0–4 menor de lo que implica la fecundidad) produce un repunte de menores de 15 hacia 2036–2040. Es un efecto conocido de los datos, no del código.

**Pendiente (fuera del alcance del código):** contrastar 2054 con la proyección oficial (INEI / CELADE / ONU WPP) y calibrar σ_f y σ_m con la dispersión entre sus variantes alta, media y baja. Mientras tanto, los resultados conservan el estado `DEMO_NO_VALIDADO`.

## 3. Convergencia Monte Carlo

Estimaciones sobre los primeros R escenarios de `resultados_incertidumbre/escenarios.csv` (semilla 12345). Intervalos de confianza al 95 %:

| R | P(inversión ≤ 2065) | Media de T | IC 95 % de la media | Desv. T | P(T ≤ 2055) |
|---:|---|---:|---|---:|---|
| 100 | 0,980 ± 0,027 | 2054,45 | ± 0,46 | 2,34 | 0,700 ± 0,090 |
| 1 000 | 0,994 ± 0,005 | 2054,43 | ± 0,14 | 2,27 | 0,711 ± 0,028 |
| 10 000 | 0,9925 ± 0,0017 | 2054,50 | ± 0,045 | 2,29 | 0,686 ± 0,009 |

El semiancho del IC baja como 1/√R: ×10 en R lo divide por ≈ 3,2. Con R = 10⁷ (S12), el IC de la media sería de ≈ ± 0,0014 años y el de P(T ≤ y), de ≈ ± 0,0003. Lograr esa precisión es lo que justifica la paralelización: secuencialmente tomaría unas 8,5 h (10⁷ × 3,06 ms).

## 4. Línea base secuencial T1

Medida con `scripts/linea_base.py` (3 repeticiones por R). El detalle está en `MonteCarlo_Secuencial/linea_base/linea_base.md`. Equipo: Intel Xeon 2,8 GHz, g++ 13.3 -O2.

| R | T1 (s) | ms/escenario | escenarios/s | RSS (MiB) |
|---:|---:|---:|---:|---:|
| 1 000 | 3,193 ± 0,058 | 3,19 | 313 | 14,1 |
| 10 000 | 32,937 ± 1,547 | 3,29 | 304 | 14,1 |
| 100 000 | 305,876 ± 6,232 | 3,06 | 327 | 14,1 |

Escalado lineal en R (×100 en R → ×95,8 en T1) y memoria constante. El CPU/pared ≈ 98–99 % confirma que el programa está limitado por cálculo y no por E/S, lo que lo hace buen candidato para paralelizar.

**Nota para el Sprint 3.** El speedup solo se calcula con T1 y Tp **medidos en la misma máquina**. Por eso `MonteCarlo_Paralelo/scripts/rendimiento.py` vuelve a medir T1 junto a cada Tp, intercalando las corridas. Los T1 de esta tabla (Xeon) no deben dividirse entre los Tp de otro equipo.
