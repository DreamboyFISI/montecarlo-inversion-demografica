# Rendimiento de OpenMP y MPI frente a la linea base (S10)

Maquina: Intel(R) Core(TM) i5-9300H CPU @ 2.40GHz · 8 CPU logicas · Linux 7.2.11-200.fc44.x86_64 · g++ (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0 · mpirun (Open MPI) 4.1.6 · -O2

R = 10,000 escenarios, horizonte 40 anios, 3 repeticiones intercaladas por configuracion. T = tiempo total de pared (carga + simulacion + escritura), media ± sd.

| Version | p | Tp (s) | S(p) = T1/Tp | E(p) = S/p | C(p) = p·Tp (s) | Karp-Flatt f | Amdahl S_max | CPU/pared | RSS max (MiB) | Espera+Gatherv (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| secuencial | 1 | 25.253 ± 0.220 | 1.00 | 1.00 | 25.25 | — | — | 1.00 | 14.7 | — |
| openmp | 1 | 25.577 ± 0.381 | 0.99 | 0.99 | 25.58 | — | — | 1.00 | 14.7 | — |
| openmp | 2 | 13.166 ± 0.156 | 1.92 | 0.96 | 26.33 | 0.0427 | 23.4 | 1.99 | 14.7 | — |
| openmp | 4 | 7.776 ± 0.434 | 3.25 | 0.81 | 31.10 | 0.0772 | 12.9 | 3.97 | 14.7 | — |
| openmp | 8 | 6.820 ± 0.417 | 3.70 | 0.46 | 54.56 | 0.1658 | 6.0 | 7.16 | 14.7 | — |
| mpi | 1 | 25.964 ± 0.371 | 0.97 | 0.97 | 25.96 | — | — | 1.00 | 15.1 | 0.000 |
| mpi | 2 | 13.665 ± 0.307 | 1.85 | 0.92 | 27.33 | 0.0823 | 12.2 | 2.00 | 15.1 | 0.093 |
| mpi | 4 | 9.061 ± 0.617 | 2.79 | 0.70 | 36.25 | 0.1451 | 6.9 | 3.97 | 15.4 | 0.249 |
| mpi | 8 | 9.234 ± 0.478 | 2.73 | 0.34 | 73.87 | 0.2751 | 3.6 | 6.98 | 15.4 | 0.398 |

Lectura: S(p) cercano a p y E(p) cercano a 1 indican escalado lineal; un f de Karp-Flatt que crece con p indica sobrecosto paralelo (sincronizacion, comunicacion), y uno constante, una parte secuencial fija (escritura ordenada de los CSV en un solo hilo/proceso).
