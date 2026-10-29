"""Interfaz de escritorio para el simulador Monte Carlo demografico.

Ejecutar desde la carpeta MonteCarlo_Secuencial:
    python interfaz.py

La interfaz no reemplaza el modelo: ejecuta ``simulador.exe`` (Windows) o
``simulador`` (Linux/macOS) y presenta los CSV producidos por el programa C++.
"""

from __future__ import annotations

import csv
import math
import queue
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


BASE = Path(__file__).resolve().parent
GO_BASE = BASE.parent / "MonteCarlo_Go"
AZUL = "#2469A0"
CELESTE = "#10BCE3"
MENTA = "#3DD6AF"
VERDE = "#8BE27E"
FONDO = "#F4F7FA"
TEXTO = "#17324D"
GRIS = "#66788A"
BLANCO = "#FFFFFF"
NARANJA = "#E8893A"
ROJO = "#C44747"
# Linea base observada en Windows con las versiones exactas actuales.
# Son estimaciones orientativas: carga del equipo, antivirus y escritura a disco
# pueden producir variaciones entre corridas.
MS_REFERENCIA = {"C++": 2.17, "Go": 2.19}


def entero_positivo(texto: str) -> int:
    valor = int(texto.replace(" ", "").replace(",", ""))
    if valor < 1 or valor > 1_000_000_000:
        raise ValueError
    return valor


def duracion_legible(segundos: float) -> str:
    if segundos < 60:
        return f"{segundos:.1f} s"
    if segundos < 3600:
        return f"{segundos / 60:.1f} min"
    return f"{segundos / 3600:.1f} h"


