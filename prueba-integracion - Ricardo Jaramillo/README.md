# Prueba de Integración de Sistemas - Ricardo Jaramillo

## 1. Descripción

Este proyecto implementa una prueba de concepto (PoC) de una arquitectura de integración entre un Sistema de Gestión, un Sistema Contable y un Sistema de Lealtad.

La solución utiliza una Capa de Integración encargada de recibir eventos de venta, aplicar reglas de negocio, gestionar la comunicación entre sistemas y garantizar resiliencia ante fallos mediante una cola persistente, reintentos automáticos, idempotencia y trazabilidad.

La arquitectura fue implementada utilizando:

- Python
- FastAPI
- RabbitMQ
- Docker
- Docker Compose
- Pytest

---

## 2. Objetivo

El objetivo de la solución es automatizar el proceso de facturación asociado a una venta y garantizar que:

1. Las ventas sean recibidas por la Capa de Integración.
2. Las solicitudes de facturación sean procesadas mediante una cola persistente.
3. El Sistema Contable emita la factura.
4. El Sistema de Gestión reciba la confirmación de la factura.
5. El Sistema de Lealtad acredite puntos únicamente después de que la factura haya sido emitida.
6. Los fallos temporales sean tratados mediante reintentos automáticos.
7. No se generen facturas duplicadas.
8. Durante el cierre contable las solicitudes permanezcan en cola.
9. Los eventos importantes queden registrados mediante logs estructurados.
10. Los fallos definitivos puedan conservarse en una Dead Letter Queue (DLQ).

---

## 3. Arquitectura

El flujo principal implementado es:

```text
                    CLIENTE
                       |
                       v
              SISTEMA DE GESTIÓN
                       |
                  evento de venta
                       |
                       v
              CAPA DE INTEGRACIÓN
                       |
                       v
                  RABBITMQ
              COLA "facturacion"
                       |
                       v
                    WORKER
                       |
                       v
              SISTEMA CONTABLE
                       |
                 factura emitida
                       |
                       v
                    WORKER
                    /    \
                   /      \
                  v        v
        SISTEMA GESTIÓN   SISTEMA LEALTAD
               |                |
         confirmación      acredita puntos
```

Durante el cierre contable:

```text
22:00 - 23:59

Venta
  |
  v
Capa de Integración
  |
  v
RabbitMQ
  |
  v
COLA
  |
  X
NO enviar al Sistema Contable
```

Una vez finalizado el cierre, el Worker puede continuar procesando las solicitudes pendientes.

---

## 4. Componentes

### Orchestrator

Expone el endpoint principal:

```text
POST /ventas
```

Su responsabilidad es recibir y validar la venta y publicarla en RabbitMQ para su procesamiento asíncrono.

También dispone de:

```text
GET /health
```

---

### RabbitMQ

Se utiliza como mecanismo de mensajería persistente.

Cola principal:

```text
facturacion
```

Cola de mensajes fallidos:

```text
facturacion_dlq
```

RabbitMQ permite desacoplar la recepción de ventas del procesamiento de facturas.

---

### Worker

Consume secuencialmente los mensajes almacenados en la cola `facturacion`.

Sus principales responsabilidades son:

- Comprobar el horario de cierre contable.
- Solicitar la emisión de la factura.
- Aplicar reintentos con backoff exponencial.
- Mantener control de idempotencia.
- Notificar la factura al Sistema de Gestión.
- Notificar al Sistema de Lealtad.
- Generar logs estructurados.
- Enviar fallos definitivos a la DLQ.

El procesamiento utiliza:

```text
prefetch_count = 1
```

para mantener un procesamiento secuencial de los eventos.

---

### Mock Sistema Contable

Simula el sistema encargado de emitir las facturas.

Endpoint:

```text
POST /facturas
```

También permite simular fallos temporales y permanentes para comprobar los mecanismos de resiliencia.

---

### Mock Sistema de Gestión

Simula el sistema que origina las ventas y recibe posteriormente la confirmación de la factura.

Endpoints principales:

```text
POST /webhook
POST /facturas/confirmacion
```

---

### Mock Sistema de Lealtad

Simula la acreditación de puntos.

Endpoint:

```text
POST /puntos
```

La regla principal implementada es:

```text
Solo acreditar puntos si:
estado_factura = "Factura Emitida"
```

