// Title detail: backdrop, metadata, a Play/Resume button (if available), thumbs rating,
// the episode list (for shows), and a content-based "More Like This" row.
// Supports both local library titles and TMDB-only titles.

import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api, imageUrl, type Library, type Movie, type RecItem, type Show } from '../api/client';
import { useProfile } from '../profile';
import PosterRow from '../components/PosterRow';
import PosterCard from '../components/PosterCard';
import { parseGenres } from '../utils';

export default function Detail() {
  const { kind, id, source } = useParams<{ kind: string; id: string; source?: string }>();
  const navigate = useNavigate();
  const { activeProfile } = useProfile();
  const [library, setLibrary] = useState<Library | null>(null);
  const [tmdbItem, setTmdbItem] = useState<Record<string, unknown> | null>(null);
  const [similar, setSimilar] = useState<RecItem[]>([]);
  const [rating, setRating] = useState<1 | -1 | 0>(0);

  const numericId = Number(id);
  const isTmdbOnly = source === 'tmdb';

  useEffect(() => {
    api
      .library()
      .then(setLibrary)
      .catch(() => setLibrary({ movies: [], shows: [] }));
  }, []);

  useEffect(() => {
    setTmdbItem(null);
    if (!isTmdbOnly || (kind !== 'movie' && kind !== 'show')) return;
    const fetch$ = kind === 'movie' ? api.tmdbMovie(numericId) : api.tmdbTv(numericId);
    Promise.resolve(fetch$)
      .then(setTmdbItem)
      .catch(() => setTmdbItem(null));
  }, [isTmdbOnly, kind, numericId]);

  useEffect(() => {
    setRating(0);
    if (kind !== 'movie' && kind !== 'show') return;
    api
      .similar(kind, numericId)
      .then((r) => setSimilar(r.items))
      .catch(() => setSimilar([]));
  }, [kind, numericId]);

  useEffect(() => {
    setRating(0);
    if (!activeProfile || (kind !== 'movie' && kind !== 'show')) return;
    api
      .ratings(activeProfile.id)
      .then((r) => {
        const saved = r.ratings.find((x) => x.kind === kind && x.id === numericId);
        setRating(saved ? saved.value : 0);
      })
      .catch(() => undefined);
  }, [activeProfile, kind, numericId]);

  if (!library) return <div className="page-loading">Loading…</div>;

  let movie: Movie | undefined;
  let show: Show | undefined;

  if (!isTmdbOnly) {
    movie = kind === 'movie' ? library.movies.find((m) => m.id === numericId) : undefined;
    show = kind === 'show' ? library.shows.find((s) => s.id === numericId) : undefined;
  }

  if (!movie && !show && !isTmdbOnly) {
    return (
      <div className="page-error">
        Title not found. <Link to="/">Back home</Link>
      </div>
    );
  }

  if (isTmdbOnly && !tmdbItem) {
    return <div className="page-loading">Loading…</div>;
  }

  const item = (movie ?? show ?? tmdbItem) as Movie | Show | Record<string, unknown>;
  const backdrop = imageUrl(
    (item as any)?.backdrop_path as string | null | undefined,
    'w780'
  );
  const title = (item as any)?.title || (item as any)?.parsed_title || (item as any)?.name;
  const genres = parseGenres((item as any)?.genres || []);
  const inLibrary = !!movie || !!show;

  function sendRating(value: 1 | -1) {
    if (!activeProfile) return;
    setRating(value);
    api
      .rate({
        profile_id: activeProfile.id,
        movie_id: movie?.id,
        show_id: show?.id,
        value,
      })
      .catch(() => undefined);
  }

  return (
    <div className="detail">
      <div
        className="detail-backdrop"
        style={backdrop ? { backgroundImage: `url(${backdrop})` } : undefined}
      >
        <div className="detail-overlay">
          <h1>{title}</h1>
          <div className="detail-meta">
            {((item as any)?.year || (item as any)?.release_date?.slice(0, 4) || (item as any)?.first_air_date?.slice(0, 4)) && (
              <span>{(item as any)?.year || (item as any)?.release_date?.slice(0, 4) || (item as any)?.first_air_date?.slice(0, 4)}</span>
            )}
            {(item as any)?.vote_average != null && (
              <span>★ {Number((item as any).vote_average).toFixed(1)}</span>
            )}
            {(item as any)?.rating != null && (
              <span>★ {Number((item as any).rating).toFixed(1)}</span>
            )}
            {movie?.runtime && <span>{movie.runtime} min</span>}
            {(item as any)?.runtime && <span>{(item as any).runtime} min</span>}
            {genres.length > 0 && <span>{genres.join(' · ')}</span>}
          </div>
          {((item as any)?.overview || (item as any)?.description) && (
            <p className="detail-overview">{(item as any)?.overview || (item as any)?.description}</p>
          )}

          <div className="detail-actions">
            {inLibrary && movie && movie.media_file_id != null && (
              <button
                className="btn btn-play"
                onClick={() => navigate(`/watch/${movie.media_file_id}`, { state: { title } })}
              >
                ► Play
              </button>
            )}
            {!inLibrary && (
              <button className="btn btn-play" disabled title="Not in your library">
                📭 Not in your library
              </button>
            )}
            <button
              className={`btn btn-thumb ${rating === 1 ? 'active' : ''}`}
              title="I like this"
              aria-pressed={rating === 1}
              onClick={() => sendRating(1)}
            >
              👍
            </button>
            <button
              className={`btn btn-thumb ${rating === -1 ? 'active' : ''}`}
              title="Not for me"
              aria-pressed={rating === -1}
              onClick={() => sendRating(-1)}
            >
              👎
            </button>
          </div>
        </div>
      </div>

      {show && (
        <div className="detail-episodes">
          <h2>Episodes</h2>
          {show.episodes.map((ep) => (
            <button
              key={ep.id}
              className="episode-row"
              onClick={() =>
                ep.media_file_id != null &&
                navigate(`/watch/${ep.media_file_id}`, {
                  state: {
                    title,
                    subtitle: `S${ep.season}E${ep.episode} · ${ep.title || `Episode ${ep.episode}`}`,
                  },
                })
              }
            >
              <span className="episode-num">
                S{ep.season}E{ep.episode}
              </span>
              <span className="episode-title">{ep.title || `Episode ${ep.episode}`}</span>
              <span className="episode-play">►</span>
            </button>
          ))}
        </div>
      )}

      {similar.length > 0 && (
        <div className="detail-similar">
          <PosterRow title="More Like This">
            {similar.map((it) => (
              <PosterCard
                key={`${it.kind}-${it.id}`}
                title={it.title}
                posterPath={it.poster_path}
                to={`/title/${it.kind}/${it.id}`}
                subtitle={it.year ? String(it.year) : undefined}
              />
            ))}
          </PosterRow>
        </div>
      )}
    </div>
  );
}
