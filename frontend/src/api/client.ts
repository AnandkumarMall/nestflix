// Typed fetch wrappers for the Nestflix backend.
// All backend calls go through this module — never raw fetch() in components.

const BASE = '/api';

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Types (mirror the backend response shapes).
// ---------------------------------------------------------------------------

export interface Health {
  status: string;
  tmdb_configured: boolean;
  library_paths: string[];
}

export interface Profile {
  id: number;
  name: string;
  avatar_color: string;
  created_at?: string;
}

export interface Movie {
  id: number;
  tmdb_id: number | null;
  parsed_title: string;
  title: string | null;
  year: number | null;
  overview: string | null;
  poster_path: string | null;
  backdrop_path: string | null;
  rating: number | null;
  runtime: number | null;
  genres: string | null; // JSON array string
  match_status: 'pending' | 'matched' | 'unmatched';
  path: string;
  container: string;
  // Joined in get_library via media_files; the media_file id used for playback:
  media_file_id?: number;
}

export interface Episode {
  id: number;
  season: number;
  episode: number;
  title: string | null;
  overview: string | null;
  still_path: string | null;
  path: string;
  container: string;
  media_file_id?: number;
}

export interface Show {
  id: number;
  tmdb_id: number | null;
  parsed_title: string;
  title: string | null;
  year: number | null;
  overview: string | null;
  poster_path: string | null;
  backdrop_path: string | null;
  rating: number | null;
  genres: string | null;
  match_status: 'pending' | 'matched' | 'unmatched';
  episodes: Episode[];
}

export interface Library {
  movies: Movie[];
  shows: Show[];
}

// Raw TMDB result (movies use `title`/`release_date`, TV uses `name`/`first_air_date`).
export interface DiscoverItem {
  id: number;
  title?: string;
  name?: string;
  poster_path: string | null;
  backdrop_path: string | null;
  overview: string | null;
  vote_average?: number;
  release_date?: string;
  first_air_date?: string;
}

export type PlayMode = 'direct' | 'remux' | 'transcode' | 'unavailable';

export interface SubtitleTrack {
  track: string;
  label: string;
  language: string | null;
  kind: 'embedded' | 'sidecar';
}

export interface PlaybackInfo {
  media_file_id: number;
  play_mode: PlayMode;
  container: string;
  video_codec: string | null;
  audio_codec: string | null;
  duration_seconds: number | null;
  width: number | null;
  height: number | null;
  ffmpeg_available: boolean;
  subtitles: SubtitleTrack[];
  // Display metadata (movie or episode):
  kind?: 'movie' | 'episode';
  title?: string;
  year?: number | null;
  season?: number;
  episode?: number;
  episode_title?: string | null;
  poster_path?: string | null;
  backdrop_path?: string | null;
  still_path?: string | null;
}

export interface WatchProgress {
  position_seconds: number;
  duration_seconds: number;
  completed: boolean;
}

export interface ContinueItem {
  media_file_id: number;
  position_seconds: number;
  duration_seconds: number;
  kind: 'movie' | 'episode';
  title: string;
  poster_path: string | null;
  backdrop_path: string | null;
  still_path?: string | null;
  season?: number;
  episode?: number;
}

// One recommended title (a card). `reason` is the human-readable explanation.
export interface RecItem {
  kind: 'movie' | 'show';
  id: number;
  title: string;
  year: number | null;
  poster_path: string | null;
  backdrop_path: string | null;
  media_file_id: number | null;
  reason: string;
  score: number;
}

// A titled, ordered row of recommendations (Top Picks, Because You Watched …, genres).
export interface RecRow {
  key: string;
  title: string;
  items: RecItem[];
}

// A local-library search hit: a movie or show, tagged with its `type`.
export type SearchResult = ({ type: 'movie' } & Movie) | ({ type: 'show' } & Show);

