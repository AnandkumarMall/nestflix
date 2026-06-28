// Full-bleed featured banner at the top of Home — mirrors the nestflix.html hero:
// ORIGINAL eyebrow, big title, a metadata bar (match / year / rating / runtime / HD),
// a truncated synopsis, and Play / More Info actions.

import { useNavigate } from "react-router-dom";
import { imageUrl, type Movie } from "../api/client";
import { formatRuntime, parseGenres } from "../utils";

export default function Hero({ movie }: { movie: Movie }) {
  const navigate = useNavigate();
  const backdrop = imageUrl(movie.backdrop_path, "w780");
  const title = movie.title || movie.parsed_title;
  const genres = parseGenres(movie.genres);
  // A stable, pseudo-random "match" derived from the TMDB rating (cosmetic, like Netflix).
  const match =
    movie.rating != null ? Math.min(99, Math.round(movie.rating * 9.5)) : null;
  const runtimeLabel = formatRuntime(movie.runtime);
  // Cosmetic age-rating chip (we don't store certifications) — mirrors the reference.
  const ageRating = movie.match_status === "matched" ? "16+" : "PG";

  return (
    <div
      className="hero-banner"
      style={backdrop ? { backgroundImage: `url(${backdrop})` } : undefined}
    >
      <div className="hero-content">
        <div className="hero-eyebrow">
          <span className="hero-brand">N E S T F L I X</span>
          <span className="hero-kind">
            {movie.match_status === "matched" ? "FILM" : "ORIGINAL"}
          </span>
        </div>

        <h1 className="hero-title">{title}</h1>

        <div className="hero-meta">
          {match != null && <span className="hero-match">{match}% Match</span>}
          {movie.year && <span>{movie.year}</span>}
          <span className="hero-rating">{ageRating}</span>
          {runtimeLabel && <span>{runtimeLabel}</span>}
          <span className="hero-hd">HD</span>
        </div>

        {genres.length > 0 && (
          <div className="hero-genres">{genres.join(" · ")}</div>
        )}

        {movie.overview && <p className="hero-overview">{movie.overview}</p>}

        <div className="hero-actions">
          <button
            className="btn btn-play"
            onClick={() =>
              movie.media_file_id != null &&
              navigate(`/watch/${movie.media_file_id}`, { state: { title } })
            }
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="black">
              <path d="M8 5v14l11-7z" />
            </svg>
            Play
          </button>
          <button
            className="btn btn-secondary"
            onClick={() => navigate(`/title/movie/${movie.id}`)}
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="white">
              <path d="M11 7h2v2h-2zm0 4h2v6h-2zm1-9C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z" />
            </svg>
            More Info
          </button>
        </div>
      </div>
    </div>
  );
}
