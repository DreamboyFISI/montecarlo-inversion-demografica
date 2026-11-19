"""Prueba real del lanzador de la interfaz, incluido el puente Windows -> WSL.

Requiere los binarios Linux compilados, Tk/Matplotlib y pantalla.
Ejecutar desde Windows o Ubuntu: python tests/integracion_interfaz_s13.py
Solo simula 8 escenarios; no es una medicion academica.
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from MonteCarlo_Secuencial.interfaz import InterfazMonteCarlo, ruta_a_wsl


def main():
    errores = []
    base = ROOT / "salidas_s13"
    base.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base, prefix="integracion con espacios ") as tmp:
        with patch("tkinter.messagebox.showerror", side_effect=lambda *a, **k: errores.append(a)):
            app = InterfazMonteCarlo()
            try:
                app.withdraw()
                salida = Path(tmp) / "resultado con espacios"
                usar_wsl = sys.platform == "win32"
                ruta = ruta_a_wsl if usar_wsl else str
                args = ["ejecutar", "--version", "openmp", "--hilos", "1", "--escenarios", "8",
                        "--config", ruta(ROOT / "MonteCarlo_Secuencial/config_incertidumbre.ini"),
                        "--datos", ruta(ROOT / "MonteCarlo_Secuencial/datos"), "--salida", ruta(salida)]
                comando = app._comando_s13(args, usar_wsl)
                # El mismo worker usado por el boton, aqui sin hilo para que el test sea determinista.
                app._ejecutar_hilo(comando, salida, ROOT)
                app._procesar_cola()
                app.update_idletasks()
                assert not errores, errores
                e = app.panel_analisis.ejecucion
                assert e.metricas["escenarios"] == 8
                assert e.procedencia is not None
                if usar_wsl:
                    assert e.procedencia["contexto"]["entorno"]["sistema"].startswith("Linux")
                print("Integracion interfaz S13: OK (ejecucion real, rutas con espacios y procedencia)")
            finally:
                app.destroy()


if __name__ == "__main__":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    main()
