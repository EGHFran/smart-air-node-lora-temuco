# smart-air-node-lora-temuco

Plataforma inteligente de telemetría ambiental inalámbrica de largo alcance (LoRa) con persistencia cloud, visualización centralizada, notificaciones proactivas y predicción mediante Machine Learning, orientada a monitorear material particulado (PM2.5) en la conurbación Temuco–Padre Las Casas.

Proyecto de tesis, Ingeniería Civil en Informática, Universidad Católica de Temuco.

- **Autora:** Francisca Belén Fuentes Pérez
- **Profesor guía:** Luis Alberto Caro

## Estado del proyecto

Este repositorio corresponde a la **Etapa 2 (Sprint 2): diseño detallado e implementación inicial de hardware (capa física y enlace LoRa)**. La ingesta en la nube, el dashboard, el bot y el módulo predictivo pertenecen a los Sprints 3 y 4 y todavía no están en este repositorio.

| Prueba | Descripción | Estado |
|---|---|---|
| P-01 | Lazo UART (GPIO18 con GPIO19) | Realizada |
| P-02 | Enlace en banco (581 tramas, 0 pérdidas) | Realizada |
| P-03 | Checksum con errores inyectados | Pendiente (firmware listo) |
| P-04a | Estabilidad 18 h, periodo de 30 s | Interrumpida a las 15,5 h |
| P-04b | Repetición con nodo ventilado | Pendiente |
| P-05 | Alcance escalonado con línea de vista | Pendiente |
| P-06 | Sin línea de vista (NLOS) | Pendiente |

Lo que no se ha medido se declara pendiente, no validado. El detalle está en el informe de la Etapa 2 (`docs/`).

## Arquitectura

```
Nodo sensor                                   Estación base
ESP32 + PMS5003 + BMP280 + AS7341             ESP32 + DX-LR22        USB
        + DX-LR22  ~~~~ LoRa 915 MHz ~~~~>    (solo recibe)  ------> PC (registrador.py)
```

El enlace es unidireccional y sin confirmación de recepción. El nodo solo transmite y la estación base solo recibe.

## Hardware

| Componente | Función | Interfaz |
|---|---|---|
| ESP32 DevKit V1 | Unidad de control (nodo y estación base) | UART0, UART1, UART2, I²C |
| Plantower PMS5003 | PM1.0, PM2.5 y PM10 | UART2, 9600 8N1 |
| Bosch BMP280 | Temperatura y presión (sin humedad) | I²C, 0x76 |
| ams OSRAM AS7341 | Irradiancia espectral (canal F5, 555 nm) | I²C, 0x39 |
| DX-LR22-900T22D (LLCC68) | Enlace LoRa a 915 MHz | UART1, 9600 8N1, TTL 3,3 V |

### Asignación de pines

| Periférico | Señal | GPIO | Se conecta a |
|---|---|---|---|
| PMS5003 | RX2 | 16 | TX del PMS5003 |
| PMS5003 | TX2 | 17 | RX del PMS5003 |
| LoRa | RX1 | 18 | TXD del módem |
| LoRa | TX1 | 19 | RXD del módem |
| I²C | SDA | 21 | SDA del BMP280 y del AS7341 |
| I²C | SCL | 22 | SCL del BMP280 y del AS7341 |

Alimentación: 5 V por VIN para el PMS5003 y el módem; 3,3 V del ESP32 para el BMP280 y el AS7341; tierra común. Pines M0 y M1 del módem a GND; AUX, SET y RESET del PMS5003 sin conectar. Los esquemáticos están en `hardware/`.

## Formato de trama

```
$ID,SEQ,PM1,PM25,PM10,TEMP,PRES,HUM,LUX*CC<LF>
```

