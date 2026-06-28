// Per-profile viewing stats: totals, thumbs, top genres, and recent finishes.
// All data comes from /api/stats (no charting library — bars are plain CSS widths).

import { useEffect, useState } from "react";
import { api, type Stats } from "../api/client";
import { useProfile } from "../profile";
import PosterRow from "../components/PosterRow";
import PosterCard from "../components/PosterCard";

export default function StatsPage() {
  const { activeProfile } = useProfile();
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    if (!activeProfile) return;
    api
      .stats(activeProfile.id)
      .then(setStats)
      .catch(() => setStats(null));
  }, [activeProfile]);

  if (!activeProfile) return <div className="page-loading">Pick a profile to see stats.</div>;
  if (!stats) return <div className="page-loading">Loading your stats…</div>;

  const hours = stats.seconds_watched / 3600;
  const maxGenre = stats.top_genres[0]?.count ?? 1;

  return (
    <div className="stats">
      <h1 className="stats-heading">{activeProfile.name}'s viewing</h1>

      <div className="stat-cards">
        <div className="stat-card">
          <span className="stat-value">{stats.titles_finished}</span>
          <span className="stat-label">Titles finished</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{hours.toFixed(1)}</span>
          <span className="stat-label">Hours watched</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">👍 {stats.ratings.up}</span>
          <span className="stat-label">Liked</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">👎 {stats.ratings.down}</span>
          <span className="stat-label">Disliked</span>
        </div>
      </div>

      {stats.top_genres.length > 0 && (
        <section className="stat-genres">
          <h2 className="row-title">Top genres</h2>
          {stats.top_genres.map((g) => (
            <div className="genre-bar-row" key={g.name}>
              <span className="genre-bar-label">{g.name}</span>
              <div className="genre-bar-track">
                <div
                  className="genre-bar-fill"
                  style={{ width: `${(g.count / maxGenre) * 100}%` }}
                />
              </div>
              <span className="genre-bar-count">{g.count}</span>
            </div>
          ))}
        </section>
      )}

      {stats.recently_finished.length > 0 && (
        <PosterRow title="Recently Finished">
          {stats.recently_finished.map((t) => (
            <PosterCard
              key={`${t.kind}-${t.id}`}
              title={t.title}
              posterPath={t.poster_path}
              to={`/title/${t.kind}/${t.id}`}
            />
          ))}
        </PosterRow>
      )}

      {stats.titles_finished === 0 && (
        <div className="page-loading">
          Finish something to start building your stats.
        </div>
      )}
    </div>
  );
}
