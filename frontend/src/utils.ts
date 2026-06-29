// Small shared formatting helpers used across cards, the hero, and detail pages.

/** Runtime in minutes -> "2h 14m" (or null for missing/zero). */
export function formatRuntime(minutes: number | null | undefined): string | null {
  if (!minutes || minutes <= 0) return null;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${m}m`;
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
}

/** Parse a JSON array string of genre names; returns [] for null/malformed input. */
export function parseGenres(raw: string | null | undefined): string[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

/** TMDB-style "match" score from rating (0–99). */
export function matchScore(rating: number | null): number | null {
  return rating != null ? Math.min(99, Math.round(rating * 9.5)) : null;
}
