"""Turn TMDB metadata into dense feature vectors the recommender can compare.

A title's vector is mostly multi-hot — genres, keywords, top-billed cast drawn from a
**vocabulary** built over the library — plus a few normalized scalars (rating, recency,
runtime). Keeping the vocabulary library-scoped bounds the vector size and means a fresh
library with five movies doesn't carry thousands of unused keyword dimensions.

The same ``feature_vector`` is used three ways: to build the taste profile, to score
candidates by cosine similarity, and as the model's input features — so the meaning of
each index is stable within a vocabulary (see ``Vocabulary.feature_names``).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np

# Cap the rarer multi-hot blocks so a big library can't explode the vector. Genres are a
# small fixed TMDB set, so we keep them all.
_MAX_KEYWORDS = 80
_MAX_CAST = 80

# Number of trailing scalar (non-multi-hot) features.
_NUM_SCALARS = 3
_SCALAR_NAMES = ("Highly rated", "Recent", "Runtime")


@dataclass(frozen=True)
class Vocabulary:
    """Stable index maps for the multi-hot blocks, plus derived layout offsets."""

    genres: list[str]
    keywords: list[str]
    cast: list[str]

    @property
    def genre_offset(self) -> int:
        return 0

    @property
    def keyword_offset(self) -> int:
        return len(self.genres)

    @property
    def cast_offset(self) -> int:
        return len(self.genres) + len(self.keywords)

    @property
    def scalar_offset(self) -> int:
        return len(self.genres) + len(self.keywords) + len(self.cast)

    @property
    def dim(self) -> int:
        return self.scalar_offset + _NUM_SCALARS

    @property
    def feature_names(self) -> list[str]:
        """Human label per vector index — used to explain recommendations."""
        return [
            *self.genres,
            *(f"Keyword: {k}" for k in self.keywords),
            *(f"Stars {c}" for c in self.cast),
            *_SCALAR_NAMES,
        ]


def _top(counter: Counter, limit: int | None) -> list[str]:
    """Most-common values, ties broken alphabetically for deterministic ordering."""
    items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    chosen = items if limit is None else items[:limit]
    return [name for name, _ in chosen]


def build_vocabulary(titles: list[dict]) -> Vocabulary:
    """Build the index maps from the library's titles (genres/keywords/cast)."""
    genres: Counter = Counter()
    keywords: Counter = Counter()
    cast: Counter = Counter()
    for t in titles:
        genres.update(t.get("genres") or [])
        keywords.update(t.get("keywords") or [])
        cast.update(t.get("cast") or [])
    return Vocabulary(
        genres=_top(genres, None),
        keywords=_top(keywords, _MAX_KEYWORDS),
        cast=_top(cast, _MAX_CAST),
    )


def _scalar(value: float | None, default: float, lo: float, span: float) -> float:
    """Normalize a numeric field into [0, 1], substituting a neutral default for None."""
    raw = default if value is None else float(value)
    return float(np.clip((raw - lo) / span, 0.0, 1.0))


def feature_vector(title: dict, vocab: Vocabulary) -> np.ndarray:
    """Dense feature vector for one title. Missing metadata maps to neutral values."""
    vec = np.zeros(vocab.dim, dtype=np.float64)

    genre_idx = {g: i for i, g in enumerate(vocab.genres)}
    keyword_idx = {k: i for i, k in enumerate(vocab.keywords)}
    cast_idx = {c: i for i, c in enumerate(vocab.cast)}

    for g in title.get("genres") or []:
        if g in genre_idx:
            vec[vocab.genre_offset + genre_idx[g]] = 1.0
    for k in title.get("keywords") or []:
        if k in keyword_idx:
            vec[vocab.keyword_offset + keyword_idx[k]] = 1.0
    for c in title.get("cast") or []:
        if c in cast_idx:
            vec[vocab.cast_offset + cast_idx[c]] = 1.0

    s = vocab.scalar_offset
    # rating 0-10 → 0-1 (default to the TMDB-ish mean so unrated titles stay neutral).
    vec[s] = _scalar(title.get("rating"), default=6.0, lo=0.0, span=10.0)
    # year → recency in [0,1] across a ~1950-2030 window.
    vec[s + 1] = _scalar(title.get("year"), default=2000.0, lo=1950.0, span=80.0)
    # runtime minutes → [0,1] across a 0-200 window (shows have none → neutral).
    vec[s + 2] = _scalar(title.get("runtime"), default=100.0, lo=0.0, span=200.0)
    return vec


def feature_matrix(titles: list[dict], vocab: Vocabulary) -> np.ndarray:
    """Stack per-title vectors into an (n_titles, dim) matrix (empty-safe)."""
    if not titles:
        return np.zeros((0, vocab.dim), dtype=np.float64)
    return np.vstack([feature_vector(t, vocab) for t in titles])
