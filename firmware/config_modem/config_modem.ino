/*
  config_modem.ino  -  Puente USB <-> módem LoRa DX-LR22-900T22D
  Sirve para escribir comandos AT al módem desde el Monitor Serie del Arduino IDE.
  Se usa UNA vez por módem (emisor y receptor). No es parte del firmware final.

  Cableado (el mismo de la tabla 6.3 del informe):
    Módem TXD -> GPIO18 (RX1)      Módem RXD -> GPIO19 (TX1)
    Módem VCC -> VIN (5 V)         Módem GND -> GND

  Uso:
    1. Monitor Serie a 115200 baudios.
    2. Para entrar al modo AT: selecciona "Sin ajuste de línea" y envía  +++
       (no escribas nada más durante ~1 s antes y después).
    3. Para los comandos AT: selecciona "Both NL & CR" (o la terminación que
       indique el manual) y envía por ejemplo  AT+HELP
    4. La sintaxis exacta de cada comando y la forma de salir del modo AT están
       en el manual técnico v2.0 de DX-SMART: verifícalas con AT+HELP.
*/

#define LORA_RX 18
#define LORA_TX 19

void mostrar(const char *titulo) {
  Serial.print(titulo);
  bool hubo = false;
  while (Serial1.available()) { Serial.write(Serial1.read()); hubo = true; }
  if (!hubo) Serial.print("(sin respuesta)");
  Serial.println();
}

void setup() {
  Serial.begin(115200);
  Serial1.begin(9600, SERIAL_8N1, LORA_RX, LORA_TX);
}

void loop() {
  Serial.println("--- intento ---");
  while (Serial1.available()) Serial1.read();
  delay(1500);
  Serial1.print("+++");
  delay(1500);
  mostrar("tras +++: ");
  Serial1.print("AT\r\n");
  delay(600);
  mostrar("tras AT: ");
  Serial1.print("AT+HELP\r\n");
  delay(800);
  mostrar("tras AT+HELP: ");
  delay(5000);
}
