/**
 * Pasarela simulada: reemplaza a Webpay cuando PAYMENT_PROVIDER=mock.
 * Cada botón lleva al retorno del backend, que confirma el pago y redirige al resultado.
 */
import { useSearchParams } from "react-router-dom";
import { usePageView } from "../analytics";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";

export default function MockPaymentPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";

  usePageView("Pago simulado | TCGMASTER");

  const go = (decision: "aprobar" | "rechazar") =>
    window.location.assign(
      `${API_BASE}/checkout/simulado/retorno?${new URLSearchParams({ token, decision })}`,
    );

  return (
    <div className="mx-auto max-w-md px-4 py-20 text-center sm:px-6">
      <p className="text-sm text-ivory-dim">Ambiente de prueba</p>
      <h1 className="mt-2 font-display text-3xl">Pago simulado</h1>
      <p className="mt-3 text-ivory-dim">
        Esta pantalla reemplaza a la pasarela de pago. Elige el resultado que quieres probar.
      </p>
      {token ? (
        <div className="mt-8 grid gap-3 sm:grid-cols-2">
          <button
            type="button"
            onClick={() => go("aprobar")}
            className="rounded-sm bg-cond-nm py-3 font-semibold text-felt hover:opacity-90"
          >
            Aprobar pago
          </button>
          <button
            type="button"
            onClick={() => go("rechazar")}
            className="rounded-sm border border-cond-hp py-3 font-semibold text-cond-hp hover:bg-cond-hp hover:text-felt"
          >
            Rechazar pago
          </button>
        </div>
      ) : (
        <p className="mt-8 text-cond-hp">Falta el identificador del pago. Vuelve al carrito e inténtalo de nuevo.</p>
      )}
    </div>
  );
}
