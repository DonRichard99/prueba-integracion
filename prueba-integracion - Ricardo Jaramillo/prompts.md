# Prompts de IA utilizados

## 1. Implementación del Worker

### Prompt utilizado

> Ayúdame a implementar un Worker en Python que consuma mensajes de RabbitMQ, invoque al Sistema Contable y aplique hasta tres reintentos con backoff exponencial.

### Uso de la respuesta

Se utilizó la propuesta como base para implementar el consumidor de RabbitMQ y la estrategia de reintentos.

### Validación realizada

La implementación se probó manualmente mediante escenarios de fallo temporal y permanente del mock Contable.

---

## 4. Idempotencia

### Prompt utilizado

> ¿Cómo puedo evitar que una factura vuelva a emitirse si el Sistema de Gestión falla después de que Contable ya creó la factura?

### Uso de la respuesta

Se implementó un registro de facturas emitidas asociado a `id_venta`.

### Validación realizada

Se simuló un fallo temporal de Gestión y se comprobó que Gestión recibiera tres intentos mientras Contable recibía una sola solicitud.

---

## 5. Pruebas automatizadas

### Prompt utilizado

> Ayúdame a crear cinco pruebas con pytest para venta exitosa, cierre nocturno, fallo de Contable con reintento, fallo de Gestión sin duplicar factura y payload inválido.

### Uso de la respuesta

La IA ayudó a estructurar la suite de pruebas y los endpoints de inspección de los mocks.

### Validación realizada

Las pruebas se ejecutaron dentro de Docker Compose obteniendo:

```text
5 passed