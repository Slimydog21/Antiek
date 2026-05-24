

# SPR-03: role-shape metadata (see substrate/role_shape.py)
from substrate.role_shape import RoleMetadata

__role_metadata__ = RoleMetadata.crew(
    expected_input_tokens=6000,
    expected_output_tokens=1500,
    spawn_pattern_doc=(
        'User-facing conversational role; multi-turn by nature. Prompt-only role (program.md). State lives in the chat transcript the caller maintains.'
    ),
)
