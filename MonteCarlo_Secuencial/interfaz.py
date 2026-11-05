"""Interfaz de escritorio y panel de presentacion para la simulacion Monte Carlo y Clustering.
Proyecto: montecarlo-inversion-demografica (Semana 11 y Semana 13)

Uso desde la raiz o desde MonteCarlo_Secuencial:
    python MonteCarlo_Secuencial/interfaz.py

Permite presentar:
1. Simulacion Monte Carlo: secuencial, OpenMP, MPI, Hibrido (S11) y Go.
2. Segmentacion y Mineria de Datos (Clustering S13): perfiles demograficos,
   graficos de dispersion de factores, boxplots de anio de cruce, arbol de decision
   explicable y agrupamiento de edades simples (Parte B).
3. Metricas de rendimiento, speedup y arquitectura Scrum.
"""

from __future__ import annotations

import csv
import math
import os
import queue
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.image as mpimg

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
PARALELO_BASE = ROOT / "MonteCarlo_Paralelo"
GO_BASE = ROOT / "MonteCarlo_Go"
CLUSTERING_BASE = ROOT / "MonteCarlo_Clustering"

# Paleta cromatica moderna y profesional
AZUL = "#1E5F8A"
AZUL_OSCURO = "#133C57"
CELESTE = "#0288D1"
MENTA = "#26A69A"
VERDE = "#43A047"
FONDO = "#F5F7FA"
TEXTO = "#1C2D42"
GRIS = "#546E7A"
BLANCO = "#FFFFFF"
NARANJA = "#FB8C00"
ROJO = "#E53935"

MS_REFERENCIA = {
    "C++ Secuencial": 2.17,
    "C++ OpenMP": 0.65,
    "C++ MPI": 0.85,
    "C++ Híbrido (MPI+OpenMP)": 0.55,
    "Go": 2.19,
}


def entero_positivo(texto: str) -> int:
    valor = int(texto.replace(" ", "").replace(",", ""))
    if valor < 1 or valor > 1_000_000_000:
        raise ValueError
    return valor


def duracion_legible(segundos: float) -> str:
    if segundos < 60:
        return f"{segundos:.2f} s"
    if segundos < 3600:
        return f"{segundos / 60:.1f} min"
    return f"{segundos / 3600:.1f} h"


def ruta_a_wsl(p: Path) -> str:
    res = p.resolve().as_posix()
    if len(res) >= 2 and res[1] == ':':
        return f"/mnt/{res[0].lower()}{res[2:]}"
    return res


