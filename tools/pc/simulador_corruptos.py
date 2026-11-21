#!/usr/bin/env python3
"""
test_corruptas.py - Script de prueba para capturar tramas corruptas (ERR)
Incluye modo simulación para probar sin la estación base.
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

def ahora_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")

def fecha_actual():
    return datetime.now().strftime("%Y-%m-%d")

def procesar_linea(linea, carpeta_base):
    linea = linea.strip()
    if not linea:
        return

    if linea.startswith("ERR,"):
        marca = ahora_iso()
        fecha = fecha_actual()
        
        # Crear estructura: tests/evidenciaCorruptas/2026-10-20/
        ruta_carpeta = Path(carpeta_base) / "evidenciaCorruptas" / fecha
        ruta_carpeta.mkdir(parents=True, exist_ok=True)
        
        archivo_salida = ruta_carpeta / "evidencia_corruptas.txt"
        
        # Guardar la trama corrupta
        with open(archivo_salida, "a", encoding="utf-8") as f:
            f.write(f"[{marca}] {linea}\n")
            
        print(f"[{marca}] CORRUPTA CAPTURADA -> {linea}")
    else:
        # Imprime de qué tipo es la trama ignorada para dar feedback visual
        if linea.startswith("OK,"):
            print(f"[{ahora_iso()}] (Ignorada) Trama OK recibida")
        elif linea.startswith("INFO,"):
            print(f"[{ahora_iso()}] (Ignorada) Trama INFO recibida")

# --- CLASE SIMULADORA ---
class SimuladorSerial:
    """Simula un puerto serial enviando datos de prueba predefinidos."""
    def __init__(self):
        self.datos = [
            b"INFO,Iniciando sistema receptor\n",
            b"OK,1,123,4,5,6,25,1013,50,100,-80,10,0,0\n",
            b"ERR,CRC_FAIL,Trama invalida desde nodo 2\n",
            b"OK,1,124,4,5,6,25,1013,50,100,-80,11,1,0\n",
            b"ERR,SIZE_ERROR,Longitud de payload incorrecta\n",
        ]
        self.idx = 0
        self.port = "SIMULADOR"

    def readline(self):
        time.sleep(1.5) # Simula que los datos llegan cada 1.5 segundos
        if self.idx < len(self.datos):
            linea = self.datos[self.idx]
            self.idx += 1
            return linea
        # Cuando termina la lista, pausa un poco más y repite
        time.sleep(2)
        self.idx = 0
        return b""

    def close(self):
        print("Cerrando puerto simulado...")

# --- FIN CLASE SIMULADORA ---

def abrir_puerto(serial_mod, puerto, baud):
    ser = serial_mod.Serial()
    ser.port = puerto
    ser.baudrate = baud
    ser.timeout = 1
    ser.dtr = False
    ser.rts = False
    ser.open()
    return ser

def main():
    ap = argparse.ArgumentParser(description="Test de captura de tramas corruptas")
    ap.add_argument("--puerto", default="COM1", help="COM5, /dev/ttyUSB0, ...")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--carpeta", default="tests", help="Carpeta base (por defecto: tests)")
    ap.add_argument("--simular", action="store_true", help="Usa un simulador de puerto serial para pruebas")
    args = ap.parse_args()

    # Solo requiere pyserial si NO estamos simulando
    if not args.simular:
        try:
            import serial
        except ImportError:
            sys.exit("Falta pyserial: ejecuta pip install pyserial")

    print(f"Iniciando test de corruptas...")
    print(f"Se guardarán en: {args.carpeta}/evidenciaCorruptas/<fecha>/evidencia_corruptas.txt")
    if args.simular:
        print(">>> MODO SIMULACIÓN ACTIVADO <<<")
    print("Presiona Ctrl+C para terminar.\n")

    ser = None
    try:
        while True:
            if ser is None:
                if args.simular:
                    ser = SimuladorSerial()
                    print("Puerto simulado abierto.")
                else:
                    try:
                        ser = abrir_puerto(serial, args.puerto, args.baud)
                        print(f"Puerto {args.puerto} abierto.")
                    except serial.SerialException as e:
                        print(f"No se pudo abrir {args.puerto}: {e}. Reintentando en 5 s...")
                        time.sleep(5)
                        continue
            try:
                bruto = ser.readline()
            except Exception:
                print("\nPuerto desconectado. Reintentando...")
                try:
                    ser.close()
                except Exception:
                    pass
                ser = None
                time.sleep(2)
                continue
            
            if bruto:
                procesar_linea(bruto.decode("utf-8", errors="replace"), args.carpeta)
                
    except KeyboardInterrupt:
        print("\nTest detenido por el usuario.")
    finally:
        if ser is not None:
            ser.close()

if __name__ == "__main__":
    main()