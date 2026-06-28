// A single poster tile used inside a PosterRow. The whole tile is the poster image;
// on hover it scales up and reveals an info overlay (Netflix-style) with quick action
// buttons, a "match" score, key metadata, and genres. Optionally shows a resume bar.

import { Link, useNavigate } from "react-router-dom";
import { imageUrl } from "../api/client";
import { formatRuntime, parseGenres } from "../utils";

interface Props {
  title: string;
  posterPath: string | null;
  to: string;
  subtitle?: string;
  /** 0..1 watched fraction; renders a resume bar when > 0. */
  progress?: number;
  /** Where the overlay Play button navigates. Falls back to `to` when omitted. */
  playTo?: string;
  /** TMDB-style "match" percentage (0..99). */
  match?: number | null;
  /** Runtime in minutes; rendered as "2h 14m" in the overlay meta line. */
  runtime?: number | null;
  /** JSON array string of genre names (as stored on Movie/Show). */
  genres?: string | null;
}

export default function PosterCard({
  title,
  posterPath,
  to,
  subtitle,
  progress,
  playTo,
  match,
  runtime,
  genres,
}: Props) {
  const navigate = useNavigate();
  const src = imageUrl(posterPath, "w342");
  const runtimeLabel = formatRuntime(runtime);
  const genreList = parseGenres(genres);

  const play = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    navigate(playTo ?? to);
  };

  return (
    <Link to={to} className="poster-card" title={title}>
      <div className="poster-img">
        {src ? (
          <img src={src} alt={title} loading="lazy" />
        ) : (
          <div className="poster-fallback">{title}</div>
        )}
      </div>

      <div className="card-info">
        <div className="card-actions">
          <button
            type="button"
            className="card-btn play"
            onClick={play}
            aria-label={`Play ${title}`}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="black">
              <path d="M8 5v14l11-7z" />
            </svg>
          </button>
        </div>

        <div className="card-title">{title}</div>

        {(match != null || runtimeLabel || subtitle) && (
          <div className="card-meta">
            {match != null && <span className="card-match">{match}% Match</span>}
            {runtimeLabel && <span>{runtimeLabel}</span>}
            {subtitle && <span>{subtitle}</span>}
          </div>
        )}

        {genreList.length > 0 && (
          <div className="card-tags">{genreList.slice(0, 3).join(" · ")}</div>
        )}
      </div>

      {progress != null && progress > 0 && (
        <div className="poster-progress">
          <div
            className="poster-progress-bar"
            style={{ width: `${Math.min(100, progress * 100)}%` }}
          />
        </div>
      )}
    </Link>
  );
}
