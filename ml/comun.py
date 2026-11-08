"""Utilidades compartidas: conexion, carga de datos y construccion de variables."""
import os

import numpy as np
import pandas as pd
import pymysql
from dotenv import load_dotenv

load_dotenv()

NODO = os.getenv("NODO", "N01")
PASOS_ADELANTE = 12                 # 12 pasos de 5 min = prediccion a 1 hora
EXCLUIR = []                        # rangos UTC a ignorar, ej: [("2026-10-29 04:30:00", "2026-10-29 05:10:00")]


def conectar(escritura=False):
    return pymysql.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"), port=int(os.getenv("DB_PORT", "3307")),
        user=os.getenv("DB_W_USER" if escritura else "DB_USER"),
        password=os.getenv("DB_W_PASS" if escritura else "DB_PASS", ""),
        database=os.getenv("DB_NAME", "telemetria_iot6"), charset="utf8mb4", autocommit=True)


def cargar(horas=None):
    """Lecturas promediadas cada 5 min (UTC). Huecos de hasta 10 min se interpolan."""
    sql = ("SELECT timestamp, pm2_5, pm10, temperatura, humedad, presion "
           "FROM lecturas_raw WHERE nodo_id = %s")
    params = [NODO]
    if horas:
        sql += " AND timestamp >= UTC_TIMESTAMP() - INTERVAL %s HOUR"
        params.append(int(horas))
    conn = conectar()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            filas, cols = cur.fetchall(), [d[0] for d in cur.description]
    finally:
        conn.close()
    df = pd.DataFrame(filas, columns=cols)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    for c in cols[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.set_index("timestamp").sort_index()
    for ini, fin in EXCLUIR:
        df = df[(df.index < ini) | (df.index > fin)]
    return df.resample("5min").mean().interpolate(limit=2)


def construir(df, con_objetivo=True):
    """Variables de entrada. Con objetivo: agrega 'futuro' (PM2.5 dentro de 1 h)."""
    p = df["pm2_5"]
    X = pd.DataFrame(index=df.index)
    X["pm25"] = p
    for k in (3, 6, 12):
        X[f"pm25_lag{k}"] = p.shift(k)
    X["pm25_media1h"] = p.rolling(12).mean()
    X["pm25_std1h"] = p.rolling(12).std()
    X["pm10"], X["temp"], X["hum"], X["pres"] = df["pm10"], df["temperatura"], df["humedad"], df["presion"]
    h = df.index.hour + df.index.minute / 60
    X["hora_sin"], X["hora_cos"] = np.sin(2 * np.pi * h / 24), np.cos(2 * np.pi * h / 24)
    if con_objetivo:
        return X.join(p.shift(-PASOS_ADELANTE).rename("futuro")).dropna()
    return X.dropna()
