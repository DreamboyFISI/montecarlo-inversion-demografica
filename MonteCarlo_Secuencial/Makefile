# Compilacion del simulador secuencial (C++17, sin MPI ni OpenMP).
# Uso: make            -> compila ./simulador
#      make test       -> pruebas controladas
#      make demo       -> 1 000 escenarios en resultados_demo/
#      make campana    -> 10 000 escenarios con incertidumbre en resultados_incertidumbre/
#      make clean

CXX      ?= g++
CXXFLAGS ?= -std=c++17 -O2 -Wall -Wextra -Wpedantic
FUENTES  := src/main.cpp src/configuracion.cpp src/datos.cpp src/modelo.cpp src/escenario.cpp src/salida.cpp src/pruebas.cpp
CABECERAS:= $(wildcard src/*.hpp)

simulador: $(FUENTES) $(CABECERAS)
	$(CXX) $(CXXFLAGS) $(FUENTES) -o $@

test: simulador
	./simulador --self-test --datos datos

demo: simulador
	./simulador --config config_demostracion.ini --datos datos --salida resultados_demo

# 10 000 escenarios con incertidumbre macro: campana del anio de inversion (distribucion_anio.svg)
campana: simulador
	./simulador --config config_incertidumbre.ini --datos datos --salida resultados_incertidumbre --escenarios 10000

clean:
	rm -f simulador simulador.exe

.PHONY: test demo campana clean
