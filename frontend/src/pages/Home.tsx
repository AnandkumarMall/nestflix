// Netflix-style home: a hero plus rows for Continue Watching, the local library, and
// TMDB discovery (trending / new releases).

import { useEffect, useState } from 'react';
import {
  api,
  type ContinueItem,
  type DiscoverItem,
  type Library,
  type RecRow,
} from '../api/client';
import { useProfile } from '../profile';
import { matchScore } from '../utils';
import Hero from '../components/Hero';
import PosterRow from '../components/PosterRow';
import PosterCard from '../components/PosterCard';

export default function Home() {
  const { activeProfile } = useProfile();
  const [library, setLibrary] = useState<Library | null>(null);
  const [continueItems, setContinueItems] = useState<ContinueItem[]>([]);
  const [recRows, setRecRows] = useState<RecRow[]>([]);
  const [trending, setTrending] = useState<DiscoverItem[]>([]);
  const [newReleases, setNewReleases] = useState<DiscoverItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .library()
      .then(setLibrary)
      .catch((e) => setError(String(e)));
    api
      .trending()
      .then((r) => setTrending(r.items))
      .catch(() => undefined);
    api
      .newReleases()
      .then((r) => setNewReleases(r.items))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!activeProfile) return;
    api
      .continueWatching(activeProfile.id)
      .then((r) => setContinueItems(r.items))
      .catch(() => undefined);
    api
      .recommendationRows(activeProfile.id)
      .then((r) => setRecRows(r.rows))
      .catch(() => undefined);
  }, [activeProfile]);

  if (error) return <div className="page-error">Couldn&apos;t load library: {error}</div>;
  if (!library) return <div className="page-loading">Loading your library…</div>;

  const heroMovie = library.movies.find((m) => m.backdrop_path) ?? library.movies[0];

  return (
    <div className="home">
      {heroMovie && <Hero movie={heroMovie} />}

      <div className="rows">
        {continueItems.length > 0 && (
          <PosterRow title="Continue Watching">
            {continueItems.map((c) => (
              <PosterCard
                key={c.media_file_id}
                title={
                  c.kind === 'episode' && c.season != null
                    ? `${c.title} S${c.season}E${c.episode}`
                    : c.title
                }
                posterPath={c.poster_path}
                to={`/watch/${c.media_file_id}`}
                progress={c.duration_seconds > 0 ? c.position_seconds / c.duration_seconds : 0}
              />
            ))}
          </PosterRow>
        )}

        {recRows.map((row) => (
          <PosterRow key={row.key} title={row.title}>
            {row.items.map((it) => (
              <PosterCard
                key={`${row.key}-${it.kind}-${it.id}`}
                title={it.title}
                posterPath={it.poster_path}
                to={`/title/${it.kind}/${it.id}`}
                subtitle={it.reason}
              />
            ))}
          </PosterRow>
        ))}

        {library.movies.length > 0 && (
          <PosterRow title="Movies">
            {library.movies.map((m) => (
              <PosterCard
                key={m.id}
                title={m.title || m.parsed_title}
                posterPath={m.poster_path}
                to={`/title/movie/${m.id}`}
                playTo={m.media_file_id != null ? `/watch/${m.media_file_id}` : undefined}
                subtitle={m.year ? String(m.year) : undefined}
                match={matchScore(m.rating)}
                runtime={m.runtime}
                genres={m.genres}
              />
            ))}
          </PosterRow>
        )}

        {library.shows.length > 0 && (
          <PosterRow title="TV Shows">
            {library.shows.map((s) => (
              <PosterCard
                key={s.id}
                title={s.title || s.parsed_title}
                posterPath={s.poster_path}
                to={`/title/show/${s.id}`}
                subtitle={`${s.episodes.length} episodes`}
                match={matchScore(s.rating)}
                genres={s.genres}
              />
            ))}
          </PosterRow>
        )}

        {trending.length > 0 && (
          <PosterRow title="Trending on TMDB">
            {trending.map((d) => (
              <PosterCard
                key={`tr-${d.id}`}
                title={d.title || d.name || 'Untitled'}
                posterPath={d.poster_path}
                to="/"
                subtitle={(d.release_date || d.first_air_date)?.slice(0, 4)}
              />
            ))}
          </PosterRow>
        )}

        {newReleases.length > 0 && (
          <PosterRow title="New Releases">
            {newReleases.map((d) => (
              <PosterCard
                key={`nr-${d.id}`}
                title={d.title || d.name || 'Untitled'}
                posterPath={d.poster_path}
                to="/"
                subtitle={(d.release_date || d.first_air_date)?.slice(0, 4)}
              />
            ))}
          </PosterRow>
        )}
      </div>
    </div>
  );
}