Por tanto, una venta cuya factura no haya sido emitida correctamente no genera puntos.

---

## 5. Decisiones de diseño

### Cola persistente

Se utiliza RabbitMQ para desacoplar la recepción de ventas del procesamiento contable.

Esto permite que una venta pueda conservarse aunque temporalmente no sea posible procesarla.

### Procesamiento asíncrono

El endpoint `POST /ventas` no espera a que finalice todo el proceso de facturación.

La venta es aceptada y publicada en la cola para que posteriormente sea procesada por el Worker.

### Reintentos automáticos

Las comunicaciones externas disponen de hasta tres intentos.

El backoff implementado es exponencial:

```text
Intento 1
   |
   | fallo
   v
esperar 1 segundo

Intento 2
   |
   | fallo
   v
esperar 2 segundos

Intento 3
```

Los valores son configurables mediante variables de entorno.

### Idempotencia

Una factura emitida se registra inmediatamente después de obtener una respuesta satisfactoria del Sistema Contable.

Si posteriormente falla la comunicación con Gestión o Lealtad, el sistema evita volver a emitir la factura para la misma venta.

Para esta PoC el registro de idempotencia se mantiene en memoria.

En un entorno productivo debería almacenarse en un mecanismo persistente, por ejemplo una base de datos o almacenamiento distribuido.

### Cierre contable

Entre:

```text
22:00 - 23:59
```

las solicitudes no deben enviarse al Sistema Contable.

Los eventos permanecen en cola y pueden procesarse una vez finalizada la ventana de cierre.

La zona horaria utilizada es:

```text
America/Guayaquil
```

### Dead Letter Queue

Los eventos que agotan los reintentos contra el Sistema Contable pueden enviarse a:

```text
facturacion_dlq
```

Esto evita perder definitivamente una venta que no pudo procesarse.

### Trazabilidad

El Worker genera logs estructurados en JSON.

Ejemplo:

```json
{
  "timestamp": "2026-08-17T00:59:03.755543-05:00",
  "id_venta": "V-LOG-001",
  "sistema_destino": "SISTEMA_CONTABLE",
  "estado": "OK",
  "detalle_error": null
}
```

Los estados principales utilizados son:

```text
OK
FALLIDO
ENCOLADO
```

---

## 6. Resiliencia

La solución contempla distintos escenarios de fallo.

### Sistema Contable temporalmente no disponible

```text
Worker
   |
   v
Contable
   |
  503
   |
   v
Reintento
```

Se realizan hasta tres intentos con backoff exponencial.

### Sistema Contable permanentemente no disponible

Después de agotar los reintentos, el evento puede enviarse a la DLQ.

### Fallo del Sistema de Gestión

Si la factura ya fue emitida pero Gestión no responde:

```text
Factura emitida
      |
      v
Gestión
      |
     503
      |
      v
Reintentos
```

La factura no vuelve a emitirse.

### Fallo del Sistema de Lealtad

Si Lealtad falla después de haberse emitido la factura:

```text
Factura emitida
      |
      v
Gestión OK
      |
      v
Lealtad
      |
     503
      |
      v
Reintentos
```

Los puntos únicamente se acreditan cuando Lealtad confirma correctamente la operación.

---

## 7. Estructura del proyecto

```text
prueba-integracion/
|
├── docker-compose.yml
├── README.md
├── prompts.md
|
├── src/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── worker_main.py
│   └── app/
│       ├── main.py
│       ├── adapters/
│       ├── models/
│       ├── queue/
│       └── services/
|
├── mocks/
│   ├── contable/
│   ├── gestion/
│   └── lealtad/
|
├── tests/
│   ├── Dockerfile
│   └── test_ventas.py
|
└── docs/
```

---

## 8. Ejecución

La solución puede levantarse y probarse con un máximo de tres comandos.

### Comando 1 — Levantar la solución

```bash
docker compose up -d --build
```

### Comando 2 — Construir las pruebas

```bash
docker compose --profile test build tests
```

### Comando 3 — Ejecutar las pruebas

```bash
docker compose --profile test run --rm tests
```

---

## 9. Pruebas automatizadas

Se implementaron cinco pruebas automatizadas con Pytest.

### Prueba 1 — Venta procesada exitosamente

Comprueba el flujo:

```text
Venta
→ RabbitMQ
→ Contable
→ Gestión
→ Lealtad
```

