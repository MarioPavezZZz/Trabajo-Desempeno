/**
 * Encabezado: marca, navegación principal, búsqueda, cuenta y carrito.
 * En celular la navegación pasa a una fila desplazable bajo la marca.
 */
import { type FormEvent, useEffect, useState } from "react";
import { Link, NavLink, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useCart, useMe } from "../lib/session";

const NAV = [
  { to: "/", label: "Inicio", end: true },
  { to: "/cartas", label: "Cartas" },
  { to: "/sellados", label: "Sellados" },
  { to: "/ofertas", label: "Ofertas" },
  { to: "/accesorios", label: "Accesorios" },
];

const navClass = ({ isActive }: { isActive: boolean }) =>
  `whitespace-nowrap border-b-2 py-1 text-sm font-semibold transition-colors ${
    isActive ? "border-brass text-ivory" : "border-transparent text-ivory-dim hover:text-ivory"
  }`;

export default function Header() {
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const [query, setQuery] = useState("");
  const { data: me } = useMe();
  const count = useCart().data?.item_count ?? 0;

  // Mantiene el texto de búsqueda sincronizado con la URL de /buscar.
  useEffect(() => {
    setQuery(location.pathname === "/buscar" ? (params.get("q") ?? "") : "");
  }, [location.pathname, params]);

  function onSearch(event: FormEvent) {
    event.preventDefault();
    const q = query.trim();
    if (q) navigate(`/buscar?q=${encodeURIComponent(q)}`);
  }

  return (
    <header className="border-b border-felt-line bg-felt-deep">
      <div className="mx-auto flex max-w-shop flex-wrap items-center gap-x-4 gap-y-3 px-4 py-4 sm:gap-x-8 sm:px-6">
        <Link to="/" className="font-display text-xl leading-none text-ivory sm:text-2xl" aria-label="TCGMASTER, inicio">
          TCG<span className="text-brass">MASTER</span>
        </Link>

        <nav aria-label="Principal" className="order-3 -mx-4 w-full overflow-x-auto overflow-y-hidden px-4 [scrollbar-width:none] lg:order-none lg:mx-0 lg:w-auto lg:overflow-visible lg:px-0">
          <ul className="flex gap-6">
            {NAV.map((item) => (
              <li key={item.to}>
                <NavLink to={item.to} end={item.end} className={navClass}>
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        <div className="ml-auto flex items-center gap-4 sm:gap-5">
          <form role="search" onSubmit={onSearch} className="hidden sm:block">
            <label htmlFor="buscar" className="sr-only">
              Buscar cartas y productos
            </label>
            <input
              id="buscar"
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Buscar por nombre o set"
              maxLength={100}
              className="w-56 rounded-sm border border-felt-line bg-felt px-3 py-1.5 text-sm text-ivory placeholder:text-ivory-dim focus:border-brass lg:w-64"
            />
          </form>
          <NavLink to={me ? "/cuenta" : "/cuenta/ingresar"} className={navClass}>
            {me ? "Mi cuenta" : "Ingresar"}
          </NavLink>
          <NavLink to="/carrito" className={navClass}>
            Carrito{" "}
            <span className="price text-brass" aria-label={`${count} productos`}>
              ({count})
            </span>
          </NavLink>
        </div>

        {/* Búsqueda en celular: ocupa una fila propia. */}
        <form role="search" onSubmit={onSearch} className="order-4 w-full sm:hidden">
          <label htmlFor="buscar-movil" className="sr-only">
            Buscar cartas y productos
          </label>
          <input
            id="buscar-movil"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Buscar por nombre o set"
            maxLength={100}
            className="w-full rounded-sm border border-felt-line bg-felt px-3 py-2 text-sm text-ivory placeholder:text-ivory-dim focus:border-brass"
          />
        </form>
      </div>
    </header>
  );
}
