// Gate the app until a profile is chosen. With a single profile it auto-selects, so this
// only shows when there are multiple profiles and none is active yet.

import type { ReactNode } from 'react';
import { useProfile } from '../profile';

export default function ProfileGate({ children }: { children: ReactNode }) {
  const { profiles, activeProfile, setActiveProfile, loading } = useProfile();

  if (loading) return <div className="gate">Loading…</div>;

  if (!activeProfile) {
    return (
      <div className="gate">
        <h1>Who&apos;s watching?</h1>
        <div className="gate-profiles">
          {profiles.map((p) => (
            <button key={p.id} className="gate-profile" onClick={() => setActiveProfile(p.id)}>
              <span className="gate-avatar" style={{ background: p.avatar_color }}>
                {p.name.charAt(0).toUpperCase()}
              </span>
              <span>{p.name}</span>
            </button>
          ))}
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