- `ID`: identificador del nodo (por ejemplo, `N01`).
- `SEQ`: contador de secuencia (0 a 65535), sirve para medir pérdidas.
- `PM1`, `PM25`, `PM10`: µg/m³ (valores de atmósfera del PMS5003).
- `TEMP` en °C y `PRES` en hPa.
- `HUM`: siempre `-999` con el BMP280.
- `LUX`: conteo crudo del canal F5 del AS7341. Depende de la ganancia y del tiempo de integración configurados; no es una medida calibrada en lux.
- `CC`: checksum XOR de 8 bits de los caracteres entre `$` y `*`, en hexadecimal de dos dígitos.
- Un valor no disponible se codifica como `-999`.

Ejemplo: `$N01,1042,7,10,12,22.6,1007.2,-999,0*5B`

El receptor acepta una trama solo si cumple, en orden: formato, checksum, 9 campos y valores en rango. Las tramas descartadas se registran con su motivo.

## Estructura del repositorio

```
datasheets/        Manuales oficiales de cada componente
firmware/
  emisor/          Firmware del nodo sensor
  receptor/        Firmware de la estación base
  config_modem/    Intentos de configuración del módem por comandos AT
pc/                registrador.py (marca de tiempo y registro en CSV)
hardware/          Esquemáticos, diagrama de bloques, pinout y BOM
docs/              Informes, correo del profesor guía y actas
tests/             Registros de las pruebas (CSV y capturas)
```

## Compilación y carga del firmware

1. Instalar el soporte de ESP32 en el IDE de Arduino y elegir la placa **ESP32 Dev Module**.
2. Instalar las bibliotecas **Adafruit BMP280 Library** y **Adafruit AS7341** (con sus dependencias: Adafruit BusIO y Adafruit Unified Sensor).
3. Abrir `firmware/emisor/emisor.ino` y cargarlo en el ESP32 del nodo.
4. Abrir `firmware/receptor/receptor.ino` y cargarlo en el ESP32 de la estación base.

Parámetros útiles en el emisor:

| Constante | Uso |
|---|---|
| `PERIODO_MS` | 300000 en operación; 30000 en pruebas aceleradas |
| `LUZ_GANANCIA`, `LUZ_ATIME`, `LUZ_ASTEP` | Configuración del AS7341 |
| `PRUEBA_CHECKSUM`, `PRUEBA_CADA` | Corrompe 1 de cada N tramas (prueba P-03). Dejar en `false` en operación |
| `USAR_WATCHDOG`, `WATCHDOG_S` | Reinicio automático si el nodo se cuelga |

Parámetros del receptor: `RSSI_ACTIVO` (requiere `AT+DRSSI=1` en el módem; hoy desactivado) y `DEBUG_HEX`.

## Configuración del módem LoRa

Ambos módems operan con valores de fábrica: 9600 8N1, modo transparente, canal 0x41 (915,15 MHz), nivel de velocidad aérea 2, 22 dBm, clave 12345. No se pudo leer la configuración por comandos AT (incidente I-02), por lo que estos valores se asumen y no están verificados.

## Registrador del PC

```
pip install pyserial
python pc/registrador.py --puerto COM5
```

Guarda dos archivos CSV: uno con las lecturas válidas (columnas de la tabla `lecturas_raw`) y otro con las tramas descartadas y los avisos. Los valores `-999` se guardan como celdas vacías. La marca de tiempo es la hora de recepción en el PC, por lo que requiere el reloj sincronizado.

## Limitaciones conocidas

- Sin humedad relativa: se usa el BMP280 en lugar del BME280 (no disponible en el mercado local).
- RSSI no activado y SNR no disponible en el módem.
- Checksum XOR de 8 bits, más débil que un CRC; se mitiga con el contador de secuencia y la verificación de rangos.
- El receptor lleva un único contador de secuencia: con más de un nodo habría falsas pérdidas.
- Prueba de estabilidad incompleta y pruebas de campo pendientes.

## Convención de commits

Se usa Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`. Los hitos se marcan con etiquetas de versión (por ejemplo, `v0.2.0-etapa2`).
