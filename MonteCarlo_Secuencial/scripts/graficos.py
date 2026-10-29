"""Graficos de la ejecucion secuencial.

Uso: python3 scripts/graficos.py [carpeta_resultados] [carpeta_datos_procesados] [carpeta_salida]
     (por defecto: resultados_demo  datos_procesados  graficos)
"""
import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

RES = Path(sys.argv[1] if len(sys.argv) > 1 else "resultados_demo")
PROC = Path(sys.argv[2] if len(sys.argv) > 2 else "datos_procesados")
OUT = Path(sys.argv[3] if len(sys.argv) > 3 else "graficos")
OUT.mkdir(parents=True, exist_ok=True)
AZUL, NARANJA, GRIS = "#1F4E79", "#C55A11", "#7F7F7F"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.spines.top": False,
                     "axes.spines.right": False})


def leer(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


tray = leer(RES / "trayectoria_escenario_1.csv")
anios = [int(r["anio"]) for r in tray]
J = [int(r["menores15"]) / 1e6 for r in tray]
A = [int(r["mayores65"]) / 1e6 for r in tray]
dist = leer(RES / "distribucion.csv")
cruce = next((int(r["anio"]) for r in dist if int(r["primeras_inversiones"]) > 0), None)

# 1. Menores de 15 vs 65 o mas
fig, ax = plt.subplots(figsize=(9, 5))
ax.plot(anios, J, color=AZUL, lw=2.5, label="Menores de 15 (J)")
ax.plot(anios, A, color=NARANJA, lw=2.5, label="65 o mas (A)")
if cruce:
    ax.axvline(cruce, color=GRIS, ls="--", lw=1)
    ax.annotate(f"Primera inversion: {cruce}", xy=(cruce, A[anios.index(cruce)]), xytext=(cruce + 1, 4.4),
                arrowprops=dict(arrowstyle="->", color=GRIS))
ax.set_ylabel("Millones de personas")
ax.set_title("Escenario 1: menores de 15 frente a personas de 65 o mas")
ax.legend(frameon=False)
fig.tight_layout()
fig.savefig(OUT / "01_menores_vs_mayores.png", dpi=160)

# 2. Nacimientos y defunciones
fig, ax = plt.subplots(figsize=(9, 5))
ax.plot(anios, [int(r["nacimientos"]) / 1e3 for r in tray], color=AZUL, lw=2.5, label="Nacimientos B(t)")
ax.plot(anios, [int(r["defunciones"]) / 1e3 for r in tray], color=NARANJA, lw=2.5, label="Defunciones D(t)")
ax.set_ylabel("Miles por anio")
ax.set_title("Escenario 1: nacimientos y defunciones simulados")
ax.legend(frameon=False)
fig.tight_layout()
fig.savefig(OUT / "02_nacimientos_defunciones.png", dpi=160)

# 3. Poblacion total
fig, ax = plt.subplots(figsize=(9, 5))
ax.plot(anios, [int(r["poblacion_final"]) / 1e6 for r in tray], color=AZUL, lw=2.5)
ax.set_ylabel("Millones de personas")
ax.set_title("Escenario 1: poblacion total al cierre de cada anio")
fig.tight_layout()
fig.savefig(OUT / "03_poblacion_total.png", dpi=160)

# 4. Piramide inicial por grupos quinquenales
pob = leer(PROC / "poblacion_edad_simple.csv")
grupos = [f"{a}-{a+4}" for a in range(0, 100, 5)] + ["100+"]
h = [sum(int(pob[a + j]["hombres"]) for j in range(5)) for a in range(0, 100, 5)] + [int(pob[100]["hombres"])]
m = [sum(int(pob[a + j]["mujeres"]) for j in range(5)) for a in range(0, 100, 5)] + [int(pob[100]["mujeres"])]
fig, ax = plt.subplots(figsize=(8, 6.5))
y = range(len(grupos))
ax.barh(y, [-v / 1e6 for v in h], color=AZUL, label="Hombres")
ax.barh(y, [v / 1e6 for v in m], color=NARANJA, label="Mujeres")
ax.set_yticks(list(y), grupos)
ax.set_xticks([-1.5, -1, -0.5, 0, 0.5, 1, 1.5], ["1,5", "1", "0,5", "0", "0,5", "1", "1,5"])
ax.set_xlabel("Millones de personas")
ax.set_title("Poblacion inicial por edad y sexo (32,7 millones)")
ax.legend(frameon=False, loc="upper right")
fig.tight_layout()
fig.savefig(OUT / "04_piramide_inicial.png", dpi=160)

# 5. Probabilidad acumulada F(y)
fig, ax = plt.subplots(figsize=(9, 5))
ax.step([int(r["anio"]) for r in dist], [float(r["probabilidad_acumulada"]) for r in dist], where="post",
        color=AZUL, lw=2.5)
ax.set_ylim(-0.02, 1.05)
ax.set_ylabel("F(y) = P(T <= y)")
ax.set_title("Probabilidad acumulada del primer anio de inversion F(y)")
fig.tight_layout()
fig.savefig(OUT / "05_probabilidad_acumulada.png", dpi=160)
# 6. Distribucion del primer anio de inversion p(T = y) (campana cuando hay incertidumbre macro)
anios_d = [int(r["anio"]) for r in dist]
p_anual = [float(r["probabilidad_anual"]) for r in dist]
con_masa = [a for a, p in zip(anios_d, p_anual) if p > 0]
n_total = sum(int(r["primeras_inversiones"]) for r in dist)
media = sum(a * p for a, p in zip(anios_d, p_anual)) / max(sum(p_anual), 1e-12)
sd = (sum(p * (a - media) ** 2 for a, p in zip(anios_d, p_anual)) / max(sum(p_anual), 1e-12)) ** 0.5
fig, ax = plt.subplots(figsize=(9, 5))
ax.bar(anios_d, p_anual, color=AZUL, width=0.8)
ax.axvline(media, color=NARANJA, ls="--", lw=1.5)
ax.text(media + 0.3, max(p_anual) * 0.95, f"media {media:.1f}\nsd {sd:.1f} anios", color=NARANJA, va="top")
if con_masa:
    ax.set_xlim(min(con_masa) - 2, max(con_masa) + 2)
ax.set_ylabel("p(T = y)")
ax.set_xlabel("Primer anio de inversion T")
p_sin = 1 - sum(p_anual)
ax.set_title(f"Primer anio de inversion T ({n_total:,} escenarios con inversion; "
             f"{p_sin:.1%} sin inversion)".replace(",", " "))
fig.tight_layout()
fig.savefig(OUT / "06_distribucion_anio.png", dpi=160)
print("Graficos en", OUT)
