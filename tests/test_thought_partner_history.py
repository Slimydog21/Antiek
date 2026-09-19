"""compose_thought_partner_prompt multi-turn history."""
from roles.thought_partner.prompt import MAX_HISTORY_TURNS, compose_thought_partner_prompt


def test_compose_includes_conversation_history():
    text = compose_thought_partner_prompt(
        user_prompt="what next?",
        selected_notes=[{"note_id": "n1", "note_text": "alpha"}],
        conversation_history=[
            {"question": "first?", "answer": "first reply"},
            {"question": "second?", "answer": "second reply"},
        ],
    )
    assert "CONVERSATION SO FAR:" in text
    assert "User: first?" in text
    assert "Thought partner: first reply" in text
    assert "USER PROMPT: what next?" in text
    assert "NOTE n1: alpha" in text


def test_compose_bounds_history():
    hist = [
        {"question": f"q{i}", "answer": f"a{i}"}
        for i in range(MAX_HISTORY_TURNS + 5)
    ]
    text = compose_thought_partner_prompt(
        user_prompt="now",
        selected_notes=[],
        conversation_history=hist,
    )
    assert "User: q0" not in text
    assert f"User: q{5}" in text
