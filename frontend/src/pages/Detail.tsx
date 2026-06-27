// Title detail: backdrop, metadata, a Play/Resume button, and (for shows) the episode
// list. Data comes from the library endpoint and is matched by kind + id from the route.

import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, imageUrl, type Library, type Movie, type Show } from "../api/client";

export default function Detail() {
  const { kind, id } = useParams<{ kind: string; id: string }>();
  const navigate = useNavigate();
  const [library, setLibrary] = useState<Library | null>(null);

  useEffect(() => {
    api.library().then(setLibrary).catch(() => setLibrary({ movies: [], shows: [] }));
  }, []);

  if (!library) return <div className="page-loading">Loading…</div>;

  const numericId = Number(id);
  const movie =
    kind === "movie"
      ? library.movies.find((m) => m.id === numericId)
      : undefined;
  const show =
    kind === "show" ? library.shows.find((s) => s.id === numericId) : undefined;

  if (!movie && !show) {
    return (
      <div className="page-error">
        Title not found. <Link to="/">Back home</Link>
      </div>
    );
  }

  const item = (movie ?? show) as Movie | Show;
  const backdrop = imageUrl(item.backdrop_path, "w780");
  const title = item.title || item.parsed_title;
  const genres = item.genres ? safeGenres(item.genres) : [];

  return (
    <div className="detail">
      <div
        className="detail-backdrop"
        style={backdrop ? { backgroundImage: `url(${backdrop})` } : undefined}
      >
        <div className="detail-overlay">
          <h1>{title}</h1>
          <div className="detail-meta">
            {item.year && <span>{item.year}</span>}
            {item.rating != null && <span>★ {item.rating.toFixed(1)}</span>}
            {movie?.runtime && <span>{movie.runtime} min</span>}
            {genres.length > 0 && <span>{genres.join(" · ")}</span>}
          </div>
          {item.overview && <p className="detail-overview">{item.overview}</p>}

          {movie && movie.media_file_id != null && (
            <button
              className="btn btn-play"
              onClick={() => navigate(`/watch/${movie.media_file_id}`)}
            >
              ► Play
            </button>
          )}
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
                ep.media_file_id != null && navigate(`/watch/${ep.media_file_id}`)
              }
            >
              <span className="episode-num">
                S{ep.season}E{ep.episode}
              </span>
              <span className="episode-title">
                {ep.title || `Episode ${ep.episode}`}
              </span>
              <span className="episode-play">►</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function safeGenres(raw: string): string[] {
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}
