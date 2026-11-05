# Diseño del modelo probabilístico (S5–S6)

Modelo de proyección por componentes, estocástico, con edades simples, dos sexos y paso anual. El código está en `MonteCarlo_Secuencial/src/modelo.cpp` (un año) y `src/escenario.cpp` (un escenario completo).

## 1. Estado

N_t[s][a] es el número de personas de sexo s ∈ {H, M} y edad a ∈ {0, …, 99, 100+} al inicio del año t: 2 × 101 = 202 conteos enteros.

- P(t) = Σ N_t[s][a] es la población total.
- J(t) = Σ_{a=0..14} N_t[s][a] son los menores de 15.
- A(t) = Σ_{a≥65} N_t[s][a] son las personas de 65 años o más.

**Estado inicial.** `poblacion_inicial_peru.csv` trae 21 grupos quinquenales. Cada grupo G se reparte en 5 edades simples de forma uniforme y entera: G/5 a cada edad y el resto a las primeras. El total se conserva exactamente: P(0) = 32 706 028.

## 2. Transición de un año (t → t+1)

| Paso | Variable | Distribución | Parámetros |
|---|---|---|---|
| 1 | Nacimientos esperados | determinista | λ_t = Σ_{a=15..49} N_t[M][a] · f_t(a) |
| 2 | Nacimientos B_t | **Poisson**(λ_t) | f_t(a): tasa anual por mujer del quinquenio que contiene a t |
| 3 | Nacidas mujeres B_t^M | **Binomial**(B_t, p_F) | p_F = 0,49; B_t^H = B_t − B_t^M |
| 4 | Defunciones D_t[s][a] | **Binomial**(N_t[s][a], q[s][a]) | q anual por edad simple y sexo |
| 5 | Envejecimiento | determinista | N_{t+1}[s][min(a+1, 100)] += N_t[s][a] − D_t[s][a] |
| 6 | Nacidos que sobreviven al cierre | **Binomial**(B_t^s, u_s) | u_s = 0,99 → N_{t+1}[s][0] |

**Mortalidad.** Las filas 0, 1 y 5…95 de `mortalidad_peru.csv` se interpretan como probabilidades de supervivencia en intervalos de 1, 4 y 5 años: l_n. La probabilidad anual de muerte es q = 1 − l_n^(1/n). Así se obtiene e0 = 71,9 años en hombres y 77,1 en mujeres, valores plausibles para el Perú. La fila 100 vale 0 y no se usa: q(100+) = 0,35 se toma de la configuración.

**Fecundidad.** Cada columna quinquenal (2020_2025, …, 2065_2070) se aplica a los 5 años calendario de su quinquenio. La tasa de un grupo 15-19, …, 45-49 se asigna a sus 5 edades simples.

**Invariante comprobado en cada paso:** P(t+1) = P(t) + B_t − D_t, de forma exacta y con todos los conteos ≥ 0. Si falla, el programa se detiene.

## 3. Incertidumbre macro (opcional)

Sobre 33 millones de personas, el ruido Poisson/binomial es demasiado pequeño para mover el año de inversión: con tasas fijas sale 2054 en el 100 % de los escenarios. Para representar la incertidumbre de las tasas futuras, cada escenario r sortea dos factores una sola vez:

- factor_fec ~ N(1, σ_f), acotado a ≥ 0, que multiplica f_t(a) durante los 40 años;
- factor_mort ~ N(1, σ_m), que multiplica q[s][a], acotado a [0, 1].

`config_incertidumbre.ini` usa σ_f = 0,05 y σ_m = 0,015. Son valores didácticos y su calibración contra proyecciones oficiales queda como pendiente (ver `03_validacion_linea_base.md`). Con σ = 0 no se consume ningún número aleatorio y la salida es idéntica a la de tasas fijas.

## 4. Evento de interés y estimadores

T_r es el primer año de la trayectoria r con A > J. El estado inicial también se revisa, y el empate no cuenta. Si no ocurre dentro del horizonte H = 40, el escenario cuenta como "sin inversión".

Con R escenarios independientes:

- p̂(T = y) = #{r : T_r = y} / R (`distribucion.csv`, columna `probabilidad_anual`);
- F̂(y) = P̂(T ≤ y) = Σ_{y' ≤ y} p̂(T = y') (columna `probabilidad_acumulada`);
- media, desviación, mínimo y máximo de T sobre los escenarios con inversión (`resumen.txt`).

Error Monte Carlo: el error estándar de F̂(y) es √(F̂(1 − F̂)/R) y el de la media es s/√R'. Por eso, pasar de 10⁴ a 10⁷ escenarios reduce el error unas 32 veces (√1000). Ese es el motivo para paralelizar.

## 5. Números aleatorios y reproducibilidad (diseño para el paralelismo)

- Cada escenario r tiene **su propio generador** `std::mt19937_64` con semilla `splitmix64(semilla + r)`.
- Los sorteos de un escenario siguen un orden fijo: factores macro, y luego en cada año Poisson, binomial de sexo, binomiales de muerte por sexo y edad, y binomial de supervivencia de los nacidos.
- `sorteo_binomial` no consume números en los casos triviales (n = 0, p = 0 o p = 1). Lo verifica la prueba P6.

**Consecuencia.** El resultado del escenario r depende solo de (semilla, r) y no de qué hilo o proceso lo calcula ni en qué orden. Los escenarios son **vergonzosamente paralelos**: OpenMP y MPI reparten el rango [0, R) sin comunicarse durante la simulación, y sus CSV coinciden byte a byte con los del secuencial. Esto está comprobado en S10 (`MonteCarlo_Paralelo/scripts/verificar_equivalencia.sh`).

## 6. Costo computacional

Cada escenario cuesta lo mismo, porque siempre se simula el horizonte completo aunque la inversión ya haya ocurrido: por año hay 1 Poisson, 1 binomial de sexo, 202 binomiales de muerte y 2 de supervivencia de nacidos, es decir 206 sorteos; en H = 40 años son ≈ 8 240 sorteos. El costo total es O(R · H) y la memoria es O(1) por escenario en la versión secuencial. Con costo uniforme por escenario, un reparto estático por bloques queda balanceado (MPI).

## 7. Supuestos (estado `DEMO_NO_VALIDADO`)

| Supuesto | Valor | Fuente / estado |
|---|---|---|
| Año de la población inicial | 2025 | El CSV no lo indica: pendiente de confirmar |
| Unidad de fecundidad | nacimientos por mujer y año | La TGF resultante (1,7–2,15) es plausible; falta la ficha técnica |
| Interpretación de la mortalidad | supervivencia por intervalo | La e0 resultante es plausible; falta la ficha técnica |
| p_F, u_s, q(100+) | 0,49; 0,99; 0,35 | Didácticos, sin fuente |
| Mortalidad constante en el tiempo | — | Simplificación del modelo |
| Sin migración | — | Simplificación del modelo |
| σ_f, σ_m | 0,05; 0,015 | Didácticos; calibración pendiente |
