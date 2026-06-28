"""The optional learned re-ranker: "will I finish this?" as logistic regression.

Single-user data is tiny, so the model is intentionally lightweight (per CLAUDE.md) and
only used to *re-rank* the content-based candidates — never as the sole signal. It:

* trains on the profile's watch history (finished = 1, didn't finish = 0),
* persists per-profile to ``data/models/profile_<id>.pkl`` alongside the **vocabulary it
  was trained with** (so saved coefficients always line up with freshly-vectorized
  candidates, even after the library grows),
* activates only past ``settings.model_min_samples`` completed watches and auto-retrains
  every ``settings.retrain_every`` completed watches,
* fails safe: a missing/corrupt/mismatched pickle loads as ``None`` and the caller falls
  back to the pure content score.
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

from ..config import settings
from .features import Vocabulary, feature_matrix, feature_vector


@dataclass
class TasteModel:
    """A trained model bundled with the vocabulary and metadata it depends on."""

    estimator: LogisticRegression
    vocab: Vocabulary
    trained_at_count: int
    metrics: dict


def _model_path(profile_id: int) -> Path:
    # Filename is built from an int only — no client-controlled path component. The pickle
    # is trusted because both the path and the bytes are app-written under gitignored
    # data/. If models ever become shareable/importable, switch to a non-pickle format
    # (JSON coefficients + vocab) to remove the arbitrary-deserialization risk.
    settings.ensure_dirs()
    return settings.models_dir / f"profile_{profile_id}.pkl"


def training_data(
    entries: list[dict], vocab: Vocabulary
) -> tuple[np.ndarray, np.ndarray]:
    """Build (X, y) from watch history: y = 1 if the title was finished, else 0.

    ``entries`` are ``{"title": <title dict>, "completed": bool, "finishes": int, ...}``.
    """
    if not entries:
        return np.zeros((0, vocab.dim)), np.zeros(0)
    X = feature_matrix([e["title"] for e in entries], vocab)
    y = np.array(
        [1 if (e.get("completed") or e.get("finishes", 0) > 0) else 0 for e in entries],
        dtype=np.int64,
    )
    return X, y


def train(
    profile_id: int, entries: list[dict], vocab: Vocabulary, *, completed_count: int
) -> TasteModel | None:
    """Fit and persist a model for the profile, or return ``None`` if not yet trainable.

    Returns ``None`` (and writes nothing) when there are too few samples or only one
    class — both of which make a classifier meaningless on this much data.
    """
    if len(entries) < settings.model_min_samples:
        return None
    X, y = training_data(entries, vocab)
    if len(np.unique(y)) < 2:
        return None

    estimator = LogisticRegression(max_iter=1000, class_weight="balanced")
    estimator.fit(X, y)
    metrics = {
        "n_samples": int(len(y)),
        "n_finished": int(y.sum()),
        "train_accuracy": float(estimator.score(X, y)),
    }
    model = TasteModel(
        estimator=estimator,
        vocab=vocab,
        trained_at_count=completed_count,
        metrics=metrics,
    )
    _save(profile_id, model)
    return model


def _save(profile_id: int, model: TasteModel) -> None:
    with open(_model_path(profile_id), "wb") as fh:
        pickle.dump(model, fh)


def load_model(profile_id: int) -> TasteModel | None:
    """Load the persisted model, or ``None`` if missing/corrupt/incompatible."""
    path = _model_path(profile_id)
    if not path.exists():
        return None
    # Broad except on purpose: a corrupt/incompatible pickle must degrade to None (pure
    # content scoring) rather than 500 a request — and unpickling can raise almost anything.
    try:
        with open(path, "rb") as fh:
            model = pickle.load(fh)
    except Exception:  # noqa: BLE001
        return None
    return model if isinstance(model, TasteModel) else None


def predict(model: TasteModel, titles: list[dict]) -> np.ndarray:
    """Finish-probability in [0, 1] for each title, vectorized with the model's vocab."""
    if not titles:
        return np.zeros(0, dtype=np.float64)
    X = feature_matrix(titles, model.vocab)
    # Probability of the "finished" (class 1) column; guard the degenerate single-class
    # estimator (shouldn't happen — train() rejects it — but stay defensive).
    classes = list(model.estimator.classes_)
    proba = model.estimator.predict_proba(X)
    if 1 not in classes:
        return np.zeros(len(titles), dtype=np.float64)
    return proba[:, classes.index(1)]


def top_features(model: TasteModel, *, top_k: int = 5) -> list[str]:
    """Feature labels with the largest positive coefficients (global explanation)."""
    coef = model.estimator.coef_[0]
    names = model.vocab.feature_names
    order = np.argsort(coef)[::-1]
    return [names[i] for i in order if coef[i] > 0][:top_k]


def should_retrain(profile_id: int, completed_count: int) -> bool:
    """Whether to (re)train now given the completed-watch cadence.

    Train once the threshold is first crossed, then again every ``retrain_every``
    completed watches. A model already trained at the current count is left alone.
    """
    if completed_count < settings.model_min_samples:
        return False
    existing = load_model(profile_id)
    if existing is None:
        return True
    if existing.trained_at_count == completed_count:
        return False
    return completed_count % settings.retrain_every == 0


def maybe_retrain(
    profile_id: int, entries: list[dict], vocab: Vocabulary, *, completed_count: int
) -> TasteModel | None:
    """Retrain on the configured cadence; otherwise return the existing model (if any)."""
    if should_retrain(profile_id, completed_count):
        trained = train(profile_id, entries, vocab, completed_count=completed_count)
        if trained is not None:
            return trained
    return load_model(profile_id)
