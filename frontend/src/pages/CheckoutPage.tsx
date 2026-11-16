/**
 * Checkout con cuenta o como invitado: contacto (solo invitados), entrega,
 * resumen y botón de pago. Al pagar, el servidor reserva el stock y devuelve
 * a dónde enviar al navegador (Webpay o el simulador).
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { trackAddPaymentInfo, trackAddShippingInfo, trackBeginCheckout, usePageView } from "../analytics";
import { api, errorMessage } from "../lib/api";
import {
  checkoutPayload,
  EMPTY_CHECKOUT,
  goToPayment,
  REGIONS,
  TEST_CHECKOUT,
  TEST_HELPERS_ENABLED,
  validateCheckout,
} from "../lib/checkout";
import { formatCLP } from "../lib/format";
import { useCart, useMe } from "../lib/session";
import type { CheckoutForm } from "../lib/types";

const inputClass =
  "mt-1 w-full rounded-sm border bg-felt px-3 py-2 text-ivory placeholder:text-ivory-dim focus:border-brass";

function Field({
  id,
  label,
  error,
  children,
}: {
  id: string;
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label htmlFor={id} className="text-sm font-semibold">
        {label}
      </label>
      {children}
      {error && (
        <p id={`${id}-error`} className="mt-1 text-xs text-cond-hp">
          {error}
        </p>
      )}
    </div>
  );
}

export default function CheckoutPage() {
  const { data: me, isLoading: meLoading } = useMe();
  const { data: cart, isLoading: cartLoading } = useCart();
  const options = useQuery({ queryKey: ["checkout-options"], queryFn: api.checkoutOptions });
  const [form, setForm] = useState<CheckoutForm>(EMPTY_CHECKOUT);
  const [errors, setErrors] = useState<Partial<Record<keyof CheckoutForm, string>>>({});
  const isGuest = !me;

  const pay = useMutation({
    mutationFn: () => api.checkout(checkoutPayload(form, isGuest)),
    // El pedido quedó creado con el stock reservado: se informa add_payment_info
    // (esperando a que GA4 lo despache) y se envía al navegador a pagar.
    onSuccess: async (start) => {
      if (cart) await trackAddPaymentInfo(cart, start.provider === "mock" ? "simulado" : "webpay", start.total_clp);
      goToPayment(start.payment);
    },
  });

  usePageView("Pagar | TCGMASTER");
  const begun = useRef(false);
  useEffect(() => {
    if (cart && cart.items.length > 0 && !begun.current) {
      begun.current = true;
      trackBeginCheckout(cart);
    }
  }, [cart]);

  if (meLoading || cartLoading) return <div className="min-h-screen" />;
  if (!cart || cart.items.length === 0) {
    return (
      <div className="mx-auto max-w-shop px-4 py-24 sm:px-6">
        <h1 className="font-display text-3xl">Tu carrito está vacío</h1>
        <p className="mt-3 text-ivory-dim">Agrega productos antes de pagar.</p>
        <Link to="/cartas" className="mt-6 inline-block font-semibold text-brass hover:text-brass-bright">
          Ver cartas
        </Link>
      </div>
    );
  }

  const shipping = form.shipping_method === "domicilio" ? (options.data?.shipping_home_clp ?? 0) : 0;
  const total = cart.subtotal_clp + shipping;
  const blocked = cart.warnings.length > 0;
  const set = (key: keyof CheckoutForm) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm({ ...form, [key]: e.target.value });
  const fieldProps = (key: keyof CheckoutForm) => ({
    id: key,
    value: form[key],
    onChange: set(key),
    "aria-invalid": Boolean(errors[key]),
    "aria-describedby": errors[key] ? `${key}-error` : undefined,
    className: `${inputClass} ${errors[key] ? "border-cond-hp" : "border-felt-line"}`,
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    const found = validateCheckout(form, isGuest);
    setErrors(found);
    if (Object.keys(found).length === 0) {
      trackAddShippingInfo(cart!, form.shipping_method === "domicilio" ? "envio_domicilio" : "retiro_tienda", shipping);
      pay.mutate();
    }
  }

  const providerLabel = options.data?.provider === "mock" ? "Pagar (simulado)" : "Pagar con Webpay";

  return (
    <div className="mx-auto max-w-shop px-4 pt-10 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <h1 className="font-display text-3xl sm:text-4xl">Pagar</h1>
        {TEST_HELPERS_ENABLED && (
          <button
            type="button"
            onClick={() => {
              setForm(TEST_CHECKOUT);
              setErrors({});
            }}
            className="rounded-sm border border-dashed border-brass-dim px-3 py-1.5 text-sm text-brass hover:border-brass"
          >
            Usar datos de prueba
          </button>
        )}
      </div>

      <form onSubmit={submit} noValidate className="mt-8 grid gap-10 lg:grid-cols-[1fr_22rem]">
        <div className="space-y-10">
          <section aria-labelledby="contacto">
            <h2 id="contacto" className="font-display text-xl">Contacto</h2>
            {isGuest ? (
              <>
                <p className="mt-1 text-sm text-ivory-dim">
                  Compras como invitado. ¿Tienes cuenta?{" "}
                  <Link to="/cuenta/ingresar?volver=/checkout" className="font-semibold text-brass hover:text-brass-bright">
                    Ingresa
                  </Link>
                </p>
                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  <Field id="contact_name" label="Nombre" error={errors.contact_name}>
                    <input {...fieldProps("contact_name")} autoComplete="name" maxLength={120} />
                  </Field>
                  <Field id="contact_email" label="Correo" error={errors.contact_email}>
                    <input {...fieldProps("contact_email")} type="email" autoComplete="email" />
                  </Field>
                </div>
              </>
            ) : (
              <p className="mt-2 text-sm">
                {me!.full_name}, <span className="text-ivory-dim">{me!.email}</span>
              </p>
            )}
          </section>

          <section aria-labelledby="entrega">
            <h2 id="entrega" className="font-display text-xl">Entrega</h2>
            <div className="mt-4 grid gap-3 sm:grid-cols-2" role="radiogroup" aria-label="Método de entrega">
              {[
                { value: "retiro" as const, title: "Retiro en tienda", note: "Gratis" },
                {
                  value: "domicilio" as const,
                  title: "Envío a domicilio",
                  note: formatCLP(options.data?.shipping_home_clp ?? 0),
                },
              ].map((o) => (
                <label
                  key={o.value}
                  className={`flex cursor-pointer items-center gap-3 rounded-sm border p-4 ${
                    form.shipping_method === o.value ? "border-brass bg-felt-raised" : "border-felt-line"
                  }`}
                >
                  <input
                    type="radio"
                    name="shipping_method"
                    value={o.value}
                    checked={form.shipping_method === o.value}
                    onChange={() => setForm({ ...form, shipping_method: o.value })}
                    className="h-4 w-4 accent-[#B8913A]"
                  />
                  <span className="flex-1 font-semibold">{o.title}</span>
                  <span className="price text-sm text-ivory-dim">{o.note}</span>
                </label>
              ))}
            </div>

            {form.shipping_method === "domicilio" && (
              <div className="mt-5 grid gap-4 sm:grid-cols-2">
                <div className="sm:col-span-2">
                  <Field id="street" label="Dirección" error={errors.street}>
                    <input {...fieldProps("street")} autoComplete="street-address" maxLength={160} />
                  </Field>
                </div>
                <Field id="comuna" label="Comuna" error={errors.comuna}>
                  <input {...fieldProps("comuna")} autoComplete="address-level2" maxLength={80} />
                </Field>
                <Field id="region" label="Región" error={errors.region}>
                  <select {...fieldProps("region")} autoComplete="address-level1">
                    <option value="">Elige una región</option>
                    {REGIONS.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field id="phone" label="Teléfono" error={errors.phone}>
                  <input {...fieldProps("phone")} type="tel" autoComplete="tel" maxLength={20} />
                </Field>
              </div>
            )}
          </section>
        </div>

        <aside aria-label="Resumen del pedido" className="h-fit border border-felt-line bg-felt-raised p-6">
          <h2 className="font-display text-xl">Tu pedido</h2>
          <ul className="mt-4 space-y-2 text-sm">
            {cart.items.map((line) => (
              <li key={line.id} className="flex justify-between gap-3">
                <span className="min-w-0 truncate">
                  {line.quantity} × {line.product.name}
                </span>
                <span className="price shrink-0">{formatCLP(line.line_total_clp)}</span>
              </li>
            ))}
          </ul>
          <dl className="price mt-4 space-y-2 border-t border-felt-line pt-4 text-sm">
            <div className="flex justify-between">
              <dt className="text-ivory-dim">Subtotal</dt>
              <dd>{formatCLP(cart.subtotal_clp)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-ivory-dim">Envío</dt>
              <dd>{shipping ? formatCLP(shipping) : "Gratis"}</dd>
            </div>
            <div className="flex justify-between border-t border-felt-line pt-3 text-base">
              <dt className="font-semibold">Total</dt>
              <dd className="font-semibold text-brass">{formatCLP(total)}</dd>
            </div>
          </dl>

          {pay.isError && (
            <p role="alert" className="mt-4 rounded-sm border border-cond-hp px-3 py-2 text-sm text-cond-hp">
              {errorMessage(pay.error)}
            </p>
          )}
          {blocked && (
            <p className="mt-4 text-sm text-cond-mp">
              Hay avisos en tu{" "}
              <Link to="/carrito" className="font-semibold underline">
                carrito
              </Link>
              . Revísalos antes de pagar.
            </p>
          )}

          <button
            type="submit"
            disabled={pay.isPending || pay.isSuccess || blocked || !options.data}
            className="mt-6 w-full rounded-sm bg-brass py-3 font-semibold text-felt hover:bg-brass-bright disabled:opacity-60"
          >
            {pay.isPending || pay.isSuccess ? "Conectando con el pago…" : providerLabel}
          </button>
          <p className="mt-3 text-xs text-ivory-dim">
            Reservamos tu stock por {options.data?.reservation_minutes ?? 15} minutos mientras pagas.
            {options.data?.provider === "webpay" && " Ambiente de prueba de Transbank: no se cobra dinero real."}
          </p>
        </aside>
      </form>
    </div>
  );
}
