"""Genera docs/cronograma.png: cronograma Scrum del proyecto (S4-S15).

Uso:  python docs/generar_cronograma.py
Para cambiar el cronograma, editar la lista ACTIVIDADES y volver a ejecutar.
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Rectangle

SEMANAS = list(range(4, 16))  # S4 .. S15

# (nombre, primera semana, última semana, color de relleno de la franja, color de las barras)
SPRINTS = [
    ("Sprint 1", 4, 6, "#dcecfb", "#8fc0f5"),
    ("Sprint 2 · pausa en S8", 7, 9, "#dff1dc", "#86c98a"),
    ("Sprint 3", 10, 12, "#fde6d2", "#f7a55e"),
    ("Sprint 4", 13, 14, "#ebdcf8", "#b388e8"),
    ("Presentación", 15, 15, "#e4e4e4", "#7a7a7a"),
]

# (actividad, primera semana, última semana)
ACTIVIDADES = [
    ("Definición del Product Backlog", 4, 4),
    ("Recopilación y limpieza de datos", 4, 5),
    ("Diseño del modelo probabilístico", 5, 6),
    ("Implementación secuencial", 7, 7),
    ("Validación y línea base", 9, 9),
    ("Paralelización con OpenMP", 10, 10),
    ("MPI y contenedores Docker", 10, 10),
    ("Integración MPI + OpenMP", 11, 11),
    ("Clustering de escenarios", 11, 12),
    ("Ejecución de 10 millones de escenarios", 12, 12),
    ("Análisis de resultados y rendimiento", 13, 13),
    ("Informe final y correcciones", 13, 14),
    ("Diapositivas y ensayo", 14, 14),
    ("Presentación final", 15, 15),
]

PLANNING = [4, 7, 10, 13]
REVIEW = [6, 9, 12, 14]
PAUSA = 8

ANCHO_ETIQUETA = 5.6  # ancho de la columna de actividades, en unidades de semana
TINTA = "#16233f"
LINEA = "#c9c9c9"


def sprint_de(semana):
    for sprint in SPRINTS:
        if sprint[1] <= semana <= sprint[2]:
            return sprint
    raise ValueError(semana)


def x_de(semana):
    return ANCHO_ETIQUETA + (semana - SEMANAS[0])


def main():
    n = len(ACTIVIDADES)
    filas_total = n + 2  # + Planning y Review
    ancho = ANCHO_ETIQUETA + len(SEMANAS)
    y_flechas, y_cabecera = 2.0, 1.0  # altos de la franja de sprints y de la cabecera

    fig, ax = plt.subplots(figsize=(16.5, 8.8), dpi=150)
    ax.set_xlim(-0.05, ancho + 0.35)
    ax.set_ylim(filas_total + 0.05, -(y_flechas + y_cabecera) - 1.9)
    ax.axis("off")

    ax.text(ancho / 2, -(y_flechas + y_cabecera) - 1.25, "Cronograma del proyecto — Scrum",
            ha="center", va="center", fontsize=24, fontweight="bold", color=TINTA)
    ax.text(ancho / 2, -(y_flechas + y_cabecera) - 0.45,
            "Inversión demográfica del Perú · Monte Carlo con MPI y OpenMP",
            ha="center", va="center", fontsize=15, fontweight="bold", color=TINTA)

    # Franja de sprints (flechas)
    for nombre, ini, fin, _fondo, fuerte in SPRINTS:
        x0, x1 = x_de(ini), x_de(fin) + 1
        y0, y1 = -(y_flechas + y_cabecera) + 0.15, -y_cabecera - 0.05
        punta = 0.22
        ax.add_patch(Polygon(
            [(x0, y0), (x1, y0), (x1 + punta, (y0 + y1) / 2), (x1, y1), (x0, y1), (x0 + punta, (y0 + y1) / 2)],
            closed=True, facecolor=fuerte, edgecolor="white", linewidth=1.5, zorder=3 + ini))
        es_presentacion = nombre == "Presentación"
        ax.text((x0 + x1) / 2 + punta * 0.6, (y0 + y1) / 2, nombre, ha="center", va="center",
                fontsize=7.5 if es_presentacion else (10.5 if len(nombre) > 10 else 12), fontweight="bold",
                color="white" if es_presentacion else TINTA, zorder=20)

    # Fondos por sprint y columna de pausa
    for semana in SEMANAS:
        fondo = "#dedede" if semana == PAUSA else sprint_de(semana)[3]
        ax.add_patch(Rectangle((x_de(semana), -y_cabecera), 1, filas_total + y_cabecera,
                               facecolor=fondo, edgecolor="none", zorder=0))
        ax.text(x_de(semana) + 0.5, -y_cabecera / 2, f"S{semana}", ha="center", va="center",
                fontsize=12, fontweight="bold", color=TINTA)
    ax.add_patch(Rectangle((0, -y_cabecera), ANCHO_ETIQUETA, y_cabecera, facecolor="#e6e6e6", edgecolor="none"))
    ax.text(ANCHO_ETIQUETA / 2, -y_cabecera / 2, "ACTIVIDADES", ha="center", va="center",
            fontsize=13, fontweight="bold", color=TINTA)
    ax.text(x_de(PAUSA) + 0.5, n / 2, "EXÁMENES PARCIALES · SIN ACTIVIDADES", rotation=90,
            ha="center", va="center", fontsize=10, color="#333333")

    # Rejilla
    for fila in range(filas_total + 1):
        ax.plot([0, ancho], [fila, fila], color=LINEA, linewidth=0.8, zorder=1)
    ax.plot([0, ancho], [n, n], color="#8a8a8a", linewidth=1.4, zorder=2)
    for semana in SEMANAS:
        ax.plot([x_de(semana)] * 2, [-y_cabecera, filas_total], color=LINEA, linewidth=0.8, zorder=1)
    ax.add_patch(Rectangle((0, -y_cabecera), ancho, filas_total + y_cabecera,
                           facecolor="none", edgecolor="#8a8a8a", linewidth=1.2, zorder=5))

    # Actividades
    for fila, (nombre, ini, fin) in enumerate(ACTIVIDADES):
        ax.text(0.2, fila + 0.5, nombre, ha="left", va="center", fontsize=11.5, color="#111111")
        for semana in range(ini, fin + 1):
            if semana == PAUSA:
                continue
            ax.add_patch(Rectangle((x_de(semana) + 0.04, fila + 0.14), 0.92, 0.72,
                                   facecolor=sprint_de(semana)[4], edgecolor="none", zorder=4))

    # Ceremonias
    for desplazamiento, (nombre, semanas, marcador, color, tam) in enumerate([
        ("Sprint Planning", PLANNING, "o", "#1f5fbf", 11),
        ("Sprint Review y Retrospectiva", REVIEW, "D", "#c8283c", 10),
    ]):
        y = n + desplazamiento + 0.5
        ax.text(0.2, y, nombre, ha="left", va="center", fontsize=11.5, fontweight="bold", color=TINTA)
        for semana in semanas:
            ax.plot(x_de(semana) + 0.5, y, marker=marcador, markersize=tam, color=color, zorder=6)

    salida = Path(__file__).with_name("cronograma.png")
    fig.savefig(salida, bbox_inches="tight", facecolor="white")
    print(f"Escrito {salida}")


if __name__ == "__main__":
    main()
