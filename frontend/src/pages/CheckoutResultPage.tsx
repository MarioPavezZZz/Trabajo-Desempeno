/**
 * Resultado del pago. Llega aquí desde el retorno de la pasarela con
 * `?clave=` (invitados) o con la sesión de la cuenta dueña del pedido.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { trackPurchase, usePageView } from "../analytics";
import { api, ApiError } from "../lib/api";
import { formatCLP, formatDate } from "../lib/format";
import { CART_KEY } from "../lib/session";
import type { Order } from "../lib/types";

const COPY: Record<Order["status"], { title: string; body: string }> = {
  pagada: {
    title: "Pago aprobado",
    body: "Recibimos tu pago y tu pedido quedó confirmado. Guarda este enlace para volver a consultarlo.",
  },
  rechazada: {
    title: "El pago fue rechazado",
    body: "No se realizó ningún cobro. Tus productos siguen en el carrito para que lo intentes de nuevo.",
  },
  anulada: {
    title: "El pago no se completó",
    body: "Se canceló el pago o se agotó el tiempo. No se realizó ningún cobro y tus productos siguen en el carrito.",
  },
  pendiente: {
    title: "Esperando la confirmación del pago",
    body: "Esto toma unos segundos. La página se actualiza sola.",
  },
};

export default function CheckoutResultPage() {
  const { transactionId = "" } = useParams();
  const [params] = useSearchParams();
  const key = params.get("clave");
  const qc = useQueryClient();
  const { data: order, error } = useQuery({
    queryKey: ["order", transactionId, key],
    queryFn: () => api.order(transactionId, key),
    retry: (count, err) => !(err instanceof ApiError && err.status === 404) && count < 2,
    // Mientras esté pendiente se consulta cada 2 s.
    refetchInterval: (q) => (q.state.data?.status === "pendiente" ? 2000 : false),
  });

  usePageView("Resultado del pago | TCGMASTER");
  useEffect(() => {
    // El carrito cambió (se vació o se liberó la reserva): se recarga el contador.
    qc.invalidateQueries({ queryKey: CART_KEY });
    // purchase solo con el pago aprobado; no se repite si se recarga la página.
    if (order) trackPurchase(order);
  }, [qc, order?.status]);

  if (error) {
    return (
      <div className="mx-auto max-w-shop px-4 py-24 sm:px-6">
        <h1 className="font-display text-3xl">No encontramos este pedido</h1>
        <p className="mt-3 text-ivory-dim">Revisa el enlace o ingresa con la cuenta con que compraste.</p>
      </div>
    );
  }
  if (!order) return <div className="min-h-screen" />;

  const copy = COPY[order.status];
  const ok = order.status === "pagada";
  return (
    <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
      <p className={`text-sm font-semibold ${ok ? "text-cond-nm" : order.status === "pendiente" ? "text-ivory-dim" : "text-cond-hp"}`}>
        Pedido {order.transaction_id}
      </p>
      <h1 className="mt-1 font-display text-3xl sm:text-4xl">{copy.title}</h1>
      <p className="mt-3 max-w-prose text-ivory-dim">{copy.body}</p>

      {!ok && order.status !== "pendiente" && (
        <Link
          to="/carrito"
          className="mt-6 inline-block rounded-sm bg-brass px-5 py-2.5 font-semibold text-felt hover:bg-brass-bright"
        >
          Volver al carrito
        </Link>
      )}

      <section aria-labelledby="detalle" className="mt-10 border border-felt-line bg-felt-raised p-6">
        <h2 id="detalle" className="font-display text-xl">Detalle</h2>
        <ul className="mt-4 divide-y divide-felt-line">
          {order.items.map((item) => (
            <li key={item.product_id} className="flex items-center gap-4 py-3 text-sm">
              {item.thumb && (
                <img src={item.thumb} alt="" width={40} height={56} loading="lazy" className="rounded-[3px] bg-ivory object-contain" />
              )}
              <span className="flex-1">
                {item.slug ? (
                  <Link to={`/producto/${item.slug}`} className="hover:text-brass-bright">
                    {item.name}
                  </Link>
                ) : (
                  item.name
                )}
                <span className="block text-xs text-ivory-dim">
                  {item.quantity} × {formatCLP(item.unit_price_clp)}
                </span>
              </span>
              <span className="price">{formatCLP(item.line_total_clp)}</span>
            </li>
          ))}
        </ul>
        <dl className="price mt-2 space-y-2 border-t border-felt-line pt-4 text-sm">
          <div className="flex justify-between">
            <dt className="text-ivory-dim">Subtotal</dt>
            <dd>{formatCLP(order.subtotal_clp)}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-ivory-dim">{order.shipping_method === "domicilio" ? "Envío a domicilio" : "Retiro en tienda"}</dt>
            <dd>{order.shipping_clp ? formatCLP(order.shipping_clp) : "Gratis"}</dd>
          </div>
          <div className="flex justify-between text-base">
            <dt className="font-semibold">Total</dt>
            <dd className="font-semibold text-brass">{formatCLP(order.total_clp)}</dd>
          </div>
        </dl>

        <dl className="mt-6 grid grid-cols-[9rem_1fr] gap-y-2 border-t border-felt-line pt-4 text-sm">
          <dt className="text-ivory-dim">Fecha</dt>
          <dd>{formatDate(order.created_at)}</dd>
          <dt className="text-ivory-dim">Contacto</dt>
          <dd className="break-all">
            {order.contact_name}, {order.contact_email}
          </dd>
          {order.shipping_method === "domicilio" && (
            <>
              <dt className="text-ivory-dim">Dirección</dt>
              <dd>
                {order.shipping_address.street}, {order.shipping_address.comuna}, {order.shipping_address.region}
              </dd>
            </>
          )}
          {order.payment && (
            <>
              <dt className="text-ivory-dim">Medio de pago</dt>
              <dd>
                {order.payment.provider === "mock" ? "Pago simulado" : "Webpay Plus (prueba)"}
                {order.payment.card_last4 && ok && `, tarjeta terminada en ${order.payment.card_last4}`}
              </dd>
              {order.payment.authorization_code && ok && (
                <>
                  <dt className="text-ivory-dim">Autorización</dt>
                  <dd className="price">{order.payment.authorization_code}</dd>
                </>
              )}
            </>
          )}
        </dl>
      </section>

      {ok && (
        <Link to="/cartas" className="mt-8 inline-block font-semibold text-brass hover:text-brass-bright">
          Seguir comprando
        </Link>
      )}
    </div>
  );
}
