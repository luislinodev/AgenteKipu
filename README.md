# AgenteKipu

**Stellar Odyssey Perú · Track: AI Agents & Automated Workflows**

Un agente que paga en Stellar testnet **solo cuando un tercero independiente del recolector confirma la entrega** — nunca por el reporte del propio recolector.

Aplicado a la recolección de aceite usado: el fraude ocurre porque el recolector controla toda la información que le llega al dueño del negocio. El agente no "decide"; aplica dos reglas verificables: confirmación del punto de recolección + chequeo de consistencia de una foto.

## El problema

Luis trabajaba para José recolectando baldes de aceite usado en su ruta diaria. José pagaba una comisión estándar, más un bono y un precio mayor por balde si Luis lograba acumular y entregar volúmenes grandes — más de 20 baldes juntos.

Luis compraba más baldes de los que reportaba, o desviaba parte de lo recolectado, y los escondía de a dos en la casa de su suegra. Cuando llegaba a los 20, se los "vendía" a José como si fuera un gran logro comercial — un cliente masivo conseguido — cobrando precio sobrevaluado, comisión y bono de volumen sobre mercadería que ya le pertenecía al negocio.

Se descubrió por casualidad: un día Luis salió a la ruta con un asistente nuevo, pero en vez de recolectar se fue a dormir a la casa de su suegra y cargó desde ahí los baldes ya escondidos. El asistente, por miedo a verse involucrado en algo ilegal, le contó todo a José.

El sistema debía haber hecho innecesaria esa casualidad: el pago no puede depender de la palabra de quien tiene el incentivo — en este caso, un bono por volumen — de mentir.

## La solución

Hay tres actores. El **Operador** crea la ruta. El **Recolector** la recorre y sube una foto en cada punto. El **Proveedor de punto** (el restaurante, taller o negocio del que se recoge) confirma o niega la entrega **sin crear cuenta**, con un link único.

1. El **Operador** crea una `Ruta`, la asigna a un recolector y define los `Puntos` (local, monto en XLM) — hoy esto se hace desde `/admin/`, por decisión de scope, no porque falte terminar: construir una UI propia de creación de rutas no suma al mecanismo anti-fraude, así que no se justifica el tiempo de ingeniería. El panel `/operador/` es para **consultar** el historial y copiar el link de confirmación, no para crear rutas.
2. El **Recolector**, desde `/recolector/`, sube en cada punto una foto de los baldes recogidos junto con la cantidad que él reporta. Esa subida dispara el resto del flujo — no hay GPS: es falsificable desde el propio navegador y no resuelve el problema real.
3. Al subir la foto, ocurren dos cosas:
   - La foto va a la **API de Gemini** con un prompt acotado (contar baldes). Es un **chequeo de consistencia de respaldo**, no la prueba principal — una foto se puede preparar de antemano y no se presenta como prueba infalible. Se considera consistente si `|conteo de Gemini − cantidad reportada| ≤ 1`. Gemini **no** cierra el link de confirmación ni pone el punto en revisión por sí solo: si falla o la diferencia es mayor, el dato queda guardado y el pago no saldrá solo *después* de que el local responda.
   - El sistema genera un token secreto y un link único de confirmación (`/confirmar/<token>/`) y se lo muestra **solo al Operador**. El Operador se lo reenvía al Proveedor de punto por su WhatsApp — no hay integración con Twilio ni envío automático. Si el link se le mostrara al Recolector, podría confirmarse a sí mismo y el mecanismo colapsaría — es el hueco que detectamos y cerramos en el diseño.
