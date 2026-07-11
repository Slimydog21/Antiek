"""Pure persona-seeding contracts for perspective-conditioned gathering."""

from .derive import GroundingFact, Persona, derive_personas, grounding_facts
from .descriptors import (
    BudgetSlice,
    SubRunDescriptor,
    build_sub_run_descriptors,
    parse_sub_run_descriptor,
    parse_sub_run_descriptors,
)
from .questions import PersonaQuestions, QuestionGenerator, generate_questions

__all__ = [
    "BudgetSlice", "GroundingFact", "Persona", "PersonaQuestions", "QuestionGenerator",
    "SubRunDescriptor", "build_sub_run_descriptors", "derive_personas", "generate_questions",
    "grounding_facts", "parse_sub_run_descriptor", "parse_sub_run_descriptors",
]
