"""Entrena y evalua modelos de PM2.5 a 1 h contra la linea base (persistencia).

Evaluacion: validacion cruzada temporal (TimeSeriesSplit) con MAE, RMSE y R2.
Seleccion del mejor modelo por RMSE promedio. Incluye analisis por situacion
(PM2.5 estable vs cambio brusco en la hora siguiente).

Al final guarda en la tabla 'predicciones' las predicciones FUERA DE MUESTRA de la
validacion cruzada (modelos *_cv_<VERSION>), que son las unicas sin sesgo para graficar.
"""
from datetime import timedelta

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.neural_network import MLPRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from comun import NODO, PASOS_ADELANTE, cargar, conectar, construir

VERSION = "v3"              # cambiar a v4, v5... al reentrenar
N_FOLDS = 4
PERCENTIL_BRUSCO = 0.80     # el 20 % de casos con mayor |cambio| se considera "cambio brusco"

datos = construir(cargar())
cols = [c for c in datos.columns if c != "futuro"]
n = len(datos)
print(f"Filas utiles: {n} ({datos.index.min()} -> {datos.index.max()})")
if n < 300:
    print("AVISO: muy pocos datos, los resultados no son confiables.")

delta = lambda d: d["futuro"] - d["pm25"]              # se predice el CAMBIO respecto a ahora


def crear_modelos():
    """Modelos nuevos en cada llamada, para no arrastrar entrenamiento entre folds."""
    return {
        "ridge": make_pipeline(StandardScaler(), Ridge(alpha=10.0)),
        "gbr": GradientBoostingRegressor(n_estimators=150, max_depth=2, learning_rate=0.05, subsample=0.8, random_state=0),
        "rf": RandomForestRegressor(n_estimators=200, max_depth=4, min_samples_leaf=10, random_state=0, n_jobs=-1),
        "mlp": make_pipeline(StandardScaler(), MLPRegressor(
            hidden_layer_sizes=(16, 8), alpha=1.0, max_iter=800, random_state=0)),
    }

def metricas(real_abs, pred_abs, pm25_actual):
    """MAE y RMSE sobre el valor absoluto; R2 sobre el valor absoluto y sobre el delta."""
    real_d, pred_d = real_abs - pm25_actual, pred_abs - pm25_actual
    return {
        "mae": mean_absolute_error(real_abs, pred_abs),
        "rmse": np.sqrt(mean_squared_error(real_abs, pred_abs)),
        "r2": r2_score(real_abs, pred_abs),
        "r2_delta": r2_score(real_d, pred_d),
    }


def guardar_cv(oof, nombres_modelos):
    """Guarda en 'predicciones' las predicciones fuera de muestra de la validacion cruzada."""
    conn = conectar(escritura=True)
    try:
        with conn.cursor() as cur:
            for nombre in nombres_modelos:
                modelo = f"{nombre}_cv_{VERSION}"
                cur.execute("DELETE FROM predicciones WHERE nodo_id=%s AND variable='pm2_5' "
                            "AND modelo=%s", (NODO, modelo))          # permite volver a ejecutar
                filas = [((t + timedelta(minutes=5 * PASOS_ADELANTE)).to_pydatetime(),
                          NODO, "pm2_5", float(v), modelo) for t, v in oof[nombre].items()]
                cur.executemany("INSERT INTO predicciones (timestamp, nodo_id, variable, "
                                "valor_predicho, modelo) VALUES (%s,%s,%s,%s,%s)", filas)
        print(f"Guardadas predicciones fuera de muestra (*_cv_{VERSION}) en 'predicciones'.")
    finally:
        conn.close()


# ---------------------------------------------------------------- validacion cruzada temporal
tscv = TimeSeriesSplit(n_splits=N_FOLDS, gap=PASOS_ADELANTE)   # gap: no filtra el futuro al entrenar
nombres = ["persistencia", "ridge", "gbr", "rf", "mlp"]
folds = {k: [] for k in nombres}   # metricas por fold
oof = []  # predicciones fuera de muestra

print(f"\nValidacion cruzada temporal: {N_FOLDS} folds")
for i, (idx_tr, idx_te) in enumerate(tscv.split(datos), 1):
    train, test = datos.iloc[idx_tr], datos.iloc[idx_te]
    print(f"  fold {i}: entrena {len(train):>5} filas | prueba {len(test):>4} filas "
          f"({test.index.min()} -> {test.index.max()})")

    preds = {"persistencia": test["pm25"].copy()}
    for nombre, m in crear_modelos().items():
        m.fit(train[cols], delta(train))
        preds[nombre] = np.clip(test["pm25"] + m.predict(test[cols]), 0, None)

    for nombre in nombres:
        folds[nombre].append(metricas(test["futuro"], preds[nombre], test["pm25"]))

    tabla = pd.DataFrame({"real": test["futuro"], "pm25": test["pm25"], **preds})
    tabla["fold"] = i
    oof.append(tabla)

