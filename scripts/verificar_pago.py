#!/usr/bin/env python
"""Consulta un hash de transacción en Horizon Testnet. No usa Django."""

import sys

from stellar_sdk import Server
from stellar_sdk.exceptions import BadRequestError, NotFoundError

HORIZON_TESTNET_URL = "https://horizon-testnet.stellar.org"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("uso: python scripts/verificar_pago.py <tx_hash>", file=sys.stderr)
        return 2

    tx_hash = argv[1].strip()
    server = Server(horizon_url=HORIZON_TESTNET_URL)

    try:
        tx = server.transactions().transaction(tx_hash).call()
    except NotFoundError:
        print("existe: no")
        print(f"hash: {tx_hash}")
        return 1
    except BadRequestError as exc:
        print("existe: no")
        print(f"hash: {tx_hash}")
        print(f"motivo: hash inválido ({exc.detail or exc.title})")
        return 1

    print("existe: sí")
    print(f"hash: {tx.get('hash', tx_hash)}")
    print(f"exitosa: {tx.get('successful')}")
    print(f"origen (source_account): {tx.get('source_account')}")

    payments = server.payments().for_transaction(tx_hash).call()
    records = payments.get("_embedded", {}).get("records", [])
    if not records:
        print("pagos: ninguno en esta transacción")
        return 0

    for i, op in enumerate(records, start=1):
        tipo = op.get("type")
        print(f"operación {i} ({tipo}):")
        if tipo == "payment":
            print(f"  monto: {op.get('amount')} ({op.get('asset_type')})")
            print(f"  origen: {op.get('from')}")
            print(f"  destino: {op.get('to')}")
        elif tipo == "create_account":
            print(f"  monto: {op.get('starting_balance')} (native)")
            print(f"  origen: {op.get('funder')}")
            print(f"  destino: {op.get('account')}")
        else:
            print(f"  detalle: {op}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
