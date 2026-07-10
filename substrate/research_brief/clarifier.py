"""Pure clarifier orchestration; generators are always caller-injected."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace

from .model import ResearchBrief

QuestionGenerator = Callable[[str], Sequence[str]]


def clarifying_questions(raw_prompt: str, generator: QuestionGenerator) -> tuple[str, ...]:
    """Return 2–3 questions; other counts are rejected.

    Two to three mirrors shipped research flows: more feels like interrogation,
    while fewer defeats a dedicated clarification stage.
    """
    if not raw_prompt.strip():
        raise ValueError("raw_prompt is required")
    questions = tuple(question.strip() for question in generator(raw_prompt) if question.strip())
    if not 2 <= len(questions) <= 3:
        raise ValueError("generator must return 2 or 3 non-empty questions")
    return questions


def fold_answers(
    brief: ResearchBrief,
    questions: Sequence[str],
    answers: Mapping[str, str],
) -> ResearchBrief:
    """Fold answered clarification slots into the brief's editable scope."""
    missing = [question for question in questions if not answers.get(question, "").strip()]
    if missing:
        raise ValueError("every clarifying question requires an answer")
    additions = "\n".join(f"{q}: {answers[q].strip()}" for q in questions)
    return replace(brief, scope=f"{brief.scope.rstrip()}\n\nClarifications:\n{additions}")
