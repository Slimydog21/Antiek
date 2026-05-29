"""Learned value scorer — pure-Python calibrated regressor (SPR-10 M2).

The Axon-style learned core: a lightweight in-process model that predicts the
EXPECTED VALUE of showing a candidate in a slot, trained OFFLINE on recorded
sessions and serialized to a small canonical-JSON artifact loaded at startup.

WHY PURE PYTHON (no numpy/sklearn — §16 + no-new-heavy-dep constraint):
The feature vector is tiny (``auction_features.FEATURE_DIM`` ≈ 9). A logistic
regressor over 9 features trained by batch gradient descent is a few hundred
lines of stdlib arithmetic and runs in microseconds at inference — there is no
need for a matrix library, a GPU, or an external service. Importing numpy at
module top level would also pull a core-dep we are forbidden to add. So the
model is plain ``float`` lists + loops. (If the feature space ever grows to
hundreds of dimensions this trade flips — recorded as an open question in the
handoff, not pre-optimized here.)

THE MODEL (calibrated logistic over the M1 features):
* The label is the per-impression "value signal" in [0, 1]: the realized
  attention-weighted value of the impression normalized to [0,1] (the A/B
  harness owns turning recorded sessions into labels; the model just learns the
  mapping features → P(high-value)). We learn a logistic ``σ(w·x)`` because the
  label is a bounded fraction and a logit is naturally in [0,1] — and because a
  calibrated logistic gives a probability we can read as an EXPECTED-VALUE
  estimate, not an uncalibrated score (M2's calibration requirement).
* Training is L2-regularized batch gradient descent (deterministic: fixed
  iteration count, fixed init at zeros, no shuffling/randomness) so a retrain on
  the same data yields byte-identical coefficients — the same reproducibility
  discipline the attribution audit demands.
* CALIBRATION: after fitting, we fit a 1-D Platt scaler (a, b) on a held-out
  split so the final score ``σ(a·(w·x) + b)`` is calibrated — its mean over a
  bucket of examples matches the empirical mean label of that bucket. The
  reliability check (:func:`reliability_table`) bins predictions and reports
  predicted-vs-empirical per bin so calibration is MEASURED, not assumed.

INFERENCE IS IN-PROCESS CPU ONLY: :meth:`AuctionModel.predict` is a dot product
+ two sigmoids. No DB, no network, no subprocess, no GPU. Proven by inspection —
the only imports are ``math`` and stdlib ``json``.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from .auction_features import FEATURE_DIM, FEATURE_SCHEMA_VERSION

# Bump on ANY change to the model wire-shape (a new calibration term, a changed
# serialization) so an old artifact is identifiable. Distinct from the feature
# schema version: the model records BOTH, and load refuses a feature-schema
# mismatch (coefficients would be positionally wrong).
MODEL_SCHEMA_VERSION = "auction-model-v1"

# Training defaults — exposed as module constants so a retrain is reproducible
# and the operator can tune without touching the math.
DEFAULT_ITERATIONS = 2000
DEFAULT_LEARNING_RATE = 0.5
DEFAULT_L2 = 1e-3
DEFAULT_CALIBRATION_ITERATIONS = 1000


def _sigmoid(z: float) -> float:
    # Numerically stable logistic.
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


def _dot(w: list[float], x: tuple[float, ...]) -> float:
    return sum(wi * xi for wi, xi in zip(w, x, strict=True))


@dataclass(frozen=True)
class AuctionModel:
    """A trained, calibrated logistic value scorer.

    ``weights`` are the positional coefficients over the M1 feature vector
    (length ``FEATURE_DIM``); ``calib_a`` / ``calib_b`` are the Platt scaler
    applied to the raw logit. ``predict`` returns a calibrated expected-value
    estimate in [0, 1]. Frozen + JSON-serializable to a small artifact."""

    weights: tuple[float, ...]
    calib_a: float
    calib_b: float
    feature_schema_version: str
    model_schema_version: str
    n_train: int

    def raw_logit(self, x: tuple[float, ...]) -> float:
        return _dot(list(self.weights), x)

    def predict(self, x: tuple[float, ...]) -> float:
        """Calibrated expected-value estimate in [0, 1] for one feature vector.

        Pure CPU: a dot product + a Platt rescale + a sigmoid. No I/O."""
        if len(x) != len(self.weights):
            raise ValueError(
                f"feature vector has {len(x)} dims, model expects "
                f"{len(self.weights)}"
            )
        z = self.raw_logit(x)
        return _sigmoid(self.calib_a * z + self.calib_b)

    def to_json(self) -> str:
        """Serialize to canonical JSON (sorted keys, tight separators) with the
        version stamps — mirrors ``attribution_audit._canonical_json``. Small:
        ~FEATURE_DIM floats + two calibration scalars."""
        obj = {
            "calib_a": self.calib_a,
            "calib_b": self.calib_b,
            "feature_schema_version": self.feature_schema_version,
            "model_schema_version": self.model_schema_version,
            "n_train": self.n_train,
            "weights": list(self.weights),
        }
        return json.dumps(obj, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def from_json(blob: str) -> AuctionModel:
        """Load a model artifact. Refuses a feature-schema mismatch (the
        coefficients would be positionally meaningless against the current
        extractor) and a wrong vector length — loud failure, not silent
        misprediction."""
        obj = json.loads(blob)
        feat_ver = obj["feature_schema_version"]
        if feat_ver != FEATURE_SCHEMA_VERSION:
            raise ValueError(
                f"model artifact feature schema {feat_ver!r} != current "
                f"{FEATURE_SCHEMA_VERSION!r}; refusing to load stale coefficients"
            )
        weights = tuple(float(w) for w in obj["weights"])
        if len(weights) != FEATURE_DIM:
            raise ValueError(
                f"model artifact has {len(weights)} weights, current feature "
                f"dim is {FEATURE_DIM}"
            )
        return AuctionModel(
            weights=weights,
            calib_a=float(obj["calib_a"]),
            calib_b=float(obj["calib_b"]),
            feature_schema_version=feat_ver,
            model_schema_version=obj["model_schema_version"],
            n_train=int(obj["n_train"]),
        )


def _fit_logistic(
    features: list[tuple[float, ...]],
    labels: list[float],
    *,
    iterations: int,
    learning_rate: float,
    l2: float,
) -> list[float]:
    """Deterministic L2-regularized logistic regression by batch gradient
    descent. Init at zeros, fixed iteration count, full-batch (no shuffling) →
    same data yields byte-identical weights."""
    dim = len(features[0])
    w = [0.0] * dim
    n = len(features)
    for _ in range(iterations):
        grad = [0.0] * dim
        for x, y in zip(features, labels, strict=True):
            pred = _sigmoid(_dot(w, x))
            err = pred - y
            for j in range(dim):
                grad[j] += err * x[j]
        for j in range(dim):
            # Mean gradient + L2 (do not regularize the bias term, index 0).
            g = grad[j] / n
            if j != 0:
                g += l2 * w[j]
            w[j] -= learning_rate * g
    return w


def _fit_platt(
    raw_logits: list[float],
    labels: list[float],
    *,
    iterations: int,
    learning_rate: float,
) -> tuple[float, float]:
    """Fit a 1-D Platt scaler σ(a·z + b) mapping raw logits → calibrated
    probabilities by gradient descent on log-loss. Deterministic init (a=1,
    b=0)."""
    a, b = 1.0, 0.0
    n = len(raw_logits)
    if n == 0:
        return a, b
    for _ in range(iterations):
        ga, gb = 0.0, 0.0
        for z, y in zip(raw_logits, labels, strict=True):
            p = _sigmoid(a * z + b)
            err = p - y
            ga += err * z
            gb += err
        a -= learning_rate * (ga / n)
        b -= learning_rate * (gb / n)
    return a, b


@dataclass(frozen=True)
class ReliabilityBin:
    """One calibration bin: how many examples landed in it, the mean predicted
    score, and the mean empirical label. A calibrated model has predicted ≈
    empirical within each bin."""

    lo: float
    hi: float
    count: int
    mean_predicted: float
    mean_empirical: float


def reliability_table(
    model: AuctionModel,
    features: list[tuple[float, ...]],
    labels: list[float],
    *,
    n_bins: int = 5,
) -> list[ReliabilityBin]:
    """Bin held-out predictions and report predicted-vs-empirical per bin (the
    calibration check — calibration is MEASURED, not assumed). Read-only."""
    bins: list[list[tuple[float, float]]] = [[] for _ in range(n_bins)]
    for x, y in zip(features, labels, strict=True):
        p = model.predict(x)
        idx = min(int(p * n_bins), n_bins - 1)
        bins[idx].append((p, y))
    out: list[ReliabilityBin] = []
    for i, members in enumerate(bins):
        lo = i / n_bins
        hi = (i + 1) / n_bins
        if not members:
            out.append(ReliabilityBin(lo, hi, 0, 0.0, 0.0))
            continue
        mp = sum(p for p, _ in members) / len(members)
        me = sum(y for _, y in members) / len(members)
        out.append(ReliabilityBin(lo, hi, len(members), mp, me))
    return out


def expected_calibration_error(bins: list[ReliabilityBin]) -> float:
    """Count-weighted mean |predicted - empirical| across non-empty bins (ECE).
    A small ECE means the score reads as an expected-value estimate."""
    total = sum(b.count for b in bins)
    if total == 0:
        return 0.0
    return sum(b.count * abs(b.mean_predicted - b.mean_empirical) for b in bins) / total


def train_model(
    features: list[tuple[float, ...]],
    labels: list[float],
    *,
    iterations: int = DEFAULT_ITERATIONS,
    learning_rate: float = DEFAULT_LEARNING_RATE,
    l2: float = DEFAULT_L2,
    calibration_iterations: int = DEFAULT_CALIBRATION_ITERATIONS,
    calibration_split: float = 0.3,
) -> AuctionModel:
    """Train a calibrated logistic value scorer offline from recorded examples.

    Splits a tail ``calibration_split`` fraction off for fitting the Platt
    scaler (so calibration is on data the logistic did not directly minimize
    log-loss against). Deterministic throughout. Labels must be in [0, 1]."""
    if not features:
        raise ValueError("cannot train on an empty feature set")
    if len(features) != len(labels):
        raise ValueError("features and labels length mismatch")
    for y in labels:
        if not (0.0 <= y <= 1.0):
            raise ValueError(f"labels must be in [0,1], got {y}")

    n = len(features)
    # Deterministic split: last `calibration_split` fraction (caller controls
    # ordering; no shuffle so a retrain is reproducible).
    n_cal = max(1, int(round(n * calibration_split))) if n > 1 else 0
    n_fit = n - n_cal
    if n_fit < 1:
        # Too few rows to split — fit on everything, calibrate on everything.
        n_fit, n_cal = n, 0
    fit_x, fit_y = features[:n_fit], labels[:n_fit]
    cal_x = features[n_fit:] if n_cal else features
    cal_y = labels[n_fit:] if n_cal else labels

    weights = _fit_logistic(
        fit_x, fit_y,
        iterations=iterations, learning_rate=learning_rate, l2=l2,
    )
    cal_logits = [_dot(weights, x) for x in cal_x]
    a, b = _fit_platt(
        cal_logits, cal_y,
        iterations=calibration_iterations, learning_rate=learning_rate,
    )
    return AuctionModel(
        weights=tuple(weights),
        calib_a=a,
        calib_b=b,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        model_schema_version=MODEL_SCHEMA_VERSION,
        n_train=n,
    )


__all__ = [
    "DEFAULT_ITERATIONS",
    "DEFAULT_LEARNING_RATE",
    "DEFAULT_L2",
    "MODEL_SCHEMA_VERSION",
    "AuctionModel",
    "ReliabilityBin",
    "expected_calibration_error",
    "reliability_table",
    "train_model",
]
