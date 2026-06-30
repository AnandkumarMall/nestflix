// Active-profile context. Playback/progress calls are per-profile, so the chosen
// profile id is kept here and persisted to localStorage across reloads.

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { api, type Profile } from './api/client';

const STORAGE_KEY = 'nestflix.profileId';

interface ProfileContextValue {
  profiles: Profile[];
  activeProfile: Profile | null;
  setActiveProfile: (id: number) => void;
  loading: boolean;
}

const ProfileContext = createContext<ProfileContextValue | null>(null);

export function ProfileProvider({ children }: { children: ReactNode }) {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [activeId, setActiveId] = useState<number | null>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? Number(stored) : null;
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .profiles()
      .then((p) => setProfiles(p.profiles))
      .catch(() => setProfiles([]))
      .finally(() => setLoading(false));
  }, []);

  const setActiveProfile = (id: number) => {
    setActiveId(id);
    localStorage.setItem(STORAGE_KEY, String(id));
  };

  const activeProfile =
    profiles.find((p) => p.id === activeId) ??
    // If only one profile exists, treat it as active automatically.
    (profiles.length === 1 ? profiles[0] : null);

  return (
    <ProfileContext.Provider value={{ profiles, activeProfile, setActiveProfile, loading }}>
      {children}
    </ProfileContext.Provider>
  );
}

export function useProfile(): ProfileContextValue {
  const ctx = useContext(ProfileContext);
  if (!ctx) throw new Error('useProfile must be used within a ProfileProvider');
  return ctx;
}
