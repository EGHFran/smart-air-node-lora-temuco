"""
registrador3.py - Puente serial (receptor ESP32) -> MariaDB

Lineas que entrega el receptor:
  OK,ID,SEQ,PM1,PM25,PM10,TEMP,PRES,HUM,LUX,RSSI,recibidas,corruptas,perdidas  (14 campos)
  ESP,ID,SEQ,F1..F8,CLEAR,NIR,RSSI                                            (14 campos)
  ERR,motivo,linea_recibida
  INFO,mensaje

Requiere ejecutar antes schema_nuevas_tablas.sql (el .py no crea tablas)
"""
import os
from dotenv import load_dotenv
load_dotenv()
import re
import time
from datetime import datetime, timezone

import pymysql
import serial

# --- Configuracion (se puede sobreescribir con variables de entorno) ---
PUERTO_SERIAL = os.getenv("LORA_PUERTO")
BAUD_RATE = 115200

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("GRAFANA_ADMIN_PASSWORD"),
    "port": int(os.getenv("DB_PORT")),
    "database": os.getenv("DB_NAME"),
    "charset": "utf8mb4",
    "autocommit": False,
}

CARPETA_EVIDENCIA = "tests/evidenciaCorruptas"
ESPERA_REINTENTO_S = 5

SQL_RAW = """INSERT INTO lecturas_raw
    (timestamp, nodo_id, seq, pm1_0, pm2_5, pm10, temperatura, presion, humedad,
     luz_f5, rssi, recibidas, corruptas, perdidas)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""

SQL_ESP = """INSERT INTO lecturas_espectro
    (timestamp, nodo_id, seq, f1_415nm, f2_445nm, f3_480nm, f4_515nm, f5_555nm,
     f6_590nm, f7_630nm, f8_680nm, clear_ch, nir, rssi)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""

SQL_ERR = "INSERT INTO tramas_corruptas (timestamp, motivo, linea) VALUES (%s,%s,%s)"
SQL_INFO = "INSERT INTO eventos_receptor (timestamp, mensaje) VALUES (%s,%s)"


# ---------- Utilidades ----------
def ahora():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def num(texto, tipo=float):
    """-999, NA, nan o vacio -> None (NULL en SQL); si no, convierte al tipo pedido."""
    t = texto.strip()
    if t in ("", "NA", "nan", "NaN"):
        return None
    valor = float(t)
    if valor == -999:
        return None
    return tipo(valor)


def limpiar(texto, largo=255):
    """Quita caracteres no imprimibles (lineas corruptas pueden traer basura)."""
    return re.sub(r"[^\x20-\x7E]", "?", texto)[:largo]


def guardar_evidencia(ts, linea):
    """Copia local en texto de TODA trama descartada, separada por dia."""
    carpeta = os.path.join(CARPETA_EVIDENCIA, datetime.now().strftime("%Y-%m-%d"))
    os.makedirs(carpeta, exist_ok=True)
    with open(os.path.join(carpeta, "evidencia_corruptas.txt"), "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {linea}\n")


# ---------- Base de datos ----------
def conectar_db():
    while True:
        try:
            conn = pymysql.connect(**DB_CONFIG)
            print("Conectado a MariaDB.")
            return conn
        except pymysql.MySQLError as e:
            print(f"No se pudo conectar a MariaDB ({e}). Reintento en {ESPERA_REINTENTO_S} s...")
            time.sleep(ESPERA_REINTENTO_S)


def ejecutar(conn, sql, valores):
    """INSERT con un reintento si la conexion se cayo. Devuelve la conexion vigente."""
    for intento in (1, 2):
        try:
            conn.ping(reconnect=True)
            with conn.cursor() as cur:
                cur.execute(sql, valores)
            conn.commit()
            return conn
        except pymysql.err.OperationalError as e:
            print(f"Conexion a MariaDB perdida ({e}).")
            try:
                conn.close()
            except Exception:
                pass
            conn = conectar_db()
            if intento == 2:
                raise
    return conn


