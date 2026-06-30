"""Aggregate a profile's watch history into a single weighted "taste vector".

Each watched title contributes its feature vector, signed and scaled by how strong a
signal the watch was:

* **Finishing** a title (or a thumbs-up) pulls the taste vector toward it.
* **Bailing early** on a title, or a thumbs-down, pushes it away (negative weight).
* More **recent** watches count for more than old ones.

Cosine similarity between this taste vector and an unwatched title's vector is the
content-based score. The same overlap, read per-feature, is what we surface as the
human-readable "because you like Sci-Fi / Keanu Reeves" explanation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .features import Vocabulary, feature_vector

# A title watched < this fraction and then abandoned is read as an active dislike.
_BAILED_THRESHOLD = 0.15


@dataclass(frozen=True)
class TasteProfile:
    """The weighted taste vector plus the features that dominate it."""

    vector: np.ndarray
    dominant_features: list[str]

    @property
    def has_signal(self) -> bool:
        return bool(np.any(self.vector))


def watch_weight(entry: dict) -> float:
    """Signed weight for one watched title from its completion + rating + recency.

    ``entry`` carries ``completed``, ``pct``, ``abandoned``, ``rating`` (+1/-1/0) and a
    ``recency`` factor in ~[0.5, 1.0]. Returns a positive weight to attract, negative to
    repel, ~0 to ignore.
    """
    rating = entry.get("rating", 0)
    recency = float(entry.get("recency", 1.0))

    if rating < 0:  # explicit thumbs-down — strongest repel.
        return -1.5 * recency
    if rating > 0:  # explicit thumbs-up — strongest attract.
        return 1.8 * recency

    if entry.get("completed"):
        return 1.0 * recency
    if entry.get("abandoned") and entry.get("pct", 0.0) < _BAILED_THRESHOLD:
        return -0.6 * recency  # bailed in the first few minutes — mild repel.
    return float(entry.get("pct", 0.0)) * recency  # partial watch — partial credit.


def build_taste_profile(entries: list[dict], vocab: Vocabulary, *, top_k: int = 6) -> TasteProfile:
    """Weighted sum of watched titles' feature vectors → a normalized taste vector.

    Each entry is ``{"title": <title dict>, ...signal fields}`` (see ``watch_weight``).
    The dominant features are the highest-weighted positive dimensions, for explanations.
    """
    acc = np.zeros(vocab.dim, dtype=np.float64)
    for entry in entries:
        w = watch_weight(entry)
        if w == 0.0:
            continue
        acc += w * feature_vector(entry["title"], vocab)

    norm = np.linalg.norm(acc)
    vector = acc / norm if norm > 0 else acc

    names = vocab.feature_names
    # Only the multi-hot block makes sense as a label; the trailing scalars don't.
    multi_hot_end = vocab.scalar_offset
    ranked = np.argsort(vector[:multi_hot_end])[::-1]
    dominant = [names[i] for i in ranked if vector[i] > 0][:top_k]
    return TasteProfile(vector=vector, dominant_features=dominant)


def content_scores(taste: np.ndarray, candidates: np.ndarray) -> np.ndarray:
    """Cosine similarity of each candidate row against the taste vector ([-1, 1])."""
    if candidates.shape[0] == 0:
        return np.zeros(0, dtype=np.float64)
    taste_norm = np.linalg.norm(taste)
    if taste_norm == 0:
        return np.zeros(candidates.shape[0], dtype=np.float64)
    cand_norms = np.linalg.norm(candidates, axis=1)
    cand_norms[cand_norms == 0] = 1.0  # avoid /0; a zero vector scores 0 anyway.
    return (candidates @ taste) / (cand_norms * taste_norm)


def explain(
    taste: np.ndarray, candidate: np.ndarray, vocab: Vocabulary, *, top_k: int = 2
) -> list[str]:
    """Top shared features driving a candidate's score, as human labels.

    Picks the multi-hot dimensions where both the taste vector and the candidate are
    positive, ranked by taste weight — i.e. "what about *your* taste this title matches".
    """
    multi_hot_end = vocab.scalar_offset
    names = vocab.feature_names
    overlap = (taste[:multi_hot_end] > 0) & (candidate[:multi_hot_end] > 0)
    idx = np.where(overlap)[0]
    idx = idx[np.argsort(taste[idx])[::-1]]
    return [names[i] for i in idx[:top_k]]
