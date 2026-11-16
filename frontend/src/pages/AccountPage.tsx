/**
 * Mi cuenta: datos del usuario y cierre de sesión. Los pedidos se agregan en el paso 6.
 */
import { useQuery } from "@tanstack/react-query";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { usePageView } from "../analytics";
import { api } from "../lib/api";
import { formatCLP, formatDate } from "../lib/format";
import { useAuthActions, useCart, useMe } from "../lib/session";
import type { OrderStatus } from "../lib/types";

const STATUS_LABEL: Record<OrderStatus, string> = {
  pagada: "Pagado",
  pendiente: "Esperando pago",
  rechazada: "Rechazado",
  anulada: "Anulado",
};
const STATUS_STYLE: Record<OrderStatus, string> = {
  pagada: "text-cond-nm",
  pendiente: "text-ivory-dim",
  rechazada: "text-cond-hp",
  anulada: "text-ivory-dim",
};

export default function AccountPage() {
  const { data: me, isLoading } = useMe();
  const orders = useQuery({ queryKey: ["orders", me?.id], queryFn: api.orders, enabled: !!me });
  const cart = useCart().data;
  const { logout } = useAuthActions();
  const navigate = useNavigate();

  usePageView("Mi cuenta | TCGMASTER");

  if (isLoading) return <div className="min-h-screen" />;
  if (!me) return <Navigate to="/cuenta/ingresar" replace />;

  return (
    <div className="mx-auto max-w-shop px-4 py-12 sm:px-6">
      <h1 className="font-display text-3xl sm:text-4xl">Hola, {me.full_name.split(" ")[0]}</h1>
      <div className="mt-8 grid gap-6 md:grid-cols-2">
        <section aria-labelledby="datos" className="border border-felt-line bg-felt-raised p-6">
          <h2 id="datos" className="font-display text-xl">Tus datos</h2>
          <dl className="mt-4 grid grid-cols-[7rem_1fr] gap-y-2 text-sm">
            <dt className="text-ivory-dim">Nombre</dt>
            <dd>{me.full_name}</dd>
            <dt className="text-ivory-dim">Correo</dt>
            <dd className="break-all">{me.email}</dd>
            <dt className="text-ivory-dim">Cliente desde</dt>
            <dd>{formatDate(me.created_at)}</dd>
          </dl>
          <button
            type="button"
            onClick={() => logout.mutate(undefined, { onSuccess: () => navigate("/") })}
            disabled={logout.isPending}
            className="mt-6 rounded-sm border border-felt-line px-4 py-2 text-sm font-semibold hover:border-brass"
          >
            {logout.isPending ? "Cerrando sesión…" : "Cerrar sesión"}
          </button>
        </section>

        <section aria-labelledby="carrito-resumen" className="border border-felt-line bg-felt-raised p-6">
          <h2 id="carrito-resumen" className="font-display text-xl">Tu carrito</h2>
          <p className="mt-4 text-sm text-ivory-dim">
            {cart && cart.item_count > 0
              ? `Tienes ${cart.item_count} ${cart.item_count === 1 ? "producto guardado" : "productos guardados"}.`
              : "Tu carrito está vacío."}
          </p>
          <Link to={cart && cart.item_count > 0 ? "/carrito" : "/cartas"} className="mt-4 inline-block text-sm font-semibold text-brass hover:text-brass-bright">
            {cart && cart.item_count > 0 ? "Ir al carrito" : "Explorar cartas"}
          </Link>
        </section>
      </div>

      <section aria-labelledby="pedidos" className="mt-10">
        <h2 id="pedidos" className="font-display text-2xl">Mis pedidos</h2>
        {orders.data && orders.data.length === 0 ? (
          <p className="mt-3 text-sm text-ivory-dim">Todavía no tienes pedidos.</p>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[32rem] text-sm">
              <thead className="text-left text-ivory-dim">
                <tr>
                  <th scope="col" className="pb-2 font-semibold">Pedido</th>
                  <th scope="col" className="pb-2 font-semibold">Fecha</th>
                  <th scope="col" className="pb-2 font-semibold">Estado</th>
                  <th scope="col" className="pb-2 text-right font-semibold">Total</th>
                </tr>
              </thead>
              <tbody className="price">
                {(orders.data ?? []).map((o) => (
                  <tr key={o.transaction_id} className="border-t border-felt-line">
                    <td className="py-2.5">
                      <Link to={`/checkout/resultado/${o.transaction_id}`} className="font-semibold text-brass hover:text-brass-bright">
                        {o.transaction_id}
                      </Link>
                    </td>
                    <td className="py-2.5">{formatDate(o.created_at)}</td>
                    <td className={`py-2.5 ${STATUS_STYLE[o.status]}`}>{STATUS_LABEL[o.status]}</td>
                    <td className="py-2.5 text-right">{formatCLP(o.total_clp)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
