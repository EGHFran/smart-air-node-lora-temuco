# Carpeta de Pruebas: Validación de Integridad mediante Checksum XOR

Esta carpeta reúne los archivos de registro y la documentación asociada a los ensayos de validación de integridad de trama realizados entre el nodo emisor y la estación base receptora.

## Contenido del Directorio

### 1. Documentación
* **README.md**: Descripción técnica y organización del conjunto de pruebas.

### 2. Archivos de Lecturas (`lecturas_*.csv`)
* **lecturas_20261018_230937.csv**: Registro principal de la prueba con inyección simulada de error de checksum (tasa del 10% de error, 1 de cada 10 tramas). Contiene los datos recopilados de los sensores y los contadores de tramas recibidas, corruptas y perdidas.
* **lecturas_20261019_103004.csv**: Registro de verificación y reinicio de la sesión de monitoreo.
* **lecturas_20261019_103044.csv**: Registro de continuidad para la validación de recepción de tramas.

### 3. Archivos de Bitácora de Eventos (`eventos_*.csv`)
* **eventos_20261018_230937.csv**: Registro de eventos de la prueba de inyección de checksum, incluyendo aperturas de puerto, alertas de error de integridad y cierres de sesión.
* **eventos_20261019_103004.csv**: Bitácora de eventos del sistema para la sesión del 19 de octubre.
* **eventos_20261019_103044.csv**: Bitácora de eventos del sistema para la segunda sesión del 19 de octubre.

---

## Resumen de la Prueba de Integridad (Ensayo 20261018_230937)

* **Objetivo:** Verificar la capacidad de la estación base para identificar y descartar tramas de datos cuyo Checksum XOR no coincida con el cálculo del receptor.
* **Metodología:** Modificación del firmware del emisor para corromper la suma de comprobación en uno de cada diez envíos programados.
* **Resultado:** 
  * Identificación y descarte correcto de 13 tramas corruptas.
  * Continuidad en la secuencia de tramas recibidas sin registros de datos inválidos en la base de datos o el archivo CSV.
  * Incremento consistente del contador de tramas corruptas en la estación base.