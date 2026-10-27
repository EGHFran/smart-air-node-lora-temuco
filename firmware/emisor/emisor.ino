/*
  emisor.ino  -  Nodo sensor (Figura 7.2 del informe)
  ESP32 + PMS5003 (UART2) + BME280 y AS7341 (I2C) + DX-LR22-900T22D (UART1)

  Trama normal:   $ID,SEQ,PM1,PM25,PM10,TEMP,PRES,HUM,LUX*CC<LF>
  Trama espectro: $IDE,SEQ,F1,F2,F3,F4,F5,F6,F7,F8,CLEAR,NIR*CC<LF>
    CC = XOR de todos los caracteres entre '$' y '*' (sin incluirlos), 2 digitos hex.
    Valor no disponible = -999. HUM = humedad relativa en % (BME280); -999 si el sensor falla.
    La trama de espectro usa el mismo SEQ que la trama normal del mismo ciclo.
    LUX (trama normal) = cuentas crudas del canal F5 (555 nm), no son lux reales.

  Librerias (Gestor de bibliotecas): "Adafruit BME280 Library" y "Adafruit AS7341"
  (instala tambien sus dependencias: Adafruit BusIO y Adafruit Unified Sensor).
  Placa: "ESP32 Dev Module".
*/

#include <Wire.h>
#include <Adafruit_BME280.h>
#include <Adafruit_AS7341.h>
#include <esp_task_wdt.h>

// ---------- Configuracion ----------
#define ID_NODO "N01"
const uint32_t PERIODO_MS = 300000UL;          // 5 min en operacion; usar 30000 en pruebas aceleradas (D-10)
const uint32_t ESTABILIZACION_MS = 30000UL;  // 30 s al arrancar (PMS5003)
const int NO_DISP = -999;
const uint8_t CPU_FREC_MHZ = 80;

// AS7341: ganancia e integracion (tiempo = (ATIME+1)*(ASTEP+1)*2,78 us = 50 ms)
const as7341_gain_t LUZ_GANANCIA = AS7341_GAIN_1X+;
const uint8_t LUZ_ATIME = 29;
const uint16_t LUZ_ASTEP = 599;

// Trama de espectro (10 canales) ademas de la trama normal
const bool ENVIAR_ESPECTRO = true;

// Prueba P-03: true = corrompe 1 de cada PRUEBA_CADA tramas normales (volver a false despues)
const bool PRUEBA_CHECKSUM = false;
const uint16_t PRUEBA_CADA = 10;

// Watchdog (poner USAR_WATCHDOG en 0 si da error de compilacion con tu version del core)
#define USAR_WATCHDOG 1
const uint32_t WATCHDOG_S = 30;

// ---------- Pines (tabla 6.3) ----------
#define PMS_RX 16   // GPIO16 (RX2) <- TX del PMS5003
#define PMS_TX 17   // GPIO17 (TX2) -> RX del PMS5003
#define LORA_RX 18  // GPIO18 (RX1) <- TXD del modem
#define LORA_TX 19  // GPIO19 (TX1) -> RXD del modem
#define I2C_SDA 21
#define I2C_SCL 22

Adafruit_BME280 bme;
Adafruit_AS7341 as7341;
bool bmeOk = false;
bool asOk = false;
uint16_t seq = 0;         // 0..65535, desborda solo
uint32_t inyectadas = 0;  // tramas corrompidas a proposito (P-03)

// Espectro del ciclo actual
uint16_t espectro[10];  // F1..F8, CLEAR, NIR
bool espectroValido = false;

// ---------- Watchdog y esperas ----------
void iniciarWatchdog() {
#if USAR_WATCHDOG
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  esp_task_wdt_config_t cfg;
  cfg.timeout_ms = WATCHDOG_S * 1000;
  cfg.idle_core_mask = 0;
  cfg.trigger_panic = true;
  esp_task_wdt_reconfigure(&cfg);
#else
  esp_task_wdt_init(WATCHDOG_S, true);
#endif
  esp_task_wdt_add(NULL);
#endif
}

void alimentarWatchdog() {
#if USAR_WATCHDOG
  esp_task_wdt_reset();
#endif
}

// Espera ms milisegundos alimentando el watchdog (para esperas largas)
void esperar(uint32_t ms) {
  uint32_t t0 = millis();
  while (true) {
    uint32_t transcurrido = millis() - t0;
    if (transcurrido >= ms) break;
    uint32_t restante = ms - transcurrido;
    delay(restante < 100 ? restante : 100);
    alimentarWatchdog();
  }
}

