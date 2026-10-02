"""The sentence-transformer provider COUNTS silent window truncation and
warns once (audit wave 3, #2). No model download: the wrapped model is a
stub with a 4-token window and a whitespace tokenizer."""

from __future__ import annotations

from processing.embedding.embed import SentenceTransformerEmbedding


class _Tokenizer:
    def __call__(self, text, add_special_tokens=True, truncation=False):
        return {"input_ids": list(range(len(text.split()) + (2 if add_special_tokens else 0)))}


class _StubModel:
    max_seq_length = 4
    tokenizer = _Tokenizer()

    def get_sentence_embedding_dimension(self):
        return 3

    def encode(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


def _provider() -> SentenceTransformerEmbedding:
    p = SentenceTransformerEmbedding.__new__(SentenceTransformerEmbedding)
    p._model = _StubModel()
    p.dimension = 3
    p._model_name = "stub"
    p.encode_count = 0
    p.truncated_count = 0
    p._warned_truncation = False
    return p


def test_truncation_is_counted_and_warned_once(capsys):
    p = _provider()
    assert p.encode("one two") == [0.1, 0.2, 0.3]        # 4 tokens incl. specials: fits
    assert p.encode("one two three four five")           # 7 > 4: truncated
    assert p.encode("six seven eight nine ten eleven")   # truncated again
    assert (p.encode_count, p.truncated_count) == (3, 2)
    assert abs(p.truncation_ratio - 2 / 3) < 1e-9
    err = capsys.readouterr().err
    assert err.count("exceeds the model window of 4") == 1  # once, not per chunk


def test_control_no_truncation_no_warning(capsys):
    p = _provider()
    p.encode("a")
    p.encode("b c")
    assert (p.encode_count, p.truncated_count, p.truncation_ratio) == (2, 0, 0.0)
    assert "exceeds the model window" not in capsys.readouterr().err
