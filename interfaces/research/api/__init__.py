"""Antiek substrate API.

FastAPI app exposing:
- WebSocket /ws/events — live event tail
- POST /events/typed — typed event ingress from the reading UI
- GET /trajectory/{investigation_id} — bulk fetch
- GET /health — version probe

Run with::

    uvicorn interfaces.research.api.app:app --reload

The TS reading surface at ``apps/reading/`` consumes this app via the
generated types in ``apps/reading/src/generated/types.ts`` (produced by
``tools/codegen/emit_types.py``).
"""

from .app import (
    EmittedEventResponse,
    HealthResponse,
    TypedEventEnvelope,
    app,
    create_app,
)
from .broadcast import EventBroadcaster, EventHandler
from .cross_doc import (
    make_cross_doc_handler,
    register_handlers as register_cross_doc_handlers,
)
from .decomposer import (
    make_decomposer_handler,
    register_handlers as register_decomposer_handlers,
)
from .evidence_retriever import (
    make_evidence_retriever_handler,
    register_handlers as register_evidence_retriever_handlers,
)
from .connector import (
    make_connector_handler,
    register_handlers as register_connector_handlers,
)
from .parameter_extractor import (
    make_parameter_extractor_handler,
    register_handlers as register_parameter_extractor_handlers,
)
from .synthesizer import (
    make_synthesizer_handler,
    register_handlers as register_synthesizer_handlers,
)
from .grounding import (
    make_grounding_handler,
    register_handlers as register_grounding_handlers,
)
from .note_taking import (
    make_note_taker_handler,
    register_handlers as register_note_taking_handlers,
)
from .wrestling import (
    make_distillation_handler,
    register_handlers as register_wrestling_handlers,
)

__all__ = [
    "create_app",
    "app",
    "EventBroadcaster",
    "EventHandler",
    "TypedEventEnvelope",
    "EmittedEventResponse",
    "HealthResponse",
    "make_distillation_handler",
    "register_wrestling_handlers",
    "make_grounding_handler",
    "register_grounding_handlers",
    "make_note_taker_handler",
    "register_note_taking_handlers",
    "make_cross_doc_handler",
    "register_cross_doc_handlers",
    "make_decomposer_handler",
    "register_decomposer_handlers",
    "make_evidence_retriever_handler",
    "register_evidence_retriever_handlers",
    "make_parameter_extractor_handler",
    "register_parameter_extractor_handlers",
    "make_connector_handler",
    "register_connector_handlers",
    "make_synthesizer_handler",
    "register_synthesizer_handlers",
]
