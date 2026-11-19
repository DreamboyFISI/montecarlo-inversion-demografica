"""Pestana S13. Los calculos no dependen de Tk ni de textos de referencia."""

from __future__ import annotations

import json
import queue
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from .informes import (exportar_comparacion, exportar_ejecucion, figura_comparacion,
                       figura_ejecucion, informe_comparacion, informe_ejecucion, numero)
from .procedencia import ROOT, ruta_visible
from .rendimiento import comparar_ejecuciones, descubrir_ejecuciones
from .resultados import Ejecucion, entero


class PanelAnalisis(ttk.Frame):
    def __init__(self, padre, seleccionar_resultados, lanzar_campana, config_var, distro_var):
        super().__init__(padre, padding=8)
        self.ejecucion = None
        self.comparacion = None
        self.canvas_resultados = None
        self.canvas_rendimiento = None
        self.lanzar_campana = lanzar_campana
        self.cola_campanas = queue.Queue()
        self.revision_campana = 0
        self.validando = False
        barra = ttk.Frame(self)
        barra.pack(fill="x", pady=(0, 6))
        ttk.Button(barra, text="Cargar ejecución...", command=seleccionar_resultados).pack(side="left")
        ttk.Button(barra, text="Cargar 10 millones (S12)",
                   command=lambda: seleccionar_resultados(ROOT / "MonteCarlo_Paralelo/resultados_10000000")
                   ).pack(side="left", padx=6)
        self.origen_var = tk.StringVar(value="Seleccione o ejecute una simulación.")
        ttk.Label(self, textvariable=self.origen_var, wraplength=1100).pack(fill="x")
        notas = ttk.Notebook(self)
        notas.pack(fill="both", expand=True, pady=(6, 0))
        resultados = ttk.Frame(notas)
        rendimiento = ttk.Frame(notas)
        notas.add(resultados, text="Resultados de la ejecución")
        notas.add(rendimiento, text="Campaña y rendimiento comparado")

        ttk.Button(resultados, text="Exportar análisis (MD, CSV, JSON, PNG)...",
                   command=self._exportar_resultados).pack(anchor="w", pady=5)
        panel = ttk.Panedwindow(resultados, orient="vertical")
        panel.pack(fill="both", expand=True)
        texto_frame = ttk.Frame(panel)
        self.texto_resultados = scrolledtext.ScrolledText(texto_frame, wrap="word", height=13,
                                                         font=("Consolas", 10), state="disabled")
        self.texto_resultados.pack(fill="both", expand=True)
        self.fig_resultados = ttk.Frame(panel)
        panel.add(texto_frame, weight=1)
        panel.add(self.fig_resultados, weight=1)

        controles = ttk.LabelFrame(rendimiento, text="Nueva campaña LOCAL: todas las versiones C++ en el mismo entorno",
                                    padding=6)
        controles.pack(fill="x", pady=5)
        self.escenarios_var = tk.StringVar(value="1000")
        self.repeticiones_var = tk.StringVar(value="3")
        self.p_var = tk.StringVar(value="1,2")
        self.hibridos_var = tk.StringVar(value="1x2")
        for col, (titulo, var, ancho) in enumerate((
                ("Escenarios", self.escenarios_var, 10), ("Repeticiones", self.repeticiones_var, 5),
                ("p OpenMP/MPI", self.p_var, 12), ("Híbridos P x H", self.hibridos_var, 16))):
            ttk.Label(controles, text=titulo).grid(row=0, column=col * 2, padx=3)
            ttk.Entry(controles, textvariable=var, width=ancho).grid(row=0, column=col * 2 + 1, padx=3)
        self.versiones = {v: tk.BooleanVar(value=True) for v in ("openmp", "mpi", "hibrido")}
        elecciones = ttk.Frame(controles)
        elecciones.grid(row=1, column=0, columnspan=8, sticky="w", pady=5)
        for v, var in self.versiones.items():
            ttk.Checkbutton(elecciones, text=v, variable=var).pack(side="left", padx=3)
        self.sobresuscripcion = tk.BooleanVar(value=False)
        ttk.Checkbutton(elecciones, text="Permitir sobresuscripción (advertencia en informe)",
                        variable=self.sobresuscripcion).pack(side="left", padx=8)
        config_frame = ttk.Frame(controles)
        config_frame.grid(row=2, column=0, columnspan=8, sticky="w")
        ttk.Label(config_frame, text="Configuración:").pack(side="left")
        ttk.Combobox(config_frame, textvariable=config_var, state="readonly", width=29,
                     values=[p.name for p in (ROOT / "MonteCarlo_Secuencial").glob("config*.ini")]
                     ).pack(side="left", padx=4)
        ttk.Label(config_frame, text="Distro WSL (solo Windows):").pack(side="left", padx=(8, 0))
        ttk.Entry(config_frame, textvariable=distro_var, width=16).pack(side="left", padx=4)
        self.campana_btn = ttk.Button(config_frame, text="Ejecutar campaña...", command=self._pedir_campana)
        self.campana_btn.pack(side="left", padx=6)
        ttk.Label(controles, text="Incluye T1 secuencial. Mediciones sucesivas, no simultáneas. "
                  "Capacidad comprobada en el entorno de ejecución; evite otras tareas pesadas.",
                  wraplength=1100).grid(row=3, column=0, columnspan=8, sticky="w", pady=(5, 0))

        botones = ttk.Frame(rendimiento)
        botones.pack(fill="x", pady=4)
        ttk.Button(botones, text="Cargar campaña guardada...", command=self._seleccionar_campana).pack(side="left")
        ttk.Button(botones, text="Exportar comparación...", command=self._exportar_rendimiento).pack(side="left", padx=6)
        self.estado_var = tk.StringVar(value="No hay campaña cargada. Una ejecución aislada no demuestra speedup.")
        ttk.Label(rendimiento, textvariable=self.estado_var, wraplength=1100).pack(fill="x")
        zona = ttk.Panedwindow(rendimiento, orient="vertical")
        zona.pack(fill="both", expand=True)
        tabla_frame = ttk.Frame(zona)
        columnas = ("version", "pxh", "reps", "tiempo", "sd", "speedup", "eficiencia", "f", "amdahl")
        self.tabla = ttk.Treeview(tabla_frame, columns=columnas, show="headings", height=5)
        for clave, titulo in zip(columnas, ("Versión", "P x H", "Reps", "T medio (s)", "SD (s)",
                                           "Speedup", "Eficiencia", "Karp-Flatt", "Amdahl 1/f")):
            self.tabla.heading(clave, text=titulo)
            self.tabla.column(clave, width=105, anchor="center")
        scroll = ttk.Scrollbar(tabla_frame, orient="horizontal", command=self.tabla.xview)
        self.tabla.configure(xscrollcommand=scroll.set)
        self.tabla.pack(fill="both", expand=True)
        scroll.pack(fill="x")
        self.texto_rendimiento = scrolledtext.ScrolledText(zona, wrap="word", height=8,
                                                          font=("Consolas", 9), state="disabled")
        self.fig_rendimiento = ttk.Frame(zona)
        zona.add(tabla_frame, weight=1)
        zona.add(self.texto_rendimiento, weight=1)
        zona.add(self.fig_rendimiento, weight=2)
        self.after(100, self._recibir_campana)

    @staticmethod
    def _texto(widget, contenido):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", contenido)
        widget.configure(state="disabled")

    def mostrar_ejecucion(self, e: Ejecucion):
        self.ejecucion = e
        self.origen_var.set(f"Análisis de: {ruta_visible(e.carpeta)} — {e.metricas['version']} — "
                            f"{e.metricas['escenarios']:,} escenarios")
        self._texto(self.texto_resultados, informe_ejecucion(e))
        if self.canvas_resultados:
            self.canvas_resultados.get_tk_widget().destroy()
        self.canvas_resultados = FigureCanvasTkAgg(figura_ejecucion(e), master=self.fig_resultados)
        self.canvas_resultados.get_tk_widget().pack(fill="both", expand=True)
        self.canvas_resultados.draw_idle()

    def _pedir_campana(self):
        if self.validando:
            messagebox.showinfo("S13", "Espere a que termine la validación de la campaña cargada.")
            return
        try:
            versiones = [v for v, var in self.versiones.items() if var.get()]
            if not versiones:
                raise ValueError("Seleccione al menos una versión paralela.")
            escenarios = entero(self.escenarios_var.get(), "escenarios", 1)
            if escenarios > 1_000_000_000:
                raise ValueError("Máximo: 10^9 escenarios")
            reps = entero(self.repeticiones_var.get(), "repeticiones", 1)
            ps = list(dict.fromkeys(entero(n, "p", 1) for n in self.p_var.get().replace(",", " ").split()))
            hibridos = []
            for texto in self.hibridos_var.get().replace(",", " ").split():
                partes = texto.lower().split("x")
                if len(partes) != 2:
                    raise ValueError("Híbridos: use pares como 1x2,2x2.")
                hibridos.append(tuple(entero(n, "procesos/hilos", 1) for n in partes))
            hibridos = list(dict.fromkeys(hibridos))
            if any(v in versiones for v in ("openmp", "mpi")) and not ps:
                raise ValueError("Indique valores de p para OpenMP/MPI.")
            if "hibrido" in versiones and not hibridos:
                raise ValueError("Indique pares de procesos x hilos.")
            cantidad = 1 + sum(len(hibridos) if v == "hibrido" else len(ps) for v in versiones)
            if not messagebox.askyesno("Campaña S13",
                    f"Se harán {cantidad * reps} ejecuciones sucesivas de {escenarios:,} escenarios "
                    f"cada una ({reps} repeticiones por configuración).\n\n"
                    "Se medirán los tiempos en este equipo/entorno. No se usan tiempos históricos.\n"
                    "La campaña puede tardar; empiece con pocos escenarios. ¿Continuar?"):
                return
            self.lanzar_campana(dict(escenarios=escenarios, repeticiones=reps, versiones=versiones,
                                     p=ps, hibridos=hibridos,
                                     sobresuscripcion=self.sobresuscripcion.get()))
        except ValueError as exc:
            messagebox.showerror("Campaña S13", str(exc))

    def _seleccionar_campana(self):
        carpeta = filedialog.askdirectory(initialdir=ROOT, title="Carpeta de campaña S13")
        if carpeta:
            self.cargar_campana(Path(carpeta))

    def cargar_campana(self, carpeta: Path, segundo_plano: bool = True):
        self.revision_campana += 1
        revision = self.revision_campana
        self.validando = True
        self.comparacion = None
        self.tabla.delete(*self.tabla.get_children())
        self.estado_var.set(f"Validando procedencia y CSV de {ruta_visible(carpeta)}; "
                            "los archivos grandes se leen por bloques...")
        self._texto(self.texto_rendimiento, "Validación en curso; todavía no hay una comparación disponible.")
        if self.canvas_rendimiento:
            self.canvas_rendimiento.figure.clear()
            self.canvas_rendimiento.draw_idle()
        if segundo_plano:
            threading.Thread(target=self._leer_campana, args=(carpeta, revision), daemon=True).start()
        else:  # Pruebas de GUI sin entrar en mainloop
            self._leer_campana(carpeta, revision)
            self._recibir_campana(programar=False)

    def _leer_campana(self, carpeta: Path, revision: int):
        try:
            carpetas = descubrir_ejecuciones(carpeta)
            if not carpetas:
                raise ValueError("No hay carpetas de ejecuciones con metricas.csv.")
            c = comparar_ejecuciones(carpetas)
            estado = ""
            if (carpeta / "campana.json").is_file():
                manifiesto = json.loads((carpeta / "campana.json").read_text(encoding="utf-8"))
                estado = manifiesto.get("estado", "") if isinstance(manifiesto, dict) else "inválido"
            self.cola_campanas.put((revision, carpeta, c, estado, None))
        except (ValueError, OSError, TypeError) as exc:
            self.cola_campanas.put((revision, carpeta, None, "", str(exc)))

    def _recibir_campana(self, programar=True):
        try:
            while True:
                revision, carpeta, c, estado, error = self.cola_campanas.get_nowait()
                if revision != self.revision_campana:
                    continue  # No sobreescribir una seleccion posterior con una lectura antigua.
                self.validando = False
                if error:
                    self.estado_var.set("No se pudo validar la campaña.")
                    messagebox.showerror("Campaña S13", error)
                    continue
                self.comparacion = c
                self.estado_var.set(f"{ruta_visible(carpeta)} — estado registrado: {estado or 'no disponible'}; "
                                    f"grupos comparables: {len(c.filas)}; excluidas: {len(c.excluidas)}.")
                self.tabla.delete(*self.tabla.get_children())
                for f in c.filas:
                    self.tabla.insert("", "end", values=(
                        f["version"], f"{f['procesos']}x{f['hilos']}", f["repeticiones"],
                        numero(f["segundos_total_media"]), numero(f["segundos_total_sd"]),
                        numero(f["speedup"], 3), f"{f['eficiencia']:.1%}", numero(f["karp_flatt"], 4),
                        numero(f["amdahl_smax"], 2)))
                self._texto(self.texto_rendimiento, informe_comparacion(c))
                if self.canvas_rendimiento:
                    self.canvas_rendimiento.get_tk_widget().destroy()
                self.canvas_rendimiento = FigureCanvasTkAgg(figura_comparacion(c), master=self.fig_rendimiento)
                self.canvas_rendimiento.get_tk_widget().pack(fill="both", expand=True)
                self.canvas_rendimiento.draw_idle()
        except queue.Empty:
            pass
        if programar:
            self.after(100, self._recibir_campana)

    def _destino_exportacion(self):
        carpeta = filedialog.asksaveasfilename(initialdir=ROOT, title="Nombre de una CARPETA NUEVA para el informe",
                                             initialfile="informe_s13")
        return Path(carpeta) if carpeta else None

    def _exportar_resultados(self):
        if self.ejecucion is None:
            messagebox.showinfo("S13", "Cargue primero una ejecución.")
            return
        salida = self._destino_exportacion()
        if salida:
            try:
                exportar_ejecucion(self.ejecucion, salida)
                messagebox.showinfo("S13", f"Análisis exportado a {salida}")
            except (ValueError, OSError) as exc:
                messagebox.showerror("Exportación", str(exc))

    def _exportar_rendimiento(self):
        if self.comparacion is None:
            messagebox.showinfo("S13", "Cargue primero una campaña.")
            return
        salida = self._destino_exportacion()
        if salida:
            try:
                exportar_comparacion(self.comparacion, salida)
                messagebox.showinfo("S13", f"Comparación exportada a {salida}")
            except (ValueError, OSError) as exc:
                messagebox.showerror("Exportación", str(exc))
