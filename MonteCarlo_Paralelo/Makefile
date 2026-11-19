# Compilacion de las versiones paralelas (Sprint 3, S10-S11). Reutilizan el modelo de ../MonteCarlo_Secuencial/src.
# Uso: make               -> simulador_omp, simulador_mpi y simulador_hibrido
#      make secuencial     -> ../MonteCarlo_Secuencial/simulador (linea base T1)
#      make verificar      -> CSV de OpenMP, MPI e Hibrido identicos byte a byte a los secuenciales
#      make rendimiento    -> speedup, eficiencia y Karp-Flatt (scripts/rendimiento.py)
#      make simulador_cuda simulador_mpi_cuda -> versiones CUDA y MPI + CUDA (necesitan nvcc; no forman parte de make all)
#      make clean

SEC      := ../MonteCarlo_Secuencial
CXX      ?= g++
MPICXX   ?= mpicxx
NVCC     ?= nvcc
CUDA_HOME?= /usr/local/cuda
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

# CUDA: gpu.cu se compila con nvcc y el resto con g++. --fmad=false evita que la GPU fusione
# multiplicacion y suma, para que calcule lo mismo que la CPU con el mismo codigo (prueba C4).
CUDA_FUENTES := src/gpu.hpp src/nucleo_cuda.hpp src/cuda_comun.hpp

gpu_cuda.o: src/gpu.cu src/gpu.hpp src/nucleo_cuda.hpp
	$(NVCC) -std=c++17 -O3 --fmad=false -c src/gpu.cu -o $@

simulador_cuda: src/main_cuda.cpp gpu_cuda.o $(CUDA_FUENTES) $(COMUNES) $(CABECERAS)
	$(CXX) $(CXXFLAGS) src/main_cuda.cpp $(COMUNES) gpu_cuda.o -o $@ -L$(CUDA_HOME)/lib64 -lcudart

# MPI + CUDA + OpenMP: el proceso 0 usa la GPU y los demas la CPU, todos con el nucleo de nucleo_cuda.hpp.
simulador_mpi_cuda: src/main_mpi_cuda.cpp gpu_cuda.o $(CUDA_FUENTES) $(COMUNES) $(CABECERAS)
	$(MPICXX) $(CXXFLAGS) -fopenmp -DOMPI_SKIP_MPICXX src/main_mpi_cuda.cpp $(COMUNES) gpu_cuda.o -o $@ -L$(CUDA_HOME)/lib64 -lcudart

secuencial:
	$(MAKE) -C $(SEC) simulador

verificar: all secuencial
	./scripts/verificar_equivalencia.sh

rendimiento: all secuencial
	python3 scripts/rendimiento.py --salida rendimiento

clean:
	rm -f simulador_omp simulador_mpi simulador_hibrido simulador_cuda simulador_mpi_cuda gpu_cuda.o

.PHONY: all secuencial verificar rendimiento clean
