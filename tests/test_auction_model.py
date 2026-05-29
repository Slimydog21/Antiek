"""Learned value scorer tests (SPR-10 M2).

train → serialize → load → predict round-trip; calibration measured;
pure-CPU inference; deterministic retrain."""

from __future__ import annotations

import math

import pytest

from substrate.ad_inventory.auction_features import FEATURE_DIM, FEATURE_SCHEMA_VERSION
from substrate.ad_inventory.auction_model import (
    AuctionModel,
    expected_calibration_error,
    reliability_table,
    train_model,
)


def _synthetic_dataset(
    n: int = 400,
) -> tuple[list[tuple[float, ...]], list[float]]:
    """A deterministic separable-ish dataset over FEATURE_DIM features.

    The label is a logistic function of a known 'true' weight vector plus a
    deterministic pseudo-noise, so a well-fit model should recover lift and be
    calibratable. No randomness module — uses a fixed LCG for reproducibility."""
    true_w = [0.0, 1.5, 1.0, 0.8, 0.6, 0.9, 0.3, 0.2, 0.1]
    assert len(true_w) == FEATURE_DIM
    feats: list[tuple[float, ...]] = []
    labels: list[float] = []
    state = 12345
    for _ in range(n):
        x = [1.0]
        row_feats = []
        for _j in range(FEATURE_DIM - 1):
            state = (1103515245 * state + 12345) % (2**31)
            row_feats.append((state % 1000) / 1000.0)
        x.extend(row_feats)
        xt = tuple(x)
        z = sum(w * xi for w, xi in zip(true_w, xt, strict=True))
        p = 1.0 / (1.0 + math.exp(-(z - 2.0)))  # shift so labels span (0,1)
        feats.append(xt)
        labels.append(p)
    return feats, labels


def test_train_serialize_load_predict_round_trip() -> None:
    feats, labels = _synthetic_dataset()
    model = train_model(feats, labels)
    blob = model.to_json()
    reloaded = AuctionModel.from_json(blob)
    # Predictions identical after round-trip.
    for x in feats[:20]:
        assert model.predict(x) == reloaded.predict(x)
    # Artifact is small (a handful of floats), not a megabyte blob.
    assert len(blob) < 2000


def test_predict_is_bounded_probability() -> None:
    feats, labels = _synthetic_dataset()
    model = train_model(feats, labels)
    for x in feats:
        p = model.predict(x)
        assert 0.0 <= p <= 1.0


def test_retrain_is_deterministic() -> None:
    feats, labels = _synthetic_dataset()
    a = train_model(feats, labels)
    b = train_model(feats, labels)
    assert a.weights == b.weights
    assert a.calib_a == b.calib_a
    assert a.calib_b == b.calib_b
    assert a.to_json() == b.to_json()  # byte-identical artifact


def test_model_is_calibrated_on_holdout() -> None:
    """Calibration is MEASURED: ECE on a held-out slice is small."""
    feats, labels = _synthetic_dataset(n=600)
    # Train on first 400, evaluate calibration on last 200 (unseen).
    model = train_model(feats[:400], labels[:400])
    bins = reliability_table(model, feats[400:], labels[400:], n_bins=5)
    ece = expected_calibration_error(bins)
    assert ece < 0.12, f"expected-calibration-error too high: {ece}"
    # At least one populated bin shows predicted tracking empirical.
    populated = [b for b in bins if b.count > 0]
    assert populated
    for b in populated:
        assert abs(b.mean_predicted - b.mean_empirical) < 0.25


def _miscalibrated_dataset(
    n: int = 600,
) -> tuple[list[tuple[float, ...]], list[float]]:
    """A deterministic dataset whose labels come from a logit the model can
    recover IN DIRECTION but is systematically OVER-CONFIDENT about in scale.

    We generate labels as ``σ(GAIN · (w·x) + SHIFT)`` with a known affine
    distortion (GAIN >> 1, SHIFT pulling toward the extremes). A logistic fit on
    the raw features recovers a w pointing the right way, but its UNCALIBRATED
    sigmoid ``σ(w·x)`` is far less confident than the true labels — so the raw
    sigmoid is badly mis-calibrated. The Platt scaler (calib_a, calib_b) exists
    precisely to absorb that affine gap; this dataset makes calibration do real
    work, so a no-op Platt step would leave ECE high. No RNG — fixed LCG."""
    true_w = [0.0, 1.5, 1.0, 0.8, 0.6, 0.9, 0.3, 0.2, 0.1]
    assert len(true_w) == FEATURE_DIM
    # The deliberate mis-calibration: amplify the logit hard and shove it
    # outward so the empirical labels are far more extreme (0-or-1-ish) than the
    # L2-regularized logistic fit can reach within its fixed iteration budget —
    # so σ(w·x) stays systematically UNDER-confident (high raw ECE) while the
    # Platt scaler, which can apply an unbounded affine on the logit, absorbs it.
    gain = 12.0
    shift_center = 2.0  # subtract the typical logit mean so labels span (0,1)
    feats: list[tuple[float, ...]] = []
    labels: list[float] = []
    state = 98765
    for _ in range(n):
        x = [1.0]
        for _j in range(FEATURE_DIM - 1):
            state = (1103515245 * state + 12345) % (2**31)
            x.append((state % 1000) / 1000.0)
        xt = tuple(x)
        z = sum(w * xi for w, xi in zip(true_w, xt, strict=True))
        p = 1.0 / (1.0 + math.exp(-(gain * (z - shift_center))))
        feats.append(xt)
        labels.append(p)
    return feats, labels


