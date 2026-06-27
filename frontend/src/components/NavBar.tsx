// Top navigation bar: brand, primary links, and the active profile indicator.

import { Link } from "react-router-dom";
import { useProfile } from "../profile";

export default function NavBar() {
  const { activeProfile, profiles, setActiveProfile } = useProfile();

  return (
    <header className="navbar">
      <Link to="/" className="brand">
        NESTFLIX
      </Link>
      <nav className="nav-links">
        <Link to="/">Home</Link>
      </nav>
      {activeProfile && (
        <div className="nav-profile">
          <span
            className="nav-avatar"
            style={{ background: activeProfile.avatar_color }}
          >
            {activeProfile.name.charAt(0).toUpperCase()}
          </span>
          {profiles.length > 1 && (
            <select
              value={activeProfile.id}
              onChange={(e) => setActiveProfile(Number(e.target.value))}
            >
              {profiles.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          )}
        </div>
      )}
    </header>
  );
}
