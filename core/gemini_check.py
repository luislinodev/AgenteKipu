"""Chequeo de consistencia de la foto. No dispara el pago."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

MODELO_GEMINI = "gemini-3.6-flash"
TOLERANCIA_BALDES = 1
TIMEOUT_MS = 15_000
PROMPT = (
    "Cuenta cuántos baldes o bidones ves en esta imagen. "
    "Responde solo con un número entero, sin texto extra."
)


@dataclass(frozen=True)
class ResultadoGemini:
    cantidad: int | None
    consistente: bool | None
    respuesta: str
    error: str


def chequear_consistencia(
    *,
    foto_bytes: bytes,
    mime_type: str,
    cantidad_reportada: int | None,
) -> ResultadoGemini:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return ResultadoGemini(
            cantidad=None,
            consistente=None,
            respuesta="",
            error="Falta GEMINI_API_KEY.",
        )
    if not foto_bytes:
        return ResultadoGemini(
            cantidad=None,
            consistente=None,
            respuesta="",
            error="La foto está vacía.",
        )

    try:
        client = genai.Client(
            api_key=api_key,
            http_options={"timeout": TIMEOUT_MS},
        )
        response = client.models.generate_content(
            model=MODELO_GEMINI,
            contents=[
                PROMPT,
                types.Part.from_bytes(data=foto_bytes, mime_type=mime_type),
            ],
        )
        texto = (response.text or "").strip()
    except Exception as exc:
        logger.exception("Falló la llamada a Gemini.")
        return ResultadoGemini(
            cantidad=None,
            consistente=None,
            respuesta="",
            error=str(exc),
        )

    cantidad = _parsear_cantidad(texto)
    if cantidad is None:
        return ResultadoGemini(
            cantidad=None,
            consistente=None,
            respuesta=texto,
            error="Gemini no devolvió un entero parseable.",
        )

    consistente = None
    if cantidad_reportada is not None:
        consistente = abs(cantidad - cantidad_reportada) <= TOLERANCIA_BALDES

    return ResultadoGemini(
        cantidad=cantidad,
        consistente=consistente,
        respuesta=texto,
        error="",
    )


def _parsear_cantidad(texto: str) -> int | None:
    match = re.search(r"-?\d+", texto)
    if not match:
        return None
    cantidad = int(match.group(0))
    if cantidad < 0:
        return None
    return cantidad
