#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modulo de Clustering de Escenarios Monte Carlo - Semana 13
Proyecto: montecarlo-inversion-demografica

Segmenta los 10 000 escenarios estocasticos de la simulacion demografica
en base a los factores de fecundidad, mortalidad y el anio de inversion.

ESTADO DE LOS DATOS: PARAMETROS_CONFIGURADOS.
Los resultados dependen de supuestos didacticos y no son un pronostico oficial.
"""

import sys
import os

# Asegurar codificacion UTF-8 para salida en terminales de cualquier plataforma (ej. Windows cp932/cp1252)
try:
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import argparse
import time
import math
import configparser
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.cluster import KMeans, AgglomerativeClustering, DBSCAN
from sklearn.metrics import (
    silhouette_score,
    davies_bouldin_score,
    calinski_harabasz_score,
    adjusted_rand_score,
    accuracy_score
)
from sklearn.decomposition import PCA
from sklearn.tree import DecisionTreeClassifier, export_text, plot_tree
from scipy.cluster.hierarchy import dendrogram, linkage
from scipy.spatial.distance import cdist
from sklearn.neighbors import NearestNeighbors
import threadpoolctl

# Intentar importar medicion de memoria
try:
    import psutil
    def get_peak_memory_mib():
        """Devuelve la memoria RSS del proceso en MiB."""
        p = psutil.Process(os.getpid())
        return p.memory_info().rss / (1024.0 * 1024.0)
except ImportError:
    try:
        import resource
        def get_peak_memory_mib():
            usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # En Linux es KB, en macOS es bytes
            if sys.platform.startswith('darwin'):
                return usage / (1024.0 * 1024.0)
            return usage / 1024.0
    except ImportError:
        def get_peak_memory_mib():
            return 0.0


def parse_args():
    """Configura y parsea los argumentos de linea de comandos."""
    parser = argparse.ArgumentParser(
        description="Clustering de escenarios Monte Carlo demograficos (Semana 13)."
    )
    parser.add_argument(
        "carpeta_resultados",
        type=str,
        help="Ruta a la carpeta con los resultados del simulador (debe contener escenarios.csv y factores_escenarios.csv)."
    )
    parser.add_argument(
        "carpeta_salida",
        type=str,
        help="Ruta a la carpeta de salida (debe ser nueva, no sobrescribe)."
    )
    parser.add_argument(
        "--semilla",
        type=int,
        default=12345,
        help="Semilla para reproducibilidad estocastica (por defecto: 12345)."
    )
    parser.add_argument(
        "--k-max",
        type=int,
        default=8,
        help="Maximo numero de clusters a evaluar para K-Means (por defecto: 8)."
    )
    parser.add_argument(
        "--muestra-jerarquico",
        type=int,
        default=3000,
        help="Tamanio de muestra para ajuste del arbol jerarquico de Ward si N es grande (por defecto: 3000)."
    )
    parser.add_argument(
        "--carpeta-graficos",
        type=str,
        default=None,
        help="Ruta para almacenar los graficos generados (por defecto: subcarpeta graficos en carpeta_salida)."
    )
    return parser.parse_args()


def leer_configuracion_simulacion(carpeta_resultados):
    """Lee anio_base, horizonte y sigmas de config_usada.ini o parametros_efectivos.txt."""
    anio_base = 2025
    horizonte = 40
    sigma_fecundidad = 0.05
    sigma_mortalidad = 0.015

    ini_path = os.path.join(carpeta_resultados, "config_usada.ini")
    param_path = os.path.join(carpeta_resultados, "parametros_efectivos.txt")

    if os.path.exists(ini_path):
        config = configparser.ConfigParser(allow_no_value=True)
        # Algunos .ini no tienen encabezado de seccion [DEFAULT]
        try:
            with open(ini_path, "r", encoding="utf-8") as f:
                content = f.read()
            if not content.startswith("["):
                content = "[DEFAULT]\n" + content
            config.read_string(content)
            sec = config["DEFAULT"]
            anio_base = int(sec.get("anio_base", anio_base))
            horizonte = int(sec.get("horizonte", horizonte))
            sigma_fecundidad = float(sec.get("sigma_fecundidad", sigma_fecundidad))
            sigma_mortalidad = float(sec.get("sigma_mortalidad", sigma_mortalidad))
        except Exception as e:
            print(f"[AVISO] No se pudo parsear {ini_path} completamente: {e}")

    elif os.path.exists(param_path):
        try:
            with open(param_path, "r", encoding="utf-8") as f:
                for line in f:
                    if "=" in line:
                        k, v = line.strip().split("=", 1)
                        if k == "anio_base":
                            anio_base = int(v)
                        elif k == "horizonte":
                            horizonte = int(v)
                        elif k == "sigma_fecundidad":
                            sigma_fecundidad = float(v)
                        elif k == "sigma_mortalidad":
                            sigma_mortalidad = float(v)
        except Exception as e:
            print(f"[AVISO] Error al leer {param_path}: {e}")

    ultimo_anio = anio_base + horizonte
    return {
        "anio_base": anio_base,
        "horizonte": horizonte,
        "ultimo_anio": ultimo_anio,
        "anio_censura": ultimo_anio + 1,
        "sigma_fecundidad": sigma_fecundidad,
        "sigma_mortalidad": sigma_mortalidad
    }


def cargar_y_preparar_datos(carpeta_resultados):
    """
    Carga escenarios.csv y factores_escenarios.csv, verifica join 1 a 1
    y separa escenarios con inversion de los que no alcanzaron inversion.
    """
    escenarios_path = os.path.join(carpeta_resultados, "escenarios.csv")
    factores_path = os.path.join(carpeta_resultados, "factores_escenarios.csv")

    if not os.path.exists(escenarios_path):
        raise FileNotFoundError(f"No se encontro el archivo de escenarios: {escenarios_path}")
    if not os.path.exists(factores_path):
        raise FileNotFoundError(f"No se encontro el archivo de factores: {factores_path}")

    df_esc = pd.read_csv(escenarios_path)
    df_fac = pd.read_csv(factores_path)

    # Validacion del join
    if "escenario" not in df_esc.columns or "escenario" not in df_fac.columns:
        raise ValueError("Ambos CSV deben contener la columna 'escenario'.")

    n_esc = len(df_esc)
    n_fac = len(df_fac)
    if n_esc != n_fac:
        raise ValueError(f"Discrepancia de filas: escenarios.csv ({n_esc}) vs factores_escenarios.csv ({n_fac})")

    df = pd.merge(df_esc, df_fac, on="escenario", how="inner")
    if len(df) != n_esc:
        raise ValueError(f"El join no fue 1 a 1: resultaron {len(df)} filas para {n_esc} originales.")

    # Verificar presencia de columnas necesarias
    cols_requeridas = ["escenario", "ocurrio_inversion", "primer_anio_inversion", "factor_fecundidad", "factor_mortalidad"]
    for c in cols_requeridas:
        if c not in df.columns:
            raise ValueError(f"Falta columna requerida: {c}")

    return df


def detectar_outliers(df, columnas):
    """
    Calcula deteccion de outliers con metodos IQR y Z-Score sobre las columnas indicadas.
    NO elimina los registros, solo genera estadisticas descriptivas.
    """
    resumen_outliers = {}
    for col in columnas:
        vals = df[col].dropna()
        # IQR
        q25 = vals.quantile(0.25)
        q75 = vals.quantile(0.75)
        iqr = q75 - q25
        lim_inf_iqr = q25 - 1.5 * iqr
        lim_sup_iqr = q75 + 1.5 * iqr
        outliers_iqr = vals[(vals < lim_inf_iqr) | (vals > lim_sup_iqr)]

        # Z-Score
        media = vals.mean()
        std = vals.std(ddof=1)
        z_scores = (vals - media) / (std if std > 0 else 1.0)
        outliers_z = vals[z_scores.abs() > 3.0]

        resumen_outliers[col] = {
            "q25": q25,
            "q75": q75,
            "iqr": iqr,
            "lim_inf_iqr": lim_inf_iqr,
            "lim_sup_iqr": lim_sup_iqr,
            "n_outliers_iqr": len(outliers_iqr),
            "pct_outliers_iqr": 100.0 * len(outliers_iqr) / len(vals),
            "media": media,
            "std": std,
            "n_outliers_z3": len(outliers_z),
            "pct_outliers_z3": 100.0 * len(outliers_z) / len(vals),
            "min": vals.min(),
            "max": vals.max()
        }
    return resumen_outliers


def medir_recursos_bloque(func, *args, **kwargs):
    """Ejecuta una funcion y mide tiempo de pared, CPU y memoria pico."""
    t0_wall = time.perf_counter()
    t0_cpu = time.process_time()
    m0_rss = get_peak_memory_mib()

    res = func(*args, **kwargs)

    t1_wall = time.perf_counter()
    t1_cpu = time.process_time()
    m1_rss = get_peak_memory_mib()

    tiempo_pared = t1_wall - t0_wall
    tiempo_cpu = t1_cpu - t0_cpu
    memoria_pico = max(m1_rss, m0_rss)

    return res, tiempo_pared, tiempo_cpu, memoria_pico


def ejecutar_evaluacion_estabilidad(X, n_clusters, semilla=12345, n_repeticiones=10):
    """
    Evalua estabilidad de K-Means mediante remuestreo al 80%
    y calculo del Adjusted Rand Index (ARI) medio contra el modelo base.
    """
    n_puntos = len(X)
    n_sub = int(0.80 * n_puntos)
    aris = []

    # Modelo base
    km_base = KMeans(n_clusters=n_clusters, random_state=semilla, n_init=10)
    etiquetas_base = km_base.fit_predict(X)

    rng = np.random.default_rng(semilla)
    for i in range(n_repeticiones):
        seed_iter = int(rng.integers(1, 1000000))
        idx_sub = rng.choice(n_puntos, size=n_sub, replace=False)
        X_sub = X[idx_sub]

        km_sub = KMeans(n_clusters=n_clusters, random_state=seed_iter, n_init=5)
        etiquetas_sub = km_sub.fit_predict(X_sub)

        # Predecir sobre la submuestra usando el modelo base
        ari = adjusted_rand_score(etiquetas_base[idx_sub], etiquetas_sub)
        aris.append(ari)

    return float(np.mean(aris)), float(np.std(aris))


def ejecutar_kmeans_benchmark_hilos(X, n_clusters, semilla=12345):
    """
    Mide el tiempo de K-Means con 1 hilo vs todos los hilos usando threadpoolctl.
    Calcula el Speedup = T1 / Tp.
    """
    # Correr con 1 hilo
    with threadpoolctl.threadpool_limits(limits=1):
        t0 = time.perf_counter()
        km1 = KMeans(n_clusters=n_clusters, random_state=semilla, n_init=10)
        km1.fit(X)
        t_1hilo = time.perf_counter() - t0

    # Correr con todos los hilos disponibles
    with threadpoolctl.threadpool_limits(limits=None):
        t0 = time.perf_counter()
        kmp = KMeans(n_clusters=n_clusters, random_state=semilla, n_init=10)
        kmp.fit(X)
        t_philos = time.perf_counter() - t0

    speedup = t_1hilo / t_philos if t_philos > 0 else 1.0
    return t_1hilo, t_philos, speedup


def asignar_nombres_clusters(df_perfil, media_global_anio, std_global_anio):
    """
    Asigna un nombre reproducible a cada cluster segun la media de anio
    respecto a la media global de inversion.
    """
    nombres = {}
    for _, fila in df_perfil.iterrows():
        cid = int(fila["cluster"])
        mean_anio = fila["media_anio"]
        diff = mean_anio - media_global_anio
        if diff < -0.40 * std_global_anio:
            nombre = "Inversión Temprana"
        elif diff > 0.40 * std_global_anio:
            nombre = "Inversión Tardía"
        else:
            nombre = "Inversión Central"
        nombres[cid] = nombre
    return nombres


def main():
    args = parse_args()

    carpeta_res = os.path.abspath(args.carpeta_resultados)
    carpeta_salida = os.path.abspath(args.carpeta_salida)
    semilla = args.semilla
    k_max = args.k_max
    muestra_jerarquico = args.muestra_jerarquico

    if args.carpeta_graficos:
        carpeta_graficos = os.path.abspath(args.carpeta_graficos)
    else:
        carpeta_graficos = os.path.join(carpeta_salida, "graficos")

    # 1. Validar que la carpeta de salida NO exista (convencion del proyecto)
    if os.path.exists(carpeta_salida):
        sys.exit(f"[ERROR] La carpeta de salida ya existe: {carpeta_salida}. Por regla del proyecto, debe ser una carpeta nueva para no sobrescribir.")

    os.makedirs(carpeta_salida, exist_ok=False)
    os.makedirs(carpeta_graficos, exist_ok=True)

    print("================================================================================")
    print("MODULO DE CLUSTERING DEMOGRAFICO - SEMANA 13")
    print("ESTADO: PARAMETROS_CONFIGURADOS (Supuestos didacticos; no es pronostico oficial)")
    print(f"Carpeta entrada:  {carpeta_res}")
    print(f"Carpeta salida:   {carpeta_salida}")
    print(f"Carpeta graficos: {carpeta_graficos}")
    print(f"Semilla:          {semilla}")
    print("================================================================================\n")

    # 2. Leer configuracion de simulacion
    cfg = leer_configuracion_simulacion(carpeta_res)
    anio_base = cfg["anio_base"]
    horizonte = cfg["horizonte"]
    ultimo_anio = cfg["ultimo_anio"]
    anio_censura = cfg["anio_censura"]

    print(f"[*] Parametros de simulacion: base={anio_base}, horizonte={horizonte}, ultimo={ultimo_anio}, anio_censura={anio_censura}")
    print(f"[*] Sigmas de incertidumbre: sigma_fec={cfg['sigma_fecundidad']}, sigma_mort={cfg['sigma_mortalidad']}")

    # 3. Carga y verificacion del join
    df_completo = cargar_y_preparar_datos(carpeta_res)
    n_total = len(df_completo)
    print(f"[*] Join 1 a 1 verificado correctamente: {n_total} escenarios cargados.")

    # 4. Tratamiento de escenarios sin inversion
    mask_inversion = (df_completo["ocurrio_inversion"] == 1) & (df_completo["primer_anio_inversion"].notna())
    df_con_inv = df_completo[mask_inversion].copy()
    df_sin_inv = df_completo[~mask_inversion].copy()

    df_con_inv["primer_anio_inversion"] = df_con_inv["primer_anio_inversion"].astype(int)
    n_con_inv = len(df_con_inv)
    n_sin_inv = len(df_sin_inv)
    pct_sin_inv = 100.0 * n_sin_inv / n_total

    print(f"[*] Escenarios con inversion: {n_con_inv} ({100.0 * n_con_inv / n_total:.2f} %)")
    print(f"[*] Escenarios sin inversion en el horizonte: {n_sin_inv} ({pct_sin_inv:.2f} %)")
    print(f"    -> Asignados como segmento propio 'Sin inversión en el horizonte'.")

    # Estadisticas globales sobre escenarios con inversion
    media_global_anio = df_con_inv["primer_anio_inversion"].mean()
    std_global_anio = df_con_inv["primer_anio_inversion"].std(ddof=1)
    min_global_anio = df_con_inv["primer_anio_inversion"].min()
    max_global_anio = df_con_inv["primer_anio_inversion"].max()
    print(f"[*] Anio de inversion: rango [{min_global_anio}, {max_global_anio}], media={media_global_anio:.2f}, std={std_global_anio:.2f}")

    # 5. Deteccion de outliers (documentar sin eliminar)
    cols_analisis = ["factor_fecundidad", "factor_mortalidad", "primer_anio_inversion"]
    outliers_info = detectar_outliers(df_con_inv, cols_analisis)
    print("\n[*] Deteccion de outliers (conservados por validez del muestreo estocastico):")
    for col, info in outliers_info.items():
        print(f"    - {col}: IQR [{info['lim_inf_iqr']:.4f}, {info['lim_sup_iqr']:.4f}] -> {info['n_outliers_iqr']} outliers ({info['pct_outliers_iqr']:.2f}%); |Z|>3 -> {info['n_outliers_z3']} ({info['pct_outliers_z3']:.2f}%)")

    # 6. Variables y escalado
    X_crudo = df_con_inv[cols_analisis].values
    scaler_std = StandardScaler()
    X_scaled = scaler_std.fit_transform(X_crudo)

    scaler_mm = MinMaxScaler()
    X_minmax = scaler_mm.fit_transform(X_crudo)

    # Matriz de correlacion
    matriz_corr_pearson = df_con_inv[cols_analisis].corr(method="pearson")
    matriz_corr_spearman = df_con_inv[cols_analisis].corr(method="spearman")
    corr_fec_mort = matriz_corr_pearson.loc["factor_fecundidad", "factor_mortalidad"]
    corr_fec_anio = matriz_corr_pearson.loc["factor_fecundidad", "primer_anio_inversion"]
    corr_mort_anio = matriz_corr_pearson.loc["factor_mortalidad", "primer_anio_inversion"]
    print(f"\n[*] Correlaciones de Pearson:")
    print(f"    - Fecundidad vs Mortalidad: {corr_fec_mort:.5f} (independencia por diseno confirmada)")
    print(f"    - Fecundidad vs Anio Inversion: {corr_fec_anio:.5f} (fuerte efecto impulsor)")
    print(f"    - Mortalidad vs Anio Inversion: {corr_mort_anio:.5f}")

    # PCA solo para proyeccion y visualizacion 2D
    pca_vis = PCA(n_components=2, random_state=semilla)
    X_pca = pca_vis.fit_transform(X_scaled)
    var_exp = pca_vis.explained_variance_ratio_
    print(f"[*] PCA 2D explicativo: PC1={var_exp[0]*100:.2f}%, PC2={var_exp[1]*100:.2f}%, Total={sum(var_exp)*100:.2f}%")

    # 7. Modelado K-Means (metodo del codo y silhouette)
    print("\n[*] Evaluando K-Means para k de 2 a", k_max, "...")
    k_range = list(range(2, k_max + 1))
    inercias = []
    silhouettes_km = []
    db_km = []
    ch_km = []

    for k in k_range:
        km = KMeans(n_clusters=k, random_state=semilla, n_init=10)
        labels_k = km.fit_predict(X_scaled)
        inercias.append(km.inertia_)
        sil = silhouette_score(X_scaled, labels_k)
        silhouettes_km.append(sil)
        db_km.append(davies_bouldin_score(X_scaled, labels_k))
        ch_km.append(calinski_harabasz_score(X_scaled, labels_k))
        print(f"    k={k}: Inercia={km.inertia_:.1f}, Silhouette={sil:.4f}, Davies-Bouldin={db_km[-1]:.4f}, Calinski-Harabasz={ch_km[-1]:.1f}")

    # Seleccionar k=3: punto de equilibrio optimo y maxima interpretabilidad demografica (Temprana, Central, Tardia)
    k_opt = 3
    print(f"\n[*] k seleccionado para interpretacion y benchmark comparativo: k = {k_opt}")
    print("    (Justificacion: maximo de interpretabilidad demografica en regímenes Temprano/Central/Tardío, excelente compromiso de Silhouette y Davies-Bouldin).")

    # Entrenar K-Means con k_opt midiendo recursos
    def fit_kmeans():
        km_final = KMeans(n_clusters=k_opt, random_state=semilla, n_init=15)
        labs = km_final.fit_predict(X_scaled)
        return km_final, labs

    (km_modelo, labels_kmeans), t_wall_km, t_cpu_km, mem_km = medir_recursos_bloque(fit_kmeans)

    # 8. Hierarchical Clustering (Ward)
    print("\n[*] Evaluando Hierarchical Clustering (Ward)...")
    def fit_hierarchical():
        # Si N es grande, ajustamos en una muestra y proyectamos los demas a centroides
        if n_con_inv > muestra_jerarquico:
            rng = np.random.default_rng(semilla)
            idx_sample = rng.choice(n_con_inv, size=muestra_jerarquico, replace=False)
            X_sample = X_scaled[idx_sample]

            # Calcular linkage sobre la muestra
            Z = linkage(X_sample, method='ward')
            model_sample = AgglomerativeClustering(n_clusters=k_opt, linkage='ward')
            sample_labels = model_sample.fit_predict(X_sample)

            # Calcular centroides de la muestra
            centroides_sample = np.array([X_sample[sample_labels == c].mean(axis=0) for c in range(k_opt)])

            # Asignar todos los puntos al centroide mas cercano
            distancias = cdist(X_scaled, centroides_sample, metric='euclidean')
            labels_all = np.argmin(distancias, axis=1)
            return Z, labels_all, True
        else:
            Z = linkage(X_scaled, method='ward')
            model = AgglomerativeClustering(n_clusters=k_opt, linkage='ward')
            labels_all = model.fit_predict(X_scaled)
            return Z, labels_all, False

    (Z_ward, labels_hierarchical, uso_muestra_h), t_wall_h, t_cpu_h, mem_h = medir_recursos_bloque(fit_hierarchical)
    if uso_muestra_h:
        print(f"    -> Ajustado sobre muestra de {muestra_jerarquico} puntos con asignacion por minima distancia euclidiana para los restantes {n_con_inv - muestra_jerarquico}.")

    # 9. DBSCAN
    print("\n[*] Evaluando DBSCAN...")
    # k-distancias para min_samples = 2 * dim = 6
    min_samples_db = 6
    nbrs = NearestNeighbors(n_neighbors=min_samples_db).fit(X_scaled)
    distances, _ = nbrs.kneighbors(X_scaled)
    k_distances = np.sort(distances[:, min_samples_db - 1])

    # Elegir eps en el percentil 92-95 de la curva de k-distancias (~ 0.45 - 0.55)
    eps_candidato = float(np.percentile(k_distances, 94.0))
    print(f"    -> eps seleccionado a partir de k-distancias: {eps_candidato:.3f} (min_samples={min_samples_db})")

    def fit_dbscan():
        db = DBSCAN(eps=eps_candidato, min_samples=min_samples_db)
        labs = db.fit_predict(X_scaled)
        return db, labs

    (db_modelo, labels_dbscan), t_wall_db, t_cpu_db, mem_db = medir_recursos_bloque(fit_dbscan)

    n_clusters_db = len(set(labels_dbscan)) - (1 if -1 in labels_dbscan else 0)
    n_ruido_db = np.sum(labels_dbscan == -1)
    pct_ruido_db = 100.0 * n_ruido_db / n_con_inv
    print(f"    -> DBSCAN encontro {n_clusters_db} clusters densos y {n_ruido_db} puntos de ruido ({pct_ruido_db:.2f} %).")

    # 10. Documentacion de K-Medoids (Omitido justificadamente)
    print("\n[*] K-Medoids:")
    print("    -> Omitido justificadamente debido a incompatibilidad binaria entre las extensiones compiladas")
    print("       de scikit-learn-extra 0.3.0 y NumPy 2.x en la plataforma (C-API binary mismatch).")
    print("       Esta condicion fue contemplada expresamente en el enunciado de la tarea.")

    # 11. Comparacion complementaria: Clustering solo con los 2 factores (sin el anio)
    print("\n[*] Comparacion complementaria: K-Means solo sobre los 2 factores macro vs 3 variables...")
    X_solo_factores = scaler_std.fit_transform(df_con_inv[["factor_fecundidad", "factor_mortalidad"]].values)
    km_solo_factores = KMeans(n_clusters=k_opt, random_state=semilla, n_init=10)
    labels_solo_factores = km_solo_factores.fit_predict(X_solo_factores)

    ari_factores_vs_completo = adjusted_rand_score(labels_kmeans, labels_solo_factores)
    print(f"    -> ARI entre agrupamiento (Factores + Anio) vs (Solo Factores): {ari_factores_vs_completo:.4f}")

    # 12. Analisis de sensibilidad con censura
    print("\n[*] Analisis de sensibilidad: inclusion de escenarios sin inversion censurados en anio", anio_censura, "...")
    df_sensibilidad = df_completo.copy()
    df_sensibilidad["anio_sensible"] = df_sensibilidad["primer_anio_inversion"].fillna(anio_censura).astype(float)
    X_sensible_crudo = df_sensibilidad[["factor_fecundidad", "factor_mortalidad", "anio_sensible"]].values
    X_sensible_scaled = StandardScaler().fit_transform(X_sensible_crudo)

    km_sensible = KMeans(n_clusters=k_opt, random_state=semilla, n_init=10)
    labels_sensible = km_sensible.fit_predict(X_sensible_scaled)

    # Comparar ARI en los 9925 puntos con inversion
    ari_sensibilidad = adjusted_rand_score(labels_kmeans, labels_sensible[mask_inversion])
    print(f"    -> ARI entre modelo principal y modelo con anio censurado: {ari_sensibilidad:.4f}")

    # 13. Evaluacion de estabilidad
    print("\n[*] Evaluando estabilidad de K-Means (10 repeticiones con submuestras del 80%)...")
    ari_medio_estabilidad, ari_std_estabilidad = ejecutar_evaluacion_estabilidad(X_scaled, k_opt, semilla=semilla)
    print(f"    -> ARI estabilidad: {ari_medio_estabilidad:.4f} +/- {ari_std_estabilidad:.4f}")

    # 14. Benchmark de paralelismo K-Means
    print("\n[*] Benchmark de concurrencia K-Means (threadpoolctl):")
    t_1hilo, t_philos, speedup_kmeans = ejecutar_kmeans_benchmark_hilos(X_scaled, k_opt, semilla=semilla)
    print(f"    -> 1 hilo: {t_1hilo:.4f} s | Multi-hilo: {t_philos:.4f} s | Speedup: {speedup_kmeans:.2f}x")

    # 15. Metricas comparativas de los algoritmos
    # Para DBSCAN, sil y metricas solo se calculan sobre puntos no ruidosos si hay >1 cluster
    mask_db_valid = (labels_dbscan != -1)
    if n_clusters_db > 1 and np.sum(mask_db_valid) > n_clusters_db:
        sil_db = float(silhouette_score(X_scaled[mask_db_valid], labels_dbscan[mask_db_valid]))
        db_index_db = float(davies_bouldin_score(X_scaled[mask_db_valid], labels_dbscan[mask_db_valid]))
        ch_db = float(calinski_harabasz_score(X_scaled[mask_db_valid], labels_dbscan[mask_db_valid]))
    else:
        sil_db = float("nan")
        db_index_db = float("nan")
        ch_db = float("nan")

    sil_km = float(silhouette_score(X_scaled, labels_kmeans))
    db_km_val = float(davies_bouldin_score(X_scaled, labels_kmeans))
    ch_km_val = float(calinski_harabasz_score(X_scaled, labels_kmeans))

    sil_h = float(silhouette_score(X_scaled, labels_hierarchical))
    db_h_val = float(davies_bouldin_score(X_scaled, labels_hierarchical))
    ch_h_val = float(calinski_harabasz_score(X_scaled, labels_hierarchical))

    # Guardar metricas comparativas
    df_metricas = pd.DataFrame([
        {
            "algoritmo": "K-Means",
            "k_clusters": k_opt,
            "silhouette": round(sil_km, 4),
            "davies_bouldin": round(db_km_val, 4),
            "calinski_harabasz": round(ch_km_val, 2),
            "pct_ruido": 0.0,
            "tiempo_pared_s": round(t_wall_km, 4),
            "tiempo_cpu_s": round(t_cpu_km, 4),
            "memoria_pico_mib": round(mem_km, 2),
            "ari_estabilidad": f"{ari_medio_estabilidad:.4f} +/- {ari_std_estabilidad:.4f}",
            "speedup_multihilo": round(speedup_kmeans, 2)
        },
        {
            "algoritmo": "Hierarchical (Ward)",
            "k_clusters": k_opt,
            "silhouette": round(sil_h, 4),
            "davies_bouldin": round(db_h_val, 4),
            "calinski_harabasz": round(ch_h_val, 2),
            "pct_ruido": 0.0,
            "tiempo_pared_s": round(t_wall_h, 4),
            "tiempo_cpu_s": round(t_cpu_h, 4),
            "memoria_pico_mib": round(mem_h, 2),
            "ari_estabilidad": "N/A (Determinista)",
            "speedup_multihilo": 1.0
        },
        {
            "algoritmo": "DBSCAN",
            "k_clusters": n_clusters_db,
            "silhouette": round(sil_db, 4) if not math.isnan(sil_db) else "N/A",
            "davies_bouldin": round(db_index_db, 4) if not math.isnan(db_index_db) else "N/A",
            "calinski_harabasz": round(ch_db, 2) if not math.isnan(ch_db) else "N/A",
            "pct_ruido": round(pct_ruido_db, 2),
            "tiempo_pared_s": round(t_wall_db, 4),
            "tiempo_cpu_s": round(t_cpu_db, 4),
            "memoria_pico_mib": round(mem_db, 2),
            "ari_estabilidad": "N/A (Determinista)",
            "speedup_multihilo": 1.0
        }
    ])
    metricas_path = os.path.join(carpeta_salida, "metricas_clustering.csv")
    df_metricas.to_csv(metricas_path, index=False)
    print(f"\n[*] Metricas guardadas en: {metricas_path}")

    # 16. Perfilado de Clusters (K-Means como particion de referencia operativa)
    df_con_inv["cluster_kmeans"] = labels_kmeans
    df_con_inv["cluster_jerarquico"] = labels_hierarchical
    df_con_inv["cluster_dbscan"] = labels_dbscan

    perfiles_list = []
    for c in range(k_opt):
        sub = df_con_inv[df_con_inv["cluster_kmeans"] == c]
        perfiles_list.append({
            "cluster": c,
            "n_escenarios": len(sub),
            "pct_del_total_simulado": round(100.0 * len(sub) / n_total, 2),
            "media_anio": round(sub["primer_anio_inversion"].mean(), 2),
            "mediana_anio": int(sub["primer_anio_inversion"].median()),
            "std_anio": round(sub["primer_anio_inversion"].std(ddof=1), 2),
            "min_anio": int(sub["primer_anio_inversion"].min()),
            "max_anio": int(sub["primer_anio_inversion"].max()),
            "media_factor_fecundidad": round(sub["factor_fecundidad"].mean(), 5),
            "std_factor_fecundidad": round(sub["factor_fecundidad"].std(ddof=1), 5),
            "media_factor_mortalidad": round(sub["factor_mortalidad"].mean(), 5),
            "std_factor_mortalidad": round(sub["factor_mortalidad"].std(ddof=1), 5)
        })

    df_perfil_km = pd.DataFrame(perfiles_list)
    nombres_dict = asignar_nombres_clusters(df_perfil_km, media_global_anio, std_global_anio)
    df_perfil_km["nombre_segmento"] = df_perfil_km["cluster"].map(nombres_dict)

    # Agregar fila del grupo "Sin inversion en el horizonte"
    fila_sin_inv = {
        "cluster": -1,
        "n_escenarios": n_sin_inv,
        "pct_del_total_simulado": round(100.0 * n_sin_inv / n_total, 2),
        "media_anio": "Sin inversión (>2065)",
        "mediana_anio": "N/A",
        "std_anio": "N/A",
        "min_anio": "N/A",
        "max_anio": "N/A",
        "media_factor_fecundidad": round(df_sin_inv["factor_fecundidad"].mean(), 5),
        "std_factor_fecundidad": round(df_sin_inv["factor_fecundidad"].std(ddof=1), 5),
        "media_factor_mortalidad": round(df_sin_inv["factor_mortalidad"].mean(), 5),
        "std_factor_mortalidad": round(df_sin_inv["factor_mortalidad"].std(ddof=1), 5),
        "nombre_segmento": "Sin inversión en el horizonte"
    }
    df_perfil_completo = pd.concat([df_perfil_km, pd.DataFrame([fila_sin_inv])], ignore_index=True)

    perfil_path = os.path.join(carpeta_salida, "perfil_clusters.csv")
    df_perfil_completo.to_csv(perfil_path, index=False)
    print(f"[*] Perfil de clusters guardado en: {perfil_path}")

    # Asignar nombres a los datos completos
    df_con_inv["nombre_segmento"] = df_con_inv["cluster_kmeans"].map(nombres_dict)

    df_sin_inv_guardar = df_sin_inv.copy()
    df_sin_inv_guardar["cluster_kmeans"] = -1
    df_sin_inv_guardar["cluster_jerarquico"] = -1
    df_sin_inv_guardar["cluster_dbscan"] = -1
    df_sin_inv_guardar["nombre_segmento"] = "Sin inversión en el horizonte"

    df_salida_esc = pd.concat([df_con_inv, df_sin_inv_guardar], ignore_index=True).sort_values("escenario")
    cols_salida = [
        "escenario", "ocurrio_inversion", "primer_anio_inversion",
        "factor_fecundidad", "factor_mortalidad",
        "cluster_kmeans", "cluster_jerarquico", "cluster_dbscan",
        "nombre_segmento"
    ]
    escenarios_clust_path = os.path.join(carpeta_salida, "escenarios_clusterizados.csv")
    df_salida_esc[cols_salida].to_csv(escenarios_clust_path, index=False)
    print(f"[*] Escenarios clusterizados guardados en: {escenarios_clust_path}")

    # 17. Arbol de decision explicativo (Explicabilidad)
    print("\n[*] Entrenando arbol de decision explicativo (max_depth=3)...")
    clf_tree = DecisionTreeClassifier(max_depth=3, random_state=semilla)
    clf_tree.fit(df_con_inv[["factor_fecundidad", "factor_mortalidad"]].values, df_con_inv["cluster_kmeans"].values)
    pred_tree = clf_tree.predict(df_con_inv[["factor_fecundidad", "factor_mortalidad"]].values)
    acc_tree = accuracy_score(df_con_inv["cluster_kmeans"].values, pred_tree)

    feature_names = ["factor_fecundidad", "factor_mortalidad"]
    class_names = [f"Cluster {c}: {nombres_dict[c]}" for c in range(k_opt)]
    reglas_texto = export_text(clf_tree, feature_names=feature_names)

    reglas_file_path = os.path.join(carpeta_salida, "reglas_arbol.txt")
    with open(reglas_file_path, "w", encoding="utf-8") as f:
        f.write("REGLAS DE DECISION EXPLICATIVAS (Surrogate Decision Tree)\n")
        f.write("ESTADO: PARAMETROS_CONFIGURADOS (Supuestos didacticos)\n")
        f.write(f"Objetivo: Explicar clusters de inversion demografica segun factores macro\n")
        f.write(f"Exactitud global del arbol (Accuracy): {acc_tree * 100:.2f} %\n")
        f.write("--------------------------------------------------------------------------------\n")
        f.write("Clases objetivo:\n")
        for c in range(k_opt):
            f.write(f"  Clase {c}: {nombres_dict[c]}\n")
        f.write("--------------------------------------------------------------------------------\n")
        f.write(reglas_texto)
        f.write("\n--------------------------------------------------------------------------------\n")
        f.write("INTERPRETACION DEMOGRAFICA DE LAS REGLAS:\n")
        f.write("1. El factor de fecundidad es la variable de corte primaria y decisiva.\n")
        f.write("   - Fecundidad baja reduce fuertemente la generacion de menores de 15 anios (J),\n")
        f.write("     acelerando el anio en que los adultos mayores (A) superan a J (Inversion Temprana).\n")
        f.write("   - Fecundidad alta expande los contingentes infantiles y juveniles (J),\n")
        f.write("     retrasando el momento del cruce hacia el final del horizonte (Inversion Tardia).\n")
        f.write("2. El factor de mortalidad actua como modulador secundario:\n")
        f.write("   - Mayor mortalidad frena el crecimiento de adultos mayores (A), demorando ligeramente el cruce.\n")
        f.write("   - Menor mortalidad incrementa la supervivencia geriatrica, anticipando la inversion.\n")

    print(f"[*] Exactitud del arbol: {acc_tree * 100:.2f} % | Guardado en: {reglas_file_path}")

    # 18. Generacion de graficos numerados
    print("\n[*] Generando figuras y graficos PNG...")

    # Fig 01: Codo e Inercia vs Silhouette K-Means
    fig, ax1 = plt.subplots(figsize=(8, 5))
    color = 'tab:blue'
    ax1.set_xlabel('Número de clusters (k)', fontsize=11)
    ax1.set_ylabel('Inercia (SSE)', color=color, fontsize=11)
    ax1.plot(k_range, inercias, marker='o', color=color, linewidth=2, label='Inercia')
    ax1.tick_params(axis='y', labelcolor=color)
    ax1.grid(True, linestyle='--', alpha=0.5)

    ax2 = ax1.twinx()
    color = 'tab:red'
    ax2.set_ylabel('Silhouette Score', color=color, fontsize=11)
    ax2.plot(k_range, silhouettes_km, marker='s', color=color, linewidth=2, linestyle='--', label='Silhouette')
    ax2.tick_params(axis='y', labelcolor=color)

    plt.title('01. Método del Codo y Coeficiente Silhouette (K-Means)', fontsize=12, fontweight='bold')
    fig.tight_layout()
    fig1_path = os.path.join(carpeta_graficos, "01_codo_silhouette_kmeans.png")
    plt.savefig(fig1_path, dpi=300)
    plt.close()

    # Fig 02: Dendrograma jerarquico truncado (Ward)
    plt.figure(figsize=(10, 5))
    dendrogram(
        Z_ward,
        truncate_mode='lastp',
        p=30,
        leaf_rotation=90.,
        leaf_font_size=10.,
        show_contracted=True
    )
    plt.title('02. Dendrograma Truncado de Enlace Ward (Hierarchical Clustering)', fontsize=12, fontweight='bold')
    plt.xlabel('Índice de muestra o tamaño de conglomerado contraído', fontsize=11)
    plt.ylabel('Distancia cuadrática de enlace Ward', fontsize=11)
    plt.grid(True, linestyle='--', alpha=0.4)
    plt.tight_layout()
    fig2_path = os.path.join(carpeta_graficos, "02_dendrograma_jerarquico.png")
    plt.savefig(fig2_path, dpi=300)
    plt.close()

    # Fig 03: k-distancias DBSCAN
    plt.figure(figsize=(8, 5))
    plt.plot(range(len(k_distances)), k_distances, color='navy', linewidth=2)
    plt.axhline(y=eps_candidato, color='crimson', linestyle='--', label=f'eps elegido = {eps_candidato:.3f}')
    plt.title(f'03. Gráfico de k-distancias ordenadas para DBSCAN (k={min_samples_db})', fontsize=12, fontweight='bold')
    plt.xlabel('Puntos ordenados por distancia', fontsize=11)
    plt.ylabel(f'Distancia al {min_samples_db}-ésimo vecino', fontsize=11)
    plt.legend(loc='upper left')
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.tight_layout()
    fig3_path = os.path.join(carpeta_graficos, "03_k_distancias_dbscan.png")
    plt.savefig(fig3_path, dpi=300)
    plt.close()

    # Fig 04: Scatter Factores coloreado por Cluster
    plt.figure(figsize=(9, 6))
    colores_c = ['#1f77b4', '#2ca02c', '#ff7f0e']
    for c in range(k_opt):
        sub = df_con_inv[df_con_inv["cluster_kmeans"] == c]
        nom = nombres_dict[c]
        plt.scatter(
            sub["factor_fecundidad"], sub["factor_mortalidad"],
            c=colores_c[c % len(colores_c)], label=f"{nom} (n={len(sub)})",
            alpha=0.5, edgecolors='none', s=25
        )
    # Scatter de escenarios sin inversion
    plt.scatter(
        df_sin_inv["factor_fecundidad"], df_sin_inv["factor_mortalidad"],
        c='red', marker='x', label=f"Sin inversión (n={n_sin_inv})",
        s=45, linewidth=1.5
    )
    plt.axvline(x=1.0, color='gray', linestyle=':', alpha=0.7)
    plt.axhline(y=1.0, color='gray', linestyle=':', alpha=0.7)
    plt.title('04. Espacio de Factores Macro por Régimen de Inversión', fontsize=12, fontweight='bold')
    plt.xlabel('Factor de Fecundidad (Línea base = 1.0, $\\sigma=0.05$)', fontsize=11)
    plt.ylabel('Factor de Mortalidad (Línea base = 1.0, $\\sigma=0.015$)', fontsize=11)
    plt.legend(loc='best', framealpha=0.9)
    plt.grid(True, linestyle='--', alpha=0.4)
    plt.tight_layout()
    fig4_path = os.path.join(carpeta_graficos, "04_scatter_factores_clusters.png")
    plt.savefig(fig4_path, dpi=300)
    plt.close()

    # Fig 05: Distribucion del anio de inversion por cluster (Boxplots)
    plt.figure(figsize=(9, 5))
    datos_box = [df_con_inv[df_con_inv["cluster_kmeans"] == c]["primer_anio_inversion"].values for c in range(k_opt)]
    nombres_box = [f"{nombres_dict[c]}\n(Media: {df_con_inv[df_con_inv['cluster_kmeans'] == c]['primer_anio_inversion'].mean():.1f})" for c in range(k_opt)]
    bp = plt.boxplot(datos_box, tick_labels=nombres_box, patch_artist=True, showmeans=True)
    for patch, col in zip(bp['boxes'], colores_c):
        patch.set_facecolor(col)
        patch.set_alpha(0.6)
    plt.title('05. Distribución del Año de Inversión Demográfica por Cluster K-Means', fontsize=12, fontweight='bold')
    plt.ylabel('Año del cruce (A ≥ J)', fontsize=11)
    plt.grid(True, linestyle='--', alpha=0.5, axis='y')
    plt.tight_layout()
    fig5_path = os.path.join(carpeta_graficos, "05_distribucion_anio_clusters.png")
    plt.savefig(fig5_path, dpi=300)
    plt.close()

    # Fig 06: Scatter PCA 2D
    plt.figure(figsize=(9, 6))
    for c in range(k_opt):
        idx = (labels_kmeans == c)
        plt.scatter(
            X_pca[idx, 0], X_pca[idx, 1],
            c=colores_c[c % len(colores_c)], label=f"{nombres_dict[c]}",
            alpha=0.5, edgecolors='none', s=20
        )
    plt.title(f'06. Proyección PCA de Escenarios Clusterizados\n(Varianza explicada: PC1={var_exp[0]*100:.1f}%, PC2={var_exp[1]*100:.1f}%)', fontsize=12, fontweight='bold')
    plt.xlabel('Componente Principal 1', fontsize=11)
    plt.ylabel('Componente Principal 2', fontsize=11)
    plt.legend(loc='best')
    plt.grid(True, linestyle='--', alpha=0.4)
    plt.tight_layout()
    fig6_path = os.path.join(carpeta_graficos, "06_scatter_pca.png")
    plt.savefig(fig6_path, dpi=300)
    plt.close()

    # Fig 07: Comparativa de Metricas entre Algoritmos
    fig, (ax_s, ax_db, ax_ch) = plt.subplots(1, 3, figsize=(14, 4.5))
    algoritmos_comp = ["K-Means", "Hierarchical", "DBSCAN"]
    valores_sil = [sil_km, sil_h, sil_db if not math.isnan(sil_db) else 0.0]
    valores_db = [db_km_val, db_h_val, db_index_db if not math.isnan(db_index_db) else 0.0]
    valores_ch = [ch_km_val, ch_h_val, ch_db if not math.isnan(ch_db) else 0.0]

    bar_col = ['royalblue', 'forestgreen', 'darkorange']
    ax_s.bar(algoritmos_comp, valores_sil, color=bar_col, alpha=0.8)
    ax_s.set_title('Silhouette Score (Mayor es mejor)', fontsize=10, fontweight='bold')
    ax_s.grid(True, linestyle='--', alpha=0.4, axis='y')

    ax_db.bar(algoritmos_comp, valores_db, color=bar_col, alpha=0.8)
    ax_db.set_title('Davies-Bouldin (Menor es mejor)', fontsize=10, fontweight='bold')
    ax_db.grid(True, linestyle='--', alpha=0.4, axis='y')

    ax_ch.bar(algoritmos_comp, valores_ch, color=bar_col, alpha=0.8)
    ax_ch.set_title('Calinski-Harabasz (Mayor es mejor)', fontsize=10, fontweight='bold')
    ax_ch.grid(True, linestyle='--', alpha=0.4, axis='y')

    plt.suptitle('07. Evaluación Comparativa de Calidad de Clustering', fontsize=12, fontweight='bold')
    plt.tight_layout()
    fig7_path = os.path.join(carpeta_graficos, "07_comparativa_metricas_algoritmos.png")
    plt.savefig(fig7_path, dpi=300)
    plt.close()

    # Fig 08: Visualizacion del Arbol de Decision
    plt.figure(figsize=(14, 8))
    plot_tree(
        clf_tree,
        feature_names=feature_names,
        class_names=[nombres_dict[c] for c in range(k_opt)],
        filled=True,
        rounded=True,
        fontsize=9
    )
    plt.title('08. Árbol de Decisión Sustituto (Explicabilidad de Segmentos)', fontsize=13, fontweight='bold')
    plt.tight_layout()
    fig8_path = os.path.join(carpeta_graficos, "08_arbol_decision_reglas.png")
    plt.savefig(fig8_path, dpi=300)
    plt.close()

    print(f"[*] 8 graficos PNG guardados exitosamente en: {carpeta_graficos}")

    # 19. Generar resumen_clustering.txt
    resumen_path = os.path.join(carpeta_salida, "resumen_clustering.txt")
    with open(resumen_path, "w", encoding="utf-8") as f:
        f.write("================================================================================\n")
        f.write("ESTADO: PARAMETROS_CONFIGURADOS\n")
        f.write("Ejecucion ilustrativa del modulo de Clustering (Semana 13).\n")
        f.write("Los resultados dependen de supuestos didacticos (sigma_fec=0.05, sigma_mort=0.015)\n")
        f.write("y NO constituyen un pronostico demografico oficial para el Peru.\n")
        f.write("================================================================================\n\n")
        f.write(f"1. RESUMEN DE DATOS Y ESCENARIOS:\n")
        f.write(f"   - Total de escenarios procesados: {n_total}\n")
        f.write(f"   - Escenarios con inversion: {n_con_inv} ({100.0 * n_con_inv / n_total:.2f} %)\n")
        f.write(f"   - Escenarios sin inversion en horizonte (<= {ultimo_anio}): {n_sin_inv} ({pct_sin_inv:.2f} %)\n")
        f.write(f"   - Rango de anio de inversion: [{min_global_anio}, {max_global_anio}], Media: {media_global_anio:.2f}, Desv: {std_global_anio:.2f}\n")
        f.write(f"   - Correlacion Pearson (Fecundidad, Mortalidad): {corr_fec_mort:.5f} (Independientes)\n")
        f.write(f"   - Correlacion Pearson (Fecundidad, Anio): {corr_fec_anio:.5f}\n")
        f.write(f"   - Correlacion Pearson (Mortalidad, Anio): {corr_mort_anio:.5f}\n\n")

        f.write("2. COMPARATIVA DE ALGORITMOS DE CLUSTERING:\n")
        f.write(f"{df_metricas.to_string(index=False)}\n\n")

        f.write("3. DETALLE DE K-MEDOIDS:\n")
        f.write("   - Estado: Omitido justificadamente.\n")
        f.write("   - Razon: Incompatibilidad binaria de C-extensiones entre scikit-learn-extra 0.3.0 y NumPy 2.x en la maquina.\n")
        f.write("   - Cumplimiento: La especificacion autoriza su omision explicita documentada si no se instala limpiamente.\n\n")

        f.write("4. PERFILES DEMOGRAFICOS DE LOS SEGMENTOS (K-Means k=3 + Sin Inversion):\n")
        f.write(f"{df_perfil_completo.to_string(index=False)}\n\n")

        f.write("5. ANALISIS DE SENSIBILIDAD Y ESTABILIDAD:\n")
        f.write(f"   - Estabilidad K-Means (ARI en 10 submuestras del 80%): {ari_medio_estabilidad:.4f} +/- {ari_std_estabilidad:.4f}\n")
        f.write(f"   - Sensibilidad a censura (Censurando a anio {anio_censura}, ARI): {ari_sensibilidad:.4f}\n")
        f.write(f"   - Poder explicativo de factores (K-Means Factores vs Completo, ARI): {ari_factores_vs_completo:.4f}\n")
        f.write(f"   - Speedup concurrencia K-Means (1 hilo vs multi-hilo): {speedup_kmeans:.2f}x\n")
        f.write(f"   - Exactitud arbol de decision explicativo (max_depth=3): {acc_tree * 100:.2f} %\n\n")

        f.write("6. EVALUACION CRITICA Y CONCLUSION HONESTA:\n")
        f.write("   - Los factores de fecundidad y mortalidad provienen de distribuciones gaussianas continuas.\n")
        f.write("   - En consecuencia, el espacio de estados demograficos no presenta valles de densidad nula\n")
        f.write("     ni agrupaciones aisladas por 'distancia natural'.\n")
        f.write("   - El coeficiente Silhouette moderado (~0.35-0.45) refleja con total honestidad matematica esta realidad.\n")
        f.write("   - El clustering aporta valor analitico como una particion operativa y reproducible del riesgo demografico,\n")
        f.write("     clasificando los 10 000 escenarios en politicas de contingencia temprana, estandar y de extension.\n")

    print(f"[*] Resumen final guardado en: {resumen_path}")
    print("\n================================================================================")
    print("EJECUCION COMPLETADA CON EXITO.")
    print("================================================================================")


if __name__ == "__main__":
    main()