4. El **Proveedor de punto** abre el link, sin cuenta, y responde Sí/No: ¿se recogieron esos baldes en tu local? Puede responder **aunque Gemini haya fallado o no cuadre**. **La respuesta es de una sola vez** — un segundo intento sobre el mismo token no cambia la decisión ya registrada. Esto cierra un vector de manipulación: nadie puede reabrir la confirmación para revertir un "No" después de que el recolector hable con el dueño del punto.
5. Recién entonces `signals.py` combina las dos señales y, si ambas cumplen, llama a `stellar_agent.py` para firmar y enviar el pago: (a) el punto confirmó "Sí" y (b) Gemini marcó consistente. Si el punto dice "No", Gemini no cuadra, faltan fondos o Horizon rechaza la transacción, el punto queda **en revisión** con un `motivo_no_pago` registrado — no se paga solo. El panel `/operador/` muestra ese motivo; no tiene botón para pagar ni desbloquear. Cualquier decisión posterior es fuera del agente (p. ej. `/admin/`). Un pago ya enviado en Stellar no lo puede revertir nadie, ni el propio equipo.
6. El historial se parte en dos modelos: **Punto** guarda la foto, la respuesta de Gemini, la confirmación del local y `motivo_no_pago`; **Payment** guarda el hash de la transacción, el monto, la fecha y el estado del pago. El panel `/operador/` consulta estado, Gemini, confirmación y motivo; la foto y el hash quedan en media / `/admin/`.

**Qué sí cubre:** que el recolector desvíe volumen o infle un reporte para alcanzar un umbral de bono, sin que quede registrado en ningún punto real — porque el pago depende de una confirmación que él no controla.

**Qué no promete:** no es una prueba forense. Es la automatización de una decisión que antes dependía enteramente de la palabra del recolector.

## Por qué esto no es "otra app de logística"

Confirmación por un tercero no es una idea nueva — es el patrón de cualquier sistema de custodia (escrow) desde hace siglos, y es lo que hacen internamente muchas apps de delivery. Lo que sí distingue a AgenteKipu es lo que pasa *después* de la confirmación: el pago se ejecuta de forma autónoma e irreversible en Stellar, sin que un backend centralizado — ni siquiera el propio equipo — pueda revertirlo o editarlo en silencio una vez que se cumplen las condiciones. El Proveedor de punto actúa como un oráculo humano mínimo; la transacción en Stellar es la regla ejecutada, no una planilla que alguien puede modificar después.

**Alcance:** el aceite usado es el caso piloto, con un fraude real y documentado detrás. La misma estructura — recolector que cobra por volumen autorreportado, de puntos de origen informales sin sistema propio — aplica en principio a otras redes de acopio (reciclables, pequeños productores), pero este proyecto no tiene evidencia de fraude documentada fuera del caso del aceite, y no se presenta como una solución genérica de logística.

## Arquitectura

Detalle en [`docs/architecture.md`](docs/architecture.md).

```mermaid
flowchart LR
    A[Operador crea Ruta y Puntos<br/>vía /admin/] --> B[(Base de datos<br/>Django ORM)]
    C[Recolector sube foto + cantidad<br/>en /recolector/] --> B
    C --> D[API Gemini:<br/>chequeo de consistencia<br/>|conteo − reportado| ≤ 1]
    D --> B
    C --> E[Sistema genera token y link único<br/>/confirmar/token/ → se lo muestra al Operador en /operador/]
    E --> F[Operador reenvía el link<br/>al Proveedor de punto por WhatsApp]
    F --> G[Punto confirma Sí/No una sola vez<br/>sin necesidad de cuenta]
    G --> B
    B --> H{Agente revisa:<br/>¿confirmó el Punto?<br/>¿Gemini es consistente?}
    H -- Sí --> I[stellar-sdk Python:<br/>construye y firma TX]
    I --> J[Horizon Testnet Stellar]
    J --> K[Pago registrado<br/>en Payment + hash TX]
    H -- No --> L[Queda en revisión<br/>con motivo_no_pago]
```

La construcción, firma y envío de la transacción viven en `core/stellar_agent.py` (no valida confirmación ni Gemini: recibe monto y destino). Las reglas de si corresponde pagar viven en `core/signals.py`. El chequeo de Gemini vive en `core/gemini_check.py`; la vista `subir_foto` lo llama en el mismo request de la subida. El agente firma con una clave de servidor en `.env`; no usa Freighter — el punto del track es que el agente firma solo, sin intervención humana.

## Uso de la API de Gemini

