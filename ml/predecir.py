"""Genera predicciones de PM2.5 a 1 h y las guarda en la tabla 'predicciones'.

  python predecir.py                # una vez cada 5 min, en bucle
  python predecir.py --una-vez      # una sola prediccion
  python predecir.py --backfill 48  # predicciones de las ultimas 48 h (solo para ver el grafico)
"""
import argparse
import time
from datetime import datetime, timedelta, timezone

import joblib
import numpy as np

from comun import NODO, PASOS_ADELANTE, cargar, conectar, construir

ap = argparse.ArgumentParser()
ap.add_argument("--una-vez", action="store_true")
ap.add_argument("--backfill", type=int, default=0, help="horas hacia atras")
args = ap.parse_args()

paquete = joblib.load("modelo.joblib")
cols = paquete["features"]
# Soporta tanto el formato nuevo (varios modelos) como el antiguo (un solo modelo)
modelos = paquete.get("modelos") or {paquete["nombre"]: paquete["modelo"]}


def predecir(modelo, X):
    return np.clip(X["pm25"] + modelo.predict(X[cols]), 0, None)


def guardar(filas, nombre):
    """filas: lista de (timestamp_objetivo, valor). Omite las que ya existen."""
    if not filas:
        return 0
    conn = conectar(escritura=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT timestamp FROM predicciones WHERE nodo_id=%s AND variable='pm2_5' "
                        "AND modelo=%s AND timestamp >= %s", (NODO, nombre, min(t for t, _ in filas)))
            existentes = {r[0] for r in cur.fetchall()}
            nuevas = [(t, NODO, "pm2_5", float(v), nombre) for t, v in filas if t not in existentes]
            cur.executemany("INSERT INTO predicciones (timestamp, nodo_id, variable, valor_predicho, modelo) "
                            "VALUES (%s,%s,%s,%s,%s)", nuevas)
        return len(nuevas)
    finally:
        conn.close()


def ciclo():
    if args.backfill:
        X = construir(cargar(args.backfill + 4), con_objetivo=False)
        X = X[X.index >= datetime.utcnow() - timedelta(hours=args.backfill)]
        for nombre, m in modelos.items():
            filas = [((t + timedelta(minutes=5 * PASOS_ADELANTE)).to_pydatetime(), v)
                     for t, v in predecir(m, X).items()]
            n = guardar(filas, nombre + "_backfill")
            print(f"Backfill {nombre}: {n} predicciones nuevas.")
        return

    X = construir(cargar(4), con_objetivo=False)
    if X.empty or datetime.utcnow() - X.index[-1].to_pydatetime() > timedelta(minutes=20):
        print("Sin datos recientes del nodo: no se predice.")
        return
    t = X.index[-1]
    t_obj = (t + timedelta(minutes=5 * PASOS_ADELANTE)).to_pydatetime()
    for nombre, m in modelos.items():
        v = predecir(m, X.iloc[[-1]]).iloc[0]
        n = guardar([(t_obj, v)], nombre)
        print(f"[{t}] {nombre} -> pred a 1 h: {v:.1f} ug/m3 ({'guardada' if n else 'ya existia'})")


if args.una_vez or args.backfill:
    ciclo()
else:
    while True:
        try:
            ciclo()
        except Exception as e:                     # un fallo puntual no debe detener el bucle
            print(f"Error: {e}")
        time.sleep(300)
