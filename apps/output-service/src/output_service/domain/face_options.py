"""Opciones de selección de rostro para la desambiguación multi-rostro (ADR-0016). Puro (stdlib).

El reportante recibe N miniaturas numeradas y un **botón de opciones** para elegir cuál es la persona.
Esta capa decide la presentación (qué opciones y qué primitiva de WhatsApp usar), sin tocar la red.

INVARIANTE (no romper): los `label` deben seguir siendo parseables por
`chatbot_gateway.domain.disambiguation.parse_selection` — cuando el usuario toca una opción, Meta
devuelve su `title` (= `label`) como texto y el chatbot lo resuelve: `"Rostro 2"` → índice 1,
`"Ninguno"` → `none_of_these`. Si cambian estos textos, actualizar `parse_selection` en paralelo.
"""
from __future__ import annotations

from dataclasses import dataclass

# WhatsApp Cloud API: los reply buttons permiten como máximo 3 opciones. Con N rostros + "Ninguno",
# caben en botones solo si N <= 2; con N >= 3 se usa una lista ("Ver opciones", hasta 10 filas).
_MAX_BUTTON_FACES = 2

NONE_LABEL = "Ninguno"
NONE_ID = "face:none"


@dataclass(frozen=True)
class FaceOption:
    id: str       # id estable para el reply de Meta (no se le muestra al usuario)
    label: str    # título visible y parseable por parse_selection


def build_face_options(n_faces: int) -> list[FaceOption]:
    """`["Rostro 1".."Rostro N", "Ninguno"]`. `n_faces` es el número de rostros candidatos (≥2)."""
    options = [FaceOption(id=f"face:{i}", label=f"Rostro {i + 1}") for i in range(n_faces)]
    options.append(FaceOption(id=NONE_ID, label=NONE_LABEL))
    return options


def use_buttons(n_faces: int) -> bool:
    """True → reply buttons (≤2 rostros); False → list message (≥3 rostros)."""
    return n_faces <= _MAX_BUTTON_FACES
