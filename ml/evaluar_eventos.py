#!/usr/bin/env python3
"""
evaluar_eventos.py - Curva ROC y matriz de confusion del evento
"PM2,5 a 1 h > umbral" (RET-06) con filtro causal opcional (RET-07 / M-08).

Replica el pipeline descrito en la seccion 4.5 del informe:
  - lecturas crudas -> promedio de 5 min -> interpolacion de huecos <= 10 min
  - caracteristicas: lag3, lag6, lag12, media y desv. estandar movil (12 pasos),
    temperatura, humedad, presion, hora codificada con seno y coseno
  - objetivo: delta = PM2,5(t+12) - PM2,5(t)  (12 pasos de 5 min = 1 h)
  - validacion: TimeSeriesSplit de 4 bloques con gap de 12 pasos

Convierte la regresion en clasificacion: puntaje = PM2,5(t) + delta_predicho;
evento real = PM2,5(t+1 h) > umbral. Las predicciones de los 4 bloques de
prueba se juntan (out-of-fold) para trazar una sola ROC por modelo.

Uso (base de datos, credenciales por variables de entorno, como en el .env):
    python ml/evaluar_eventos.py --base telemetria_iot6
    python ml/evaluar_eventos.py --base telemetria_iot6 --filtro 3
    python ml/evaluar_eventos.py --base telemetria_iot6 --umbral 35

Uso (CSV con columnas timestamp,pm2_5,pm10,temperatura,humedad,presion):
    python ml/evaluar_eventos.py --csv datos.csv

Salidas en ml/resultados/ (o --salida): roc_*.png, confusion_*.png,
metricas_*.csv, metricas_por_bloque_*.csv.

IMPORTANTE: los hiperparametros de MODELOS son los descritos en el informe
(MLP 16-8, alpha=1,0) o valores por defecto razonables. Ajustalos a los de
ml/entrenar.py para que los resultados sean comparables con P-12.
"""
import argparse
import os
import warnings
from dotenv import load_dotenv

# Carga automática del archivo .env ubicado en la raíz del proyecto
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../.env'))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import (average_precision_score, confusion_matrix,
                             roc_auc_score, roc_curve)
from sklearn.model_selection import TimeSeriesSplit
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

PASOS = 12          # 12 pasos de 5 min = 1 h
N_BLOQUES = 4
MIN_EVENTOS_AVISO = 10

# Ajustar a los valores usados en ml/entrenar.py
MODELOS = {
    "Ridge": lambda: make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
    "GBR": lambda: GradientBoostingRegressor(random_state=0),
    "RF": lambda: RandomForestRegressor(n_estimators=200, min_samples_leaf=5,
                                        random_state=0, n_jobs=-1),
    "MLP": lambda: make_pipeline(
        StandardScaler(),
        MLPRegressor(hidden_layer_sizes=(16, 8), alpha=1.0, max_iter=800,
                     random_state=0)),
}


# --------------------------------------------------------------------------
# Datos
# --------------------------------------------------------------------------
def cargar(args):
    cols = "timestamp, pm2_5, pm10, temperatura, humedad, presion"
    if args.csv:
        df = pd.read_csv(args.csv, parse_dates=["timestamp"])
        return df[["timestamp", "pm2_5", "pm10", "temperatura",
                   "humedad", "presion"]]
    import pymysql  # import tardio: no se necesita con --csv
    
    # Soporta de forma robusta las variables DB_USER, MYSQL_USER, DB_PASSWORD y DB_PASS
    db_user = os.getenv("DB_USER", os.getenv("MYSQL_USER", "root"))
    db_pass = os.getenv("DB_PASSWORD", os.getenv("DB_PASS", ""))
    
    conn = pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=db_user,
        password=db_pass,
        database=args.base,
    )
    try:
        sql = f"SELECT {cols} FROM lecturas_raw"
        params = []
        if args.nodo is not None:
            sql += " WHERE nodo_id = %s"
            params.append(args.nodo)
        sql += " ORDER BY timestamp"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return pd.read_sql(sql, conn, params=params,
                               parse_dates=["timestamp"])
    finally:
        conn.close()