// Per-profile viewing summary for the Stats page.
export interface Stats {
  profile_id: number;
  titles_finished: number;
  seconds_watched: number;
  ratings: { up: number; down: number };
  top_genres: { name: string; count: number }[];
  recently_finished: {
    kind: 'movie' | 'show';
    id: number;
    title: string;
    poster_path: string | null;
  }[];
}

// ---------------------------------------------------------------------------
// URL helpers (kept here so components never build backend URLs themselves).
// ---------------------------------------------------------------------------

/** Cached TMDB image URL (poster/backdrop/still path), or null if no path. */
export function imageUrl(path: string | null | undefined, size = 'w342'): string | null {
  if (!path) return null;
  // Local library stores bare filenames; raw TMDB paths have a leading slash. The image
  // route expects a bare "abc123.jpg", so strip any leading slashes.
  return `${BASE}/images/${size}/${path.replace(/^\/+/, '')}`;
}

/** Video stream URL for a media file. `t` is the start offset (ffmpeg modes only). */
export function streamUrl(mediaFileId: number, t = 0): string {
  const q = t > 0 ? `?t=${encodeURIComponent(t.toFixed(3))}` : '';
  return `${BASE}/playback/${mediaFileId}/stream${q}`;
}

/** WebVTT URL for one subtitle track of a media file. */
export function subtitleUrl(mediaFileId: number, track: string): string {
  return `${BASE}/playback/${mediaFileId}/subtitles/${track}.vtt`;
}

export const api = {
  health: () => get<Health>('/health'),
  profiles: () => get<{ profiles: Profile[] }>('/profiles'),
  library: () => get<Library>('/library'),
  trending: () => get<{ items: DiscoverItem[] }>('/discovery/trending'),
  newReleases: () => get<{ items: DiscoverItem[] }>('/discovery/new-releases'),
  tmdbMovie: (id: number) => get('/discovery/movie/' + id),
  tmdbTv: (id: number) => get('/discovery/tv/' + id),

  searchLibrary: (q: string) =>
    get<{ query: string; results: SearchResult[] }>(`/library/search?q=${encodeURIComponent(q)}`),

  stats: (profileId: number) => get<Stats>(`/stats?profile_id=${profileId}`),

  playbackInfo: (mediaFileId: number) => get<PlaybackInfo>(`/playback/${mediaFileId}/info`),

  readProgress: (profileId: number, mediaFileId: number) =>
    get<WatchProgress>(`/playback/progress?profile_id=${profileId}&media_file_id=${mediaFileId}`),

  saveProgress: (body: {
    profile_id: number;
    media_file_id: number;
    position_seconds: number;
    duration_seconds: number;
    event?: string;
  }) => post<{ ok: boolean; completed: boolean }>('/playback/progress', body),

  continueWatching: (profileId: number) =>
    get<{ profile_id: number; items: ContinueItem[] }>(
      `/playback/continue?profile_id=${profileId}`
    ),

  recommendationRows: (profileId: number) =>
    get<{ profile_id: number; rows: RecRow[] }>(`/recommendations/rows?profile_id=${profileId}`),

  similar: (kind: 'movie' | 'show', id: number) =>
    get<{ kind: string; id: number; items: RecItem[] }>(
      `/recommendations/similar?kind=${kind}&id=${id}`
    ),

  ratings: (profileId: number) =>
    get<{ ratings: { kind: 'movie' | 'show'; id: number; value: 1 | -1 }[] }>(
      `/recommendations/ratings?profile_id=${profileId}`
    ),

  rate: (body: { profile_id: number; movie_id?: number; show_id?: number; value: 1 | -1 }) =>
    post<{ ok: boolean }>('/recommendations/rate', body),

  saveProgressBeacon: (body: {
    profile_id: number;
    media_file_id: number;
    position_seconds: number;
    duration_seconds: number;
  }) => {
    navigator.sendBeacon(`${BASE}/playback/progress`, JSON.stringify(body));
  },
};
