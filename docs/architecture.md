# Arquitectura — AgentePago

## Flujo
1. Se crea una Task con monto y dirección Stellar del trabajador.
2. Al pasar a estado "verificada", una signal de Django dispara el agente.
3. El agente valida la regla (¿verificada? ¿fondos suficientes?) y si se 
   cumple, construye y firma la transacción con stellar-sdk.
4. Se envía a Horizon Testnet; el hash se guarda en Payment y se muestra 
   en el dashboard.

## Modelo de datos
- Worker: nombre, direccion_stellar
- Task: titulo, descripcion, monto, worker (FK), estado
- Payment: task (FK 1-1), tx_hash, monto, fecha, estado

## Decisión de stack
[pega tu tabla de la sección 2 del plan, sin la columna de "trade-off 
narrativo" si quieres que quede técnico]

## Fuera de alcance (v1)
- Sin Celery/cola de tareas — ejecución síncrona
- Sin contrato Soroban — pagos nativos vía SDK (evaluar agregar si 
  sobra tiempo, ver riesgos)