Resultado esperado:

```text
Factura emitida
Gestión actualizada
Puntos acreditados
```

### Prueba 2 — Cierre nocturno

Comprueba la regla:

```text
22:00 <= hora <= 23:59
```

Durante este periodo las solicitudes no deben enviarse al Sistema Contable.

También verifica que:

```text
21:59 → fuera de cierre
00:00 → fuera de cierre
```

### Prueba 3 — Fallo del Sistema Contable

El mock Contable devuelve errores temporales.

Resultado esperado:

```text
Intento 1 → 503
espera 1s

Intento 2 → 503
espera 2s

Intento 3 → OK
```

### Prueba 4 — Fallo de Gestión sin duplicar factura

El Sistema Contable emite correctamente la factura.

Gestión falla temporalmente:

```text
Gestión intento 1 → 503
Gestión intento 2 → 503
Gestión intento 3 → OK
```

La prueba comprueba que:

```text
Solicitudes a Contable = 1
```

demostrando que la factura no se duplica.

### Prueba 5 — Payload inválido

Se envía una venta que no cumple el contrato esperado.

Resultado esperado:

```text
HTTP 400
```

---

## 10. Resultado de las pruebas

Ejecución:

```bash
docker compose --profile test run --rm tests
```

Resultado obtenido:

```text
collected 5 items

test_venta_procesada_exitosamente PASSED
test_horario_cierre PASSED
test_fallo_contable_con_reintento PASSED
test_fallo_gestion_sin_duplicar_factura PASSED
test_payload_invalido PASSED

5 passed
```

---

## 11. Escenarios especiales disponibles

Los mocks permiten simular determinados errores mediante `id_venta`.

### Fallo temporal del Contable

```text
V-FAIL-RETRY-*
```

Los dos primeros intentos fallan y el tercero funciona.

### Fallo permanente del Contable

```text
V-FAIL-ALWAYS-*
```

Los intentos fallan permanentemente, permitiendo comprobar la DLQ.

### Fallo temporal de Gestión

```text
V-FAIL-GESTION-*
```

Los dos primeros intentos fallan y el tercero funciona.

### Fallo temporal de Lealtad

```text
V-FAIL-LEALTAD-*
```

Los dos primeros intentos fallan y el tercero funciona.

---

## 12. Contrato de venta

Ejemplo de una venta válida:

```json
{
  "id_venta": "V-10001",
  "id_cliente": "CLI-1001",
  "items": [
    {
      "sku": "SKU-001",
      "descripcion": "Tiempo estacion gamer",
      "cantidad": 1,
      "precio_unitario": 15.0
    }
  ],
  "total": 15.0,
  "canal": "ecommerce",
  "timestamp": "2026-08-17T01:00:00-05:00"
}
```

---

## 13. Variables de entorno principales

```text
RABBITMQ_URL
CONTABLE_URL
GESTION_URL
LEALTAD_URL
CLOSING_START
CLOSING_END
RETRY_MAX
RETRY_BASE_SECONDS
```

Configuración utilizada en la PoC:

```text
CLOSING_START=22:00
CLOSING_END=23:59
RETRY_MAX=3
RETRY_BASE_SECONDS=1
```

---

## 14. Limitaciones de la PoC

La solución implementada es una prueba de concepto y no pretende representar directamente una implementación productiva.

Entre sus principales limitaciones se encuentran:

- La idempotencia se mantiene en memoria.
- Los mocks no utilizan bases de datos reales.
- Los contadores de intentos de los mocks se mantienen en memoria.
- No existe autenticación entre servicios.
- No se implementa observabilidad mediante una plataforma externa.
- La DLQ requiere intervención o un proceso adicional para reprocesar sus eventos.

Estas decisiones permiten mantener la PoC simple y reproducible, conservando los mecanismos fundamentales solicitados para la integración.

---

## 15. Conclusión

La PoC demuestra una arquitectura de integración desacoplada y resiliente para el procesamiento de ventas y facturas.

La utilización de RabbitMQ permite mantener los eventos pendientes y desacoplar el Sistema de Gestión del Sistema Contable.

Los mecanismos de reintento, idempotencia, cierre contable, DLQ y logging estructurado permiten controlar los principales escenarios de fallo.

Finalmente, las pruebas automatizadas validan los escenarios principales de funcionamiento y resiliencia de la solución.