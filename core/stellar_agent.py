import os
from decimal import Decimal

from stellar_sdk import Asset, Keypair, Network, Server, TransactionBuilder
from stellar_sdk.exceptions import BaseHorizonError

HORIZON_TESTNET_URL = "https://horizon-testnet.stellar.org"
STROOPS_PER_XLM = Decimal("10000000")
MEMO_TEXT_MAX_BYTES = 28


class FondosInsuficientesError(ValueError):
    pass


class HorizonTransactionError(RuntimeError):
    pass


def procesar_pago(task) -> str:
    if task.estado != "verificada":
        raise ValueError(
            f"La tarea {task.pk} no está verificada (estado actual: {task.estado!r})."
        )

    secret = os.environ.get("STELLAR_SECRET_KEY", "").strip()
    if not secret:
        raise ValueError("Falta la variable de entorno STELLAR_SECRET_KEY.")

    horizon_url = os.environ.get("STELLAR_HORIZON_URL", HORIZON_TESTNET_URL).strip()
    server = Server(horizon_url=horizon_url)
    source_keypair = Keypair.from_secret(secret)

    try:
        source_account = server.load_account(source_keypair.public_key)
    except BaseHorizonError as exc:
        raise HorizonTransactionError(_mensaje_horizon(exc)) from exc

    monto = Decimal(task.monto)
    if monto <= 0:
        raise ValueError(f"El monto de la tarea {task.pk} debe ser mayor que cero.")

    saldo = _saldo_nativo(source_account)
    reserva = _margen_reserva(server, source_account)
    fee_stroops = server.fetch_base_fee()
    fee_xlm = Decimal(fee_stroops) / STROOPS_PER_XLM
    requerido = monto + reserva + fee_xlm

    if saldo < requerido:
        raise FondosInsuficientesError(
            f"Saldo XLM insuficiente en la cuenta pagadora: "
            f"disponible={saldo}, requerido={requerido} "
            f"(monto={monto} + reserva={reserva} + fee={fee_xlm})."
        )

    destino = task.worker.direccion_stellar
    memo = _memo_tarea(task.pk)

    try:
        transaction = (
            TransactionBuilder(
                source_account=source_account,
                network_passphrase=Network.TESTNET_NETWORK_PASSPHRASE,
                base_fee=fee_stroops,
            )
            .add_text_memo(memo)
            .append_payment_op(destino, Asset.native(), format(monto, "f"))
            .set_timeout(30)
            .build()
        )
        transaction.sign(source_keypair)
        response = server.submit_transaction(transaction)
    except BaseHorizonError as exc:
        raise HorizonTransactionError(_mensaje_horizon(exc)) from exc

    tx_hash = response.get("hash")
    if not tx_hash:
        raise HorizonTransactionError(
            f"Horizon aceptó la transacción pero no devolvió hash: {response}"
        )
    return tx_hash


def _saldo_nativo(account) -> Decimal:
    """
    stellar-sdk 16.1.0 no expone un getter de saldo.
    load_account() guarda la respuesta de Horizon en account.raw_data
    (GET /accounts/{id}), que incluye balances[].
    """
    if not account.raw_data:
        raise ValueError("Horizon no devolvió datos de la cuenta pagadora.")

    for balance in account.raw_data.get("balances", []):
        if balance.get("asset_type") == "native":
            disponible = Decimal(balance["balance"])
            vendiendo = Decimal(balance.get("selling_liabilities", "0"))
            return disponible - vendiendo

    raise ValueError("Horizon no reportó saldo nativo (XLM) en la cuenta pagadora.")


def _margen_reserva(server: Server, account) -> Decimal:
    """
    Reserva mínima de la cuenta según el ledger actual de Horizon:
    (2 + subentry_count + num_sponsoring - numSponsored) * base_reserve.
    """
    latest = server.ledgers().order(desc=True).limit(1).call()
    record = latest["_embedded"]["records"][0]
    base_reserve = Decimal(record["base_reserve_in_stroops"]) / STROOPS_PER_XLM

    data = account.raw_data or {}
    subentries = int(data.get("subentry_count", 0))
    sponsoring = int(data.get("num_sponsoring", 0))
    sponsored = int(data.get("num_sponsored", 0))
    return (2 + subentries + sponsoring - sponsored) * base_reserve


def _memo_tarea(task_id) -> str:
    memo = f"Pago tarea #{task_id}"
    encoded = memo.encode("utf-8")
    if len(encoded) <= MEMO_TEXT_MAX_BYTES:
        return memo
    return encoded[:MEMO_TEXT_MAX_BYTES].decode("utf-8", errors="ignore")


def _mensaje_horizon(exc: BaseHorizonError) -> str:
    partes = []
    if exc.title:
        partes.append(exc.title)
    if exc.detail:
        partes.append(exc.detail)
    if exc.extras:
        codes = exc.extras.get("result_codes")
        if codes:
            partes.append(f"result_codes={codes}")
        if exc.extras.get("reason"):
            partes.append(str(exc.extras["reason"]))
    if not partes:
        partes.append(exc.message or str(exc))
    return "Horizon rechazó la transacción: " + " | ".join(partes)