const char *motivoReinicio() {
  switch (esp_reset_reason()) {
    case ESP_RST_POWERON: return "encendido";
    case ESP_RST_EXT: return "reset externo (boton EN)";
    case ESP_RST_SW: return "software";
    case ESP_RST_PANIC: return "panic / excepcion";
    case ESP_RST_INT_WDT: return "watchdog de interrupciones";
    case ESP_RST_TASK_WDT: return "watchdog de tarea (nodo colgado)";
    case ESP_RST_WDT: return "watchdog";
    case ESP_RST_BROWNOUT: return "caida de tension (brownout)";
    case ESP_RST_DEEPSLEEP: return "salida de deep sleep";
    default: return "otro";
  }
}

// ---------- Sensores ----------
bool iniciarBME() {
  return bme.begin(0x76) || bme.begin(0x77);  // direccion segun el pin SDO del modulo
}

bool iniciarAS7341() {
  if (!as7341.begin()) return false;  // direccion 0x39
  as7341.setATIME(LUZ_ATIME);
  as7341.setASTEP(LUZ_ASTEP);
  as7341.setGain(LUZ_GANANCIA);
  as7341.readAllChannels();  // lectura de descarte: la primera suele ser invalida
  return true;
}

// Guarda los 10 canales del AS7341 en el arreglo global "espectro"
void guardarEspectro() {
  espectro[0] = as7341.getChannel(AS7341_CHANNEL_415nm_F1);
  espectro[1] = as7341.getChannel(AS7341_CHANNEL_445nm_F2);
  espectro[2] = as7341.getChannel(AS7341_CHANNEL_480nm_F3);
  espectro[3] = as7341.getChannel(AS7341_CHANNEL_515nm_F4);
  espectro[4] = as7341.getChannel(AS7341_CHANNEL_555nm_F5);
  espectro[5] = as7341.getChannel(AS7341_CHANNEL_590nm_F6);
  espectro[6] = as7341.getChannel(AS7341_CHANNEL_630nm_F7);
  espectro[7] = as7341.getChannel(AS7341_CHANNEL_680nm_F8);
  espectro[8] = as7341.getChannel(AS7341_CHANNEL_CLEAR);
  espectro[9] = as7341.getChannel(AS7341_CHANNEL_NIR);
  espectroValido = true;
}

// Lee un byte del PMS5003 con tiempo maximo de espera.
bool leerByteSerie2(uint8_t &b, uint32_t timeoutMs) {
  uint32_t t = millis();
  while (!Serial2.available()) {
    if (millis() - t > timeoutMs) return false;
    delay(1);
  }
  b = (uint8_t)Serial2.read();
  return true;
}

// Paso "Vaciar buffer" + "Leer trama de 32 bytes" + "Cabecera y suma correctas?"
// Usa los valores de atmosfera (bytes 10..15) del PMS5003.
bool leerPMS(int &pm1, int &pm25, int &pm10) {
  while (Serial2.available()) Serial2.read();  // descarta tramas viejas
  uint32_t inicio = millis();
  uint8_t buf[32];

  while (millis() - inicio < 4000) {
    uint8_t b;
    if (!leerByteSerie2(b, 100) || b != 0x42) continue;
    if (!leerByteSerie2(b, 100) || b != 0x4D) continue;
    buf[0] = 0x42;
    buf[1] = 0x4D;

    bool completa = true;
    for (int i = 2; i < 32; i++) {
      if (!leerByteSerie2(buf[i], 100)) {
        completa = false;
        break;
      }
    }
    if (!completa) continue;

    uint16_t suma = 0;
    for (int i = 0; i < 30; i++) suma += buf[i];
    uint16_t recibida = ((uint16_t)buf[30] << 8) | buf[31];
    uint16_t largo = ((uint16_t)buf[2] << 8) | buf[3];
    if (suma != recibida || largo != 28) continue;

    pm1 = ((uint16_t)buf[10] << 8) | buf[11];
    pm25 = ((uint16_t)buf[12] << 8) | buf[13];
    pm10 = ((uint16_t)buf[14] << 8) | buf[15];
    return true;
  }
  return false;
}

// ---------- Trama de espectro ----------
void enviarEspectro() {
  char contenido[100];
  snprintf(contenido, sizeof(contenido),
           "%sE,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u",
           ID_NODO, seq,
           espectro[0], espectro[1], espectro[2], espectro[3], espectro[4],
           espectro[5], espectro[6], espectro[7], espectro[8], espectro[9]);

  uint8_t cc = 0;
  for (size_t i = 0; contenido[i] != '\0'; i++) cc ^= (uint8_t)contenido[i];

  char trama[120];
  snprintf(trama, sizeof(trama), "$%s*%02X\n", contenido, cc);
  Serial1.print(trama);
  Serial.print("TX ESP: ");
  Serial.print(trama);
}

