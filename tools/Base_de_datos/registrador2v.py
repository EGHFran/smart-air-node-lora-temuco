import serial
import pymysql
from datetime import datetime

# --- Configuración ---
PUERTO_SERIAL = "COM6"  # puerto donde esta ESP32
BAUD_RATE = 115200

# Configuración de MariaDB
DB_CONFIG = {
    'host': '127.0.0.1',
    'user': 'root',
    'password': 'loratesis1', 
    'port': 3307,
    'database': 'telemetria_iot'
}

def iniciar_registrador():
    try:
        db_conn = pymysql.connect(**DB_CONFIG)
        cursor = db_conn.cursor()
        print("Conectado a MariaDB exitosamente.")
        
        with serial.Serial(PUERTO_SERIAL, BAUD_RATE, timeout=2) as ser:
            print(f"Escuchando en {PUERTO_SERIAL}...")
            
            while True:
                linea = ser.readline().decode('utf-8', errors='ignore').strip()
                if not linea:
                    continue
                    
                # Solo procesar las tramas validadas por el receptor
                if not linea.startswith('OK,'):
                    print(f"Mensaje del receptor: {linea}")
                    
                    # Guardar evidencia de tramas corruptas en un archivo de texto local
                    if "ERR,checksum" in linea:
                        with open("tests/evidenciaCorruptas/evidencia_corruptas_p03.txt", "a") as log:
                            timestamp_err = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            log.write(f"[{timestamp_err}] {linea}\n")
                    continue
                    
                # Extraer datos de la cadena: OK,N01,7,3,4,8,20.5,997.5,-999,93,NA,7,1,0
                datos = linea.split(',')
                if len(datos) >= 11:
                    _, nodo_id, seq, pm1, pm25, pm10, temp, pres, hum, lux, rssi = datos[:11]
                    
                    timestamp_actual = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    
                    # Reemplazar -999 o "NA" por None (NULL en SQL)
                    hum_val = None if hum == '-999' else float(hum)
                    temp_val = None if temp == '-999' or temp == 'nan' else float(temp)
                    pres_val = None if pres == '-999' or pres == 'nan' else float(pres)
                    lux_val = None if lux == '-999' else int(lux)
                    rssi_val = None if rssi == 'NA' else int(rssi)
                    
                    # Inserción en MariaDB
                    sql = """INSERT INTO lecturas_raw 
                             (timestamp, nodo_id, seq, pm1_0, pm2_5, pm10, temperatura, presion, humedad, luz_f5, rssi) 
                             VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                    valores = (timestamp_actual, nodo_id, int(seq), int(pm1), int(pm25), int(pm10), temp_val, pres_val, hum_val, lux_val, rssi_val)
                    
                    cursor.execute(sql, valores)
                    db_conn.commit()
                    
                    print(f"[{timestamp_actual}] Guardado SEQ {seq} (PM2.5: {pm25}, Temp: {temp})")
                
    except serial.SerialException as e:
        print(f"Error del puerto serial: {e}")
        print("Asegúrate de que el Serial Monitor de Arduino o VS Code esté CERRADO.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'db_conn' in locals() and db_conn.is_connected():
            cursor.close()
            db_conn.close()

if __name__ == "__main__":
    iniciar_registrador()