# ---------------------------------------------------------------- resultados por fold y promedio
resumen = {}
for nombre in nombres:
    df = pd.DataFrame(folds[nombre])
    resumen[nombre] = {"media": df.mean(), "std": df.std()}

print("\nRMSE por fold (ug/m3, a 1 hora)")
print(f"{'modelo':<14}" + "".join(f"{'f' + str(i):>8}" for i in range(1, N_FOLDS + 1)))
for nombre in nombres:
    print(f"{nombre:<14}" + "".join(f"{f['rmse']:>8.2f}" for f in folds[nombre]))

print("\nPromedio de los folds (± desviacion entre folds)")
print(f"{'modelo':<14}{'MAE':>14}{'RMSE':>14}{'R2':>14}{'R2 delta':>14}")
for nombre in nombres:
    mu, sd = resumen[nombre]["media"], resumen[nombre]["std"]
    print(f"{nombre:<14}"
          f"{mu['mae']:>8.2f}±{sd['mae']:<5.2f}"
          f"{mu['rmse']:>8.2f}±{sd['rmse']:<5.2f}"
          f"{mu['r2']:>8.2f}±{sd['r2']:<5.2f}"
          f"{mu['r2_delta']:>8.2f}±{sd['r2_delta']:<5.2f}")
print("(R2 delta mide cuanto del CAMBIO explica el modelo; persistencia predice cambio 0)")

# ---------------------------------------------------------------- analisis por situacion
oof = pd.concat(oof)
cambio = (oof["real"] - oof["pm25"]).abs()
umbral = cambio.quantile(PERCENTIL_BRUSCO)
oof["situacion"] = np.where(cambio >= umbral, "cambio brusco", "estable")

print(f"\nAnalisis por situacion (predicciones fuera de muestra, umbral |cambio| >= {umbral:.1f} ug/m3)")
print("Nota: la situacion se define con el valor real; es solo diagnostico, no algo que el modelo conozca.")
print(f"{'situacion':<16}{'modelo':<14}{'casos':>7}{'MAE':>8}{'RMSE':>8}")
for sit in ("estable", "cambio brusco"):
    sub = oof[oof["situacion"] == sit]
    for nombre in nombres:
        mae = mean_absolute_error(sub["real"], sub[nombre])
        rmse = np.sqrt(mean_squared_error(sub["real"], sub[nombre]))
        print(f"{sit:<16}{nombre:<14}{len(sub):>7}{mae:>8.2f}{rmse:>8.2f}")

# ---------------------------------------------------------------- seleccion por RMSE
candidatos = [k for k in nombres if k != "persistencia"]
mejor = min(candidatos, key=lambda k: resumen[k]["media"]["rmse"])
base = resumen["persistencia"]["media"]
mu = resumen[mejor]["media"]
mejora_rmse = 100 * (1 - mu["rmse"] / base["rmse"])
mejora_mae = 100 * (1 - mu["mae"] / base["mae"])
print(f"\nMejor por RMSE: {mejor} ({mejora_rmse:+.1f}% de RMSE y {mejora_mae:+.1f}% de MAE "
      f"respecto a persistencia)")

folds_ganados = sum(f["rmse"] < p["rmse"] for f, p in zip(folds[mejor], folds["persistencia"]))
print(f"Supera a la persistencia en RMSE en {folds_ganados} de {N_FOLDS} folds.")
if mejora_rmse <= 0:
    print("No supera a la persistencia: con tan pocos datos es esperable. Reentrenar con mas dias.")
elif folds_ganados < N_FOLDS:
    print("La mejora no es consistente entre folds: tomarla con cautela hasta tener mas datos.")

# ---------------------------------------------------------------- modelos finales
finales = {
    f"{nombre}_{VERSION}": m.fit(datos[cols], delta(datos))
    for nombre, m in crear_modelos().items()
}
joblib.dump({
    "modelos": finales,
    "mejor": f"{mejor}_{VERSION}",
    "features": cols,
}, "modelo.joblib")
print(f"Guardados {len(finales)} modelos en modelo.joblib (mejor: {mejor}_{VERSION})")

# ---------------------------------------------------------------- predicciones sin sesgo para el panel
try:
    guardar_cv(oof, candidatos)
except Exception as e:      # el modelo ya quedo guardado; esto solo afecta al grafico
    print(f"No se pudieron guardar las predicciones del panel: {e}")
    print("Revisa DB_W_USER/DB_W_PASS en ml/.env y que ml_writer tenga INSERT, SELECT y DELETE "
          "sobre 'predicciones'.")