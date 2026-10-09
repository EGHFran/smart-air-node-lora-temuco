#define LORA_RX  18   // ESP recibe (TXD del LoRa)
#define LORA_TX  19   // ESP transmite (RXD del LoRa)
#define LORA_M0  25
#define LORA_M1  26
#define LORA_AUX 27

void setup() {
  Serial.begin(115200);
  pinMode(LORA_M0, OUTPUT);
  pinMode(LORA_M1, OUTPUT);
  pinMode(LORA_AUX, INPUT);
  digitalWrite(LORA_M0, LOW);
  digitalWrite(LORA_M1, LOW);
  Serial1.begin(9600, SERIAL_8N1, LORA_RX, LORA_TX);
  delay(1500);
  Serial.print("AUX LoRa: ");
  Serial.println(digitalRead(LORA_AUX) ? "HIGH (listo)" : "LOW (ocupado)");
  Serial.println("Receptor LoRa listo");
}

void loop() {
  while (Serial1.available()) {
    Serial.write(Serial1.read());
  }
}