def test_calibration_measurably_reduces_ece_vs_uncalibrated() -> None:
    """Calibration must DO WORK: on a deliberately mis-calibrated dataset, the
    Platt-calibrated prediction's ECE is well below the raw (uncalibrated)
    sigmoid's ECE. This FAILS if calib_a/calib_b were removed or forced to a
    no-op (a=1, b=0) — i.e. the test bites on calibration, unlike the
    well-calibrated holdout case where the scaler is near-identity."""
    feats, labels = _miscalibrated_dataset(n=600)
    # Train (incl. Platt) on the first 400; measure on the held-out last 200.
    model = train_model(feats[:400], labels[:400])
    eval_x, eval_y = feats[400:], labels[400:]

    # Calibrated ECE: bins of model.predict (which applies the Platt scaler).
    cal_bins = reliability_table(model, eval_x, eval_y, n_bins=10)
    cal_ece = expected_calibration_error(cal_bins)

    # Raw/uncalibrated ECE: the same weights but σ(w·x) with NO Platt rescale —
    # exactly what the model would emit if calibration were a no-op.
    raw_model = AuctionModel(
        weights=model.weights,
        calib_a=1.0,
        calib_b=0.0,
        feature_schema_version=model.feature_schema_version,
        model_schema_version=model.model_schema_version,
        n_train=model.n_train,
    )
    raw_bins = reliability_table(raw_model, eval_x, eval_y, n_bins=10)
    raw_ece = expected_calibration_error(raw_bins)

    # The raw sigmoid must be CLEARLY mis-calibrated (else the test would not
    # bite), and calibration must cut the error by a non-trivial margin.
    assert raw_ece > 0.05, (
        f"raw uncalibrated ECE {raw_ece} is not high enough for the test to "
        "bite — the dataset is not actually mis-calibrated"
    )
    assert cal_ece < 0.5 * raw_ece, (
        f"calibrated ECE {cal_ece} is not measurably below half the raw ECE "
        f"{raw_ece} — the Platt calibration is doing no work"
    )


def test_model_learns_signal_beats_constant() -> None:
    """A trained model's mean-squared error must beat predicting the mean label
    (otherwise it learned nothing — the lift would be fake)."""
    feats, labels = _synthetic_dataset(n=500)
    model = train_model(feats[:350], labels[:350])
    test_x, test_y = feats[350:], labels[350:]
    mean_label = sum(labels[:350]) / 350
    mse_model = sum(
        (model.predict(x) - y) ** 2 for x, y in zip(test_x, test_y, strict=True)
    ) / len(test_y)
    mse_const = sum((mean_label - y) ** 2 for y in test_y) / len(test_y)
    assert mse_model < mse_const, (
        f"model MSE {mse_model} did not beat constant baseline {mse_const}"
    )


def test_load_refuses_feature_schema_mismatch() -> None:
    feats, labels = _synthetic_dataset(n=50)
    model = train_model(feats, labels)
    import json
    obj = json.loads(model.to_json())
    obj["feature_schema_version"] = "auction-feat-vWRONG"
    bad = json.dumps(obj)
    with pytest.raises(ValueError, match="feature schema"):
        AuctionModel.from_json(bad)


def test_train_rejects_empty_and_bad_labels() -> None:
    with pytest.raises(ValueError, match="empty"):
        train_model([], [])
    with pytest.raises(ValueError, match=r"\[0,1\]"):
        train_model([tuple([1.0] * FEATURE_DIM)], [1.5])


def test_inference_imports_nothing_heavy() -> None:
    """§16 negative proof at the module level: the model module's ACTUAL import
    statements (parsed via AST, not prose-matched) are only stdlib + the pure
    feature module — no numpy/sklearn/network/subprocess/GPU lib."""
    import ast

    import substrate.ad_inventory.auction_model as m

    banned = {
        "numpy", "scipy", "sklearn", "lightgbm", "xgboost", "torch",
        "tensorflow", "requests", "httpx", "subprocess", "socket",
        "urllib", "asyncio", "multiprocessing",
    }
    with open(m.__file__, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
    offending = imported_roots & banned
    assert not offending, f"auction_model imports {offending} — violates §16"
    assert m.MODEL_SCHEMA_VERSION
    assert FEATURE_SCHEMA_VERSION  # referenced
