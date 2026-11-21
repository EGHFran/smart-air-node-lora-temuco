import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHANNEL_ID = os.environ["TELEGRAM_CHANNEL_ID"]
DATABASE_URL = os.environ["DATABASE_URL"]

TABLA = os.getenv("DB_TABLE", "lectura_raw")
COL_FECHA = os.getenv("DB_COL_FECHA", "timestamp")
COL_NODO = os.getenv("DB_COL_NODO", "nodo_id")
NODO_ID = os.getenv("NODO_ID", "").strip()  # vacío = promedia todos los nodos
DB_TZ = os.getenv("DB_TZ", "UTC")
TZ = os.getenv("TIMEZONE", "America/Santiago")

PERMITIDOS = {int(x) for x in os.getenv("ALLOWED_IDS", "").split(",") if x.strip()}

HORA_DIARIO = os.getenv("REPORTE_DIARIO_HORA", "08:00")
HORA_SEMANAL = os.getenv("REPORTE_SEMANAL_HORA", "08:00")
DIA_SEMANAL = int(os.getenv("REPORTE_SEMANAL_DIA", "1"))  # 0=domingo, 1=lunes

INTERVALO_ALERTA_S = int(os.getenv("ALERT_INTERVAL_S", "60"))
VENTANA_ALERTA_MIN = int(os.getenv("ALERT_WINDOW_MIN", "5"))
COOLDOWN_MIN = int(os.getenv("ALERT_COOLDOWN_MIN", "30"))

# Las claves (pm1, pm25...) son nombres internos; "columna" es el nombre real en tu BD.
# norma   = valor de referencia (24 h) contra el que se calcula el % de sobrepaso.
# critico = umbral de peligro que dispara la alerta push (None = sin alerta).
# Valores de ejemplo basados en la normativa chilena (PM2.5: 50, PM10: 130 µg/m³ 24 h;
# críticos = inicio de "alerta ambiental"). Verifica y ajusta a la norma que uses.
VARIABLES = {
    "pm1":  {"columna": "pm1_0",       "nombre": "PM1",         "unidad": "µg/m³", "norma": None, "critico": None},
    "pm25": {"columna": "pm2_5",       "nombre": "PM2.5",       "unidad": "µg/m³", "norma": 50,   "critico": 80},
    "pm10": {"columna": "pm10",        "nombre": "PM10",        "unidad": "µg/m³", "norma": 130,  "critico": 195},
    "temp": {"columna": "temperatura", "nombre": "Temperatura", "unidad": "°C",    "norma": None, "critico": None},
    "hum":  {"columna": "humedad",     "nombre": "Humedad",     "unidad": "%",     "norma": None, "critico": None},
}
