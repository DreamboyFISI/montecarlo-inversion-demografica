# Compilacion de las versiones paralelas (Sprint 3, S10-S11). Reutilizan el modelo de ../MonteCarlo_Secuencial/src.
# Uso: make               -> simulador_omp, simulador_mpi y simulador_hibrido
#      make secuencial     -> ../MonteCarlo_Secuencial/simulador (linea base T1)
#      make verificar      -> CSV de OpenMP, MPI e Hibrido identicos byte a byte a los secuenciales
#      make rendimiento    -> speedup, eficiencia y Karp-Flatt (scripts/rendimiento.py)
#      make clean

SEC      := ../MonteCarlo_Secuencial
CXX      ?= g++
MPICXX   ?= mpicxx
CXXFLAGS ?= -std=c++17 -O2 -Wall -Wextra -Wpedantic
CXXFLAGS += -I$(SEC)/src
COMUNES  := $(SEC)/src/configuracion.cpp $(SEC)/src/datos.cpp $(SEC)/src/modelo.cpp $(SEC)/src/escenario.cpp \
            $(SEC)/src/salida.cpp $(SEC)/src/pruebas.cpp
CABECERAS:= $(wildcard $(SEC)/src/*.hpp)

all: simulador_omp simulador_mpi simulador_hibrido

simulador_omp: src/main_openmp.cpp $(COMUNES) $(CABECERAS)
	$(CXX) $(CXXFLAGS) -fopenmp src/main_openmp.cpp $(COMUNES) -o $@

simulador_mpi: src/main_mpi.cpp $(COMUNES) $(CABECERAS)
	$(MPICXX) $(CXXFLAGS) -DOMPI_SKIP_MPICXX src/main_mpi.cpp $(COMUNES) -o $@

simulador_hibrido: src/main_hibrido.cpp $(COMUNES) $(CABECERAS)
	$(MPICXX) $(CXXFLAGS) -fopenmp -DOMPI_SKIP_MPICXX src/main_hibrido.cpp $(COMUNES) -o $@

secuencial:
	$(MAKE) -C $(SEC) simulador

verificar: all secuencial
	./scripts/verificar_equivalencia.sh

rendimiento: all secuencial
	python3 scripts/rendimiento.py --salida rendimiento

clean:
	rm -f simulador_omp simulador_mpi simulador_hibrido

.PHONY: all secuencial verificar rendimiento clean
