/**
 * Título de sección del home, con enlace opcional a la sección completa.
 */
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

interface Props {
  id: string;
  title: string;
  description?: string;
  link?: { to: string; label: string };
  children?: ReactNode;
}

export default function SectionHeading({ id, title, description, link, children }: Props) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-x-6 gap-y-3 border-b border-felt-line pb-3">
      <div>
        <h2 id={id} className="font-display text-2xl sm:text-3xl">
          {title}
        </h2>
        {description && <p className="mt-1 max-w-prose text-sm text-ivory-dim">{description}</p>}
      </div>
      <div className="flex items-center gap-4">
        {children}
        {link && (
          <Link to={link.to} className="text-sm font-semibold text-brass hover:text-brass-bright">
            {link.label}
          </Link>
        )}
      </div>
    </div>
  );
}
