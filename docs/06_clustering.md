# Clustering de Escenarios Demográficos y Perfiles de Edad (S13)

**Módulo:** Modelamiento Avanzado — Clustering (Semana 13)  
**Curso:** Programación Paralela y Concurrente / Minería de Datos  
**Repositorio:** `montecarlo-inversion-demografica`  
**Estado de los datos:** `PARAMETROS_CONFIGURADOS` (Los resultados dependen de supuestos didácticos y no constituyen un pronóstico demográfico oficial del Perú).

---

## 1. Objetivo del Módulo

El objetivo central de este entregable es segmentar los 10 000 escenarios generados por la simulación estocástica Monte Carlo de la inversión demográfica del Perú (momento en que los adultos mayores de 65+ años, $A$, superan a los menores de 15 años, $J$), caracterizando los regímenes macroeconómico-demográficos resultantes y extrayendo reglas interpretables sobre la influencia de las perturbaciones en la fecundidad y la mortalidad.

Adicionalmente, en la **Parte B**, se aborda el clustering no supervisado de los perfiles de edad simple (0 a 100+ años) para responder a una pregunta conceptual clave: ¿las particiones naturales basadas en tasas de supervivencia y fecundidad recuperan los umbrales operativos de 15 y 65 años que definen a $J$ y $A$?

---

## 2. Datos y Supuestos

Los datos provienen de la ejecución del simulador en `MonteCarlo_Secuencial/resultados_incertidumbre/` (10 000 escenarios, horizonte de 40 años: 2025–2065, semilla base 12345).

- **Incertidumbre macro:**  
  $$\text{factor\_fecundidad} \sim \mathcal{N}(1.0, 0.05), \quad \text{factor\_mortalidad} \sim \mathcal{N}(1.0, 0.015)$$  
  Ambos factores son sorteados independientemente al inicio de cada escenario mediante generadores `mt19937_64` independientes sembrados con `splitmix64(semilla + r)`.
- **Línea base determinista:** Con $\sigma = 0$ la inversión ocurre invariablemente en el año 2054.
- **Distribución empírica simulada:**  
  - 9 925 escenarios alcanzaron el cruce dentro del horizonte (99.25%). Media: 2054.50 años, desviación estándar: 2.29 años, rango: [2046, 2065].
  - 75 escenarios (0.75%) no alcanzaron la inversión dentro del horizonte de 40 años.
- **Advertencia metodológica:** Los factores $\sigma_f = 0.05$ y $\sigma_m = 0.015$ representan supuestos de laboratorio didácticos no calibrados con las variantes demográficas oficiales de INEI, CELADE o Naciones Unidas (WPP).

---

## 3. Metodología de Preparación y Modelado

### 3.1. Integración y Verificación de Integridad
Se unieron `escenarios.csv` y `factores_escenarios.csv` mediante la clave primaria `escenario`. Se verificó una correspondencia biyectiva exacta (1 a 1) sobre 10 000 filas sin duplicados ni registros huérfanos.

### 3.2. Tratamiento de Escenarios Sin Inversión
Los 75 escenarios que no invirtieron dentro del horizonte poseen año nulo (`primer_anio_inversion` vacío). Se trataron metodológicamente como un grupo propio segregado: **"Sin inversión en el horizonte"**. Fueron excluidos de la matriz de entrenamiento de los algoritmos de clustering para no distorsionar las métricas de distancia en el espacio temporal.  
Como análisis de sensibilidad, se reincorporaron censurando su año en $2066$ (último año del horizonte $+ 1$).

### 3.3. Detección y Justificación de Outliers
Se evaluaron las colas estadísticas mediante el Rango Intercuartílico (IQR) y Z-Score ($|Z| > 3$):

| Variable | Media | Desv. | Rango IQR [Q1−1.5·IQR, Q3+1.5·IQR] | Outliers IQR (%) | Outliers $|Z| > 3$ (%) |
|---|---|---|---|---|---|
| `factor_fecundidad` | 0.9993 | 0.0487 | [0.8663, 1.1335] | 29 (0.29%) | 9 (0.09%) |
| `factor_mortalidad` | 0.9998 | 0.0149 | [0.9597, 1.0401] | 72 (0.73%) | 29 (0.29%) |
| `primer_anio_inversion` | 2054.50 | 2.29 | [2048.5, 2060.5] | 114 (1.15%) | 58 (0.58%) |

**Decisión:** **NO se eliminó ningún outlier**. Los escenarios con cruces tempranos (ej. 2046) o tardíos (ej. 2065) son combinaciones estocásticas válidas y legítimas del generador pseudoaleatorio. En análisis de riesgo demográfico y actuarial, las colas de la distribución son precisamente los eventos de contingencia más críticos.

