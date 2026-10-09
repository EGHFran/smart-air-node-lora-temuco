# Smart Air Node LoRa - Temuco

Repositorio oficial del Trabajo de Título: *“Sistema inteligente de telemetría ambiental IoT de extremo a extremo”*.

* **Autora:** Francisca Belén Fuentes Pérez  
* **Profesor Guía:** Luis Alberto Caro  
* **Institución:** Universidad Católica de Temuco  
* **Facultad de Ingeniería — Ingeniería Civil en Informática**

---

##  Descripción General del Proyecto
Este proyecto implementa una plataforma IoT de borde (*Edge Computing*) y largo alcance orientada al monitoreo ambiental y de material particulado (PM1.0, PM2.5 y PM10) en la conurbación Temuco-Padre Las Casas. El sistema adquiere variables meteorológicas y espectrales de manera síncrona/asíncrona, transmite la telemetría mediante radiofrecuencia Sub-GHz (LoRa) hacia una estación base, y procesa la ingesta de datos hacia la infraestructura en la nube.

---

## Arquitectura de Hardware y Periféricos

### Nodo Sensor Remoto (Emisor)
* **Unidad Microcontroladora (MCU):** ESP32 Dev Module.
* **Sensor Meteorológico:** Bosch BME280 / BMP280 (I2C: `GPIO 21` SDA, `GPIO 22` SCL).
* **Sensor Espectral de Luz:** AS7341 (I2C compartido en `GPIO 21` y `GPIO 22`).
* **Sensor de Material Particulado:** Plantower PMS5003 (UART secundario: `GPIO 16` RX).
* **Transceptor LoRa:** DX-LR22-900T22D (UART principal y niveles lógicos TTL directos).

### Nodo Receptor (Estación Base / Gateway)
* **Unidad Microcontroladora (MCU):** ESP32 Dev Module secundario.
* **Transceptor LoRa:** DX-LR22-900T22D conectado por UART transparente (`GPIO 16` / `GPIO 17`).

---

## Estructura del Repositorio

```text
smart-air-node-lora-temuco/
│
├── firmware/
│   ├── emisor/             # Código fuente C/C++ para el nodo sensor (FSM, Deep Sleep, CRC)
│   └── receptor/           # Código fuente C/C++ para la estación base / gateway
│
├── schematics/
│   ├── emisor_sch.png      # Diagrama esquemático del nodo emisor (Proteus)
│   └── receptor_sch.png    # Diagrama esquemático del nodo receptor (Proteus)
│
├── datasheets/             # Hojas de datos técnicas de los componentes (PMS5003, BME280, etc.)
│
└── README.md               # Documentación general del repositorio