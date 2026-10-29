# Monte Carlo demografico — version Go

Implementacion secuencial en Go del mismo modelo disponible en `MonteCarlo_Secuencial`.
Se mantiene separada para poder comparar lenguaje, tiempo y memoria sin mezclar fuentes.

## Estructura

- `cmd/simulador/`: configuracion, carga de datos, modelo y ejecutable.
- `datos/`: copia de los tres CSV de entrada.
- `config_demostracion.ini` y `config_incertidumbre.ini`: configuraciones equivalentes.
- `resultados_interfaz/`: ejecuciones iniciadas desde la interfaz (se crea automaticamente).

## Compilar en Windows

Instale Go y, desde esta carpeta, ejecute:

```powershell
go build -o simulador_go.exe ./cmd/simulador
```

## Ejecutar directamente

```powershell
.\simulador_go.exe --config config_incertidumbre.ini --datos datos --salida resultados_go --escenarios 10000
```

La implementacion usa las mismas ecuaciones demograficas, distribuciones Poisson y binomial exactas y
formatos de salida. Go y C++ usan generadores y algoritmos aleatorios diferentes, por lo que escenarios
individuales no coinciden byte a byte. La comparacion debe hacerse sobre la distribucion agregada.
