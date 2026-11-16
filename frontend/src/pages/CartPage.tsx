/**
 * Carrito: líneas con cantidad editable, subtotal y avisos de stock o precio.
 */
import { useEffect, useRef } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { trackQuantityChange, trackRemoveFromCart, trackViewCart, usePageView } from "../analytics";
import { ConditionChip } from "../components/Indicators";
import { errorMessage } from "../lib/api";
import { lineQuantities } from "../lib/cart";
import { formatCLP, LANGUAGE, SEALED_TYPE } from "../lib/format";
import { useCart, useCartActions } from "../lib/session";
import type { CartLine } from "../lib/types";

function Line({ line }: { line: CartLine }) {
  const { update, remove } = useCartActions();
  const p = line.product;
  const busy =
    (update.isPending && update.variables?.itemId === line.id) || (remove.isPending && remove.variables === line.id);
  return (
    <li className={`grid grid-cols-[4.5rem_1fr] gap-4 border-t border-felt-line py-5 sm:grid-cols-[5rem_1fr_auto] ${busy ? "opacity-60" : ""}`}>
      <Link to={`/producto/${p.slug}`} className="block">
        <img
          src={p.thumb}
          alt=""
          width={80}
          height={112}
          loading="lazy"
          className={`aspect-[5/7] w-full rounded-[4px] ${p.product_type === "carta" ? "object-cover" : "bg-ivory object-contain p-1"}`}
        />
      </Link>
      <div className="min-w-0">
        <Link to={`/producto/${p.slug}`} className="font-semibold hover:text-brass-bright">
          {p.name}
        </Link>
        <p className="mt-0.5 text-sm text-ivory-dim">{p.set_name ?? "Accesorio"}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
          {p.condition && <ConditionChip condition={p.condition} />}
          {p.language && <span className="text-ivory-dim">{LANGUAGE[p.language]}</span>}
          {p.is_foil && <span className="font-semibold text-brass-bright">Foil</span>}
          {p.sealed_type && <span className="text-ivory-dim">{SEALED_TYPE[p.sealed_type]}</span>}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-ivory-dim">
            Cantidad
            <select
              value={line.quantity}
              disabled={busy}
              onChange={(e) => {
                const quantity = Number(e.target.value);
                const before = line.quantity;
                update.mutate(
                  { itemId: line.id, quantity },
                  { onSuccess: () => trackQuantityChange(p, before, quantity) },
                );
              }}
              className="price rounded-sm border border-felt-line bg-felt px-2 py-1 text-ivory focus:border-brass"
            >
              {lineQuantities(p.stock, line.quantity).map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              remove.mutate(line.id, { onSuccess: () => trackRemoveFromCart(p, line.quantity) })
            }
            className="text-sm font-semibold text-ivory-dim underline-offset-2 hover:text-ivory hover:underline"
          >
            Quitar
          </button>
        </div>
        {update.isError && update.variables?.itemId === line.id && (
          <p role="alert" className="mt-2 text-sm text-cond-hp">{errorMessage(update.error)}</p>
        )}
      </div>
      <p className="price col-start-2 text-left sm:col-start-3 sm:text-right">
        <span className="font-semibold text-brass">{formatCLP(line.line_total_clp)}</span>
        {line.quantity > 1 && (
          <span className="block text-xs text-ivory-dim">{formatCLP(line.unit_price_clp)} c/u</span>
        )}
      </p>
    </li>
  );
}

export default function CartPage() {
  const { data: cart, isLoading, isError } = useCart();
  const paymentError = useSearchParams()[0].get("pago") === "error";

  usePageView("Carrito | TCGMASTER");
  // view_cart una vez por visita a la página, cuando el carrito ya cargó.
  const viewed = useRef(false);
  useEffect(() => {
    if (cart && cart.items.length > 0 && !viewed.current) {
      viewed.current = true;
      trackViewCart(cart);
    }
  }, [cart]);

  if (isError) {
    return (
      <div className="mx-auto max-w-shop px-4 py-24 sm:px-6">
        <h1 className="font-display text-3xl">No pudimos cargar tu carrito</h1>
        <p className="mt-3 text-ivory-dim">Recarga la página en unos segundos.</p>
      </div>
    );
  }
  if (isLoading || !cart) return <div className="min-h-screen" />;

  if (cart.items.length === 0) {
    return (
      <div className="mx-auto max-w-shop px-4 py-24 sm:px-6">
        <h1 className="font-display text-3xl sm:text-4xl">Tu carrito está vacío</h1>
        <p className="mt-3 text-ivory-dim">Agrega cartas, sobres o accesorios desde el catálogo.</p>
        <div className="mt-6 flex gap-5">
          <Link to="/cartas" className="font-semibold text-brass hover:text-brass-bright">Ver cartas</Link>
          <Link to="/sellados" className="font-semibold text-brass hover:text-brass-bright">Ver sellados</Link>
        </div>
      </div>
    );
  }

  const blocked = cart.warnings.some((w) => w.includes("ya no está disponible") || w.includes("pediste"));
  return (
    <div className="mx-auto max-w-shop px-4 pt-10 sm:px-6">
      <h1 className="font-display text-3xl sm:text-4xl">Carrito</h1>
      {paymentError && (
        <p role="alert" className="mt-4 border border-cond-hp px-4 py-3 text-sm text-cond-hp">
          No pudimos confirmar el pago. No se realizó ningún cobro; puedes intentarlo de nuevo.
        </p>
      )}
      <div className="mt-8 grid gap-10 lg:grid-cols-[1fr_20rem]">
        <section aria-label="Productos en el carrito">
          {cart.warnings.length > 0 && (
            <ul role="status" className="mb-4 space-y-1 border border-cond-mp px-4 py-3 text-sm text-cond-mp">
              {cart.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}
          <ul className="border-b border-felt-line">
            {cart.items.map((line) => (
              <Line key={line.id} line={line} />
            ))}
          </ul>
        </section>

        <aside aria-label="Resumen" className="h-fit border border-felt-line bg-felt-raised p-6">
          <h2 className="font-display text-xl">Resumen</h2>
          <dl className="price mt-4 space-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-ivory-dim">Productos ({cart.item_count})</dt>
              <dd>{formatCLP(cart.subtotal_clp)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-ivory-dim">Envío</dt>
              <dd className="text-ivory-dim">Se calcula al pagar</dd>
            </div>
            <div className="flex justify-between border-t border-felt-line pt-3 text-base">
              <dt className="font-semibold">Subtotal</dt>
              <dd className="font-semibold text-brass">{formatCLP(cart.subtotal_clp)}</dd>
            </div>
          </dl>
          {blocked ? (
            <p className="mt-6 text-sm text-cond-mp">Revisa los avisos del carrito antes de pagar.</p>
          ) : (
            <Link
              to="/checkout"
              className="mt-6 block w-full rounded-sm bg-brass py-2.5 text-center font-semibold text-felt hover:bg-brass-bright"
            >
              Continuar al pago
            </Link>
          )}
          <p className="mt-2 text-xs text-ivory-dim">Puedes comprar con tu cuenta o como invitado.</p>
        </aside>
      </div>
    </div>
  );
}
