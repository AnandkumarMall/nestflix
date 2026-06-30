// A horizontally-scrolling titled row of poster cards, with hover scroll arrows
// (Netflix-style) that page the scroller left/right.

import { useRef, type ReactNode } from 'react';

interface Props {
  title: string;
  children: ReactNode;
}

export default function PosterRow({ title, children }: Props) {
  const scrollerRef = useRef<HTMLDivElement>(null);

  const page = (dir: -1 | 1) => {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollBy({ left: dir * el.clientWidth * 0.8, behavior: 'smooth' });
  };

  return (
    <section className="poster-row">
      <h2 className="row-title">{title}</h2>
      <div className="row-wrap">
        <button className="row-arrow left" onClick={() => page(-1)} aria-label="Scroll left">
          ‹
        </button>
        <div className="row-scroller" ref={scrollerRef}>
          {children}
        </div>
        <button className="row-arrow right" onClick={() => page(1)} aria-label="Scroll right">
          ›
        </button>
      </div>
    </section>
  );
}