def preparar(df, filtro):
    """Devuelve (X, y_delta, pm_actual, pm_futuro) alineados y sin NaN.

    El filtro (media movil causal de `filtro` pasos) solo se aplica a las
    ENTRADAS. El actual y el futuro, y por tanto el evento real, se toman
    siempre del PM2,5 sin filtrar.
    """
    s = (df.set_index("timestamp").sort_index()
           .resample("5min").mean(numeric_only=True))
    s = s.interpolate(limit=2, limit_area="inside")  # huecos <= 10 min

    pm = s["pm2_5"]
    pm_in = pm.rolling(filtro, min_periods=filtro).mean() if filtro > 1 else pm

    X = pd.DataFrame(index=s.index)
    X["lag3"] = pm_in.shift(3)
    X["lag6"] = pm_in.shift(6)
    X["lag12"] = pm_in.shift(12)
    X["pm_now"] = pm_in
    X["media12"] = pm_in.rolling(12).mean()
    X["std12"] = pm_in.rolling(12).std()
    X["temperatura"] = s["temperatura"]
    X["humedad"] = s["humedad"]
    X["presion"] = s["presion"]
    hora = s.index.hour + s.index.minute / 60.0
    X["hora_sin"] = np.sin(2 * np.pi * hora / 24)
    X["hora_cos"] = np.cos(2 * np.pi * hora / 24)

    futuro = pm.shift(-PASOS)
    datos = X.assign(pm_actual=pm, pm_futuro=futuro).dropna()
    y_delta = datos["pm_futuro"] - datos["pm_actual"]
    return (datos.drop(columns=["pm_actual", "pm_futuro"]), y_delta,
            datos["pm_actual"].to_numpy(), datos["pm_futuro"].to_numpy())


# --------------------------------------------------------------------------
# Metricas
# --------------------------------------------------------------------------
def metricas_clasificacion(y_ev, score, umbral_score):
    pred = score > umbral_score
    tn, fp, fn, tp = confusion_matrix(y_ev, pred, labels=[False, True]).ravel()
    div = lambda a, b: a / b if b else np.nan
    return {
        "TN": tn, "FP": fp, "FN": fn, "TP": tp,
        "precision": div(tp, tp + fp),
        "recall_TPR": div(tp, tp + fn),
        "FPR": div(fp, fp + tn),
        "F1": div(2 * tp, 2 * tp + fp + fn),
        "exactitud": div(tp + tn, tp + tn + fp + fn),
    }


def evaluar(X, y_delta, actual, futuro, umbral):
    y_ev = futuro > umbral
    tscv = TimeSeriesSplit(n_splits=N_BLOQUES, gap=PASOS)
    nombres = ["Persistencia"] + list(MODELOS)
    oof = {n: np.full(len(X), np.nan) for n in nombres}
    bloque = np.full(len(X), -1)
    por_bloque = []

    for k, (tr, te) in enumerate(tscv.split(X), start=1):
        bloque[te] = k
        oof["Persistencia"][te] = actual[te]  # supone cambio cero
        for nombre, fabrica in MODELOS.items():
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # MLP sin converger
                m = fabrica().fit(X.iloc[tr], y_delta.iloc[tr])
                delta = m.predict(X.iloc[te])
            oof[nombre][te] = actual[te] + delta
        for n in nombres:
            ev = y_ev[te]
            auc = (roc_auc_score(ev, oof[n][te])
                   if 0 < ev.sum() < len(ev) else np.nan)
            por_bloque.append({"modelo": n, "bloque": k, "n": len(te),
                               "eventos": int(ev.sum()), "AUC": auc})

    mask = bloque > 0
    return y_ev, mask, oof, pd.DataFrame(por_bloque)


# --------------------------------------------------------------------------
# Graficos
# --------------------------------------------------------------------------
def graficar_roc(y, mask, oof, umbral, etiqueta, ruta):
    fig, ax = plt.subplots(figsize=(6, 5.5))
    for n, sc in oof.items():
        fpr, tpr, _ = roc_curve(y[mask], sc[mask])
        auc = roc_auc_score(y[mask], sc[mask])
        ax.plot(fpr, tpr, lw=2 if n == "Ridge" else 1.4,
                label=f"{n} (AUC = {auc:.2f})")
    ax.plot([0, 1], [0, 1], "k--", lw=1, label="Azar")
    ax.set(xlabel="Tasa de falsos positivos (FPR)",
           ylabel="Tasa de verdaderos positivos (TPR)",
           title=f"ROC: evento PM2,5(t+1 h) > {umbral:g} µg/m³ {etiqueta}",
           xlim=(0, 1), ylim=(0, 1.02))
    ax.legend(loc="lower right")
    ax.grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(ruta, dpi=200)
    plt.close(fig)


