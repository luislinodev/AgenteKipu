#!/usr/bin/env python
"""Genera un keypair de Testnet y lo fondea con Friendbot. No usa Django."""

import sys

import requests
from stellar_sdk import Keypair, Server

FRIENDBOT_URL = "https://friendbot.stellar.org"
HORIZON_TESTNET_URL = "https://horizon-testnet.stellar.org"


def main() -> int:
    keypair = Keypair.random()
    public_key = keypair.public_key
    secret_key = keypair.secret

    print(f"clave pública: {public_key}")
    print(f"clave secreta: {secret_key}")

    try:
        response = requests.get(FRIENDBOT_URL, params={"addr": public_key}, timeout=30)
    except requests.RequestException as exc:
        print(f"fondeo: error de red al llamar a Friendbot ({exc})", file=sys.stderr)
        return 1

    if not response.ok:
        print(
            f"fondeo: Friendbot rechazó la cuenta (HTTP {response.status_code}): {response.text}",
            file=sys.stderr,
        )
        return 1

    payload = response.json()
    tx_hash = payload.get("hash", "—")

    server = Server(horizon_url=HORIZON_TESTNET_URL)
    account = server.load_account(public_key)
    saldo = "—"
    for balance in (account.raw_data or {}).get("balances", []):
        if balance.get("asset_type") == "native":
            saldo = balance.get("balance")
            break

    print("fondeo: ok")
    print(f"hash Friendbot: {tx_hash}")
    print(f"saldo XLM: {saldo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
