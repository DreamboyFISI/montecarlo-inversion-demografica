# Análisis de resultados y rendimiento — S13 (PB-10)

## 1. Alcance

`MonteCarlo_Analisis/` analiza las salidas **de la ejecución seleccionada**, no valores
fijos de una presentación. Incluye consola, una pestaña en la interfaz y exportación
de Markdown, CSV, JSON y PNG. No cambia ecuaciones, generadores aleatorios, datos
originales ni paralelización.

Hay dos operaciones distintas:

- **Análisis individual:** estadísticas demográficas y métricas informadas por una
  ejecución, incluidas las referencias antiguas del repositorio.
- **Campaña de rendimiento:** ejecuciones C++ secuencial/OpenMP/MPI/híbrido sucesivas,
  con la misma entrada y semilla, procedencia registrada y repeticiones. Solo esta
  operación habilita el cálculo automático de speedup.

El informe final (PB-11) sigue siendo otro entregable. Los informes exportados sirven
para elaborarlo; no sustituyen la discusión académica ni la confirmación de fuentes.

## 2. Consola en WSL / Linux

Desde la raíz del repositorio:

```bash
make -C MonteCarlo_Paralelo all secuencial
```

Los cálculos necesitan **Python 3.10+ y su biblioteca estándar**. Matplotlib es
opcional para PNG y obligatorio para la interfaz existente; Tkinter/pantalla (por
ejemplo WSLg) solo se necesitan para la interfaz. No hay otra dependencia científica.

### Analizar una salida existente

```bash
python -m MonteCarlo_Analisis analizar MonteCarlo_Paralelo/resultados_10000000 \
    --salida salidas_s13/mi_informe_10m
```

Acepta también las salidas Go. `--sin-graficos` evita generar imágenes.
La lectura estadística usa el histograma, de tamaño O(horizonte), no los CSV de
millones de escenarios. Los valores `--escenarios` efectivos prevalecen sobre el R
original copiado en `config_usada.ini`.

### Ejecutar un motor con procedencia

```bash
python -m MonteCarlo_Analisis ejecutar --version openmp --hilos 2 \
    --escenarios 1000 --salida salidas_s13/mi_openmp
```

Motores: `secuencial`, `openmp`, `mpi`, `hibrido`, `go`. MPI acepta `--procesos`;
híbrido acepta `--procesos` y `--hilos`. `--config` y `--datos` permiten sustituir las
rutas por defecto de C++. Una ejecución individual **no** se convierte por sí sola
en una campaña de rendimiento.

### Medir en el equipo de la presentación

Primero probar una campaña pequeña:

```bash
python -m MonteCarlo_Analisis campana \
    --config MonteCarlo_Secuencial/config_incertidumbre.ini \
    --escenarios 1000 --repeticiones 3 \
    --versiones openmp mpi hibrido --p 1 2 --hibridos 1x2 \
    --salida salidas_s13/mi_campana
```

Después aumentar R y elegir configuraciones acordes con las CPU disponibles, por
ejemplo `--p 1 2 4 --hibridos 1x4 2x2`. El lanzador comprueba la capacidad/afinidad
expuesta por el entorno: los ejemplos no garantizan recursos en todas las máquinas.
**Cada R requiere su propia campaña y T1.**

- Siempre se mide C++ secuencial; no hace falta incluirlo en `--versiones`.
- Las corridas no son simultáneas; se rota su orden entre repeticiones.
- Se conservan todas las salidas, también si la campaña falla.
- Se verifica igualdad byte a byte de `escenarios.csv`, `trayectoria_escenario_1.csv`
  y, si corresponde, `factores_escenarios.csv`. SHA-256 se calcula por bloques,
  fuera del intervalo medido, sin cargar todos los escenarios en memoria.
- La comparación exportada aparece en `<campaña>/analisis/`.
- La exportación incluye `metricas_crudas.csv` con cada medición usada, su ID,
  repetición, fecha y carpeta de origen, además de los agregados y exclusiones.
- `--permitir-sobresuscripcion` es explícito y se advierte en el informe.
- OpenMPI es **local**, con `--use-hwthread-cpus --bind-to none`, como en el proyecto.
  Los hilos lógicos no se presentan como núcleos físicos.
- Se fijan y registran `OMP_DYNAMIC=FALSE`, `OMP_THREAD_LIMIT=4096` y
  `OMP_PROC_BIND=FALSE` en los procesos hijos.

No se calcula automáticamente speedup entre máquinas, clústeres remotos ni
contenedores presentados como equipos físicos diferentes. El script y las salidas
de `MonteCarlo_Paralelo/scripts/rendimiento.py` se conservan como referencia S10;
no se les añade procedencia retroactiva.

