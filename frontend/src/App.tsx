import { useEffect, useState } from "react";
import { api, type Health, type Profile } from "./api/client";

// Base-skeleton home screen. Confirms the frontend↔backend wiring and shows config
// status. Real Netflix-style rows arrive in the frontend feature.
export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.health(), api.profiles()])
      .then(([h, p]) => {
        setHealth(h);
        setProfiles(p.profiles);
      })
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">NESTFLIX</span>
      </header>

      <main className="hero">
        <h1>Your library, your taste.</h1>
        <p className="tagline">
          A Netflix-style home for everything you’ve downloaded — enriched, organized,
          and recommended just for you.
        </p>

        {error && <p className="status error">Backend not reachable: {error}</p>}

        {health && (
          <div className="status-card">
            <Row label="API" value={health.status === "ok" ? "✅ running" : health.status} />
            <Row
              label="TMDB key"
              value={health.tmdb_configured ? "✅ configured" : "⚠️ missing (set TMDB_API_KEY)"}
            />
            <Row
              label="Library paths"
              value={
                health.library_paths.length
                  ? health.library_paths.join(", ")
                  : "⚠️ none (set LIBRARY_PATHS)"
              }
            />
            <Row
              label="Profiles"
              value={profiles.map((p) => p.name).join(", ") || "none yet"}
            />
          </div>
        )}
      </main>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="status-row">
      <span className="status-label">{label}</span>
      <span className="status-value">{value}</span>
    </div>
  );
}