class InterfazMonteCarlo(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Monte Carlo - Inversion demografica del Peru")
        self.geometry("1240x790")
        self.minsize(1080, 700)
        self.configure(bg=FONDO)
        self.resultados: list[dict[str, str]] = []
        self.intervalos: list[tuple[int, int, int, float]] = []
        self.carpeta_actual: Path | None = None
        self.proceso: subprocess.Popen[str] | None = None
        self.cola: queue.Queue[tuple[str, object]] = queue.Queue()
        self._configurar_estilos()
        self._construir_interfaz()
        self.after(120, self._procesar_cola)
        ejemplo = BASE / "resultados_incertidumbre"
        if ejemplo.exists():
            self.after(200, lambda: self.cargar_resultados(ejemplo))

    def _configurar_estilos(self) -> None:
        estilo = ttk.Style(self)
        estilo.theme_use("clam")
        estilo.configure("TFrame", background=FONDO)
        estilo.configure("Card.TFrame", background=BLANCO, relief="flat")
        estilo.configure("TLabel", background=FONDO, foreground=TEXTO, font=("Segoe UI", 10))
        estilo.configure("Title.TLabel", font=("Segoe UI Semibold", 19), foreground=AZUL)
        estilo.configure("Subtitle.TLabel", font=("Segoe UI", 10), foreground=GRIS)
        estilo.configure("CardTitle.TLabel", background=BLANCO, font=("Segoe UI Semibold", 10), foreground=GRIS)
        estilo.configure("CardValue.TLabel", background=BLANCO, font=("Segoe UI Semibold", 17), foreground=AZUL)
        estilo.configure("Accent.TButton", background=AZUL, foreground=BLANCO, font=("Segoe UI Semibold", 10), padding=9)
        estilo.map("Accent.TButton", background=[("active", CELESTE), ("disabled", "#9BAAB7")])
        estilo.configure("Soft.TButton", background=MENTA, foreground=TEXTO, padding=8)
        estilo.map("Soft.TButton", background=[("active", VERDE)])
        estilo.configure("TEntry", fieldbackground=BLANCO, padding=6)
        estilo.configure("TCombobox", fieldbackground=BLANCO, padding=5)
        estilo.configure("Treeview", rowheight=27, background=BLANCO, fieldbackground=BLANCO, foreground=TEXTO)
        estilo.configure("Treeview.Heading", background="#DCE7F1", foreground=TEXTO, font=("Segoe UI Semibold", 9))
        estilo.configure("Horizontal.TProgressbar", background=CELESTE, troughcolor="#DCE7F1")

    def _construir_interfaz(self) -> None:
        contenedor = tk.Frame(self, bg=FONDO)
        contenedor.pack(fill="both", expand=True)
        lienzo = tk.Canvas(contenedor, bg=FONDO, highlightthickness=0)
        desplazamiento = ttk.Scrollbar(contenedor, orient="vertical", command=lienzo.yview)
        lienzo.configure(yscrollcommand=desplazamiento.set)
        desplazamiento.pack(side="right", fill="y")
        lienzo.pack(side="left", fill="both", expand=True)
        contenido = ttk.Frame(lienzo)
        ventana = lienzo.create_window((0, 0), window=contenido, anchor="nw")
        contenido.bind("<Configure>", lambda _e: lienzo.configure(scrollregion=lienzo.bbox("all")))
        lienzo.bind("<Configure>", lambda e: lienzo.itemconfigure(ventana, width=e.width))
        lienzo.bind_all("<MouseWheel>", lambda e: lienzo.yview_scroll(int(-e.delta / 120), "units"))

        cabecera = ttk.Frame(contenido, padding=(22, 15, 22, 8))
        cabecera.pack(fill="x")
        ttk.Label(cabecera, text="Simulacion de inversion demografica", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            cabecera,
            text="Distribucion probabilistica del primer año en que la poblacion de 65+ supera a la menor de 15",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        cuerpo = ttk.Panedwindow(contenido, orient="horizontal")
        cuerpo.pack(fill="both", expand=True, padx=20, pady=(5, 10))
        lateral = ttk.Frame(cuerpo, style="Card.TFrame", padding=18, width=275)
        principal = ttk.Frame(cuerpo, style="Card.TFrame", padding=14)
        cuerpo.add(lateral, weight=0)
        cuerpo.add(principal, weight=1)
        self._construir_controles(lateral)
        self._construir_grafico(principal)

        inferior = ttk.Frame(contenido, padding=(20, 0, 20, 16))
        inferior.pack(fill="x")
        self._construir_metricas(inferior)

    def _construir_controles(self, padre: ttk.Frame) -> None:
        ttk.Label(padre, text="CONFIGURACION", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 12))
        ttk.Label(padre, text="Motor de simulacion", background=BLANCO).pack(anchor="w")
        self.motor_var = tk.StringVar(value="C++")
        selector_motor = ttk.Combobox(padre, textvariable=self.motor_var, values=["C++", "Go"], state="readonly")
        selector_motor.pack(fill="x", pady=(4, 12))
        selector_motor.bind("<<ComboboxSelected>>", lambda _e: self._actualizar_estimacion())
        ttk.Label(padre, text="Archivo de configuracion", background=BLANCO).pack(anchor="w")
        self.config_var = tk.StringVar(value="config_incertidumbre.ini")
        opciones = [p.name for p in BASE.glob("config*.ini")]
        ttk.Combobox(padre, textvariable=self.config_var, values=opciones, state="readonly").pack(fill="x", pady=(4, 12))

        ttk.Label(padre, text="Cantidad de escenarios", background=BLANCO).pack(anchor="w")
        self.escenarios_var = tk.StringVar(value="10000")
        entrada = ttk.Entry(padre, textvariable=self.escenarios_var)
        entrada.pack(fill="x", pady=(4, 6))
        entrada.bind("<KeyRelease>", lambda _e: self._actualizar_estimacion())

        rapidos = ttk.Frame(padre, style="Card.TFrame")
        rapidos.pack(fill="x", pady=(0, 10))
        for valor in (1_000, 10_000, 100_000):
            ttk.Button(rapidos, text=f"{valor // 1000}k", width=6,
                       command=lambda v=valor: self._poner_escenarios(v)).pack(side="left", padx=(0, 4))

        self.aviso_var = tk.StringVar()
        self.aviso = tk.Label(padre, textvariable=self.aviso_var, bg=BLANCO, fg=GRIS,
                              justify="left", wraplength=235, font=("Segoe UI", 9))
        self.aviso.pack(fill="x", pady=(0, 12))
        self._actualizar_estimacion()

        self.ejecutar_btn = ttk.Button(padre, text="Ejecutar simulacion", style="Accent.TButton", command=self.ejecutar)
        self.ejecutar_btn.pack(fill="x", pady=(2, 7))
        ttk.Button(padre, text="Abrir resultados existentes", style="Soft.TButton",
                   command=self.seleccionar_resultados).pack(fill="x")

        self.progreso = ttk.Progressbar(padre, mode="indeterminate")
        self.progreso.pack(fill="x", pady=(16, 5))
        self.estado_var = tk.StringVar(value="Listo")
        tk.Label(padre, textvariable=self.estado_var, bg=BLANCO, fg=GRIS,
                 justify="left", wraplength=235, font=("Segoe UI", 9)).pack(fill="x")

        ttk.Separator(padre).pack(fill="x", pady=15)
        ttk.Label(padre, text="INTERPRETACION", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 6))
        tk.Label(
            padre,
            text="La linea representa P(T = año). Los puntos son probabilidades Monte Carlo reales; "
                 "no se fuerza una distribucion normal.",
            bg=BLANCO, fg=GRIS, justify="left", wraplength=235, font=("Segoe UI", 9),
        ).pack(fill="x")

    def _construir_grafico(self, padre: ttk.Frame) -> None:
        barra = ttk.Frame(padre, style="Card.TFrame")
        barra.pack(fill="x")
        ttk.Label(barra, text="DISTRIBUCION DEL PRIMER AÑO DE INVERSION", style="CardTitle.TLabel").pack(side="left")
        self.vista_var = tk.StringVar(value="Probabilidad anual")
        selector = ttk.Combobox(barra, textvariable=self.vista_var,
                                values=["Probabilidad anual", "Probabilidad acumulada"], state="readonly", width=23)
        selector.pack(side="right")
        selector.bind("<<ComboboxSelected>>", lambda _e: self.dibujar())

        self.figura = Figure(figsize=(8.4, 4.7), dpi=100, facecolor=BLANCO)
        self.eje = self.figura.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.figura, master=padre)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, pady=(8, 0))
        self.canvas.mpl_connect("motion_notify_event", self._mostrar_punto)
        self.anotacion = None
        self.dibujar()

        self.resumen_var = tk.StringVar(value="Abra resultados existentes o ejecute una simulacion.")
        tk.Label(padre, textvariable=self.resumen_var, bg="#EAF8F4", fg=TEXTO, anchor="w",
                 padx=12, pady=8, font=("Segoe UI Semibold", 10)).pack(fill="x", pady=(4, 0))
        self.intervalos_var = tk.StringVar(value="")
        tk.Label(padre, textvariable=self.intervalos_var, bg="#F0F8FD", fg=TEXTO, anchor="w",
                 justify="left", padx=12, pady=8, font=("Segoe UI", 9)).pack(fill="x", pady=(2, 0))

    def _construir_metricas(self, padre: ttk.Frame) -> None:
        tarjetas = ttk.Frame(padre)
        tarjetas.pack(fill="x")
        nombres = ["Escenarios", "Tiempo total", "ms / escenario", "Rendimiento", "CPU / pared", "RSS pico"]
        self.metricas_vars: dict[str, tk.StringVar] = {}
        for i, nombre in enumerate(nombres):
            tarjeta = ttk.Frame(tarjetas, style="Card.TFrame", padding=(12, 8))
            tarjeta.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 5, 0))
            tarjetas.columnconfigure(i, weight=1)
            ttk.Label(tarjeta, text=nombre, style="CardTitle.TLabel").pack(anchor="w")
            var = tk.StringVar(value="--")
            ttk.Label(tarjeta, textvariable=var, style="CardValue.TLabel").pack(anchor="w", pady=(2, 0))
            self.metricas_vars[nombre] = var

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
        ms_referencia = MS_REFERENCIA.get(motor, MS_REFERENCIA["C++"])
        estimado = n * ms_referencia / 1000.0
        self.aviso_var.set(f"Estimado con {motor}: {duracion_legible(estimado)} ({ms_referencia:.2f} ms/esc.)" +
                           ("\nAdvertencia: supera los 100 000 escenarios." if n > 100_000 else ""))
        self.aviso.configure(fg=NARANJA if n > 100_000 else GRIS)

    def _buscar_ejecutable(self, motor: str) -> Path | None:
        if motor == "Go":
            candidatos = [GO_BASE / "simulador_go.exe", GO_BASE / "simulador_go"]
        else:
            candidatos = [BASE / "simulador.exe", BASE / "simulador"] if sys.platform == "win32" else [BASE / "simulador", BASE / "simulador.exe"]
        return next((p for p in candidatos if p.is_file()), None)

    def ejecutar(self) -> None:
        try:
            escenarios = entero_positivo(self.escenarios_var.get())
        except ValueError:
            messagebox.showerror("Valor invalido", "Ingrese una cantidad de escenarios valida.")
            return
        motor = self.motor_var.get()
        ejecutable = self._buscar_ejecutable(motor)
        if ejecutable is None:
            if motor == "Go":
                mensaje = ("No se encontro MonteCarlo_Go/simulador_go.exe.\n\n"
                           "Instale Go y compile desde MonteCarlo_Go con:\n"
                           "go build -o simulador_go.exe ./cmd/simulador")
            else:
                mensaje = "No se encontro simulador.exe en MonteCarlo_Secuencial. Compile primero el programa C++."
            messagebox.showerror("Ejecutable no encontrado", mensaje)
            return
        motor_base = GO_BASE if motor == "Go" else BASE
        config = motor_base / self.config_var.get()
        if not config.exists():
            messagebox.showerror("Configuracion", f"No existe {config.name}.")
            return
        estimado = duracion_legible(escenarios * MS_REFERENCIA.get(motor, MS_REFERENCIA["C++"]) / 1000.0)
        if escenarios > 100_000 and not messagebox.askyesno(
            "Ejecucion prolongada",
            f"Solicitaste {escenarios:,} escenarios.\nTiempo secuencial estimado: {estimado}.\n\n¿Deseas continuar?",
        ):
            return

        marca = datetime.now().strftime("%Y%m%d_%H%M%S")
        # El ejecutable MinGW trabaja con rutas estrechas. Se le pasan rutas
        # relativas para evitar errores cuando la ruta del proyecto contiene
        # caracteres Unicode (por ejemplo, "Programación").
        salida_relativa = Path("resultados_interfaz") / f"simulacion_{motor.lower().replace('+', 'p')}_{escenarios}_{marca}"
        salida = motor_base / salida_relativa
        comando = [str(ejecutable), "--config", config.name, "--datos", "datos",
                   "--salida", str(salida_relativa), "--escenarios", str(escenarios)]
        self.ejecutar_btn.state(["disabled"])
        self.progreso.start(12)
        self.estado_var.set(f"Ejecutando {escenarios:,} escenarios con {motor}... estimado {estimado}")
        threading.Thread(target=self._ejecutar_hilo, args=(comando, salida, motor_base), daemon=True).start()

    def _ejecutar_hilo(self, comando: list[str], salida: Path, motor_base: Path) -> None:
        try:
            salida.parent.mkdir(parents=True, exist_ok=True)
            completado = subprocess.run(comando, cwd=motor_base, capture_output=True, text=True, check=False)
            if completado.returncode != 0:
                detalle = completado.stderr.strip() or completado.stdout.strip() or "Error desconocido"
                self.cola.put(("error", detalle))
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
                    self.estado_var.set(f"Simulacion terminada. Resultados: {carpeta.name}")
                else:
                    self.estado_var.set("La simulacion no pudo completarse.")
                    messagebox.showerror("Error del simulador", str(dato))
        except queue.Empty:
            pass
        self.after(120, self._procesar_cola)

    def seleccionar_resultados(self) -> None:
        carpeta = filedialog.askdirectory(initialdir=BASE, title="Seleccione una carpeta de resultados")
        if carpeta:
            self.cargar_resultados(Path(carpeta))

    def cargar_resultados(self, carpeta: Path) -> None:
        distribucion = carpeta / "distribucion.csv"
        metricas = carpeta / "metricas.csv"
        if not distribucion.exists() or not metricas.exists():
            messagebox.showerror("Resultados incompletos", "La carpeta debe contener distribucion.csv y metricas.csv.")
            return
        try:
            with distribucion.open(newline="", encoding="utf-8") as archivo:
                self.resultados = list(csv.DictReader(archivo))
            with metricas.open(newline="", encoding="utf-8") as archivo:
                m = next(csv.DictReader(archivo))
        except (OSError, StopIteration, KeyError, ValueError) as exc:
            messagebox.showerror("Lectura de resultados", str(exc))
            return
        self.carpeta_actual = carpeta
        escenarios = int(float(m["escenarios"]))
        total = float(m["segundos_total"])
        simulacion = float(m["segundos_simulacion"])
        cpu = float(m["segundos_cpu"])
        valores = {
            "Escenarios": f"{escenarios:,}".replace(",", " "),
            "Tiempo total": duracion_legible(total),
            "ms / escenario": f"{float(m['ms_por_escenario']):.2f}",
            "Rendimiento": f"{float(m['escenarios_por_segundo']):.0f} esc/s",
            "CPU / pared": f"{(100 * cpu / total if total else 0):.0f} %",
            "RSS pico": f"{float(m['memoria_pico_mib']):.1f} MiB",
        }
        for nombre, valor in valores.items():
            self.metricas_vars[nombre].set(valor)
        self.escenarios_var.set(str(escenarios))
        self._actualizar_estimacion()

        masa = [(int(r["anio"]), int(r["primeras_inversiones"])) for r in self.resultados if int(r["primeras_inversiones"]) > 0]
        con = sum(n for _, n in masa)
        if masa and con:
            media = sum(a * n for a, n in masa) / con
            varianza = sum(n * (a - media) ** 2 for a, n in masa) / con
            sin = escenarios - con
            self.resumen_var.set(
                f"Media: {media:.2f}  |  Desv.: {math.sqrt(varianza):.2f} años  |  "
                f"Rango: {masa[0][0]}-{masa[-1][0]}  |  Sin inversion: {100 * sin / escenarios:.2f} %"
            )
            desviacion = math.sqrt(varianza)
            self.intervalos = []
            textos = []
            for k in (1, 2, 3):
                desde = round(media - k * desviacion)
                hasta = round(media + k * desviacion)
                probabilidad = sum(
                    float(r["probabilidad_anual"])
                    for r in self.resultados
                    if desde <= int(r["anio"]) <= hasta
                )
                self.intervalos.append((k, desde, hasta, probabilidad))
                textos.append(f"μ±{k}σ: {desde}-{hasta} = {probabilidad:.2%}")
            self.intervalos_var.set(
                "Probabilidad absoluta real (incluye todos los escenarios):  " + "   |   ".join(textos)
            )
        else:
            self.intervalos = []
            self.resumen_var.set("Ningun escenario presenta inversion dentro del horizonte.")
            self.intervalos_var.set("No hay intervalos de inversion para calcular.")
        self.dibujar()
        self.estado_var.set(f"Mostrando: {carpeta}")

    def dibujar(self) -> None:
        # Al limpiar el eje, Matplotlib elimina la anotacion anterior. Hay que
        # soltar también la referencia para que el siguiente hover cree una nueva.
        self.anotacion = None
        self.eje.clear()
        self.eje.set_facecolor(BLANCO)
        self.eje.grid(axis="y", color="#DDE6EE", linewidth=0.8, alpha=0.9)
        self.eje.spines[["top", "right"]].set_visible(False)
        self.eje.spines[["left", "bottom"]].set_color("#AAB8C4")
        self.eje.tick_params(colors=GRIS)
        if not self.resultados:
            self.eje.text(0.5, 0.5, "Sin resultados cargados", transform=self.eje.transAxes,
                          ha="center", va="center", color=GRIS, fontsize=13)
            self.eje.set_xticks([])
            self.eje.set_yticks([])
            self.canvas.draw_idle()
            return

        anios = [int(r["anio"]) for r in self.resultados]
        anual = [float(r["probabilidad_anual"]) for r in self.resultados]
        acumulada = [float(r["probabilidad_acumulada"]) for r in self.resultados]
        if self.vista_var.get() == "Probabilidad acumulada":
            valores = acumulada
            self.eje.step(anios, valores, where="post", color=AZUL, linewidth=2.7)
            self.eje.scatter(anios, valores, color=MENTA, edgecolor=AZUL, s=22, zorder=3)
            self.eje.set_ylabel("F(y) = P(T <= y)", color=TEXTO)
            self.eje.set_ylim(-0.02, 1.04)
        else:
            valores = anual
            colores_intervalo = {3: VERDE, 2: MENTA, 1: CELESTE}
            for k, desde, hasta, _probabilidad in reversed(self.intervalos):
                self.eje.axvspan(desde - 0.45, hasta + 0.45, color=colores_intervalo[k],
                                 alpha=0.10 + (4 - k) * 0.04, linewidth=0, zorder=0)
            self.eje.fill_between(anios, valores, color=CELESTE, alpha=0.16)
            self.eje.plot(anios, valores, color=AZUL, linewidth=2.7, marker="o", markersize=4,
                          markerfacecolor=VERDE, markeredgecolor=AZUL)
            self.eje.set_ylabel("P(T = y)", color=TEXTO)
            maximo = max(anual) if anual else 1.0
            self.eje.set_ylim(-0.003, maximo * 1.34 if maximo > 0 else 1.0)
            for indice, (k, desde, hasta, probabilidad) in enumerate(self.intervalos):
                y = maximo * (1.25 - indice * 0.10)
                self.eje.annotate("", xy=(desde, y), xytext=(hasta, y),
                                  arrowprops=dict(arrowstyle="<->", color=colores_intervalo[k], linewidth=1.5))
                self.eje.text((desde + hasta) / 2, y + maximo * 0.015,
                              f"{desde}-{hasta}: {probabilidad:.1%}", ha="center", va="bottom",
                              color=TEXTO, fontsize=8, fontweight="semibold")
        positivos = [a for a, p in zip(anios, anual) if p > 0]
        if positivos:
            self.eje.set_xlim(min(positivos) - 2, max(positivos) + 2)
        self.eje.set_xlabel("Primer año de inversion T", color=TEXTO)
        self.eje.set_title(self.vista_var.get(), color=TEXTO, fontsize=13, pad=10)
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
            f"{anio}\nP(T = y): {anual:.2%}\nP(T <= y): {acumulada:.2%}",
            xy=(anio, y), xytext=(12, 18), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.45", fc=BLANCO, ec=MENTA),
            arrowprops=dict(arrowstyle="->", color=AZUL), color=TEXTO, fontsize=9,
        )
        self.canvas.draw_idle()


if __name__ == "__main__":
    InterfazMonteCarlo().mainloop()