### Reabrir sin volver a medir

```bash
python -m MonteCarlo_Analisis comparar salidas_s13/mi_campana \
    --salida salidas_s13/mi_comparacion_exportada
```

Las carpetas de ejecución, campaña y exportación deben ser **nuevas**. No se borran
ni sobrescriben resultados anteriores. `salidas_s13/` está ignorada por Git.

### Privacidad al compartir

La interfaz y el campo de origen de los informes muestran rutas relativas al
repositorio; para carpetas externas muestran solo su nombre. Los registros de
auditoría JSON y las métricas crudas conservan rutas completas para identificar
el contexto real: **no son exportaciones anonimizadas**. Revisarlos antes de
compartirlos. Los JSON de S13 también se excluyen por nombre mediante `.gitignore`,
incluso si se exportan fuera de `salidas_s13/`. Esto no elimina del historial un
archivo que alguien hubiera versionado anteriormente.

## 3. Interfaz

```bash
python interfaz.py
```

- Ejecutar o cargar resultados actualiza **«4. Análisis S13» → «Resultados de la ejecución»**.
- Puede cargarse directamente la referencia de 10 millones de S12.
- **«Campaña y rendimiento comparado»** permite elegir configuración, R, repeticiones,
  versiones, p y pares híbridos; confirma el número de corridas antes de empezar.
- Durante una campaña no se puede lanzar otra simulación en esta interfaz.
- Se pueden reabrir campañas y exportar los dos tipos de análisis.
- La comprobación de los CSV de una campaña se realiza en segundo plano para no
  bloquear la ventana mientras se leen archivos grandes.
- Se quitaron las estimaciones de tiempo fijas de otros equipos.
- Las franjas μ ± kσ se identifican como **dispersión**, no como IC de la media.
  El evento del gráfico se corrigió a **A > J**.
- La pestaña de clustering se identifica como **referencia S11–S12 de 10 000
  escenarios**, no como análisis automático de cada nueva simulación.
  S13 no vuelve a entrenar esos algoritmos.

### Python de Windows y de Ubuntu

Lo más uniforme es abrir toda la interfaz con Python **dentro de Ubuntu/WSLg**.
Si se usa Python de Windows se conserva la separación existente:

- Secuencial C++ y Go individuales necesitan sus `.exe` nativos.
- Los motores paralelos individuales usan la distribución WSL indicada.
- **Toda la campaña C++**, incluido el secuencial, se ejecuta dentro de esa misma
  distribución: nunca se mezcla un T1 nativo Windows con un Tp Linux.
- La distribución es editable; no se utiliza `docker-desktop`.
- Para registrar/ejecutar en WSL basta la biblioteca estándar. Sin Matplotlib,
  el informe numérico se genera, pero sus PNG no.

## 4. Estadística e interpretación

Para R escenarios y n que cruzan dentro del horizonte:

- `p(T=y) = conteo_y/R` y `F(y) = acumulado_y/R`. R incluye a quienes no cruzan.
- IC **Wilson 95 %** para probabilidades de cruce, no cruce y F(y). Los IC anuales
  son **puntuales**, no una banda simultánea. Wilson no declara certeza absoluta
  al observar cero o R eventos.
- Media, mediana, extremos y cuantiles del año **condicionales al cruce dentro del
  horizonte**. Cuantiles por rango más próximo (inversa de la CDF empírica).
- Desviación empírica de los años con denominador n.
- Error estándar de la media: `s_muestral/sqrt(n)`, con varianza muestral
  `sum(conteo*(año-media)^2)/(n-1)`.
- IC normal **aproximado** de la media condicional: `media ± 1.95996398454*error`.
  No se presenta si n < 2 o no hay variación observada. No certifica el año real;
  con muestras pequeñas la aproximación puede ser inadecuada.
- Mediana y cuantil 95 % no condicionales: si F no alcanza el nivel requerido,
  se informa «no alcanzado dentro del horizonte», sin asignar un año ficticio.

Sin cruces no hay media del año; con uno no se estima su error estándar.
Sin dispersión observada no se demuestra determinismo. No cruzar es **censura
temporal**, no evidencia de que nunca ocurrirá. Más R reduce error Monte Carlo,
no la dispersión causada por los supuestos ni su incertidumbre de origen.
Se mantienen las advertencias sobre parámetros didácticos, fuentes/calibración
pendientes y ausencia de migración.

### Comprobación con la referencia de S12

Leyendo solo los archivos versionados de `resultados_10000000/` se recuperan:

