"""Smoke grafico opcional: python tests/smoke_interfaz.py [carpeta_campana].

Requiere Tk, Matplotlib y una pantalla (por ejemplo WSLg). No mide rendimiento.
"""

import sys
import runpy
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from MonteCarlo_Secuencial.interfaz import InterfazMonteCarlo


def main():
    errores = []
    with patch("tkinter.messagebox.showerror", side_effect=lambda *a, **k: errores.append(a)):
        app = InterfazMonteCarlo()
        try:
            app.withdraw()
            app.cargar_resultados(ROOT / "MonteCarlo_Paralelo/resultados_10000000")
            app.update_idletasks()
            assert app.panel_analisis.ejecucion.estadisticas["con_inversion"] == 9934770
            assert "A > J" in app.eje.get_xlabel()
            assert "no IC" in app.intervalos_var.get()
            if len(sys.argv) > 1:
                app.panel_analisis.cargar_campana(Path(sys.argv[1]))
                agotado = []

                def comprobar():
                    if app.panel_analisis.validando:
                        app.after(50, comprobar)
                    else:
                        app.quit()

                def timeout():
                    agotado.append(True)
                    app.quit()

                app.after(50, comprobar)
                app.after(30000, timeout)
                app.mainloop()
                assert not agotado, "La validacion en segundo plano no termino"
                assert len(app.panel_analisis.comparacion.filas) >= 2
            assert not errores, errores
            print("Smoke Tk S13: OK (carga de resultados, tablas y graficos)")
        finally:
            app.destroy()
    # Comprobar tambien el lanzador original desde la raiz, sin dejar una ventana abierta.
    with patch("tkinter.Tk.mainloop", lambda self: self.destroy()):
        runpy.run_path(str(ROOT / "interfaz.py"), run_name="__main__")


if __name__ == "__main__":
    main()
