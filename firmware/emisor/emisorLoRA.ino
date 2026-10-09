#include <Wire.h>
#include <Adafruit_BME280.h>
#include <Adafruit_BMP280.h>
#include <Adafruit_AS7341.h>
#include "PMS.h"

// ---------- Pines ----------
#define SDA_PIN   21
#define SCL_PIN   22
#define PMS_RX    16   // ESP recibe (TX del PMS)
#define PMS_TX    17   // ESP transmite (RX del PMS)
#define LORA_RX   18   // ESP recibe (TXD del LoRa)
#define LORA_TX   19   // ESP transmite (RXD del LoRa)
#define LORA_M0   25
#define LORA_M1   26
#define LORA_AUX  27
#define ID_NODO "NODO_01"
#define INTERVALO_MS 10000

Adafruit_BME280 bme;
Adafruit_BMP280 bmp;
Adafruit_AS7341 as7341;
PMS pms(Serial2);
PMS::DATA pmsData;

enum Chip { NINGUNO, CHIP_BME280, CHIP_BMP280 };
Chip chip = NINGUNO;
uint8_t dirI2C = 0x76;
bool as7341Conectado = false; // Bandera para saber si el sensor espectral responde

int pm1 = -1, pm25 = -1, pm10 = -1;

// Variables para el sensor espectral AS7341
uint16_t spec415 = 0, spec445 = 0, spec480 = 0, spec515 = 0;
uint16_t spec555 = 0, spec590 = 0, spec630 = 0, spec680 = 0;
uint16_t specClear = 0, specNIR = 0;

// Lee el ID del chip ambiental (0x60 = BME280, 0x58 = BMP280)
int leerIdChip(uint8_t dir) {
  Wire.beginTransmission(dir);
  Wire.write(0xD0);
  if (Wire.endTransmission() != 0) return -1;
  Wire.requestFrom(dir, (uint8_t)1);
  if (!Wire.available()) return -1;
  return Wire.read();
}

void iniciarSensorAmbiental() {
  uint8_t dirs[] = {0x76, 0x77};
  for (uint8_t d : dirs) {
    int id = leerIdChip(d);
    if (id < 0) continue;
    dirI2C = d;
    Serial.printf("I2C 0x%02X, ID chip: 0x%02X\n", d, id);
    if (id == 0x60 && bme.begin(d)) {
      chip = CHIP_BME280;
      Serial.println("BME280 OK");
      return;
    }
    if ((id == 0x58 || id == 0x56 || id == 0x57) && bmp.begin(d)) {
      chip = CHIP_BMP280;
      Serial.println("BMP280 OK (sin humedad)");
      return;
    }
  }
  Serial.println("Sensor de temperatura/presion NO encontrado");
}

void iniciarSensorEspectral() {
  if (!as7341.begin()) {
    Serial.println("Sensor AS7341 NO encontrado (se omitira su lectura)");
    as7341Conectado = false;
  } else {
    as7341.setGain(AS7341_GAIN_1X);
    Serial.println("AS7341 OK");
    as7341Conectado = true;
  }
}

void esperarAux(unsigned long timeout = 2000) {
  unsigned long t = millis();
  while (digitalRead(LORA_AUX) == LOW && millis() - t < timeout) delay(5);
}

// Calcula un Checksum XOR para validar la integridad de la trama
uint8_t calcularChecksumXOR(const char* payload) {
  uint8_t crc = 0;
  while (*payload) {
    crc ^= *payload++;
  }
  return crc;
}

void setup() {
  Serial.begin(115200);
  delay(500);

  // I2C
  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(100000);
  
  iniciarSensorAmbiental();
  iniciarSensorEspectral();

  // PMS5003
  Serial2.begin(9600, SERIAL_8N1, PMS_RX, PMS_TX);

  // LoRa (modo normal: M0=LOW, M1=LOW)
  pinMode(LORA_M0, OUTPUT);
  pinMode(LORA_M1, OUTPUT);
  pinMode(LORA_AUX, INPUT);
  digitalWrite(LORA_M0, LOW);
  digitalWrite(LORA_M1, LOW);
  Serial1.begin(9600, SERIAL_8N1, LORA_RX, LORA_TX);
  delay(1500);
  Serial.print("AUX LoRa: ");
  Serial.println(digitalRead(LORA_AUX) ? "HIGH (listo)" : "LOW (ocupado)");
}

void loop() {
  // Lectura continua y fluida del PMS5003
  if (pms.read(pmsData)) {
    pm1  = pmsData.PM_AE_UG_1_0;
    pm25 = pmsData.PM_AE_UG_2_5;
    pm10 = pmsData.PM_AE_UG_10_0;
  }

  // Lectura del sensor espectral SOLO si está físicamente conectado y activo
  if (as7341Conectado) {
    if (as7341.readAllChannels()) {
      spec415   = as7341.getChannel(AS7341_CHANNEL_415nm_F1);
      spec445   = as7341.getChannel(AS7341_CHANNEL_445nm_F2);
      spec480   = as7341.getChannel(AS7341_CHANNEL_480nm_F3);
      spec515   = as7341.getChannel(AS7341_CHANNEL_515nm_F4);
      spec555   = as7341.getChannel(AS7341_CHANNEL_555nm_F5);
      spec590   = as7341.getChannel(AS7341_CHANNEL_590nm_F6);
      spec630   = as7341.getChannel(AS7341_CHANNEL_630nm_F7);
      spec680   = as7341.getChannel(AS7341_CHANNEL_680nm_F8);
      specClear = as7341.getChannel(AS7341_CHANNEL_CLEAR);
      specNIR   = as7341.getChannel(AS7341_CHANNEL_NIR);
    }
  }

  static unsigned long t = 0;
  if (millis() - t >= INTERVALO_MS) {
    t = millis();

    float temp = NAN, pres = NAN;
    char baseMsg[256];

    // 1. Armar el mensaje base dependiendo del sensor ambiental detectado
    if (chip == CHIP_BME280) {
      temp = bme.readTemperature();
      float hum  = bme.readHumidity();
      pres = bme.readPressure() / 100.0F;
      snprintf(baseMsg, sizeof(baseMsg), "%s,%.1f,%.1f,%.1f,%d,%d,%d,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u",
               ID_NODO, temp, hum, pres, pm1, pm25, pm10, 
               specClear, specNIR, spec415, spec445, spec480, spec515, spec555, spec590, spec630, spec680);
               
    } else if (chip == CHIP_BMP280) {
      temp = bmp.readTemperature();
      pres = bmp.readPressure() / 100.0F;
      snprintf(baseMsg, sizeof(baseMsg), "%s,%.1f,%.1f,%d,%d,%d,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u",
               ID_NODO, temp, pres, pm1, pm25, pm10, 
               specClear, specNIR, spec415, spec445, spec480, spec515, spec555, spec590, spec630, spec680);
               
    } else {
      snprintf(baseMsg, sizeof(baseMsg), "%s,ERR,ERR,%d,%d,%d,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u",
               ID_NODO, pm1, pm25, pm10, 
               specClear, specNIR, spec415, spec445, spec480, spec515, spec555, spec590, spec630, spec680);
    }

    // 2. Calcular el CRC (Checksum XOR)
    uint8_t crc = calcularChecksumXOR(baseMsg);

    // 3. Ensamblar el mensaje final
    char finalMsg[280];
    snprintf(finalMsg, sizeof(finalMsg), "%s,%02X", baseMsg, crc);

    // 4. Imprimir y Enviar por LoRa
    Serial.println(finalMsg);

    esperarAux();
    Serial1.println(finalMsg);
  }
}