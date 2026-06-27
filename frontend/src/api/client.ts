// Typed fetch wrappers for the Nestflix backend.
// All backend calls go through this module — never raw fetch() in components.

const BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

export interface Health {
  status: string;
  tmdb_configured: boolean;
  library_paths: string[];
}

export interface Profile {
  id: number;
  name: string;
  avatar_color: string;
  created_at?: string;
}

export const api = {
  health: () => get<Health>("/health"),
  profiles: () => get<{ profiles: Profile[] }>("/profiles"),
};
