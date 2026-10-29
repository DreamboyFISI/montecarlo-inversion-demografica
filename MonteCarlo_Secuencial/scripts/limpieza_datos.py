"""Recopilacion y limpieza de datos (Sprint 1, semanas 4-5).

Revisa los tres CSV originales, genera tablas procesadas en edades simples y
escribe un reporte de calidad. No modifica los CSV originales.

Uso:  python3 scripts/limpieza_datos.py [carpeta_datos] [carpeta_salida] [anio_base] [horizonte]
      (por defecto: datos  datos_procesados  2025  40)
"""
import csv
import math
import sys
from pathlib import Path

DATOS = Path(sys.argv[1] if len(sys.argv) > 1 else "datos")
SALIDA = Path(sys.argv[2] if len(sys.argv) > 2 else "datos_procesados")
ANIO_BASE = int(sys.argv[3]) if len(sys.argv) > 3 else 2025
HORIZONTE = int(sys.argv[4]) if len(sys.argv) > 4 else 40
Q100 = {"H": 0.35, "M": 0.35}  # supuesto de config_demostracion.ini

checks = []  # (resultado, descripcion)


def check(ok, texto):
    checks.append(("OK" if ok else "FALLA", texto))
    return ok


def leer(nombre):
    with open(DATOS / nombre, newline="", encoding="utf-8") as f:
        filas = [[c.strip() for c in fila] for fila in csv.reader(f) if any(c.strip() for c in fila)]
    check(len({len(x) for x in filas}) == 1, f"{nombre}: todas las filas tienen {len(filas[0])} columnas")
    vacias = sum(1 for fila in filas for c in fila if c == "")
    check(vacias == 0, f"{nombre}: sin celdas vacias ({vacias})")
    return filas[0], filas[1:]


# ---------------------------------------------------------------- poblacion
enc, pob = leer("poblacion_inicial_peru.csv")
check(enc == ["grupo_edad", "poblacion_hombres", "poblacion_mujeres"], "poblacion: encabezado esperado")
esperados = [f"{a}-{a+4}" for a in range(0, 100, 5)] + ["100+"]
check([r[0] for r in pob] == esperados, "poblacion: 21 grupos 0-4 ... 95-99, 100+ en orden y sin duplicados")
H = [int(r[1]) for r in pob]
M = [int(r[2]) for r in pob]
check(all(v >= 0 for v in H + M), "poblacion: conteos enteros no negativos")
total = sum(H) + sum(M)
menores = sum(H[:3]) + sum(M[:3])
mayores = sum(H[13:]) + sum(M[13:])
check(total == 32706028, f"poblacion: total = {total:,}".replace(",", " "))
check(menores == 7429471 and mayores == 3440272,
      f"poblacion: menores de 15 = {menores:,}; 65 o mas = {mayores:,}; razon A/J = {mayores/menores:.4f}".replace(",", " "))
check(mayores < menores, "poblacion: no hay inversion en el estado inicial")
ratio = sum(H) / sum(M) * 100
check(90 <= ratio <= 105, f"poblacion: indice de masculinidad plausible ({ratio:.1f} hombres por 100 mujeres)")


def desagregar(G):
    k, r = divmod(G, 5)
    return [k + (1 if j < r else 0) for j in range(5)]


simple = {"H": [], "M": []}
for i in range(20):
    simple["H"] += desagregar(H[i])
    simple["M"] += desagregar(M[i])
simple["H"].append(H[20])
simple["M"].append(M[20])
check(sum(simple["H"]) + sum(simple["M"]) == total, "desagregacion: 202 celdas conservan el total exacto")

# ---------------------------------------------------------------- fecundidad
enc_f, fec = leer("fecundidad_peru.csv")
periodos = [(int(h[10:14]), int(h[15:19])) for h in enc_f[1:]]
check(all(b - a == 5 for a, b in periodos) and periodos[0][0] == 2020 and periodos[-1][1] == 2070,
      "fecundidad: 10 periodos quinquenales contiguos 2020-2070")
check([r[0] for r in fec] == [f"{a}-{a+4}" for a in range(15, 50, 5)], "fecundidad: grupos 15-19 ... 45-49")
tasas = [[float(x) for x in r[1:]] for r in fec]
check(all(0 <= x <= 1 for fila in tasas for x in fila), "fecundidad: tasas en [0, 1]")
tgf = [5 * sum(tasas[i][j] for i in range(7)) for j in range(10)]
check(all(1.3 <= x <= 3.0 for x in tgf),
      "fecundidad: TGF = 5 x suma de tasas entre 1,3 y 3,0 en todos los periodos ("
      + ", ".join(f"{x:.2f}" for x in tgf) + ") -> compatible con 'nacimientos por mujer y anio'")
check(ANIO_BASE >= periodos[0][0] and ANIO_BASE + HORIZONTE - 1 < periodos[-1][1],
      f"fecundidad: cobertura para exposicion {ANIO_BASE}-{ANIO_BASE + HORIZONTE - 1}")

# ---------------------------------------------------------------- mortalidad
enc_m, mor = leer("mortalidad_peru.csv")
claves = [int(r[0]) for r in mor]
check(claves == [0, 1] + list(range(5, 101, 5)), "mortalidad: claves 0, 1, 5, ..., 100")
valores = {"H": [float(r[1]) for r in mor], "M": [float(r[2]) for r in mor]}
check(all(0 <= v <= 1 for s in valores for v in valores[s]), "mortalidad: valores en [0, 1]")
check(all(valores[s][-1] == 0 for s in valores), "mortalidad: fila 100 vale 0 -> no se usa; q(100+) viene de configuracion")
dec = all(valores[s][i] >= valores[s][i + 1] for s in valores for i in range(2, 21))
check(dec, "mortalidad: valores decrecientes desde 5 anios -> se comportan como probabilidades de SUPERVIVENCIA")
check(all(valores["M"][i] >= valores["H"][i] for i in range(21)), "mortalidad: supervivencia femenina >= masculina en todas las edades")

