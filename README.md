# Smart Air Node LoRa - Temuco

Repositorio del Trabajo de Título: *"Sistema inteligente de telemetría ambiental IoT de extremo a extremo"*.

* **Autora:** Francisca Belén Fuentes Pérez
* **Profesor guía:** Luis Alberto Caro
* **Institución:** Universidad Católica de Temuco, Facultad de Ingeniería, Ingeniería Civil en Informática

## Descripción
Plataforma IoT para el monitoreo de material particulado (PM1.0, PM2.5 y PM10) y variables ambientales en la conurbación Temuco-Padre Las Casas. Un nodo sensor basado en ESP32 mide partículas, temperatura, presión y espectro de luz, y transmite los datos por LoRa (Sub-GHz) a una estación base. La ingesta en la nube, el dashboard, el bot de alertas y el módulo predictivo corresponden a los sprints siguientes.

## Estado del proyecto (Etapa 2, Sprint 2)
| Elemento | Estado |
|---|---|
| Lectura de BMP280/BME280 (detección por ID), AS7341 y PMS5003 | Completado |
| Enlace LoRa punto a punto emisor-receptor | Completado |
| Trama CSV con checksum XOR | Completado |
| FSM y Deep Sleep de 5 min | Pendiente |
| Validación del checksum en el receptor | Pendiente |
| Presupuesto de enlace y prueba de alcance | Pendiente |

## Hardware

### Nodo emisor
| Componente | Pin del módulo | ESP32 |
|---|---|---|
| BMP280/BME280 (I²C, 0x76) | VIN / GND / SDA / SCL | 3V3 / GND / D21 / D22 |
| AS7341 (I²C, 0x39) | VCC / GND / SDA / SCL | 3V3 / GND / D21 / D22 |
| PMS5003 (UART2, 9600) | VCC / GND | VIN (5 V) / GND |
| | TXD / RXD | D16 / D17 |
| DX-LR22 (UART1, 9600) | VCC / GND | VIN (5 V) / GND |
| | TXD / RXD | D18 / D19 |
| | M0 / M1 / AUX | D25 / D26 / D27 |

### Nodo receptor
| Componente | Pin del módulo | ESP32 |
|---|---|---|
| DX-LR22 (UART1, 9600) | VCC / GND | VIN (5 V) / GND |
| | TXD / RXD | D18 / D19 |
| | M0 / M1 / AUX | D25 / D26 / D27 |

El sensor ambiental fue adquirido como BME280, pero su ID de chip es 0x58 (BMP280), por lo que no mide humedad. El firmware detecta el tipo de chip y omite ese campo.

## Formato de la trama
CSV terminado en salto de línea. Con BMP280:

`ID_NODO,TEMP,PRES,PM1.0,PM2.5,PM10,CLEAR,NIR,F1,F2,F3,F4,F5,F6,F7,F8,CHK`

El último campo es el checksum XOR (dos dígitos hexadecimales) de los caracteres anteriores a la última coma.

## Compilación
1. Arduino IDE con el core ESP32 de Espressif (desarrollado con la versión 3.3.11) y la placa **ESP32 Dev Module**.
2. Librerías (Gestor de librerías): Adafruit BME280, Adafruit BMP280, Adafruit AS7341, Adafruit Unified Sensor y PMS Library (Mariusz Kuchta).
3. Abrir `firmware/emisor/emisor.ino` o `firmware/receptor/receptor.ino`, seleccionar el puerto y subir. Velocidad del monitor serie: 115200.
4. Conectar siempre la antena antes de energizar el módulo LoRa.

## Estructura del repositorio
```text
smart-air-node-lora-temuco/
├── firmware/
│   ├── emisor/        # Nodo sensor
│   └── receptor/      # Estación base
├── schematics/        # Esquemas del emisor y del receptor
├── datasheets/        # Hojas de datos de los componentes
└── README.md
```

## Limitaciones conocidas
Sin medición de humedad (BMP280), checksum XOR con capacidad de detección limitada, alcance de 5 km por validar en campo.