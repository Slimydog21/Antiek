"""Antiek substrate API.

FastAPI app exposing WebSocket events, typed ingress, trajectory fetch, health.

**Lazy exports:** importing submodules such as ``cascade_routes`` must not
eager-load ``app.py`` (multi-thousand-line factory). Tests and gates that
only need the cascade router were hanging at collection when this package
re-exported ``create_app`` at import time (ANT-H2V).

Run with::

    uvicorn interfaces.research.api.app:app --reload
"""

from __future__ import annotations

import importlib
from typing import Any

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "EmittedEventResponse": (".app", "EmittedEventResponse"),
    "HealthResponse": (".app", "HealthResponse"),
    "TypedEventEnvelope": (".app", "TypedEventEnvelope"),
    "app": (".app", "app"),
    "create_app": (".app", "create_app"),
    "EventBroadcaster": (".broadcast", "EventBroadcaster"),
    "EventHandler": (".broadcast", "EventHandler"),
    "make_cross_doc_handler": (".cross_doc", "make_cross_doc_handler"),
    "register_cross_doc_handlers": (".cross_doc", "register_handlers"),
    "make_decomposer_handler": (".decomposer", "make_decomposer_handler"),
    "register_decomposer_handlers": (".decomposer", "register_handlers"),
    "make_evidence_retriever_handler": (
        ".evidence_retriever",
        "make_evidence_retriever_handler",
    ),
    "register_evidence_retriever_handlers": (
        ".evidence_retriever",
        "register_handlers",
    ),
    "make_connector_handler": (".connector", "make_connector_handler"),
    "register_connector_handlers": (".connector", "register_handlers"),
    "make_parameter_extractor_handler": (
        ".parameter_extractor",
        "make_parameter_extractor_handler",
    ),
    "register_parameter_extractor_handlers": (
        ".parameter_extractor",
        "register_handlers",
    ),
    "make_synthesizer_handler": (".synthesizer", "make_synthesizer_handler"),
    "register_synthesizer_handlers": (".synthesizer", "register_handlers"),
    "make_grounding_handler": (".grounding", "make_grounding_handler"),
    "register_grounding_handlers": (".grounding", "register_handlers"),
    "make_note_taker_handler": (".note_taking", "make_note_taker_handler"),
    "register_note_taking_handlers": (".note_taking", "register_handlers"),
    "make_distillation_handler": (".wrestling", "make_distillation_handler"),
    "register_wrestling_handlers": (".wrestling", "register_handlers"),
}

__all__ = list(_LAZY_EXPORTS.keys())


def __getattr__(name: str) -> Any:
    spec = _LAZY_EXPORTS.get(name)
    if spec is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    mod_name, attr = spec
    mod = importlib.import_module(mod_name, __name__)
    value = getattr(mod, attr)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))