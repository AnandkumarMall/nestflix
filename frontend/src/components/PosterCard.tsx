// A single poster tile used inside a PosterRow. Links somewhere (detail or player) and
// optionally shows a resume progress bar.

import { Link } from "react-router-dom";
import { imageUrl } from "../api/client";

interface Props {
  title: string;
  posterPath: string | null;
  to: string;
  subtitle?: string;
  /** 0..1 watched fraction; renders a resume bar when > 0. */
  progress?: number;
}

export default function PosterCard({
  title,
  posterPath,
  to,
  subtitle,
  progress,
}: Props) {
  const src = imageUrl(posterPath, "w342");
  return (
    <Link to={to} className="poster-card" title={title}>
      <div className="poster-img">
        {src ? (
          <img src={src} alt={title} loading="lazy" />
        ) : (
          <div className="poster-fallback">{title}</div>
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
      <div className="poster-title">{title}</div>
      {subtitle && <div className="poster-subtitle">{subtitle}</div>}
    </Link>
  );
}
