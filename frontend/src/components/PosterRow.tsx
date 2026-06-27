// A horizontally-scrolling titled row of poster cards.

import type { ReactNode } from "react";

interface Props {
  title: string;
  children: ReactNode;
}

export default function PosterRow({ title, children }: Props) {
  return (
    <section className="poster-row">
      <h2 className="row-title">{title}</h2>
      <div className="row-scroller">{children}</div>
    </section>
  );
}
