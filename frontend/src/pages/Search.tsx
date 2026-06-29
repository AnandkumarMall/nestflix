// Library search results. The query comes from the URL (?q=), set by the NavBar's
// search box, so results are linkable and survive a refresh.

import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, type SearchResult } from "../api/client";
import { matchScore } from "../utils";
import PosterRow from "../components/PosterRow";
import PosterCard from "../components/PosterCard";

export default function Search() {
  const [params] = useSearchParams();
  const q = params.get("q")?.trim() ?? "";
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!q) {
      setResults([]);
      return;
    }
    setLoading(true);
    api
      .searchLibrary(q)
      .then((r) => setResults(r.results))
      .catch(() => setResults([]))
      .finally(() => setLoading(false));
  }, [q]);

  if (!q) return <div className="page-loading">Type a title to search your library.</div>;
  if (loading) return <div className="page-loading">Searching…</div>;

  return (
    <div className="home">
      <div className="rows">
        {results.length === 0 ? (
          <div className="page-loading">No matches for “{q}”.</div>
        ) : (
          <PosterRow title={`Results for “${q}”`}>
            {results.map((r) => (
              <PosterCard
                key={`${r.type}-${r.id}`}
                title={r.title || r.parsed_title}
                posterPath={r.poster_path}
                to={`/title/${r.type}/${r.id}`}
                playTo={
                  r.type === "movie" && r.media_file_id != null
                    ? `/watch/${r.media_file_id}`
                    : undefined
                }
                subtitle={
                  r.type === "show"
                    ? `${r.episodes.length} episodes`
                    : r.year
                      ? String(r.year)
                      : undefined
                }
                match={matchScore(r.rating)}
                runtime={r.type === "movie" ? r.runtime : undefined}
                genres={r.genres}
              />
            ))}
          </PosterRow>
        )}
      </div>
    </div>
  );
}