class InterfazMonteCarlo(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Inversión Demográfica del Perú — Monte Carlo, Paralelismo y Clustering (S11–S13)")
        self.geometry("1280x830")
        self.minsize(1100, 720)
        self.configure(bg=FONDO)

        self.resultados: list[dict[str, str]] = []
        self.intervalos: list[tuple[int, int, int, float]] = []
        self.carpeta_actual: Path | None = None
        self.proceso: subprocess.Popen[str] | None = None
        self.cola: queue.Queue[tuple[str, object]] = queue.Queue()

        self._configurar_estilos()
        self._construir_interfaz()

        self.after(120, self._procesar_cola)
        # Carga automatica inicial si existen resultados
        ejemplo = BASE / "resultados_incertidumbre"
        if ejemplo.exists():
            self.after(200, lambda: self.cargar_resultados(ejemplo))
        self.after(350, self._cargar_datos_clustering)

    def _configurar_estilos(self) -> None:
        estilo = ttk.Style(self)
        estilo.theme_use("clam")
        estilo.configure("TFrame", background=FONDO)
        estilo.configure("Card.TFrame", background=BLANCO, relief="flat")
        estilo.configure("TLabel", background=FONDO, foreground=TEXTO, font=("Segoe UI", 10))
        estilo.configure("Title.TLabel", font=("Segoe UI Semibold", 18), foreground=AZUL_OSCURO)
        estilo.configure("Subtitle.TLabel", font=("Segoe UI", 9), foreground=GRIS)
        estilo.configure("CardTitle.TLabel", background=BLANCO, font=("Segoe UI Semibold", 9), foreground=GRIS)
        estilo.configure("CardValue.TLabel", background=BLANCO, font=("Segoe UI Semibold", 15), foreground=AZUL)
        estilo.configure("Accent.TButton", background=AZUL, foreground=BLANCO, font=("Segoe UI Semibold", 10), padding=8)
        estilo.map("Accent.TButton", background=[("active", CELESTE), ("disabled", "#B0BEC5")])
        estilo.configure("Soft.TButton", background=MENTA, foreground=BLANCO, font=("Segoe UI Semibold", 9), padding=7)
        estilo.map("Soft.TButton", background=[("active", VERDE)])
        estilo.configure("TNotebook", background=FONDO, borderwidth=0)
        estilo.configure("TNotebook.Tab", font=("Segoe UI Semibold", 10), padding=(16, 7), background="#CFD8DC", foreground=TEXTO)
        estilo.map("TNotebook.Tab", background=[("selected", BLANCO), ("active", "#B0BEC5")], foreground=[("selected", AZUL)])
        estilo.configure("Treeview", rowheight=26, background=BLANCO, fieldbackground=BLANCO, font=("Segoe UI", 9))
        estilo.configure("Treeview.Heading", font=("Segoe UI Semibold", 9), background="#ECEFF1", foreground=TEXTO)

    def _construir_interfaz(self) -> None:
        cabecera = tk.Frame(self, bg=BLANCO, height=72, padx=22, pady=10)
        cabecera.pack(fill="x")
        
        info_frame = tk.Frame(cabecera, bg=BLANCO)
        info_frame.pack(side="left")
        tk.Label(
            info_frame,
            text="Inversión Demográfica del Perú — Simulación Monte Carlo y Minería de Datos",
            font=("Segoe UI Semibold", 16),
            bg=BLANCO,
            fg=AZUL_OSCURO
        ).pack(anchor="w")
        tk.Label(
            info_frame,
            text="Programación Paralela y Concurrente · C++17 (Secuencial, OpenMP, MPI, Híbrido S11) + Clustering de Escenarios (S13)",
            font=("Segoe UI", 9),
            bg=BLANCO,
            fg=GRIS
        ).pack(anchor="w")

        badge_frame = tk.Frame(cabecera, bg=BLANCO)
        badge_frame.pack(side="right", padx=10)
        tk.Label(
            badge_frame,
            text="ESTADO: DEMO_NO_VALIDADO",
            bg="#FFF3E0",
            fg="#E65100",
            font=("Segoe UI Semibold", 9),
            padx=10,
            pady=4,
            relief="solid",
            bd=1
        ).pack(anchor="e")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=15, pady=(10, 15))

        # Pestaña 1: Simulacion Monte Carlo
        self.tab_simulacion = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_simulacion, text="  1. Simulación Monte Carlo (S7–S11)  ")
        self._construir_tab_simulacion(self.tab_simulacion)

        # Pestaña 2: Mineria de Datos & Clustering (Semana 13)
        self.tab_clustering = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_clustering, text="  2. Segmentación & Clustering (S13)  ")
        self._construir_tab_clustering(self.tab_clustering)

        # Pestaña 3: Resumen Ejecutivo & Cronograma Scrum
        self.tab_scrum = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_scrum, text="  3. Arquitectura y Cronograma Scrum  ")
        self._construir_tab_scrum(self.tab_scrum)

    # =========================================================================
    # PESTAÑA 1: SIMULACION MONTE CARLO
    # =========================================================================
    def _construir_tab_simulacion(self, padre: ttk.Frame) -> None:
        cuerpo = ttk.Panedwindow(padre, orient="horizontal")
        cuerpo.pack(fill="both", expand=True, padx=10, pady=10)

        lateral = ttk.Frame(cuerpo, style="Card.TFrame", padding=15, width=280)
        principal = ttk.Frame(cuerpo, style="Card.TFrame", padding=12)
        cuerpo.add(lateral, weight=0)
        cuerpo.add(principal, weight=1)

        # Controles
        ttk.Label(lateral, text="PARÁMETROS DE SIMULACIÓN", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 10))

        ttk.Label(lateral, text="Motor / Versión:", background=BLANCO).pack(anchor="w")
        self.motor_var = tk.StringVar(value="C++ Secuencial")
        motores = ["C++ Secuencial", "C++ OpenMP", "C++ MPI", "C++ Híbrido (MPI+OpenMP)", "Go"]
        selector_motor = ttk.Combobox(lateral, textvariable=self.motor_var, values=motores, state="readonly")
        selector_motor.pack(fill="x", pady=(3, 10))
        selector_motor.bind("<<ComboboxSelected>>", lambda _e: self._actualizar_estimacion())

        ttk.Label(lateral, text="Configuración (.ini):", background=BLANCO).pack(anchor="w")
        self.config_var = tk.StringVar(value="config_incertidumbre.ini")
        opciones_ini = [p.name for p in BASE.glob("config*.ini")]
        if not opciones_ini:
            opciones_ini = ["config_incertidumbre.ini", "config_demostracion.ini"]
        ttk.Combobox(lateral, textvariable=self.config_var, values=opciones_ini, state="readonly").pack(fill="x", pady=(3, 10))

        ttk.Label(lateral, text="Cantidad de escenarios:", background=BLANCO).pack(anchor="w")
        self.escenarios_var = tk.StringVar(value="10000")
        entrada_esc = ttk.Entry(lateral, textvariable=self.escenarios_var)
        entrada_esc.pack(fill="x", pady=(3, 6))
        entrada_esc.bind("<KeyRelease>", lambda _e: self._actualizar_estimacion())

        rapidos = ttk.Frame(lateral, style="Card.TFrame")
        rapidos.pack(fill="x", pady=(0, 10))
        for val in (1_000, 10_000, 100_000):
            ttk.Button(rapidos, text=f"{val // 1000}k", width=5, command=lambda v=val: self._poner_escenarios(v)).pack(side="left", padx=(0, 4))

        self.aviso_var = tk.StringVar()
        self.aviso = tk.Label(lateral, textvariable=self.aviso_var, bg=BLANCO, fg=GRIS, justify="left", wraplength=240, font=("Segoe UI", 8))
        self.aviso.pack(fill="x", pady=(0, 10))
        self._actualizar_estimacion()

        self.ejecutar_btn = ttk.Button(lateral, text="▶ Ejecutar Simulación", style="Accent.TButton", command=self.ejecutar)
        self.ejecutar_btn.pack(fill="x", pady=(2, 6))

        ttk.Button(lateral, text="Cargar Resultados CSV", style="Soft.TButton", command=self.seleccionar_resultados).pack(fill="x")

        self.progreso = ttk.Progressbar(lateral, mode="indeterminate")
        self.progreso.pack(fill="x", pady=(14, 4))
        self.estado_var = tk.StringVar(value="Listo")
        tk.Label(lateral, textvariable=self.estado_var, bg=BLANCO, fg=GRIS, justify="left", wraplength=240, font=("Segoe UI", 8)).pack(fill="x")

        ttk.Separator(lateral).pack(fill="x", pady=12)
        ttk.Label(lateral, text="HIPÓTESIS DEMOGRÁFICA", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 4))
        tk.Label(
            lateral,
            text="Inversión: Primer año donde A (≥65 años) > J (<15 años). "
                 "Con σ=0 ocurre en 2054. Con incertidumbre macro σ_f=0.05 y σ_m=0.015 se genera la distribución estocástica.",
            bg=BLANCO, fg=GRIS, justify="left", wraplength=240, font=("Segoe UI", 8)
        ).pack(fill="x")

        # Grafico y metricas
        barra_g = ttk.Frame(principal, style="Card.TFrame")
        barra_g.pack(fill="x")
        ttk.Label(barra_g, text="DISTRIBUCIÓN DEL AÑO DE INVERSIÓN DEMOGRÁFICA", style="CardTitle.TLabel").pack(side="left")
        self.vista_var = tk.StringVar(value="Probabilidad anual")
        selector_vista = ttk.Combobox(barra_g, textvariable=self.vista_var, values=["Probabilidad anual", "Probabilidad acumulada"], state="readonly", width=22)
        selector_vista.pack(side="right")
        selector_vista.bind("<<ComboboxSelected>>", lambda _e: self.dibujar())

        self.figura = Figure(figsize=(7.5, 3.8), dpi=100, facecolor=BLANCO)
        self.eje = self.figura.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.figura, master=principal)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, pady=(6, 0))
        self.canvas.mpl_connect("motion_notify_event", self._mostrar_punto)
        self.anotacion = None
        self.dibujar()

        self.resumen_var = tk.StringVar(value="Cargando resultados...")
        tk.Label(principal, textvariable=self.resumen_var, bg="#E8F5E9", fg=TEXTO, anchor="w", padx=10, pady=6, font=("Segoe UI Semibold", 9)).pack(fill="x", pady=(4, 0))
        self.intervalos_var = tk.StringVar(value="")
        tk.Label(principal, textvariable=self.intervalos_var, bg="#E1F5FE", fg=TEXTO, anchor="w", padx=10, pady=5, font=("Segoe UI", 8)).pack(fill="x", pady=(2, 6))

        # Tarjetas de metricas inferiores
        tarjetas = ttk.Frame(padre, padding=(10, 0, 10, 10))
        tarjetas.pack(fill="x")
        nombres = ["Escenarios", "Tiempo total", "ms / escenario", "Rendimiento", "CPU / pared", "RSS pico"]
        self.metricas_vars: dict[str, tk.StringVar] = {}
        for i, nombre in enumerate(nombres):
            tarjeta = ttk.Frame(tarjetas, style="Card.TFrame", padding=(10, 6))
            tarjeta.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 5, 0))
            tarjetas.columnconfigure(i, weight=1)
            ttk.Label(tarjeta, text=nombre, style="CardTitle.TLabel").pack(anchor="w")
            var = tk.StringVar(value="--")
            ttk.Label(tarjeta, textvariable=var, style="CardValue.TLabel").pack(anchor="w", pady=(1, 0))
            self.metricas_vars[nombre] = var

    # =========================================================================
    # PESTAÑA 2: CLUSTERING Y REGÍMENES DEMOGRÁFICOS (S13)
    # =========================================================================
    def _construir_tab_clustering(self, padre: ttk.Frame) -> None:
        cuerpo = ttk.Panedwindow(padre, orient="horizontal")
        cuerpo.pack(fill="both", expand=True, padx=10, pady=10)

        panel_control = ttk.Frame(cuerpo, style="Card.TFrame", padding=14, width=320)
        panel_visual = ttk.Frame(cuerpo, style="Card.TFrame", padding=12)
        cuerpo.add(panel_control, weight=0)
        cuerpo.add(panel_visual, weight=1)

        ttk.Label(panel_control, text="VISOR DE MINERÍA DE DATOS", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Label(panel_control, text="Seleccionar lámina explicativa:", background=BLANCO).pack(anchor="w")

        self.grafico_clustering_var = tk.StringVar(value="04. Espacio de Factores por Régimen")
        self.mapa_graficos = {
            "04. Espacio de Factores por Régimen": CLUSTERING_BASE / "graficos_clustering" / "04_scatter_factores_clusters.png",
            "05. Distribución de Años por Segmento (Boxplots)": CLUSTERING_BASE / "graficos_clustering" / "05_distribucion_anio_clusters.png",
            "08. Árbol de Decisión Explicable (Surrogate Tree)": CLUSTERING_BASE / "graficos_clustering" / "08_arbol_decision_reglas.png",
            "06. Proyección PCA 2D (99.4% Varianza)": CLUSTERING_BASE / "graficos_clustering" / "06_scatter_pca.png",
            "07. Comparativa de Algoritmos (Silhouette, DB, CH)": CLUSTERING_BASE / "graficos_clustering" / "07_comparativa_metricas_algoritmos.png",
            "01. Método del Codo y Silhouette (K-Means)": CLUSTERING_BASE / "graficos_clustering" / "01_codo_silhouette_kmeans.png",
            "02. Dendrograma Truncado de Enlace Ward": CLUSTERING_BASE / "graficos_clustering" / "02_dendrograma_jerarquico.png",
            "03. Curva de k-distancias DBSCAN (eps=0.145)": CLUSTERING_BASE / "graficos_clustering" / "03_k_distancias_dbscan.png",
            "Parte B: Perfiles de Edades vs Cortes Oficiales": CLUSTERING_BASE / "graficos_edades" / "03_clusters_edades_vs_oficial.png",
            "Parte B: Perfiles de Mortalidad y Fecundidad": CLUSTERING_BASE / "graficos_edades" / "01_perfiles_demograficos_edad.png",
        }

        combo_lamina = ttk.Combobox(panel_control, textvariable=self.grafico_clustering_var, values=list(self.mapa_graficos.keys()), state="readonly")
        combo_lamina.pack(fill="x", pady=(3, 12))
        combo_lamina.bind("<<ComboboxSelected>>", lambda _e: self._dibujar_grafico_clustering())

        ttk.Button(panel_control, text="🔄 Recalcular Clustering (Python)", style="Soft.TButton", command=self._ejecutar_clustering_script).pack(fill="x", pady=(0, 10))

        ttk.Separator(panel_control).pack(fill="x", pady=8)
        ttk.Label(panel_control, text="MÉTRICAS CLAVE (K-MEANS k=3)", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 4))

        self.kpis_clustering = {
            "Silhouette Score": "0.3165 (Modesta honesta)",
            "Davies-Bouldin": "1.0312",
            "Calinski-Harabasz": "6 203.1",
            "Exactitud Árbol": "89.51 %",
            "Estabilidad ARI": "0.9352 ± 0.038",
            "Speedup 1 vs multi": "1.26x (OpenMP/BLAS)"
        }
        for k, v in self.kpis_clustering.items():
            f = tk.Frame(panel_control, bg=BLANCO)
            f.pack(fill="x", pady=2)
            tk.Label(f, text=f"{k}:", font=("Segoe UI Semibold", 8), bg=BLANCO, fg=GRIS).pack(side="left")
            tk.Label(f, text=v, font=("Segoe UI Semibold", 8), bg=BLANCO, fg=AZUL).pack(side="right")

        ttk.Separator(panel_control).pack(fill="x", pady=10)
        ttk.Label(panel_control, text="HALLAZGO CENTRAL", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 4))
        tk.Label(
            panel_control,
            text="Fecundidad domina fuertemente (r = +0.97). Fecundidad ≤ 1.01 anticipa la inversión (2046–2054). "
                 "Fecundidad > 1.01 la posterga (2055–2065). Fecundidad extrema (+13.9%) nunca invierte (0.75%).",
            bg=BLANCO, fg=TEXTO, justify="left", wraplength=250, font=("Segoe UI", 8)
        ).pack(fill="x")

        # Panel visual: Canvas para la lamina y tabla de segmentos abajo
        self.figura_cl = Figure(figsize=(8, 4.4), dpi=100, facecolor=BLANCO)
        self.eje_cl = self.figura_cl.add_subplot(111)
        self.canvas_cl = FigureCanvasTkAgg(self.figura_cl, master=panel_visual)
        self.canvas_cl.get_tk_widget().pack(fill="both", expand=True)

        # Tabla inferior de perfiles demograficos
        ttk.Label(panel_visual, text="PERFILES DEMOGRÁFICOS DE LOS CUATRO REGÍMENES HALLADOS", style="CardTitle.TLabel").pack(anchor="w", pady=(8, 4))
        columnas = ("segmento", "casos", "pct", "anio_medio", "fecundidad", "mortalidad", "dinamica")
        self.tree_perfiles = ttk.Treeview(panel_visual, columns=columnas, show="headings", height=4)
        self.tree_perfiles.heading("segmento", text="Régimen Demográfico")
        self.tree_perfiles.heading("casos", text="Escenarios (N)")
        self.tree_perfiles.heading("pct", text="% Total")
        self.tree_perfiles.heading("anio_medio", text="Año Medio")
        self.tree_perfiles.heading("fecundidad", text="Factor Fecundidad")
        self.tree_perfiles.heading("mortalidad", text="Factor Mortalidad")
        self.tree_perfiles.heading("dinamica", text="Impacto Demográfico en A y J")

        self.tree_perfiles.column("segmento", width=140, anchor="w")
        self.tree_perfiles.column("casos", width=85, anchor="center")
        self.tree_perfiles.column("pct", width=65, anchor="center")
        self.tree_perfiles.column("anio_medio", width=85, anchor="center")
        self.tree_perfiles.column("fecundidad", width=105, anchor="center")
        self.tree_perfiles.column("mortalidad", width=105, anchor="center")
        self.tree_perfiles.column("dinamica", width=250, anchor="w")
        self.tree_perfiles.pack(fill="x")

        self._llenar_tabla_perfiles()
        self._dibujar_grafico_clustering()

    def _llenar_tabla_perfiles(self) -> None:
        self.tree_perfiles.delete(*self.tree_perfiles.get_children())
        datos = [
            ("Inversión Temprana", "3 499", "34.99 %", "2052.5 (min 2046)", "0.9577 ± 0.034", "0.9911 ± 0.011", "Fecundidad baja reduce J; cruce acelerado"),
            ("Inversión Central", "2 958", "29.58 %", "2054.2 (nominal)", "0.9898 ± 0.028", "1.0138 ± 0.010", "Estabilidad en torno a 2054; mortalidad amortigua A"),
            ("Inversión Tardía", "3 468", "34.68 %", "2056.8 (max 2065)", "1.0493 ± 0.026", "0.9967 ± 0.013", "Fecundidad alta expande J; inversión postergada"),
            ("Sin Inversión", "75", "0.75 %", "> 2065 (Censurado)", "1.1389 ± 0.016", "1.0057 ± 0.016", "Natalidad extrema (+13.9%): J nunca es superada"),
        ]
        for fila in datos:
            self.tree_perfiles.insert("", "end", values=fila)

    def _dibujar_grafico_clustering(self) -> None:
        self.eje_cl.clear()
        nombre = self.grafico_clustering_var.get()
        ruta = self.mapa_graficos.get(nombre)

        if ruta and ruta.exists():
            try:
                img = mpimg.imread(str(ruta))
                self.eje_cl.imshow(img)
                self.eje_cl.axis("off")
                self.figura_cl.tight_layout()
                self.canvas_cl.draw_idle()
                return
            except Exception as e:
                print("Error cargando imagen:", e)

        self.eje_cl.text(0.5, 0.5, f"Lámina no encontrada:\n{ruta}\nEjecute el script de clustering para generarla.",
                         ha="center", va="center", color=ROJO, fontsize=11, transform=self.eje_cl.transAxes)
        self.eje_cl.axis("off")
        self.canvas_cl.draw_idle()

    def _cargar_datos_clustering(self) -> None:
        self._dibujar_grafico_clustering()

    def _ejecutar_clustering_script(self) -> None:
        script = CLUSTERING_BASE / "scripts" / "clustering_escenarios.py"
        entrada = BASE / "resultados_incertidumbre"
        salida_tmp = CLUSTERING_BASE / f"resultados_clustering_{datetime.now().strftime('%H%M%S')}"
        if not script.exists() or not entrada.exists():
            messagebox.showerror("Error", f"No se encontró el script o la entrada en {script}")
            return
        cmd = [sys.executable, str(script), str(entrada), str(salida_tmp), "--carpeta-graficos", str(CLUSTERING_BASE / "graficos_clustering")]
        try:
            messagebox.showinfo("Clustering", "Ejecutando clustering de escenarios en segundo plano...")
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode == 0:
                messagebox.showinfo("Clustering completado", "Clustering recalculado exitosamente.")
                self._dibujar_grafico_clustering()
            else:
                messagebox.showerror("Fallo en clustering", res.stderr or res.stdout)
        except Exception as exc:
            messagebox.showerror("Error", str(exc))

    # =========================================================================
    # PESTAÑA 3: RESUMEN Y CRONOGRAMA SCRUM
    # =========================================================================
    def _construir_tab_scrum(self, padre: ttk.Frame) -> None:
        lienzo_s = tk.Canvas(padre, bg=FONDO, highlightthickness=0)
        scroll_s = ttk.Scrollbar(padre, orient="vertical", command=lienzo_s.yview)
        lienzo_s.configure(yscrollcommand=scroll_s.set)
        scroll_s.pack(side="right", fill="y")
        lienzo_s.pack(side="left", fill="both", expand=True)

        cont = ttk.Frame(lienzo_s, padding=16)
        ventana_s = lienzo_s.create_window((0, 0), window=cont, anchor="nw")
        cont.bind("<Configure>", lambda _e: lienzo_s.configure(scrollregion=lienzo_s.bbox("all")))
        lienzo_s.bind("<Configure>", lambda e: lienzo_s.itemconfigure(ventana_s, width=e.width))

        # Tarjeta de estado de los datos
        t_alerta = tk.Frame(cont, bg="#FFF8E1", bd=1, relief="solid", padx=14, pady=10)
        t_alerta.pack(fill="x", pady=(0, 12))
        tk.Label(t_alerta, text="⚠️ ESTADO DE LOS DATOS: DEMO_NO_VALIDADO", bg="#FFF8E1", fg="#E65100", font=("Segoe UI Semibold", 11)).pack(anchor="w")
        tk.Label(
            t_alerta,
            text="Los resultados corresponden a supuestos de laboratorio didácticos (sigma_fecundidad=0.05, sigma_mortalidad=0.015) "
                 "sobre un horizonte de 40 años (2025–2065). No constituyen una predicción oficial del INEI ni de la ONU.",
            bg="#FFF8E1", fg=TEXTO, font=("Segoe UI", 9), wraplength=950, justify="left"
        ).pack(anchor="w", pady=(3, 0))

        # Tarjeta de Cronograma Scrum
        t_scrum = ttk.Frame(cont, style="Card.TFrame", padding=14)
        t_scrum.pack(fill="x", pady=(0, 12))
        ttk.Label(t_scrum, text="CRONOGRAMA SCRUM DEL PROYECTO (SEMANAS 4 A 15)", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 8))

        columnas_s = ("sprint", "semana", "actividad", "estado")
        tree_s = ttk.Treeview(t_scrum, columns=columnas_s, show="headings", height=10)
        tree_s.heading("sprint", text="Sprint")
        tree_s.heading("semana", text="Semana")
        tree_s.heading("actividad", text="Actividad / Entregable")
        tree_s.heading("estado", text="Estado en Repositorio")

        tree_s.column("sprint", width=90, anchor="center")
        tree_s.column("semana", width=80, anchor="center")
        tree_s.column("actividad", width=480, anchor="w")
        tree_s.column("estado", width=160, anchor="center")
        tree_s.pack(fill="x")

        actividades_scrum = [
            ("Sprint 1", "S4", "Definición del Product Backlog (PB-01) y Criterios de Aceptación", "✔ Hecho"),
            ("Sprint 1", "S4–S5", "Recopilación y limpieza de datos (28 pruebas, edades simples)", "✔ Hecho"),
            ("Sprint 1", "S5–S6", "Diseño del modelo probabilístico (Poisson, binomiales, semillas)", "✔ Hecho"),
            ("Sprint 2", "S7", "Implementación secuencial en C++17 (simulador, 12 pruebas controladas)", "✔ Hecho"),
            ("Sprint 2", "S8", "Pausa académica por exámenes parciales", "— Pausa"),
            ("Sprint 2", "S9", "Validación estadística y línea base T1 (R=10³, 10⁴, 10⁵)", "✔ Hecho"),
            ("Sprint 3", "S10", "Paralelización con OpenMP (simulador_omp) y MPI + Docker (simulador_mpi)", "✔ Hecho"),
            ("Sprint 3", "S11", "Integración híbrida MPI + OpenMP (simulador_hibrido, PB-08)", "✔ Implementado"),
            ("Sprint 3", "S12", "Ejecución masiva de 10 millones de escenarios (R = 10⁷)", "⏳ Pendiente"),
            ("Sprint 4", "S13", "Modelamiento Avanzado: Clustering de Escenarios y Edades (docs/06)", "✔ Implementado"),
            ("Sprint 4", "S14", "Informe final, correcciones y ensayo de diapositivas", "⏳ En preparación"),
            ("Cierre", "S15", "Presentación final del proyecto", "📅 Programado"),
        ]
        for a in actividades_scrum:
            tree_s.insert("", "end", values=a)

        # Tarjeta de Arquitectura Hibrida S11
        t_s11 = ttk.Frame(cont, style="Card.TFrame", padding=14)
        t_s11.pack(fill="x")
        ttk.Label(t_s11, text="INTEGRACIÓN HÍBRIDA MPI + OPENMP (SEMANA 11)", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 6))
        tk.Label(
            t_s11,
            text="• Proceso multinodo con MPI: divide los R escenarios en P bloques contiguos balanceados.\n"
                 "• Multihilo multinúcleo con OpenMP: cada proceso crea H hilos con schedule(dynamic, 16) para computar su bloque.\n"
                 "• Inicialización segura: MPI_Init_thread con MPI_THREAD_FUNNELED (solo el hilo maestro efectúa llamadas MPI).\n"
                 "• Reunión sin bloqueo: MPI_Gatherv colecta los resultados y el proceso raíz escribe en orden r=0..R-1.\n"
                 "• Reproducibilidad matemática: idéntico byte a byte al secuencial para cualquier P × H con la misma semilla.",
            bg=BLANCO, fg=TEXTO, justify="left", font=("Segoe UI", 9)
        ).pack(anchor="w")

    # =========================================================================
    # LOGICA DE SIMULACION Y GRAFICADO
    # =========================================================================
    def _poner_escenarios(self, valor: int) -> None:
        self.escenarios_var.set(str(valor))
        self._actualizar_estimacion()

    def _actualizar_estimacion(self) -> None:
        try:
            n = entero_positivo(self.escenarios_var.get())
        except ValueError:
            self.aviso_var.set("Ingrese un entero entre 1 y 1 000 000 000.")
            self.aviso.configure(fg=ROJO)
            return
        motor = self.motor_var.get()
        ms = MS_REFERENCIA.get(motor, 2.0)
        estimado = n * ms / 1000.0
        self.aviso_var.set(f"Estimado ({motor}): {duracion_legible(estimado)} ({ms:.2f} ms/esc.)" +
                           ("\nAdvertencia: supera los 100 000 escenarios." if n > 100_000 else ""))
        self.aviso.configure(fg=NARANJA if n > 100_000 else GRIS)

    def ejecutar(self) -> None:
        try:
            escenarios = entero_positivo(self.escenarios_var.get())
        except ValueError:
            messagebox.showerror("Valor inválido", "Ingrese una cantidad de escenarios válida.")
            return

        motor = self.motor_var.get()
        config = BASE / self.config_var.get()
        if not config.exists():
            messagebox.showerror("Configuración", f"No existe {config.name}.")
            return

        slug = motor.replace(" ", "_").replace("+", "p").replace("(", "").replace(")", "").replace("í", "i")
        marca = datetime.now().strftime("%Y%m%d_%H%M%S")
        salida_rel = Path("resultados_interfaz") / f"sim_{slug}_{escenarios}_{marca}"

        if motor == "Go":
            ejecutable = GO_BASE / "simulador_go.exe" if sys.platform == "win32" else GO_BASE / "simulador_go"
            if not ejecutable.is_file():
                messagebox.showerror("Ejecutable no encontrado", f"No se encontró {ejecutable}.\nCompile desde MonteCarlo_Go con:\ngo build -o simulador_go.exe ./cmd/simulador")
                return
            salida = GO_BASE / salida_rel
            comando = [str(ejecutable), "--config", config.name, "--datos", "datos", "--salida", str(salida_rel), "--escenarios", str(escenarios)]
            cwd = GO_BASE

        elif motor == "C++ Secuencial":
            ejecutable = BASE / "simulador.exe" if sys.platform == "win32" else BASE / "simulador"
            if not ejecutable.is_file():
                messagebox.showerror("Ejecutable no encontrado", f"No se encontró {ejecutable}.\nCompile desde MonteCarlo_Secuencial con g++.")
                return
            salida = BASE / salida_rel
            comando = [str(ejecutable), "--config", config.name, "--datos", "datos", "--salida", str(salida_rel), "--escenarios", str(escenarios)]
            cwd = BASE

        else:
            # Versiones paralelas: C++ OpenMP, C++ MPI, C++ Híbrido (MPI+OpenMP)
            salida = BASE / salida_rel
            cfg_wsl = f"../MonteCarlo_Secuencial/{config.name}"
            datos_wsl = f"../MonteCarlo_Secuencial/datos"
            salida_wsl = ruta_a_wsl(salida)
            paralelo_wsl = ruta_a_wsl(PARALELO_BASE)

            if motor == "C++ OpenMP":
                cmd_wsl = f"cd {paralelo_wsl} && ./simulador_omp --config {cfg_wsl} --datos {datos_wsl} --salida {salida_wsl} --escenarios {escenarios} --hilos 4"
            elif motor == "C++ MPI":
                cmd_wsl = f"cd {paralelo_wsl} && mpirun --oversubscribe -np 2 ./simulador_mpi --config {cfg_wsl} --datos {datos_wsl} --salida {salida_wsl} --escenarios {escenarios}"
            elif motor == "C++ Híbrido (MPI+OpenMP)":
                cmd_wsl = f"cd {paralelo_wsl} && mpirun --oversubscribe -np 2 ./simulador_hibrido --config {cfg_wsl} --datos {datos_wsl} --salida {salida_wsl} --escenarios {escenarios} --hilos 2"
            else:
                messagebox.showerror("Error", f"Motor desconocido: {motor}")
                return

            # En Windows se invoca a traves de WSL de forma completamente transparente
            if sys.platform == "win32":
                comando = ["wsl", "bash", "-c", cmd_wsl]
            else:
                comando = ["bash", "-c", cmd_wsl]
            cwd = BASE

        self.ejecutar_btn.state(["disabled"])
        self.progreso.start(12)
        self.estado_var.set(f"Ejecutando {escenarios:,} escenarios con {motor}...")
        threading.Thread(target=self._ejecutar_hilo, args=(comando, salida, cwd), daemon=True).start()

    def _ejecutar_hilo(self, comando: list[str], salida: Path, cwd: Path) -> None:
        try:
            salida.parent.mkdir(parents=True, exist_ok=True)
            completado = subprocess.run(comando, cwd=cwd, capture_output=True, text=True, check=False)
            if completado.returncode != 0:
                det = completado.stderr.strip() or completado.stdout.strip() or "Error al ejecutar simulador"
                self.cola.put(("error", det))
            else:
                self.cola.put(("completo", salida))
        except Exception as exc:
            self.cola.put(("error", str(exc)))

    def _procesar_cola(self) -> None:
        try:
            while True:
                tipo, dato = self.cola.get_nowait()
                self.progreso.stop()
                self.ejecutar_btn.state(["!disabled"])
                if tipo == "completo":
                    carpeta = Path(dato)
                    self.cargar_resultados(carpeta)
                    self.estado_var.set(f"Terminado. Resultados en: {carpeta.name}")
                else:
                    self.estado_var.set("La simulación no pudo completarse.")
                    messagebox.showerror("Error", str(dato))
        except queue.Empty:
            pass
        self.after(120, self._procesar_cola)

    def seleccionar_resultados(self) -> None:
        carpeta = filedialog.askdirectory(initialdir=ROOT, title="Seleccione carpeta de resultados")
        if carpeta:
            self.cargar_resultados(Path(carpeta))

    def cargar_resultados(self, carpeta: Path) -> None:
        distribucion = carpeta / "distribucion.csv"
        metricas = carpeta / "metricas.csv"
        if not distribucion.exists() or not metricas.exists():
            messagebox.showerror("Resultados incompletos", "La carpeta debe contener distribucion.csv y metricas.csv.")
            return
        try:
            with distribucion.open(newline="", encoding="utf-8") as f:
                self.resultados = list(csv.DictReader(f))
            with metricas.open(newline="", encoding="utf-8") as f:
                m = next(csv.DictReader(f))
        except Exception as exc:
            messagebox.showerror("Error de lectura", str(exc))
            return

        self.carpeta_actual = carpeta
        escenarios = int(float(m["escenarios"]))
        total = float(m["segundos_total"])
        cpu = float(m["segundos_cpu"])

        valores = {
            "Escenarios": f"{escenarios:,}".replace(",", " "),
            "Tiempo total": duracion_legible(total),
            "ms / escenario": f"{float(m['ms_por_escenario']):.2f}",
            "Rendimiento": f"{float(m['escenarios_por_segundo']):.0f} esc/s",
            "CPU / pared": f"{(100 * cpu / total if total else 0):.0f} %",
            "RSS pico": f"{float(m['memoria_pico_mib']):.1f} MiB",
        }
        for nom, val in valores.items():
            if nom in self.metricas_vars:
                self.metricas_vars[nom].set(val)

        masa = [(int(r["anio"]), int(r["primeras_inversiones"])) for r in self.resultados if int(r["primeras_inversiones"]) > 0]
        con = sum(n for _, n in masa)
        if masa and con:
            media = sum(a * n for a, n in masa) / con
            varianza = sum(n * (a - media) ** 2 for a, n in masa) / con
            sin = escenarios - con
            desviacion = math.sqrt(varianza)
            self.resumen_var.set(
                f"Media: {media:.2f} años  |  Desv.: {desviacion:.2f} años  |  "
                f"Rango: {masa[0][0]}–{masa[-1][0]}  |  Sin inversión: {100 * sin / escenarios:.2f} %"
            )
            self.intervalos = []
            textos = []
            for k in (1, 2, 3):
                desde = round(media - k * desviacion)
                hasta = round(media + k * desviacion)
                p = sum(float(r["probabilidad_anual"]) for r in self.resultados if desde <= int(r["anio"]) <= hasta)
                self.intervalos.append((k, desde, hasta, p))
                textos.append(f"μ±{k}σ ({desde}–{hasta}): {p:.1%}")
            self.intervalos_var.set("Intervalos de confianza reales:   " + "   |   ".join(textos))
        else:
            self.resumen_var.set("No se registraron cruces demográficos dentro del horizonte.")
            self.intervalos_var.set("")

        self.dibujar()

    def dibujar(self) -> None:
        self.anotacion = None
        self.eje.clear()
        self.eje.set_facecolor(BLANCO)
        self.eje.grid(axis="y", color="#ECEFF1", linewidth=0.8, alpha=0.9)
        self.eje.spines[["top", "right"]].set_visible(False)
        self.eje.spines[["left", "bottom"]].set_color("#B0BEC5")

        if not self.resultados:
            self.eje.text(0.5, 0.5, "Sin resultados cargados", transform=self.eje.transAxes, ha="center", va="center", color=GRIS, fontsize=12)
            self.canvas.draw_idle()
            return

        anios = [int(r["anio"]) for r in self.resultados]
        anual = [float(r["probabilidad_anual"]) for r in self.resultados]
        acumulada = [float(r["probabilidad_acumulada"]) for r in self.resultados]

        if self.vista_var.get() == "Probabilidad acumulada":
            self.eje.step(anios, acumulada, where="post", color=AZUL, linewidth=2.5)
            self.eje.scatter(anios, acumulada, color=MENTA, edgecolor=AZUL, s=20, zorder=3)
            self.eje.set_ylabel("F(y) = P(T ≤ y)", color=TEXTO, fontsize=9)
            self.eje.set_ylim(-0.02, 1.04)
        else:
            colores_k = {3: "#E8F5E9", 2: "#E0F2F1", 1: "#E1F5FE"}
            for k, d, h, _ in reversed(self.intervalos):
                self.eje.axvspan(d - 0.45, h + 0.45, color=colores_k[k], alpha=0.7, zorder=0)
            self.eje.fill_between(anios, anual, color=CELESTE, alpha=0.15)
            self.eje.plot(anios, anual, color=AZUL, linewidth=2.4, marker="o", markersize=3.8, markerfacecolor=VERDE, markeredgecolor=AZUL)
            self.eje.set_ylabel("P(T = y)", color=TEXTO, fontsize=9)
            max_y = max(anual) if anual else 1.0
            self.eje.set_ylim(-0.002, max_y * 1.25)

        self.eje.set_xlabel("Primer año de inversión T (A ≥ J)", color=TEXTO, fontsize=9)
        self.figura.tight_layout()
        self.canvas.draw_idle()

    def _mostrar_punto(self, evento) -> None:
        if evento.inaxes != self.eje or evento.xdata is None or not self.resultados:
            return
        fila = min(self.resultados, key=lambda r: abs(int(r["anio"]) - evento.xdata))
        anio = int(fila["anio"])
        anual = float(fila["probabilidad_anual"])
        acumulada = float(fila["probabilidad_acumulada"])
        if self.anotacion is not None:
            self.anotacion.remove()
        y = acumulada if self.vista_var.get() == "Probabilidad acumulada" else anual
        self.anotacion = self.eje.annotate(
            f"Año: {anio}\nP(T = y): {anual:.2%}\nP(T ≤ y): {acumulada:.2%}",
            xy=(anio, y), xytext=(10, 16), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.4", fc=BLANCO, ec=MENTA),
            arrowprops=dict(arrowstyle="->", color=AZUL), color=TEXTO, fontsize=8
        )
        self.canvas.draw_idle()


if __name__ == "__main__":
    app = InterfazMonteCarlo()
    app.mainloop()
