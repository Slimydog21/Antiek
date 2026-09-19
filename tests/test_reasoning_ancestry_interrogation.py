from types import SimpleNamespace

import pytest

from substrate.research_artifact.reasoning_ancestry_interrogation import (
    ReasoningAncestryInterrogationConflict,
    _closure,
)


def _node(ordinal: int, parents: tuple[int, ...], children: tuple[int, ...]):
    return SimpleNamespace(
        iteration=SimpleNamespace(ordinal=ordinal),
        parent_ordinals=parents,
        child_ordinals=children,
    )


def test_terminal_union_deduplicates_overlapping_ancestors_in_canonical_order():
    nodes = (
        _node(1, (), (3, 4)),
        _node(2, (), (3,)),
        _node(3, (1, 2), (5,)),
        _node(4, (1,), ()),
        _node(5, (3,), ()),
    )

    closure = _closure(nodes, (4, 5))

    assert [node.iteration.ordinal for node in closure] == [1, 2, 3, 4, 5]


@pytest.mark.parametrize("selected", [(5, 4), (4, 4), (), (3,), (6,), (True,)])
def test_terminal_selection_rejects_order_duplicates_empty_nonterminal_missing_and_bool(
    selected,
):
    nodes = (
        _node(1, (), (3, 4)),
        _node(2, (), (3,)),
        _node(3, (1, 2), (5,)),
        _node(4, (1,), ()),
        _node(5, (3,), ()),
    )

    with pytest.raises(ReasoningAncestryInterrogationConflict):
        _closure(nodes, selected)
