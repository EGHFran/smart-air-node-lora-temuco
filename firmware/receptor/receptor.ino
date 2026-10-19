/*
  receptor.ino  -  Estación base (Figura 7.6 del informe)
  ESP32 + DX-LR22-900T22D (UART1) + USB al PC (UART0, 115200)

  Antes de usar: activar el RSSI por paquete en ESTE módem (AT+DRSSI=1) con
  config_modem.ino. Si no se activa, poner RSSI_ACTIVO = false.

  Salida hacia el PC (una línea por trama; el PC agrega la marca de tiempo, D-07):
    OK,ID,SEQ,PM1,PM25,PM10,TEMP,PRES,HUM,LUX,RSSI,recibidas,corruptas,perdidas
    ERR,motivo,linea_recibida
    INFO,mensaje
*/

// ---------- Configuración ----------
#define LORA_RX 18   // GPIO18 (RX1) <- TXD del módem
#define LORA_TX 19   // GPIO19 (TX1) -> RXD del módem

const bool     RSSI_ACTIVO   = false;   // AT+DRSSI=1 en este módem
const bool     DEBUG_HEX     = false;  // true: muestra los bytes crudos (para verificar P-02)
const uint32_t ESPERA_RSSI_MS = 100;
const int      NO_DISP       = -999;

// ---------- Estado ----------
char   linea[128];
size_t n = 0;
bool   desborde = false;

uint32_t recibidas = 0, corruptas = 0, perdidas = 0;
int32_t  ultimoSeq = -1;   // -1 = ningún paquete recibido todavía

// ---------- Utilidades ----------
void descartar(const char *motivo) {
  corruptas++;
  Serial.print("ERR,");
  Serial.print(motivo);
  Serial.print(",");
  Serial.println(linea);
}

// Valor válido = -999 (no disponible) o dentro de [min, max]
bool enRango(float v, float minimo, float maximo) {
  return (v == NO_DISP) || (v >= minimo && v <= maximo);
}

bool leerByteRSSI(uint8_t &b) {
  uint32_t t = millis();
  while (!Serial1.available()) {
    if (millis() - t > ESPERA_RSSI_MS) return false;
    delay(1);
  }
  b = (uint8_t)Serial1.read();
  return true;
}

// ---------- Procesar una línea completa ----------
void procesarLinea() {
  linea[n] = '\0';

  // Byte de RSSI que el módem agrega después de cada paquete
  bool tieneRssi = false;
  int rssi = 0;
  if (RSSI_ACTIVO) {
    uint8_t b;
    if (leerByteRSSI(b)) { tieneRssi = true; rssi = (int)b - 255; }  // -(255 - b)
  }

  if (DEBUG_HEX) {
    Serial.print("HEX: ");
    for (size_t i = 0; i < n; i++) Serial.printf("%02X ", (uint8_t)linea[i]);
    if (tieneRssi) Serial.printf("| RSSI byte=%d", rssi + 255);
    Serial.println();
  }

  if (desborde) { descartar("linea_demasiado_larga"); return; }

  // ¿Empieza con '$' y contiene '*'?
  char *estrella = strrchr(linea, '*');
  if (linea[0] != '$' || estrella == NULL) { descartar("formato"); return; }

  // CC: exactamente 2 dígitos hexadecimales
  if (strlen(estrella) != 3 || !isxdigit((uint8_t)estrella[1]) || !isxdigit((uint8_t)estrella[2])) {
    descartar("formato_cc"); return;
  }
  uint8_t ccRecibido = (uint8_t)strtol(estrella + 1, NULL, 16);

  // Separar contenido y recalcular XOR
  *estrella = '\0';
  char *contenido = linea + 1;
  uint8_t ccCalculado = 0;
  for (char *p = contenido; *p; p++) ccCalculado ^= (uint8_t)*p;
  *estrella = '*';   // restaurar para poder imprimir la línea original en caso de error

  if (ccCalculado != ccRecibido) { descartar("checksum"); return; }

  // ¿Tiene los 9 campos?
  char copia[128];
  strncpy(copia, contenido, sizeof(copia) - 1);
  copia[estrella - linea - 1] = '\0';
  copia[sizeof(copia) - 1] = '\0';

  char *campo[9];
  int cantidad = 0;
  char *token = strtok(copia, ",");
  while (token != NULL && cantidad < 10) {
    if (cantidad < 9) campo[cantidad] = token;
    cantidad++;
    token = strtok(NULL, ",");
  }
  if (cantidad != 9) { descartar("campos"); return; }

  // ¿Valores en rango o -999?
  long  seqLeido = atol(campo[1]);
  float pm1  = atof(campo[2]), pm25 = atof(campo[3]), pm10 = atof(campo[4]);
  float temp = atof(campo[5]), pres = atof(campo[6]);
  float hum  = atof(campo[7]), lux  = atof(campo[8]);

  if (seqLeido < 0 || seqLeido > 65535 ||
      !enRango(pm1, 0, 1000) || !enRango(pm25, 0, 1000) || !enRango(pm10, 0, 1000) ||
      !enRango(temp, -40, 85) || !enRango(pres, 300, 1100) ||
      !enRango(hum, 0, 100)   || !enRango(lux, 0, 65535)) {
    descartar("rango"); return;
  }

  // Pérdidas por contador de secuencia
  if (ultimoSeq >= 0) {
    uint16_t diferencia = (uint16_t)((uint16_t)seqLeido - (uint16_t)ultimoSeq);  // módulo 65536
    if (diferencia == 0) {
      Serial.println("INFO,paquete_duplicado");
      return;
    }
    if (diferencia > 1000) {
      Serial.println("INFO,posible_reinicio_del_nodo");   // no se cuentan como pérdidas
    } else if (diferencia > 1) {
      perdidas += diferencia - 1;
    }
  }
  ultimoSeq = seqLeido;
  recibidas++;

  // Registro hacia el PC (el PC agrega la marca de tiempo)
  Serial.printf("OK,%s,%s,%s,%s,%s,%s,%s,%s,%s,", campo[0], campo[1], campo[2], campo[3],
                campo[4], campo[5], campo[6], campo[7], campo[8]);
  if (tieneRssi) Serial.print(rssi); else Serial.print("NA");
  Serial.printf(",%lu,%lu,%lu\n", (unsigned long)recibidas, (unsigned long)corruptas,
                (unsigned long)perdidas);
}

// ---------- Setup y loop ----------
void setup() {
  Serial.begin(115200);
  Serial1.begin(9600, SERIAL_8N1, LORA_RX, LORA_TX);
  Serial.println("INFO,receptor_listo");
}

void loop() {
  while (Serial1.available()) {
    char c = (char)Serial1.read();
    if (c == '\n') {
      procesarLinea();
      n = 0;
      desborde = false;
    } else if (c != '\r') {
      if (n < sizeof(linea) - 1) linea[n++] = c;
      else desborde = true;
    }
  }

}
