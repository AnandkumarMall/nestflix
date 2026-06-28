// Top navigation bar: brand, primary links, search, and the active profile indicator.
// Background fades from transparent to solid once the page is scrolled (Netflix-style).

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useProfile } from "../profile";

export default function NavBar() {
  const { activeProfile, profiles, setActiveProfile } = useProfile();
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 50);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header className={`navbar ${scrolled ? "scrolled" : ""}`}>
      <Link to="/" className="brand" aria-label="Nestflix home">
        <svg className="brand-logo" viewBox="0 0 111 30" role="img">
          <path d="M105.062 14.28L111 30c-1.75-.25-3.499-.563-5.28-.845l-3.345-8.686-3.437 7.969c-1.687-.282-3.344-.376-5.031-.595l6.031-12.75-5.25-10.5c1.5-.156 2.969-.344 4.469-.5l3.188 8.344 3.156-7.875c1.688-.187 3.375-.375 5.062-.625l-6.125 12.844zM90.47 0H81.28l-.125 30c2.625-.375 5.25-.75 7.875-1.125V0zM64.25 28.625c-2.625.375-5.25.75-7.875 1.125V0h9.125v28.625zM49.469 1.875v27.125c-2.625.375-5.25.75-7.875 1.125V1.875H33.125V0h25.25v1.875h-8.906zM24.938 0v30c-2.625-.375-5.25-.75-7.875-1.125V0h7.875zM12.594 0L0 30l12.469-.031c1.781-.031 3.531-.156 5.281-.281L19.5 17.5l3.5 11.25c1.875-.156 3.75-.281 5.625-.406L16.031 0h-3.437z" />
        </svg>
      </Link>
      <nav className="nav-links">
        <Link to="/">Home</Link>
      </nav>

      <div className="nav-right">
        <button className="nav-icon" aria-label="Search" title="Search">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <circle cx="11" cy="11" r="8" />
            <path d="M21 21l-4.35-4.35" />
          </svg>
        </button>

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
      </div>
    </header>
  );
}
