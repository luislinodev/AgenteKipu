# Arquitectura — AgenteKipu

Agente que paga en Stellar testnet solo cuando un tercero independiente del recolector confirma la entrega. Caso: recolección de aceite usado. El trigger no es el reporte del recolector ni una IA "decidiendo"; son dos reglas verificables: confirmación del punto + chequeo de consistencia de Gemini.

## Actores

| Actor | Rol | Cuenta en el sistema |
|---|---|---|
| Operador | Crea rutas (hoy en `/admin/`), reenvía el link de confirmación, ve `motivo_no_pago` | Sí — panel `/operador/` |
| Recolector | Recorre la ruta y sube una foto por punto | Sí — panel `/recolector/` |
| Proveedor de punto | Dueño del local. Confirma Sí/No | No — `/confirmar/<token>/` sin login |

El link de confirmación se muestra **solo al Operador** (`url_confirmacion` en detalle de ruta/punto). El Recolector no lo recibe en el contexto ni en el template. Si lo viera, podría confirmarse a sí mismo.

## Flujo construido

1. El Operador tiene una `Ruta` asignada a un `Recolector` (asignación directa).
2. El Recolector, en cada `Punto`, sube foto + cantidad. Eso genera `token_confirmacion` (`secrets.token_urlsafe(32)`) y llama a Gemini en el mismo request.
3. Gemini (`gemini_check.py`, `gemini-2.5-flash`) cuenta baldes; consistente si `|conteo − reportado| ≤ 1`. Si falla, la foto queda y se guarda `gemini_error`.
4. El Operador copia `/confirmar/<token>/` y lo reenvía por WhatsApp. El Recolector no ve ese URL.
5. El dueño del local responde Sí/No. Un segundo POST no pisa la decisión (`update()` acotado; 0 filas → relectura).
6. El agente paga solo si confirmó Sí **y** Gemini es consistente:
   - `Payment` se crea `pendiente` **antes** de Horizon (unique de `punto` como exclusión).
   - Éxito: `tx_hash` + `completado`; Punto a `pagado` con `.update()`.
   - Cualquier excepción: `payment.delete()`; el motivo queda en `Punto.motivo_no_pago`.
7. Si No, Gemini inconsistente/error, o fallo de fondos/Horizon: `en_revision` y no se paga solo.

```mermaid
flowchart LR
    A[Operador crea Ruta<br/>y asigna Recolector] --> B[(Base de datos<br/>Django ORM)]
    C[Recolector sube foto<br/>en un Punto] --> B
    C --> D[API Gemini:<br/>chequeo de consistencia]
    D --> B
    C --> E[Sistema genera link único<br/>→ panel del Operador]
    E --> F[Operador reenvía el link<br/>al dueño del Punto por WhatsApp]
    F --> G[Punto confirma Sí/No<br/>sin necesidad de cuenta]
    G --> B
    B --> H{Agente revisa:<br/>¿confirmó el Punto?<br/>¿Gemini es consistente?}
    H -- Sí --> I[stellar-sdk Python:<br/>construye y firma TX]
    I --> J[Horizon Testnet Stellar]
    J --> K[Payment registrado<br/>en Django + hash TX]
    H -- No --> L[Queda en revisión manual,<br/>no se paga solo]
```

## Modelo de datos (flujo activo)

| Modelo | Qué guarda |
|---|---|
| **Operador** | `user` (OneToOne), `nombre` |
| **Recolector** | `user` (OneToOne), `nombre`, `direccion_stellar` |
| **Ruta** | `operador`, `recolector`, `nombre`, `fecha` |
| **Punto** | `ruta`, `nombre_local`, `monto`, foto, cantidad, Gemini, `token_confirmacion`, `confirmacion` Sí/No, estado (`pendiente` / `confirmado` / `en_revision` / `pagado`), `motivo_no_pago` |
| **Payment** | OneToOne a **Punto** (no a Task), `tx_hash`, `monto`, `fecha`, estado |

`Worker` y `Task` siguen en el schema como resto del prototipo; **no están en el flujo activo**. El dashboard ya no lista tareas.

## Dónde vive cada pieza

| Pieza | Archivo |
|---|---|
| Firma y envío Stellar | `core/stellar_agent.py` (sin cambios de contrato: duck-type `estado="verificada"`, `monto`, `worker.direccion_stellar`, `pk`) |
| Trigger del pago | `core/signals.py` → `intentar_pago_si_corresponde`; la vista pública lo llama a mano porque `update()` no dispara `post_save` |
| Gemini | `core/gemini_check.py` |
| Paneles y confirmación | `core/views.py` |
| Scripts testnet | `scripts/crear_wallet_testnet.py`, `scripts/verificar_pago.py` |

## Permisos

- Recolector: queryset `ruta__recolector=…`. 404 si el punto no es suyo. Sin token en el template.
- Operador: queryset `ruta__operador__user=request.user` (o equivalente). 404 si la ruta/punto es de otro.
- Confirmación pública: autorización = token; POST solo si `confirmacion is None` y estado `pendiente`/`confirmado`.
- Admin `Punto` y `Payment`: no superuser → mismo recorte por operador. Superuser ve todo.

## Stack (como está)

| Decisión | Por qué |
|---|---|
| Django + SQLite | Sin Postgres. `select_for_update` no bloquea filas aquí; la exclusión de pago es el unique de `Payment.punto`. |
| `stellar-sdk` Python | Pagos nativos a Horizon Testnet. |
| API de Gemini (`google-genai`) | Consistencia de la foto; timeout 15 s; no dispara el pago. |
| Templates Django + CSS | Sin React. |
| Sin GPS, marketplace, Celery, Twilio | El Operador reenvía el link por WhatsApp personal. |

## Checklist de lo construido

- [x] Modelos Operador, Recolector, Ruta, Punto, Payment (FK a Punto)
- [x] Migraciones `0003` / `0004`
- [x] Signal de pago: Sí + Gemini consistente; INSERT `pendiente` antes de Horizon; `delete` si falla
- [x] Sin botón manual de verificar
- [x] Subida de foto del Recolector + `gemini_check.py`
- [x] Token `secrets.token_urlsafe(32)` y página `/confirmar/<token>/`
- [x] Panel Operador con URL lista para copiar; Recolector sin el link
- [x] Admin de Punto/Payment acotado al operador (salvo superuser)
- [x] `motivo_no_pago` distingue No / Gemini / fondos u Horizon
- [x] `stellar_agent.py` y `scripts/` intactos respecto al prototipo Stellar

## Fuera de alcance (v1)

- Sin Celery — Gemini y el pago son síncronos
- Sin contrato Soroban
- Sin GPS ni marketplace de rutas
- Sin Twilio / WhatsApp Business
- Worker/Task no forman parte del flujo (schema legado)
- Alta de rutas/puntos: `/admin/` (el panel del Operador es lectura + copia del link)