- 9 934 770 cruces y 65 230 casos sin cruce (0,6523 %).
- Media condicional 2054,50413568; desviación ≈ 2,303814 años;
  error estándar ≈ 0,00073092 años.
- Tiempo informado ≈ 2 188,14 s: **histórico**, no medido de nuevo en el PC que lee.
- Sin T1 equivalente ni procedencia S13: **speedup no disponible**.

Son una comprobación de lectura de esa referencia, no constantes del análisis.

## 5. Rendimiento

Se usa el criterio implementado por los C++: `segundos_total`, desde antes de
cargar datos hasta antes del resumen. Incluye simulación/escritura de escenarios;
excluye la lectura previa de configuración, resumen, distribución, SVG, métricas,
registro de procedencia y análisis. MPI excluye también `MPI_Init`/`MPI_Finalize`.
El tiempo externo completo se registra separado y **no se mezcla** con ese criterio.

Sobre medias de repeticiones comparables:

- `S(p)=T1/Tp`, `E(p)=S/p`, `C(p)=p*Tp`.
- `f_KF=(1/S-1/p)/(1-1/p)`, solo para p > 1.
- `1/f_KF` se muestra solo para `0 < f_KF <= 1`, como extrapolación de Amdahl.

p = procesos × hilos, no núcleos físicos certificados. Se muestra desviación
muestral entre repeticiones (N/D con una sola); menos de tres se marca preliminar.
Una media menor es una comparación descriptiva, **no** una prueba de significación.
Tiempos menores de un segundo reciben un aviso diagnóstico de ejecución corta.
No se ocultan speedups menores que uno ni se fuerza a que una versión gane.
Karp–Flatt incluye sobrecostos: no identifica por sí solo sus causas.
Go se analiza individualmente, no se mezcla en fórmulas de paralelización C++.

### Procedencia y rechazos

`procedencia.json` registra ID de ejecución/campaña, repetición, fechas UTC, ID de
equipo resumido mediante SHA-256, modelo CPU, CPU disponibles, sistema, afinidad,
variables relevantes, herramientas detectadas, hashes de fuentes/Makefiles,
binarios, tres CSV originales y configuración. También conserva comando, criterio
de tiempo, paralelismo observado, hashes de salidas y equivalencia de escenarios.

Se comprueba que datos, configuración, fuentes y binarios no cambien durante cada
corrida. La comparación exige **misma campaña, contexto, carga, parámetros,
repeticiones y resultados equivalentes**. Rechaza copias con el mismo ID, archivos
alterados, campañas incompletas y referencias incompatibles. Si hay varias líneas
base incompatibles no elige una arbitrariamente.

Las huellas sirven para consistencia/auditoría; **no son firmas autenticadas contra
manipulación deliberada**. Las herramientas detectadas no demuestran qué compilador
o banderas generaron un binario existente: se conservan sus hashes sin inventarlo.

### Límites explícitos

- Las salidas antiguas no se atribuyen al equipo actual: no se inventa procedencia.
- CPU/pared no es speedup. En MPI/híbrido la CPU se reduce antes de la escritura
  final y no representa exactamente todo el mismo intervalo.
- La memoria MPI/híbrida es máxima **por proceso**, no suma global.
- Go asigna `CPU=Total` en `main.go`: se indica CPU no medida. Su memoria no-Windows
  es `runtime.MemStats.Sys`, no RSS pico.
- Frecuencia, temperatura, carga externa y topología física bajo virtualización
  no están controladas. No se inventan causas de pérdidas de rendimiento.
- La instrumentación va fuera de T, pero E/S y cachés siguen influyendo; no se
  pretende un control de caché fría.
- No se ejecutan automáticamente 10 millones ni se extrapola un T1 no medido.

## 6. Pruebas y entrega

```bash
python -m unittest discover -s tests -v
```

Pruebas de estadística, errores, censura, Wilson, metadatos y rechazo de comparaciones,
sin compiladores/Tk/Matplotlib. Sus fixtures se identifican como **sintéticos**.
El workflow de GitHub Actions las configura en Windows/Ubuntu y Python 3.11/3.14.

Prueba gráfica opcional, con pantalla y dependencias:

```bash
python tests/smoke_interfaz.py
python tests/smoke_interfaz.py salidas_s13/mi_campana
python tests/integracion_interfaz_s13.py
```

La integración local se comprobó con una campaña pequeña de los cuatro C++ y una
ejecución Go. **Los tiempos funcionales de prueba no son un benchmark académico.**
Para la entrega, correr en el equipo definitivo una campaña con R adecuado y varias
repeticiones, conservar los archivos y exportar el informe. No hay que cambiar
constantes ni reescribir conclusiones predeterminadas.
