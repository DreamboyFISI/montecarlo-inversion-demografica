"""Pruebas numericas con datos sinteticos, no mediciones de rendimiento reales."""

from __future__ import annotations

import csv
import json
import math
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from MonteCarlo_Analisis.informes import (exportar_comparacion, exportar_ejecucion,
                                        informe_comparacion, informe_ejecucion)
from MonteCarlo_Analisis.procedencia import CRITERIO, PROTEGIDOS, ROOT, firma, guardar_json, huella, ruta_visible
from MonteCarlo_Analisis.rendimiento import comparar_ejecuciones, descubrir_ejecuciones
from MonteCarlo_Analisis.resultados import analizar_ejecucion, wilson


def csv_escribir(archivo, filas):
    with archivo.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)


def crear_salida(carpeta, conteos=(0, 2, 2), r=5, version="secuencial", procesos=1, hilos=1, tiempo=10):
    carpeta.mkdir()
    sim = tiempo * .8
    csv_escribir(carpeta / "metricas.csv", [dict(
        version=version, procesos=procesos, hilos=hilos, escenarios=r, horizonte=len(conteos) - 1,
        segundos_carga=.001, segundos_simulacion=sim, segundos_total=tiempo, segundos_cpu=tiempo,
        ms_por_escenario=1000 * sim / r, escenarios_por_segundo=r / sim,
        memoria_pico_mib=12, segundos_comunicacion=0)])
    acumulado = 0
    filas = []
    escenarios = []
    for i, n in enumerate(conteos):
        acumulado += n
        filas.append(dict(anio=2025 + i, primeras_inversiones=n, probabilidad_anual=n / r,
                          probabilidad_acumulada=acumulado / r))
        escenarios += [dict(escenario=0, ocurrio_inversion=1, primer_anio_inversion=2025 + i)] * n
    escenarios += [dict(escenario=0, ocurrio_inversion=0, primer_anio_inversion="")] * (r - acumulado)
    escenarios = [dict(f, escenario=i + 1) for i, f in enumerate(escenarios)]
    csv_escribir(carpeta / "distribucion.csv", filas)
    csv_escribir(carpeta / "escenarios.csv", escenarios)
    (carpeta / "trayectoria_escenario_1.csv").write_text("anio,balance\n2026,0\n", encoding="utf-8")
    # El .ini original usa otro R; parametros efectivos/metricas deben prevalecer.
    (carpeta / "config_usada.ini").write_text(
        f"anio_base=2025\nhorizonte={len(conteos)-1}\nescenarios=1000\nsemilla=12345\n"
        "estado_datos=PARAMETROS_CONFIGURADOS\nsigma_fecundidad=0\nsigma_mortalidad=0\n", encoding="utf-8")
    (carpeta / "parametros_efectivos.txt").write_text(
        f"escenarios={r}\nhorizonte={len(conteos)-1}\nComentario libre\n", encoding="utf-8")
    return carpeta


def firmar_sintetico(carpeta, rep=1, campana="campana_ficticia", maquina="equipo_ficticio_A", **cambios):
    m = analizar_ejecucion(carpeta).metricas
    contexto = dict(maquina=dict(id=maquina, cpu="CPU FICTICIA PARA PRUEBAS", cpus_disponibles=4),
                    entorno=dict(sistema="ENTORNO SINTETICO"), fuentes_sha256=firma("fuentes ficticias"),
                    binarios_sha256={"suite": firma("binarios ficticios")},
                    datos_sha256={"datos": firma("datos ficticios")}, config_sha256=firma("config ficticia"),
                    proyecto="proyecto_ficticio", datos="datos_ficticios")
    p = dict(esquema=1, estado="completada", ejecucion_id=carpeta.name, campana_id=campana,
             repeticion=rep, inicio_utc="FECHA SINTETICA", contexto=contexto, firma_contexto=firma(contexto),
             criterio=CRITERIO, ejecucion={k: m[k] for k in
                                          ("version", "procesos", "hilos", "escenarios", "horizonte")},
             archivos_sha256={n: huella(carpeta / n) for n in PROTEGIDOS},
             equivalencia_sha256={n: huella(carpeta / n) for n in
                                  ("escenarios.csv", "trayectoria_escenario_1.csv")})
    p.update(cambios)
    guardar_json(carpeta / "procedencia.json", p)
    return p


class ResultadosTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def salida(self, **kw):
        return crear_salida(self.base / "salida", **kw)

    def test_estadisticas_condicionales_y_censura(self):
        e = analizar_ejecucion(self.salida())
        s = e.estadisticas
        self.assertEqual(s["con_inversion"], 4)
        self.assertEqual(s["sin_inversion"], 1)
        self.assertEqual(s["media_condicional"], 2026.5)
        self.assertAlmostEqual(s["desviacion_condicional"], .5)
        self.assertAlmostEqual(s["error_estandar_media"], math.sqrt(1 / 3) / 2)
        self.assertEqual(s["mediana_condicional"], 2026)
        self.assertEqual(s["mediana_no_condicional"], 2027)
        self.assertIsNone(s["p95_no_condicional"])
        self.assertEqual(e.configuracion["escenarios"], "5")
        self.assertIn("no son un IC", informe_ejecucion(e))

    def test_sin_cruces(self):
        e = analizar_ejecucion(self.salida(conteos=(0, 0, 0)))
        self.assertIsNone(e.estadisticas["media_condicional"])
        self.assertIsNone(e.estadisticas["mediana_no_condicional"])
        self.assertIn("No hay cruces observados", informe_ejecucion(e))
        self.assertGreater(e.estadisticas["ic95_probabilidad_inversion"][1], 0)

    def test_un_cruce(self):
        e = analizar_ejecucion(self.salida(conteos=(0, 1, 0)))
        self.assertIsNone(e.estadisticas["error_estandar_media"])
        self.assertIsNone(e.estadisticas["ic95_media_condicional"])

    def test_sin_dispersion_no_ic_degenerado(self):
        e = analizar_ejecucion(self.salida(conteos=(0, 5, 0)))
        self.assertEqual(e.estadisticas["error_estandar_media"], 0)
        self.assertIsNone(e.estadisticas["ic95_media_condicional"])
        self.assertIn("no demuestra", informe_ejecucion(e))

    def test_wilson_extremos(self):
        self.assertGreater(wilson(0, 100)[1], 0)
        self.assertLess(wilson(100, 100)[0], 1)
        for a, b in ((-1, 5), (6, 5), (0, 0)):
            with self.assertRaises(ValueError):
                wilson(a, b)

    def test_legacy_10_millones_sin_leer_csv_gigantes(self):
        e = analizar_ejecucion(ROOT / "MonteCarlo_Paralelo/resultados_10000000")
        self.assertEqual(e.estadisticas["con_inversion"], 9934770)
        self.assertAlmostEqual(e.estadisticas["media_condicional"], 2054.50413568, places=8)
        self.assertAlmostEqual(e.estadisticas["error_estandar_media"], .00073092, places=8)
        self.assertIsNone(e.procedencia)
        self.assertIn("Speedup individual: N/D", informe_ejecucion(e))

    def test_go_no_cpu_medida_ni_rss_linux(self):
        e = analizar_ejecucion(self.salida(version="go_secuencial"))
        self.assertIn("no mide tiempo de CPU", informe_ejecucion(e))
        self.assertIn("runtime.MemStats.Sys", " ".join(e.avisos))

    def test_metricas_no_finitas(self):
        carpeta = self.salida()
        for valor in ("nan", "inf", "-1"):
            with (carpeta / "metricas.csv").open(newline="", encoding="utf-8") as f:
                filas = list(csv.DictReader(f))
            filas[0]["segundos_total"] = valor
            csv_escribir(carpeta / "metricas.csv", filas)
            with self.assertRaises(ValueError):
                analizar_ejecucion(carpeta)

    def test_probabilidad_y_anios_inconsistentes(self):
        carpeta = self.salida()
        with (carpeta / "distribucion.csv").open(newline="", encoding="utf-8") as f:
            filas = list(csv.DictReader(f))
        filas[1]["probabilidad_anual"] = "0.99"
        csv_escribir(carpeta / "distribucion.csv", filas)
        with self.assertRaisesRegex(ValueError, "Probabilidad anual"):
            analizar_ejecucion(carpeta)
        filas[1]["probabilidad_anual"] = "0.4"
        filas[1]["anio"] = "2030"
        csv_escribir(carpeta / "distribucion.csv", filas)
        with self.assertRaisesRegex(ValueError, "consecutivos"):
            analizar_ejecucion(carpeta)

    def test_conteos_no_fraccionarios(self):
        carpeta = self.salida()
        f = carpeta / "distribucion.csv"
        f.write_text(f.read_text().replace("2026,2,", "2026,2.5,"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "entero"):
            analizar_ejecucion(carpeta)

    def test_config_ausente_no_inventar(self):
        carpeta = self.salida()
        (carpeta / "config_usada.ini").unlink()
        e = analizar_ejecucion(carpeta)
        self.assertNotIn("semilla", e.configuracion)
        self.assertTrue(any("Falta config_usada" in a for a in e.avisos))

    def test_exportacion_no_sobrescribe(self):
        e = analizar_ejecucion(self.salida())
        destino = self.base / "informe"
        exportar_ejecucion(e, destino, graficos=False)
        datos = json.loads((destino / "analisis.json").read_text(encoding="utf-8"))
        self.assertEqual(datos["estadisticas"]["con_inversion"], 4)
        with self.assertRaises(FileExistsError):
            exportar_ejecucion(e, destino, graficos=False)

    def test_cli_sin_dependencias_graficas(self):
        carpeta = self.salida()
        p = subprocess.run([sys.executable, "-m", "MonteCarlo_Analisis", "analizar", str(carpeta)],
                           cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("2026.500000", p.stdout)

    def test_rutas_visibles_sin_prefijos_personales(self):
        e = analizar_ejecucion(ROOT / "MonteCarlo_Secuencial/resultados_demo")
        informe = informe_ejecucion(e)
        self.assertIn("Origen: `MonteCarlo_Secuencial/resultados_demo`", informe)
        self.assertNotIn(str(ROOT), informe)
        externo = analizar_ejecucion(self.salida())
        self.assertNotIn(str(self.base), informe_ejecucion(externo))
        self.assertEqual(ruta_visible(r"C:\ruta\local\resultado"), "resultado")


class RendimientoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def crear(self, nombre, tiempo=10, version="secuencial", p=1, h=1, rep=1, **contexto):
        carpeta = crear_salida(self.base / nombre, version=version, procesos=p, hilos=h, tiempo=tiempo)
        firmar_sintetico(carpeta, rep=rep, **contexto)
        return carpeta

    def test_formulas_hibrido_y_variabilidad(self):
        carpetas = [
            self.crear("sec1", rep=1), self.crear("sec2", tiempo=12, rep=2),
            self.crear("hib1", version="hibrido", p=2, h=2, tiempo=5, rep=1),
            self.crear("hib2", version="hibrido", p=2, h=2, tiempo=6, rep=2),
        ]
        c = comparar_ejecuciones(carpetas)
        self.assertFalse(c.excluidas)
        f = next(f for f in c.filas if f["version"] == "hibrido")
        self.assertEqual(f["p"], 4)
        self.assertEqual(f["speedup"], 2)
        self.assertEqual(f["eficiencia"], .5)
        self.assertEqual(f["costo"], 22)
        self.assertAlmostEqual(f["segundos_total_sd"], math.sqrt(.5))
        self.assertAlmostEqual(f["karp_flatt"], 1 / 3)
        self.assertAlmostEqual(f["amdahl_smax"], 3)
        self.assertIn("preliminar", " ".join(c.conclusiones))

    def test_p_uno_y_superlineal_no_extrapolar(self):
        sec = self.crear("sec")
        omp1 = self.crear("omp1", version="openmp", tiempo=11)
        omp2 = self.crear("omp2", version="openmp", h=2, tiempo=2)
        c = comparar_ejecuciones([sec, omp1, omp2])
        f1 = next(f for f in c.filas if f["version"] == "openmp" and f["p"] == 1)
        f2 = next(f for f in c.filas if f["p"] == 2)
        self.assertIsNone(f1["karp_flatt"])
        self.assertLess(f2["karp_flatt"], 0)
        self.assertIsNone(f2["amdahl_smax"])

    def test_sin_t1_no_speedup(self):
        c = comparar_ejecuciones([self.crear("omp", version="openmp", h=2)])
        self.assertFalse(c.filas)
        self.assertIn("falta una linea base", " ".join(c.conclusiones))

    def test_diferente_equipo_o_campana_excluido(self):
        sec = self.crear("sec")
        for campo, valor in (("maquina", "otro_equipo"), ("campana", "otra_campana")):
            with self.subTest(campo=campo):
                omp = self.crear(campo, version="openmp", h=2, **{campo: valor})
                c = comparar_ejecuciones([sec, omp])
                self.assertEqual(len(c.filas), 1)
                self.assertEqual(len(c.excluidas), 1)

    def test_lineas_base_ambiguas(self):
        c = comparar_ejecuciones([self.crear("a"), self.crear("b", maquina="B")])
        self.assertFalse(c.filas)
        self.assertIn("distintas", " ".join(c.conclusiones))

    def test_t1_antiguo_no_se_asigna_al_equipo_actual(self):
        antiguo = crear_salida(self.base / "antiguo")
        nuevo = self.crear("omp", version="openmp", h=2)
        c = comparar_ejecuciones([antiguo, nuevo])
        self.assertFalse(c.filas)
        self.assertIn("Sin procedencia", c.excluidas[0]["motivo"])

    def test_archivos_modificados_no_son_comparables(self):
        sec = self.crear("sec")
        omp = self.crear("omp", version="openmp", h=2)
        f = omp / "escenarios.csv"
        f.write_text(f.read_text() + "\n", encoding="utf-8")
        c = comparar_ejecuciones([sec, omp])
        self.assertEqual(len(c.excluidas), 1)
        self.assertIn("cambio", c.excluidas[0]["motivo"])

    def test_metricas_modificadas_invalidan_procedencia(self):
        carpeta = self.crear("sec")
        f = carpeta / "metricas.csv"
        f.write_text(f.read_text() + "\n", encoding="utf-8")
        self.assertIsNone(analizar_ejecucion(carpeta).procedencia)

    def test_duplicar_carpeta_no_agrega_repeticion(self):
        sec = self.crear("sec")
        copia = self.base / "copia"
        shutil.copytree(sec, copia)
        c = comparar_ejecuciones([sec, copia])
        self.assertEqual(c.filas[0]["repeticiones"], 1)
        self.assertIn("duplicada", c.excluidas[0]["motivo"])

    def test_repeticiones_incompletas_no_se_promedian(self):
        c = comparar_ejecuciones([
            self.crear("sec1", rep=1), self.crear("sec2", rep=2),
            self.crear("omp", version="openmp", h=2, rep=1),
        ])
        self.assertEqual(len(c.filas), 1)
        self.assertIn("incompletas", c.excluidas[0]["motivo"])

    def test_manifiesto_incompleto(self):
        carpeta = self.crear("sec")
        guardar_json(self.base / "campana.json", dict(campana_id="campana_ficticia", estado="incompleta"))
        c = comparar_ejecuciones([carpeta])
        self.assertFalse(c.filas)
        self.assertIn("incompleta", " ".join(c.conclusiones))

    def test_no_omitir_una_configuracion_borrada(self):
        carpeta = self.crear("sec")
        guardar_json(self.base / "campana.json",
                     dict(campana_id="campana_ficticia", estado="completada", repeticiones=1,
                          ejecuciones=["sec", "mpi_borrado"]))
        c = comparar_ejecuciones([carpeta])
        self.assertFalse(c.filas)
        self.assertIn("faltan ejecuciones", " ".join(c.conclusiones))

    def test_contexto_corrupto_no_revienta_interfaz(self):
        carpeta = self.crear("sec")
        p = json.loads((carpeta / "procedencia.json").read_text())
        p["contexto"]["maquina"] = 12
        guardar_json(carpeta / "procedencia.json", p)
        self.assertIsNone(analizar_ejecucion(carpeta).procedencia)

    def test_descubrimiento_y_exportacion_sin_comparables(self):
        crear_salida(self.base / "antiguo")
        c = comparar_ejecuciones(descubrir_ejecuciones(self.base))
        exportar_comparacion(c, self.base / "informe", graficos=False)
        self.assertIn("no disponible", informe_comparacion(c))
        self.assertEqual(len(descubrir_ejecuciones(self.base)), 1)

    def test_exportacion_conserva_mediciones_y_origen(self):
        c = comparar_ejecuciones([self.crear("sec"), self.crear("omp", version="openmp", h=2)])
        exportar_comparacion(c, self.base / "informe", graficos=False)
        with (self.base / "informe/metricas_crudas.csv").open(encoding="utf-8", newline="") as f:
            filas = list(csv.DictReader(f))
        self.assertEqual(len(filas), 2)
        self.assertEqual({f["ejecucion_id"] for f in filas}, {"sec", "omp"})
        self.assertEqual(c.parametros["semilla"], "12345")


if __name__ == "__main__":
    unittest.main()
