/**
 * Página 404.
 */
import { Link } from "react-router-dom";
import { usePageView } from "../analytics";

export default function NotFoundPage() {
  usePageView("Página no encontrada | TCGMASTER");
  return (
    <div className="mx-auto max-w-shop px-4 py-24 sm:px-6">
      <h1 className="font-display text-3xl">Esta página no existe</h1>
      <p className="mt-3 text-ivory-dim">Revisa la dirección o vuelve al catálogo.</p>
      <Link to="/cartas" className="mt-6 inline-block font-semibold text-brass hover:text-brass-bright">
        Ir a las cartas
      </Link>
    </div>
  );
}
