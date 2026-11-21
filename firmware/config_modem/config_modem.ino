// puente_modem.ino: pasa lo que escribas al módem y lo que responde a la pantalla
#define LORA_RX 18
#define LORA_TX 19

void setup() {
  Serial.begin(115200);
  Serial1.begin(9600, SERIAL_8N1, LORA_RX, LORA_TX);
  Serial.println("Puente listo");
}

void loop() {
  while (Serial.available())  Serial1.write(Serial.read());
  while (Serial1.available()) Serial.write(Serial1.read());
}