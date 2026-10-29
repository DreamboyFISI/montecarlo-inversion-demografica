# Reporte de calidad de datos

Generado por `scripts/limpieza_datos.py`. Anio base supuesto: 2025; horizonte: 40.

Resultado: **27 correctas, 1 aviso(s), 0 falla(s)** de 28 comprobaciones.

| Resultado | Comprobacion |
|---|---|
| OK | poblacion_inicial_peru.csv: todas las filas tienen 3 columnas |
| OK | poblacion_inicial_peru.csv: sin celdas vacias (0) |
| OK | poblacion: encabezado esperado |
| OK | poblacion: 21 grupos 0-4 ... 95-99, 100+ en orden y sin duplicados |
| OK | poblacion: conteos enteros no negativos |
| OK | poblacion: total = 32 706 028 |
| OK | poblacion: menores de 15 = 7 429 471; 65 o mas = 3 440 272; razon A/J = 0.4631 |
| OK | poblacion: no hay inversion en el estado inicial |
| OK | poblacion: indice de masculinidad plausible (97.2 hombres por 100 mujeres) |
| OK | desagregacion: 202 celdas conservan el total exacto |
| OK | fecundidad_peru.csv: todas las filas tienen 11 columnas |
| OK | fecundidad_peru.csv: sin celdas vacias (0) |
| OK | fecundidad: 10 periodos quinquenales contiguos 2020-2070 |
| OK | fecundidad: grupos 15-19 ... 45-49 |
| OK | fecundidad: tasas en [0, 1] |
| OK | fecundidad: TGF = 5 x suma de tasas entre 1,3 y 3,0 en todos los periodos (2.15, 2.05, 1.95, 1.87, 1.80, 1.74, 1.69, 1.70, 1.72, 1.73) -> compatible con 'nacimientos por mujer y anio' |
| OK | fecundidad: cobertura para exposicion 2025-2064 |
| OK | mortalidad_peru.csv: todas las filas tienen 3 columnas |
| OK | mortalidad_peru.csv: sin celdas vacias (0) |
| OK | mortalidad: claves 0, 1, 5, ..., 100 |
| OK | mortalidad: valores en [0, 1] |
| OK | mortalidad: fila 100 vale 0 -> no se usa; q(100+) viene de configuracion |
| OK | mortalidad: valores decrecientes desde 5 anios -> se comportan como probabilidades de SUPERVIVENCIA |
| OK | mortalidad: supervivencia femenina >= masculina en todas las edades |
| OK | mortalidad: con la interpretacion supervivencia_intervalo, e0 H = 71.9 y e0 M = 77.1 anios (plausible) |
| OK | mortalidad: q anual H 20-24 = 0.001867 |
| OK | lambda inicial (2025) = 512 939.1415 |
| AVISO | coherencia: nacimientos esperados 512939/anio vs. 402744 personas por edad simple en 0-4 (razon 1.27). La cohorte 0-4 es menor de lo que implica la fecundidad: posible desfase de anio base, subregistro o fuentes distintas. Produce un repunte de menores de 15 hacia 2036-2040. |

## Pendiente de confirmar con la fuente

- Anio de referencia de la poblacion inicial (se usa 2025 como supuesto).
- Unidad de fecundidad: la TGF obtenida es plausible, pero falta la ficha tecnica.
- Mortalidad: el patron y la e0 resultante apoyan 'supervivencia por intervalo', pero falta la ficha tecnica.
- q(100+), pF y u: parametros didacticos sin fuente.

## Archivos procesados

- `poblacion_edad_simple.csv`: 101 edades x 2 sexos (reparto uniforme entero).
- `mortalidad_q_anual.csv`: q anual por edad simple y sexo.
- `fecundidad_anual.csv`: tasa por grupo para cada anio 2025-2064 y TGF.