q = {"H": [0.0] * 101, "M": [0.0] * 101}
for i, a in enumerate(claves):
    for s in ("H", "M"):
        if a == 100:
            q[s][100] = Q100[s]
            continue
        n = 1 if a == 0 else 4 if a == 1 else 5
        for edad in range(a, a + n):
            q[s][edad] = 1 - valores[s][i] ** (1 / n)


def esperanza_vida(qs):
    """e0 aproximada con q anual constante y 100+ con q de configuracion (supuesto)."""
    l, e = 1.0, 0.0
    for a in range(100):
        d = l * qs[a]
        e += l - d / 2
        l -= d
    return e + l / qs[100]


e0 = {s: esperanza_vida(q[s]) for s in q}
check(65 <= e0["H"] <= 85 and 70 <= e0["M"] <= 90,
      f"mortalidad: con la interpretacion supervivencia_intervalo, e0 H = {e0['H']:.1f} y e0 M = {e0['M']:.1f} anios (plausible)")
check(abs(q["H"][20] - 0.001867) < 5e-7, f"mortalidad: q anual H 20-24 = {q['H'][20]:.6f}")

# ---------------------------------------------------------------- lambda inicial
col = next(j for j, (a, b) in enumerate(periodos) if a <= ANIO_BASE < b)
lam = sum(simple["M"][a] * tasas[(a - 15) // 5][col] for a in range(15, 50))
check(abs(lam - 512939.1415) < 1e-6, f"lambda inicial ({ANIO_BASE}) = {lam:,.4f}".replace(",", " "))
cohorte = (H[0] + M[0]) / 5
razon_nac = lam / cohorte
if not 0.85 <= razon_nac <= 1.15:
    checks.append(("AVISO", f"coherencia: nacimientos esperados {lam:.0f}/anio vs. {cohorte:.0f} personas por edad simple en 0-4 "
                   f"(razon {razon_nac:.2f}). La cohorte 0-4 es menor de lo que implica la fecundidad: posible desfase de "
                   "anio base, subregistro o fuentes distintas. Produce un repunte de menores de 15 hacia 2036-2040."))

# ---------------------------------------------------------------- salidas
SALIDA.mkdir(parents=True, exist_ok=True)
with open(SALIDA / "poblacion_edad_simple.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["edad", "hombres", "mujeres"])
    for a in range(101):
        w.writerow(["100+" if a == 100 else a, simple["H"][a], simple["M"][a]])
with open(SALIDA / "mortalidad_q_anual.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["edad", "q_hombres", "q_mujeres"])
    for a in range(101):
        w.writerow(["100+" if a == 100 else a, f"{q['H'][a]:.10f}", f"{q['M'][a]:.10f}"])
with open(SALIDA / "fecundidad_anual.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["anio", "columna_csv"] + [f"f_{a}_{a+4}" for a in range(15, 50, 5)] + ["tgf"])
    for t in range(HORIZONTE):
        y = ANIO_BASE + t
        j = next(j for j, (a, b) in enumerate(periodos) if a <= y < b)
        w.writerow([y, enc_f[j + 1]] + [tasas[i][j] for i in range(7)] + [f"{tgf[j]:.4f}"])

fallas = [c for c in checks if c[0] == "FALLA"]
avisos = [c for c in checks if c[0] == "AVISO"]
with open(SALIDA / "reporte_calidad_datos.md", "w", encoding="utf-8") as f:
    f.write("# Reporte de calidad de datos\n\n")
    f.write(f"Generado por `scripts/limpieza_datos.py`. Anio base supuesto: {ANIO_BASE}; horizonte: {HORIZONTE}.\n\n")
    f.write(f"Resultado: **{len(checks) - len(fallas) - len(avisos)} correctas, {len(avisos)} aviso(s), {len(fallas)} falla(s)** de {len(checks)} comprobaciones.\n\n")
    f.write("| Resultado | Comprobacion |\n|---|---|\n")
    for r, t in checks:
        f.write(f"| {r} | {t} |\n")
    f.write("\n## Pendiente de confirmar con la fuente\n\n"
            "- Anio de referencia de la poblacion inicial (se usa 2025 como supuesto).\n"
            "- Unidad de fecundidad: la TGF obtenida es plausible, pero falta la ficha tecnica.\n"
            "- Mortalidad: el patron y la e0 resultante apoyan 'supervivencia por intervalo', pero falta la ficha tecnica.\n"
            "- q(100+), pF y u: parametros didacticos sin fuente.\n"
            "\n## Archivos procesados\n\n"
            "- `poblacion_edad_simple.csv`: 101 edades x 2 sexos (reparto uniforme entero).\n"
            "- `mortalidad_q_anual.csv`: q anual por edad simple y sexo.\n"
            f"- `fecundidad_anual.csv`: tasa por grupo para cada anio {ANIO_BASE}-{ANIO_BASE + HORIZONTE - 1} y TGF.\n")

for r, t in checks:
    print(f"[{r}] {t}")
print(f"\n{len(checks) - len(fallas) - len(avisos)} correctas, {len(avisos)} aviso(s), {len(fallas)} falla(s). Salida en {SALIDA}/")
sys.exit(1 if fallas else 0)