Este proyecto usa la **API de Gemini** (Google AI Studio) como **chequeo de consistencia de la foto** del punto de recolección: un conteo acotado que se compara con lo reportado por el Recolector. Se considera consistente si `|conteo de Gemini − cantidad reportada| ≤ 1`.

Gemini **no** es la señal que dispara el pago, **no** cierra `/confirmar/<token>/` y **no** se presenta como detector de fraude. La señal decisiva es la confirmación Sí/No, de una sola vez, del Proveedor de punto. Si Gemini falla o el conteo no cuadra con ese margen, el local igual puede responder; el agente combina ambas señales al decidir el pago y, si no cierran, el punto queda en revisión y el pago no sale solo.

## Stack

| Pieza | Elección |
|---|---|
| Backend | Django + SQLite |
| Stellar | `stellar-sdk` (Python), pagos nativos en Horizon Testnet |
| IA | API de Gemini (consistencia de la foto) |
| Frontend | Templates Django + CSS |
| Explorador | [stellar.expert testnet](https://stellar.expert/explorer/testnet) |

Fuera de alcance en esta versión: Celery, contratos Soroban, GPS, marketplace de rutas, Twilio / WhatsApp Business.

## Cómo ejecutarlo

Requisitos: Python 3.12+, una cuenta de [Google AI Studio](https://aistudio.google.com/) si vas a probar Gemini.

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Completa `.env` (nunca subas el archivo real):

```
SECRET_KEY=...
DEBUG=True
STELLAR_SECRET_KEY=           # clave secreta de la cuenta pagadora en testnet
STELLAR_HORIZON_URL=https://horizon-testnet.stellar.org
GEMINI_API_KEY=               # Google AI Studio; solo para el chequeo de consistencia
```

El agente siempre firma para testnet (`Network.TESTNET_NETWORK_PASSPHRASE`). Lee `STELLAR_HORIZON_URL`.

Genera y fondea una wallet de testnet (imprime clave pública y secreta; guarda la secreta en `.env`):

```bash
python scripts/crear_wallet_testnet.py
```

Levanta la app:

```bash
python manage.py migrate
python manage.py runserver
```

Abre [http://127.0.0.1:8000/](http://127.0.0.1:8000/). El admin está en `/admin/`.

Para consultar un hash en Horizon:

```bash
python scripts/verificar_pago.py <tx_hash>
```

## Evidencia en Stellar Testnet

Tres pagos completados de punta a punta (foto → Gemini → confirmación del punto → pago automático), verificables en el explorador:

| Punto | Ruta | Monto | Estado | Tx hash |
|---|---|---|---|---|
| Restaurante Entrepierna | ruta_alberto_003 | 1 XLM | Completado | `db4368b57800f2d971194cbdc5e31efc375bfc8aedba904a9917bf729b080f7a` |
| Restaurante Alita | ruta_alberto_002 | 1 XLM | Completado | `607714788c08de87a1bdfc31296b40a415510212191b6802a0cd545c35b47adf` |
| Restaurante Pierna | ruta_alberto_001 | 1 XLM | Completado | `a4826588dc4a4f4e70f67fc16ddb93d7bd3bc3ff3abf92702eee7d7c4dff870c` |

- Explorador: `https://stellar.expert/explorer/testnet/tx/<hash>`

## Qué se construyó durante el evento

- Repositorio, licencia MIT y arquitectura documentada.
- Agente Stellar en Python (`stellar_agent.py`): firma y envía un pago nativo a Horizon Testnet; el hash queda registrado. Las reglas (Sí + Gemini consistente) viven en `signals.py`.
- App Django (dashboard, modelos, signals) que soporta el flujo completo de verificación y pago.
- Scripts de testnet: crear/fondear wallet con Friendbot y verificar un hash.
- Flujo de punta a punta funcionando: foto → Gemini → link de confirmación → confirmación del punto → pago automático — con tres transacciones completadas en Horizon Testnet (ver Evidencia arriba).
- Diseño del flujo AgenteKipu: confirmación de tercero sin login + Gemini como respaldo, no como prueba principal.

## Licencia

[MIT](LICENSE)