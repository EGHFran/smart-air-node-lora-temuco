#!/usr/bin/env python3
"""
registrador.py - Registro en el PC de lo que entrega la estacion base (D-07, RF-09, RF-11)

Lee por USB las lineas del receptor.ino, agrega la marca de tiempo del PC y guarda:
  logs/lecturas_<fecha>.csv  -> una fila por trama valida (columnas de lecturas_raw)
  logs/eventos_<fecha>.csv   -> tramas descartadas (ERR) y avisos (INFO)

Uso:
  pip install pyserial
  python registrador.py --puerto COM5            (Windows)
  python registrador.py --puerto /dev/ttyUSB0    (Linux)

Detener con Ctrl+C: muestra un resumen con la tasa de perdida.
Importante: el reloj del PC debe estar sincronizado (criterio de RF-09).
"""

import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

COLUMNAS_LECTURAS = [
    "timestamp", "nodo_id", "seq", "pm1_0", "pm2_5", "pm10",
    "temperatura", "presion", "humedad", "luz_f5", "rssi", "snr",
    "recibidas", "corruptas", "perdidas",
]
COLUMNAS_EVENTOS = ["timestamp", "tipo", "detalle"]


def ahora():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def valor(texto):
    """-999 (dato no disponible) y NA se guardan como vacio (NULL)."""
    texto = texto.strip()
    return "" if texto in ("-999", "NA") else texto


class Registro:
    def __init__(self, carpeta):
        carpeta = Path(carpeta)
        carpeta.mkdir(parents=True, exist_ok=True)
        sello = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.f_lect = open(carpeta / f"lecturas_{sello}.csv", "w", newline="", encoding="utf-8")
        self.f_even = open(carpeta / f"eventos_{sello}.csv", "w", newline="", encoding="utf-8")
        self.w_lect = csv.writer(self.f_lect)
        self.w_even = csv.writer(self.f_even)
        self.w_lect.writerow(COLUMNAS_LECTURAS)
        self.w_even.writerow(COLUMNAS_EVENTOS)
        self.ultimos = {"recibidas": 0, "corruptas": 0, "perdidas": 0}
        self.rutas = (self.f_lect.name, self.f_even.name)

    def procesar(self, linea):
        """Interpreta una linea del receptor. Devuelve True si fue una lectura OK."""
        linea = linea.strip()
        if not linea:
            return False
        marca = ahora()

        if linea.startswith("OK,"):
            p = linea.split(",")
            if len(p) != 14:
                self._evento(marca, "ERR_PC", f"linea OK con {len(p)} campos: {linea}")
                return False
            # OK,ID,SEQ,PM1,PM25,PM10,TEMP,PRES,HUM,LUX,RSSI,rec,cor,per
            fila = [marca, p[1], p[2], valor(p[3]), valor(p[4]), valor(p[5]),
                    valor(p[6]), valor(p[7]), valor(p[8]), valor(p[9]),
                    valor(p[10]), "",  # snr: el modem no lo entrega (D-09)
                    p[11], p[12], p[13]]
            self.w_lect.writerow(fila)
            self.f_lect.flush()
            try:
                self.ultimos = {"recibidas": int(p[11]), "corruptas": int(p[12]),
                                "perdidas": int(p[13])}
            except ValueError:
                pass
            print(f"[{marca}] OK nodo={p[1]} seq={p[2]} PM1={p[3]} PM2.5={p[4]} PM10={p[5]} "
      f"T={p[6]} P={p[7]} HUM={p[8]} LUX={p[9]} RSSI={p[10]}")
            return True

        if linea.startswith("ERR,"):
            p = linea.split(",", 2)
            motivo = p[1] if len(p) > 1 else "desconocido"
            detalle = p[2] if len(p) > 2 else ""
            self._evento(marca, "ERR", f"{motivo} | {detalle}")
            print(f"[{marca}] DESCARTADA ({motivo})")
            return False

        if linea.startswith("INFO,"):
            self._evento(marca, "INFO", linea[5:])
            print(f"[{marca}] INFO {linea[5:]}")
            return False

        # Cualquier otra cosa (texto de arranque, basura)
        self._evento(marca, "OTRO", linea)
        return False

    def _evento(self, marca, tipo, detalle):
        self.w_even.writerow([marca, tipo, detalle])
        self.f_even.flush()

    def resumen(self):
        r = self.ultimos["recibidas"]
        c = self.ultimos["corruptas"]
        pe = self.ultimos["perdidas"]
        esperados = r + pe
        tasa = (pe / esperados * 100) if esperados else 0.0
        print("\n--- Resumen (contadores del receptor) ---")
        print(f"Recibidas validas : {r}")
        print(f"Corruptas         : {c}")
        print(f"Perdidas (por SEQ): {pe}")
        print(f"Tasa de perdida   : {tasa:.2f} %  (perdidas / esperadas)")
        print(f"Archivos: {self.rutas[0]}  y  {self.rutas[1]}")

    def cerrar(self):
        self.f_lect.close()
        self.f_even.close()


def abrir_puerto(serial_mod, puerto, baud):
    ser = serial_mod.Serial()
    ser.port = puerto
    ser.baudrate = baud
    ser.timeout = 1
    ser.dtr = False   # evita, cuando se puede, que abrir el puerto reinicie el ESP32
    ser.rts = False
    ser.open()
    return ser


def main():
    ap = argparse.ArgumentParser(description="Registrador de la estacion base LoRa")
    ap.add_argument("--puerto", required=True, help="COM5, /dev/ttyUSB0, ...")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--carpeta", default="logs")
    args = ap.parse_args()

    try:
        import serial
    except ImportError:
        sys.exit("Falta pyserial: ejecuta  pip install pyserial")

    reg = Registro(args.carpeta)
    print(f"Guardando en {reg.rutas[0]} y {reg.rutas[1]}. Ctrl+C para terminar.")

    ser = None
    try:
        while True:
            if ser is None:
                try:
                    ser = abrir_puerto(serial, args.puerto, args.baud)
                    reg._evento(ahora(), "INFO", f"puerto {args.puerto} abierto")
                    print(f"Puerto {args.puerto} abierto.")
                except serial.SerialException as e:
                    print(f"No se pudo abrir {args.puerto}: {e}. Reintentando en 5 s...")
                    time.sleep(5)
                    continue
            try:
                bruto = ser.readline()
            except serial.SerialException:
                reg._evento(ahora(), "INFO", "puerto desconectado")
                print("Puerto desconectado. Reintentando...")
                try:
                    ser.close()
                except Exception:
                    pass
                ser = None
                time.sleep(2)
                continue
            if bruto:
                reg.procesar(bruto.decode("utf-8", errors="replace"))
    except KeyboardInterrupt:
        pass
    finally:
        if ser is not None:
            ser.close()
        reg.resumen()
        reg.cerrar()


if __name__ == "__main__":
    main()
