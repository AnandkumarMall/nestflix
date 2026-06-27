// Full-bleed featured banner at the top of Home.

import { useNavigate } from "react-router-dom";
import { imageUrl, type Movie } from "../api/client";

export default function Hero({ movie }: { movie: Movie }) {
  const navigate = useNavigate();
  const backdrop = imageUrl(movie.backdrop_path, "w780");
  const title = movie.title || movie.parsed_title;

  return (
    <div
      className="hero-banner"
      style={backdrop ? { backgroundImage: `url(${backdrop})` } : undefined}
    >
      <div className="hero-content">
        <h1 className="hero-title">{title}</h1>
        {movie.overview && <p className="hero-overview">{movie.overview}</p>}
        <div className="hero-actions">
          <button
            className="btn btn-play"
            onClick={() =>
              movie.media_file_id != null &&
              navigate(`/watch/${movie.media_file_id}`)
            }
          >
            ► Play
          </button>
          <button
            className="btn btn-secondary"
            onClick={() => navigate(`/title/movie/${movie.id}`)}
          >
            More Info
          </button>
        </div>
      </div>
    </div>
  );
}
