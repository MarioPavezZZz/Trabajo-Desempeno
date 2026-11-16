/**
 * Paginación numerada con anterior/siguiente.
 * Muestra la primera, la última y las páginas cercanas a la actual.
 */
interface Props {
  page: number;
  totalPages: number;
  onPage: (page: number) => void;
}

/** Páginas a mostrar; `null` representa un salto ("…"). */
export function pageWindow(page: number, total: number): (number | null)[] {
  const pages = new Set([1, total, page - 1, page, page + 1].filter((p) => p >= 1 && p <= total));
  const sorted = [...pages].sort((a, b) => a - b);
  const out: (number | null)[] = [];
  sorted.forEach((p, i) => {
    if (i > 0 && p - sorted[i - 1] > 1) out.push(null);
    out.push(p);
  });
  return out;
}

export default function Pagination({ page, totalPages, onPage }: Props) {
  if (totalPages <= 1) return null;
  const base = "min-w-9 rounded-sm px-3 py-1.5 text-sm font-semibold";
  return (
    <nav aria-label="Paginación" className="mt-12 flex flex-wrap items-center justify-center gap-1">
      <button
        type="button"
        disabled={page <= 1}
        onClick={() => onPage(page - 1)}
        className={`${base} text-ivory-dim hover:text-ivory disabled:opacity-40`}
      >
        Anterior
      </button>
      {pageWindow(page, totalPages).map((p, i) =>
        p === null ? (
          <span key={`gap-${i}`} className="px-1 text-ivory-dim">
            …
          </span>
        ) : (
          <button
            key={p}
            type="button"
            aria-current={p === page ? "page" : undefined}
            onClick={() => onPage(p)}
            className={`${base} price ${p === page ? "bg-brass text-felt" : "text-ivory hover:bg-felt-raised"}`}
          >
            {p}
          </button>
        ),
      )}
      <button
        type="button"
        disabled={page >= totalPages}
        onClick={() => onPage(page + 1)}
        className={`${base} text-ivory-dim hover:text-ivory disabled:opacity-40`}
      >
        Siguiente
      </button>
    </nav>
  );
}