# ---------- Manejadores por tipo de linea ----------
def manejar_ok(conn, partes, ts):
    if len(partes) != 14:
        raise ValueError(f"OK con {len(partes)} campos (se esperaban 14)")
    _, nodo, seq, pm1, pm25, pm10, temp, pres, hum, lux, rssi, rec, cor, per = partes
    valores = (
        ts, nodo, int(seq),
        num(pm1, int), num(pm25, int), num(pm10, int),
        num(temp), num(pres), num(hum),
        num(lux, int), num(rssi, int),
        int(rec), int(cor), int(per),
    )
    conn = ejecutar(conn, SQL_RAW, valores)
    print(f"[{ts}] OK  {nodo} SEQ {seq} | PM2.5={pm25} T={temp} | rec={rec} cor={cor} perd={per}")
    return conn


def manejar_esp(conn, partes, ts):
    if len(partes) != 14:
        raise ValueError(f"ESP con {len(partes)} campos (se esperaban 14)")
    _, nodo, seq, *canales, rssi = partes          # 10 canales: F1..F8, CLEAR, NIR
    valores = (ts, nodo, int(seq), *[num(c, int) for c in canales], num(rssi, int))
    conn = ejecutar(conn, SQL_ESP, valores)
    print(f"[{ts}] ESP {nodo} SEQ {seq} | F5={canales[4]} CLEAR={canales[8]} NIR={canales[9]}")
    return conn


def manejar_err(conn, linea, ts):
    partes = linea.split(",", 2)                   # ERR,motivo,linea_recibida
    motivo = partes[1] if len(partes) > 1 else "desconocido"
    original = partes[2] if len(partes) > 2 else ""
    guardar_evidencia(ts, linea)
    conn = ejecutar(conn, SQL_ERR, (ts, limpiar(motivo, 40), limpiar(original)))
    print(f"[{ts}] DESCARTADA ({motivo})")
    return conn


def manejar_info(conn, linea, ts):
    mensaje = linea.split(",", 1)[1] if "," in linea else linea
    conn = ejecutar(conn, SQL_INFO, (ts, limpiar(mensaje)))
    print(f"[{ts}] INFO {mensaje}")
    return conn


def procesar_linea(conn, linea):
    ts = ahora()
    tipo = linea.split(",", 1)[0]
    try:
        if tipo == "OK":
            return manejar_ok(conn, linea.split(","), ts)
        if tipo == "ESP":
            return manejar_esp(conn, linea.split(","), ts)
        if tipo == "ERR":
            return manejar_err(conn, linea, ts)
        if tipo == "INFO":
            return manejar_info(conn, linea, ts)
        print(f"Linea no reconocida: {limpiar(linea)}")
    except (ValueError, IndexError) as e:
        # Una linea mala no debe detener el registrador
        print(f"[{ts}] Linea ignorada ({e}): {limpiar(linea)}")
    return conn


# ---------- Principal ----------
def iniciar_registrador():
    conn = conectar_db()
    try:
        while True:
            try:
                with serial.Serial(PUERTO_SERIAL, BAUD_RATE, timeout=2) as ser:
                    print(f"Escuchando en {PUERTO_SERIAL}...")
                    while True:
                        linea = ser.readline().decode("utf-8", errors="ignore").strip()
                        if linea:
                            conn = procesar_linea(conn, linea)
            except serial.SerialException as e:
                print(f"Error del puerto serial: {e}")
                print("Verifica que el Monitor Serie de Arduino/VS Code este CERRADO. "
                      f"Reintento en {ESPERA_REINTENTO_S} s...")
                time.sleep(ESPERA_REINTENTO_S)
    except KeyboardInterrupt:
        print("\nRegistrador detenido por el usuario.")
    finally:
        try:
            conn.close()
            print("Conexion a MariaDB cerrada.")
        except Exception:
            pass


if __name__ == "__main__":
    iniciar_registrador()