### 3.4. Selección de Escalamiento: StandardScaler vs MinMaxScaler
- Se seleccionó **`StandardScaler`**.
- *Justificación:* Los factores provienen de distribuciones gaussianas continuas $\mathcal{N}(1, \sigma)$ y el año de inversión exhibe una distribución unimodal tipo campana. `MinMaxScaler` comprime artificialmente el 98% de la masa de datos hacia el centro debido a la presencia de los valores extremos legítimos (2046 y 2065), deformando la métrica euclidiana.

### 3.5. Colinealidad y Análisis de Componentes Principales (PCA)
- Correlación de Pearson entre factores: $r(\text{fecundidad}, \text{mortalidad}) = -0.00518$. Confirma empíricamente la independencia ortogonal estocástica fijada en el diseño del simulador C++.
- Correlación con el año de cruce: $r(\text{fecundidad}, \text{año}) = +0.97359$ (determinante fundamental) y $r(\text{mortalidad}, \text{año}) = +0.12058$.
- PCA 2D: La primera componente explica el **66.01%** de la varianza (alineada con el eje fecundidad–año), mientras que la segunda explica el **33.38%** (eje de mortalidad). En conjunto capturan el **99.39%** de la información del espacio tridimensional.

### 3.6. Algoritmos Implementados
1. **K-Means:** Evaluación de $k \in [2, 8]$ mediante curva de inercia (codo) y coeficiente Silhouette. Selección de $k=3$ por equilibrio de compacidad e interpretabilidad demográfica directa (Inversión Temprana, Central y Tardía).
2. **Hierarchical Clustering (Ward):** Enlace de mínima varianza de Ward sobre muestra representativa de 3 000 observaciones con asignación euclidiana por centroide para las restantes 6 925, optimizando memoria ($O(N^2)$ evitado) y tiempo de cómputo.
3. **DBSCAN:** Selección de parámetros mediante gráfico de distancias ordenadas al $k$-ésimo vecino ($k = 2 \times \text{dim} = 6$). Umbral óptimo de rodilla: $\varepsilon = 0.145$, $\text{min\_samples} = 6$.
4. **K-Medoids:** Omitido formalmente debido a incompatibilidad binaria entre las extensiones compiladas Cython de `scikit-learn-extra 0.3.0` y la versión de NumPy 2.x en la máquina host (C-API binary mismatch). Esta eventualidad fue contemplada de manera explícita en las especificaciones del entregable.

---

## 4. Evaluación Comparativa de Algoritmos

Las métricas fueron registradas por el script en `MonteCarlo_Clustering/resultados_clustering/metricas_clustering.csv`:

| Algoritmo | $k$ | Silhouette | Davies-Bouldin | Calinski-Harabasz | Ruido (%) | T. Pared (s) | T. CPU (s) | Memoria Pico (MiB) | Estabilidad ARI (10 corridas 80%) | Speedup Multi-hilo |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|
| **K-Means** | **3** | **0.3165** | **1.0312** | **6 203.14** | **0.00%** | **0.0515** | **0.3125** | **193.82** | **0.9352 ± 0.0378** | **1.26x** |
| **Hierarchical (Ward)** | 3 | 0.2957 | 1.1480 | 5 832.77 | 0.00% | 0.2002 | 0.5781 | 198.49 | N/A (Determinista) | 1.00x |
| **DBSCAN** | 29 | 0.0407 | 1.2454 | 715.59 | 3.87% | 0.0501 | 0.0469 | 205.57 | N/A (Determinista) | 1.00x |

### Conclusión Honesta sobre la Estructura de Conglomerados
Los datos provienen de perturbaciones normales continuas superpuestas a un modelo demográfico suave. Por ende, **no existen fronteras vacías naturales ni cúmulos densos aislados en el espacio de estados**.  
El coeficiente Silhouette moderado (~0.32) no es una falla algorítmica ni requiere forzar artificialmente hiperparámetros: es el reflejo honesto de la topología continua de los escenarios Monte Carlo. El agrupamiento aporta un valor sustancial como **partición operativa de decisión** para planificar escenarios de contingencia demográfica.

---

## 5. Perfilado de Segmentos e Interpretación Demográfica

A partir de la partición operacional de K-Means ($k=3$) y el grupo censurado, se definieron los cuatro regímenes del sistema:

| Cluster | Nombre del Segmento | Escenarios | % Total | Año Medio | Mediana | Desv. | Rango Años | Fecundidad Media | Mortalidad Media |
|:---:|---|---:|---:|---:|---:|---:|:---:|---:|---:|
| **1** | **Inversión Temprana** | 3 499 | 34.99% | 2052.47 | 2053 | 1.25 | [2046, 2054] | 0.95773 ± 0.0336 | 0.99110 ± 0.0114 |
| **0** | **Inversión Central** | 2 958 | 29.58% | 2054.22 | 2054 | 1.20 | [2048, 2058] | 0.98980 ± 0.0277 | 1.01381 ± 0.0097 |
| **2** | **Inversión Tardía** | 3 468 | 34.68% | 2056.80 | 2056 | 1.65 | [2055, 2065] | 1.04932 ± 0.0260 | 0.99669 ± 0.0132 |
| **-1** | **Sin inversión en el horizonte** | 75 | 0.75% | > 2065 | N/A | N/A | N/A | 1.13887 ± 0.0160 | 1.00566 ± 0.0158 |

### Mecanismos Demográficos Subyacentes
1. **Régimen de Inversión Temprana (Media 2052.5):**  
   Ocurre cuando la fecundidad cae un $\approx 4.2\%$ respecto a la línea base determinista. Al nacer menos niños, el contingente de menores de 15 años ($J$) se contrae rápidamente. A la par, una mortalidad ligeramente menor a la esperada ($0.991$) favorece la supervivencia geriátrica, haciendo que $A$ alcance y supere a $J$ hasta 8 años antes del año nominal 2054 (mínimo registrado en 2046).
2. **Régimen de Inversión Central (Media 2054.2):**  
   Corresponde al corredor de estabilidad demográfica alrededor de 2054. Combina fecundidad cercana a la referencia ($0.990$) con una mortalidad discretamente mayor ($1.014$), que frena levemente el crecimiento acumulado de $A$, balanceando las pequeñas oscilaciones estocásticas anuales.
3. **Régimen de Inversión Tardía (Media 2056.8):**  
   La fecundidad experimenta un incremento de casi $+5\%$ ($1.049$). La base de la pirámide poblacional se ensancha y retiene suficiente volumen de menores de 15 años para postergar el cruce con los adultos mayores hasta 2057–2065.
4. **Segmento Sin Inversión (0.75%):**  
   Los 75 escenarios exhiben una fecundidad atípicamente elevada ($\bar{f} = 1.13887$, es decir $+13.9\%$ por encima del valor esperado, a $+2.7\sigma$). Con este volumen sostenido de nacimientos, $J$ supera permanentemente a $A$ a lo largo de los 40 años simulados.

---

## 6. Explicabilidad mediante Árbol de Decisión Sustituto

Se entrenó un árbol de decisión superficial (`DecisionTreeClassifier`, `max_depth=3`, semilla 12345) tomando exclusivamente como variables predictoras los dos factores macro de entrada (`factor_fecundidad` y `factor_mortalidad`).

- **Exactitud global (Accuracy):** **89.51%**
- **Reglas extraídas (`reglas_arbol.txt`):**

```text
|--- factor_fecundidad <= 1.01
|   |--- factor_mortalidad <= 1.00
|   |   |--- class: Inversión Temprana
|   |--- factor_mortalidad >  1.00
|   |   |--- factor_fecundidad <= 0.95 -> class: Inversión Temprana
|   |   |--- factor_fecundidad >  0.95 -> class: Inversión Central
|--- factor_fecundidad >  1.01
|   |--- factor_mortalidad <= 1.01
|   |   |--- class: Inversión Tardía
|   |--- factor_mortalidad >  1.01
|   |   |--- factor_fecundidad <= 1.04 -> class: Inversión Central
|   |   |--- factor_fecundidad >  1.04 -> class: Inversión Tardía
```

**Conclusión:** Un umbral crítico en el factor de fecundidad de $\approx 1.01$ determina si el sistema viaja hacia un envejecimiento precoz o retardado. La mortalidad opera como un modulador de segundo orden: si la fecundidad es ligeramente baja ($\le 1.01$), pero la mortalidad es alta ($> 1.00$), la sobrevida de adultos mayores disminuye y el sistema permanece en el régimen Central.

---

## 7. Análisis de Sensibilidad y Paralelismo

1. **Sensibilidad a la Censura temporal:**  
   Reincorporar los 75 escenarios censurados a año $2066$ produce un Adjusted Rand Index de **$\text{ARI} = 0.9523$** respecto a la partición de 9 925 puntos. Esto demuestra una altísima estabilidad estructural: aislar los escenarios sin cruce no sesga las fronteras de los escenarios estándar.
2. **Poder explicativo de Factores vs Año de Inversión:**  
   Al agrupar únicamente con los dos factores macro (sin suministrar el año de inversión), la concordancia con el clustering completo alcanza $\text{ARI} = 0.3595$. Esto comprueba que, si bien la fecundidad dicta la tendencia global ($r = 0.97$), la acumulación estocástica año a año (sorteos de nacimientos y defunciones) introduce una dispersión interna irreductible que el clustering tridimensional aprovecha para refinar los cortes.
