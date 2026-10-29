# Linea base secuencial (T1)

Maquina: Intel(R) Xeon(R) Processor @ 2.80GHz · Linux 6.18.44-fc-v114 · g++ (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0 · -O2

Repeticiones por R: 3. Misma semilla en todas: los CSV de resultados son identicos; solo varia el tiempo.

| R (escenarios) | T1 total (s) media ± sd | CV (%) | CPU/pared (%) | ms / escenario | escenarios/s | escenario-anios/s | RSS pico (MiB) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1,000 | 3.193 ± 0.058 | 1.8 | 98.8 | 3.192 | 313.4 | 12,534 | 14.1 |
| 10,000 | 32.937 ± 1.547 | 4.7 | 98.6 | 3.294 | 304.1 | 12,163 | 14.1 |
| 100,000 | 305.876 ± 6.232 | 2.0 | 98.4 | 3.059 | 327.0 | 13,081 | 14.1 |

Escalado con R: al multiplicar R por 100 el tiempo se multiplica por 95.8 (lineal: O(R·H), sin crecimiento de memoria).

Metricas del Sprint 3 que se calcularan con este T1 (mismo R, misma maquina):
- Speedup S(p) = T1 / Tp
- Eficiencia E(p) = S(p) / p
- Costo C(p) = p · Tp
- Fraccion secuencial (Karp-Flatt) f = (1/S(p) − 1/p) / (1 − 1/p)
- Cota de Amdahl S_max = 1 / f

