import os
import time
import requests
import pymysql
from dotenv import load_dotenv

# Cargar las mismas credenciales que usa tu registrador
load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("GRAFANA_ADMIN_PASSWORD"),
    "port": int(os.getenv("DB_PORT", 3307)),
    "database": os.getenv("DB_NAME", "telemetria_iot"),
    "charset": "utf8mb4"
}

UMBRAL_PM25 = int(os.getenv("PM25_UMBRAL", 50))
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

INTERVALO_REVISION_S = 60  # Revisa la base de datos cada 60 segundos
COOLDOWN_ALERTA_S = 3600   # Espera 1 hora antes de enviar una alerta repetida

def enviar_mensaje(nodo, pm25, fecha_hora):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    mensaje = (f"⚠️ <b>ALERTA AMBIENTAL - {nodo}</b> ⚠️\n"
               f"Se registró un peak de contaminación.\n"
               f"<b>PM2.5:</b> {pm25} µg/m³\n"
               f"<b>Límite:</b> {UMBRAL_PM25} µg/m³\n"
               f"<b>Hora:</b> {fecha_hora}")
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": mensaje, "parse_mode": "HTML"})
        print(f"[{time.strftime('%H:%M:%S')}] Alerta enviada a Telegram.")
    except Exception as e:
        print(f"Error al conectar con Telegram: {e}")

def iniciar_monitoreo():
    print(f"Iniciando monitor de alertas. Umbral: {UMBRAL_PM25} µg/m³...")
    ultima_alerta = 0

    while True:
        try:
            # Se conecta a la BD, consulta el último dato y se desconecta inmediatamente
            conn = pymysql.connect(**DB_CONFIG)
            with conn.cursor() as cur:
                cur.execute("SELECT timestamp, nodo_id, pm2_5 FROM lecturas_raw ORDER BY timestamp DESC LIMIT 1")
                resultado = cur.fetchone()
            conn.close()

            if resultado:
                fecha_hora, nodo, pm25 = resultado
                # Si supera la norma y ya pasó el tiempo de enfriamiento
                if pm25 is not None and pm25 > UMBRAL_PM25:
                    ahora = time.time()
                    if (ahora - ultima_alerta) > COOLDOWN_ALERTA_S:
                        enviar_mensaje(nodo, pm25, fecha_hora)
                        ultima_alerta = ahora

        except pymysql.MySQLError as e:
            print(f"Error de base de datos: {e}")
        
        # Espera antes de volver a consultar
        time.sleep(INTERVALO_REVISION_S)

if __name__ == "__main__":
    iniciar_monitoreo()