// ---------- Setup ----------
void setup() {
  setCpuFrequencyMhz(CPU_FREC_MHZ);
  Serial.begin(115200);
  Serial2.begin(9600, SERIAL_8N1, PMS_RX, PMS_TX);
  Serial1.begin(9600, SERIAL_8N1, LORA_RX, LORA_TX);
  Wire.begin(I2C_SDA, I2C_SCL);

  Serial.printf("\nNodo %s | CPU %u MHz | motivo de reinicio: %s\n",
                ID_NODO, (unsigned)getCpuFrequencyMhz(), motivoReinicio());

  iniciarWatchdog();

  bmeOk = iniciarBME();
  asOk = iniciarAS7341();
  Serial.printf("BME280: %s | AS7341: %s\n", bmeOk ? "OK" : "FALLA", asOk ? "OK" : "FALLA");

  Serial.println("Esperando 30 s de estabilizacion del PMS5003...");
  esperar(ESTABILIZACION_MS);
}

// ---------- Ciclo principal ----------
void loop() {
  uint32_t inicioCiclo = millis();
  alimentarWatchdog();

  // 1) PMS5003
  int pm1 = NO_DISP, pm25 = NO_DISP, pm10 = NO_DISP;
  if (!leerPMS(pm1, pm25, pm10)) {
    pm1 = pm25 = pm10 = NO_DISP;
    Serial.println("PMS5003: lectura invalida -> -999");
  }
  alimentarWatchdog();

  // 2) BME280 y AS7341
  if (!bmeOk) bmeOk = iniciarBME();
  if (!asOk) asOk = iniciarAS7341();

  float temp = NAN, pres = NAN, hum = NAN;
  if (bmeOk) {
    temp = bme.readTemperature();
    pres = bme.readPressure() / 100.0f;  // Pa -> hPa
    hum = bme.readHumidity();            // % de humedad relativa
    if (isnan(temp) || temp < -40 || temp > 85) temp = NAN;
    if (isnan(pres) || pres < 300 || pres > 1100) pres = NAN;
    if (isnan(hum) || hum < 0 || hum > 100) hum = NAN;
  }

  int lux = NO_DISP;
  espectroValido = false;  // no reenviar espectro viejo
  if (asOk) {
    for (int intento = 0; intento < 3 && lux == NO_DISP; intento++) {
      if (as7341.readAllChannels()) {
        guardarEspectro();
        lux = espectro[4];  // F5 (555 nm), cuentas crudas

        // Aviso de saturacion en cualquier canal
        for (int i = 0; i < 10; i++) {
          if (espectro[i] >= 18000) {
            Serial.println("AS7341: canal saturado (18000); reducir ganancia o tiempo de integracion");
          }
        }
      } else {
        Serial.println("AS7341: readAllChannels fallo, reintentando");
        delay(200);
      }
      alimentarWatchdog();
    }
    if (lux == NO_DISP) {
      Serial.println("AS7341: sin lectura, se reinicializa en el proximo ciclo");
      asOk = false;
    }
  } else {
    Serial.println("AS7341: begin() fallo (revisar cables SDA/SCL/3V3/GND)");
  }

  // 3) Armar contenido
  char tBuf[12], pBuf[12], hBuf[12];
  if (isnan(temp)) strcpy(tBuf, "-999");
  else snprintf(tBuf, sizeof(tBuf), "%.1f", temp);
  if (isnan(pres)) strcpy(pBuf, "-999");
  else snprintf(pBuf, sizeof(pBuf), "%.1f", pres);
  if (isnan(hum)) strcpy(hBuf, "-999");
  else snprintf(hBuf, sizeof(hBuf), "%.1f", hum);

  char contenido[96];
  snprintf(contenido, sizeof(contenido), "%s,%u,%d,%d,%d,%s,%s,%s,%d",
           ID_NODO, seq, pm1, pm25, pm10, tBuf, pBuf, hBuf, lux);

  // 4) Checksum XOR
  uint8_t cc = 0;
  for (size_t i = 0; contenido[i] != '\0'; i++) cc ^= (uint8_t)contenido[i];

  char trama[120];
  snprintf(trama, sizeof(trama), "$%s*%02X\n", contenido, cc);

  // Prueba P-03: altera un caracter (el primer digito de SEQ) sin recalcular CC
  bool corrompida = false;
  if (PRUEBA_CHECKSUM && (seq % PRUEBA_CADA == 0)) {
    trama[5] ^= 0x01;
    inyectadas++;
    corrompida = true;
  }

  // 5) Enviar por LoRa (UART1) y mostrar en el monitor serie
  Serial1.print(trama);
  if (corrompida) Serial.printf("TX (CORRUPTA #%lu): ", (unsigned long)inyectadas);
  else Serial.print("TX: ");
  Serial.print(trama);

  // 5b) Trama de espectro (mismo SEQ), con una pausa para no pegar dos paquetes en el modem
  if (ENVIAR_ESPECTRO && espectroValido) {
    esperar(300);
    enviarEspectro();
  }

  seq++;

  // 6) Esperar hasta completar el periodo (medido desde el inicio del ciclo)
  uint32_t transcurrido = millis() - inicioCiclo;
  if (transcurrido < PERIODO_MS) esperar(PERIODO_MS - transcurrido);
}