def graficar_confusion(filas, ruta, umbral, etiqueta):
    n = len(filas)
    fig, axs = plt.subplots(1, n, figsize=(3.1 * n, 3.4))
    for ax, (nombre, m) in zip(np.atleast_1d(axs), filas):
        cm = np.array([[m["TN"], m["FP"]], [m["FN"], m["TP"]]])
        ax.imshow(cm, cmap="Blues")
        for i in range(2):
            for j in range(2):
                ax.text(j, i, int(cm[i, j]), ha="center", va="center",
                        color="white" if cm[i, j] > cm.max() / 2 else "black",
                        fontsize=13)
        ax.set(xticks=[0, 1], yticks=[0, 1],
               xticklabels=["No evento", "Evento"],
               yticklabels=["No evento", "Evento"],
               xlabel="Predicho", ylabel="Real", title=nombre)
    fig.suptitle(f"Matriz de confusión (predicho > {umbral:g} µg/m³) {etiqueta}",
                 y=1.02)
    fig.tight_layout()
    fig.savefig(ruta, dpi=200, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--base", default="telemetria_iot6", help="base MariaDB")
    ap.add_argument("--csv", help="leer de CSV en vez de MariaDB")
    ap.add_argument("--nodo", type=int, help="filtrar por nodo_id")
    ap.add_argument("--umbral", type=float, default=50.0,
                    help="umbral del evento en µg/m³ (defecto 50)")
    ap.add_argument("--filtro", type=int, default=1,
                    help="ventana de la media móvil causal en pasos de 5 min "
                         "(1 = sin filtro)")
    ap.add_argument("--salida", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "resultados"))
    args = ap.parse_args()
    os.makedirs(args.salida, exist_ok=True)

    etiqueta = f"con filtro {args.filtro}" if args.filtro > 1 else "sin filtro"
    sufijo = f"f{args.filtro}_u{args.umbral:g}"

    df = cargar(args)
    X, y_delta, actual, futuro = preparar(df, args.filtro)
    y_ev, mask, oof, por_bloque = evaluar(X, y_delta, actual, futuro,
                                          args.umbral)

    n_ev = int(y_ev[mask].sum())
    print(f"Filas útiles: {len(X)} | filas de prueba (4 bloques): "
          f"{int(mask.sum())} | eventos (> {args.umbral:g}): {n_ev} "
          f"({100 * n_ev / mask.sum():.1f} %)")
    if n_ev < MIN_EVENTOS_AVISO or (~y_ev[mask]).sum() < MIN_EVENTOS_AVISO:
        print(f"AVISO: menos de {MIN_EVENTOS_AVISO} eventos en alguna clase; "
              "la ROC no es concluyente. Considera un umbral menor "
              "(p. ej. --umbral 35) y decláralo como umbral interno.")
        if n_ev == 0 or n_ev == mask.sum():
            raise SystemExit("Solo hay una clase: no se puede calcular ROC.")

    filas, graf = [], []
    for n, sc in oof.items():
        y, s = y_ev[mask], sc[mask]
        fpr, tpr, thr = roc_curve(y, s)
        j = np.argmax(tpr - fpr)                    # índice de Youden
        base = {"modelo": n, "AUC": roc_auc_score(y, s),
                "AP": average_precision_score(y, s)}
        m_fijo = metricas_clasificacion(y, s, args.umbral)
        m_opt = metricas_clasificacion(y, s, thr[j])
        filas.append({**base, "criterio": f"umbral fijo {args.umbral:g}",
                      "umbral_score": args.umbral, **m_fijo})
        filas.append({**base, "criterio": "Youden (optimista)",
                      "umbral_score": thr[j], **m_opt})
        graf.append((n, m_fijo))

    tabla = pd.DataFrame(filas)
    tabla.to_csv(os.path.join(args.salida, f"metricas_{sufijo}.csv"),
                 index=False, float_format="%.4f")
    por_bloque.to_csv(os.path.join(args.salida,
                                   f"metricas_por_bloque_{sufijo}.csv"),
                      index=False, float_format="%.4f")
    graficar_roc(y_ev, mask, oof, args.umbral, etiqueta,
                 os.path.join(args.salida, f"roc_{sufijo}.png"))
    graficar_confusion(graf, os.path.join(args.salida,
                                          f"confusion_{sufijo}.png"),
                       args.umbral, etiqueta)

    pd.set_option("display.width", 200)
    print("\nMétricas agrupadas (out-of-fold):")
    print(tabla.round(3).to_string(index=False))
    print("\nAUC por bloque (NaN = bloque sin ambas clases):")
    print(por_bloque.pivot(index="modelo", columns="bloque",
                           values="AUC").round(3).to_string())
    print(f"\nArchivos guardados en {args.salida}")
    print("Nota: el umbral de Youden se elige con los mismos datos que se "
          "evalúan, por lo que es optimista; reporta el umbral fijo como "
          "resultado principal.")


if __name__ == "__main__":
    main()