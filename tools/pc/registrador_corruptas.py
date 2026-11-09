#!/usr/bin/env python3
"""
test_corruptas.py - Script de prueba exclusivo para capturar tramas corruptas (ERR)
Crea la estructura: tests/evidenciaCorruptas/<YYYY-MM-DD>/evidencia_corruptas.txt
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

    # Solo nos interesan las tramas corruptas/errores para esta prueba
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
        # Opcional: imprimir un punto por cada línea OK para saber que está vivo, 
        # o simplemente ignorarlas.
        pass

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
    ap.add_argument("--puerto", required=True, help="COM5, /dev/ttyUSB0, ...")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--carpeta", default="tests", help="Carpeta base (por defecto: tests)")
    args = ap.parse_args()

    try:
        import serial
    except ImportError:
        sys.exit("Falta pyserial: ejecuta pip install pyserial")

    print(f"Iniciando test de corruptas...")
    print(f"Se guardarán en: {args.carpeta}/evidenciaCorruptas/<fecha>/evidencia_corruptas.txt")
    print("Presiona Ctrl+C para terminar.\n")

    ser = None
    try:
        while True:
            if ser is None:
                try:
                    ser = abrir_puerto(serial, args.puerto, args.baud)
                    print(f"Puerto {args.puerto} abierto.")
                except serial.SerialException as e:
                    print(f"No se pudo abrir {args.puerto}: {e}. Reintentando en 5 s...")
                    time.sleep(5)
                    continue
            try:
                bruto = ser.readline()
            except serial.SerialException:
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