3. **Estabilidad del Algoritmo K-Means:**  
   En 10 submuestras aleatorias al 80%, la estabilidad evaluada mediante ARI promedió **$0.9352 \pm 0.0378$**, garantizando reproducibilidad en entornos de remuestreo.
4. **Concurrencia en K-Means (OpenMP/BLAS):**  
   Utilizando `threadpoolctl`, se midió la ejecución de K-Means con 1 hilo ($0.0328$ s) versus multi-hilo ($0.0260$ s), arrojando un **Speedup de 1.26x** para 10 000 observaciones. La ganancia es moderada debido al bajo tiempo absoluto de cómputo en CPU y el overhead de sincronización de hilos en matrices pequeñas ($10^4 \times 3$).

---

## 8. Parte B: Clustering de Edades Simples (Demographic Age Profiles)

Se construyó una matriz demográfica sobre las edades simples ($a = 0, \dots, 100+$) a partir de los datos procesados en `MonteCarlo_Secuencial/datos_procesados/` (`mortalidad_q_anual.csv`, `poblacion_edad_simple.csv` y `fecundidad_anual.csv`). Las variables del perfil fueron: tasa de mortalidad masculina $q_h(a)$, tasa femenina $q_m(a)$, proporción de población $P(a)/P_{\text{total}}$ y tasa específica de fecundidad anual $f(a)$.

### Resultados del Agrupamiento no Supervisado ($k=3$)
- **Métricas:** Silhouette = **0.5854**, Davies-Bouldin = **0.5511**, Calinski-Harabasz = **188.10**.
- **Concordancia con la Partición Oficial:** $\text{ARI} = \mathbf{0.1347}$ contra las clases $[J (<15), \text{Intermedia } (15\text{--}64), A (\ge 65)]$.

| Cluster | Nombre Asignado | Rango de Edades | $N$ Edades | $q_h$ Promedio | $q_m$ Promedio | Fecundidad Promedio | % Población |
|:---:|---|:---:|---:|---:|---:|---:|---:|
| **1** | **Etapa Productiva / Reproductiva** | 15 – 39 | 25 | 0.00204 | 0.00103 | 0.07678 | 38.41% |
| **0** | **Senescencia Geriátrica Extrema** | 85 – 100+ | 16 | 0.22035 | 0.19605 | 0.00000 | 1.12% |
| **2** | **Base Infantil y Adultez No Reproductiva** | 0 – 14 y 40 – 84 | 60 | 0.02262 | 0.01595 | 0.00210 | 60.47% |

### Interpretación Demográfica y Respuesta a la Pregunta de Investigación
- **¿Los conglomerados no supervisados recuperan los cortes de 15 y 65 años?**  
  **No de forma directa (ARI = 0.1347).**
- **Causa demográfica:**  
  1. Los cortes oficiales de 15 y 65 años corresponden a **convenciones de política pública y dependencia económica laboral** (edad de entrada al mercado de trabajo y edad de jubilación).
  2. En cambio, el clustering no supervisado responde a las discontinuidades puramente biológicas:
     - Aísla la ventana de máxima fertilidad reproductiva (edades 15 a 39).
     - Aísla el régimen de mortalidad exponencial senescente extrema (Gompertz-Makeham a partir de los 85 años, donde $q > 0.20$).
     - Fusiona a la niñez ($0\text{--}14$) con la madurez post-reproductiva ($40\text{--}84$) porque en ambas la tasa de fecundidad es cero o residual y la mortalidad, aunque creciente, se mantiene órdenes de magnitud por debajo de la vejez extrema.

---

## 9. Figuras Recomendadas para las Diapositivas (Semana 13)

Para la sustentación oral del entregable de la Semana 13, se recomienda seleccionar las siguientes 4 láminas clave guardadas en `MonteCarlo_Clustering/graficos_clustering/`:

1. **`04_scatter_factores_clusters.png` (Lámina de Segmentación Central):** Muestra el plano $\text{factor\_fecundidad}$ vs $\text{factor\_mortalidad}$ coloreado por los tres regímenes de inversión más los puntos rojos correspondientes a los 75 escenarios sin cruce.
2. **`05_distribucion_anio_clusters.png` (Lámina de Impacto Temporal):** Boxplots comparativos del año de cruce para Inversión Temprana (2052.5), Central (2054.2) y Tardía (2056.8), demostrando la separación temporal lograda.
3. **`08_arbol_decision_reglas.png` (Lámina de Explicabilidad y Gobernanza):** Representación visual del árbol de decisión surrogate con sus puntos de corte y la exactitud del 89.51%.
4. **`03_clusters_edades_vs_oficial.png` (Lámina de la Parte B, en `graficos_edades/`):** Contraste visual entre los linderos normativos (15 y 65 años) y las agrupaciones fisiológicas naturales halladas por K-Means.

