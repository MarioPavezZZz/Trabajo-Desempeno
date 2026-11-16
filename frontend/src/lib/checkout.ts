/**
 * Utilidades del checkout: validación en el navegador, datos de prueba y
 * redirección a la pasarela de pago.
 */
import type { CheckoutForm, PaymentRedirect } from "./types";

export const EMPTY_CHECKOUT: CheckoutForm = {
  contact_name: "",
  contact_email: "",
  shipping_method: "retiro",
  street: "",
  comuna: "",
  region: "",
  phone: "",
};

/**
 * Datos ficticios para probar rápido (botón "Usar datos de prueba").
 * Solo se muestra si el frontend se compila con VITE_TEST_HELPERS=true.
 */
export const TEST_CHECKOUT: CheckoutForm = {
  contact_name: "Cliente de Prueba",
  contact_email: "cliente.prueba@example.com",
  shipping_method: "domicilio",
  street: "Av. Libertador Bernardo O'Higgins 1234, depto. 56",
  comuna: "Santiago",
  region: "Metropolitana",
  phone: "+56 9 1234 5678",
};

export const TEST_HELPERS_ENABLED = import.meta.env.VITE_TEST_HELPERS === "true";

export const REGIONS = [
  "Arica y Parinacota",
  "Tarapacá",
  "Antofagasta",
  "Atacama",
  "Coquimbo",
  "Valparaíso",
  "Metropolitana",
  "O'Higgins",
  "Maule",
  "Ñuble",
  "Biobío",
  "La Araucanía",
  "Los Ríos",
  "Los Lagos",
  "Aysén",
  "Magallanes",
];

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Errores por campo antes de enviar (el servidor valida lo mismo).
 * Los datos de contacto solo se exigen a invitados.
 */
export function validateCheckout(form: CheckoutForm, isGuest: boolean): Partial<Record<keyof CheckoutForm, string>> {
  const errors: Partial<Record<keyof CheckoutForm, string>> = {};
  if (isGuest) {
    if (form.contact_name.trim().length < 2) errors.contact_name = "Escribe tu nombre.";
    if (!EMAIL_RE.test(form.contact_email.trim())) errors.contact_email = "Escribe un correo válido.";
  }
  if (form.shipping_method === "domicilio") {
    if (!form.street.trim()) errors.street = "Escribe la dirección.";
    if (!form.comuna.trim()) errors.comuna = "Escribe la comuna.";
    if (!form.region) errors.region = "Elige la región.";
    if (form.phone.replace(/\D/g, "").length < 8) errors.phone = "Escribe un teléfono de al menos 8 dígitos.";
  }
  return errors;
}

/** Lo que se envía a la API: sin campos de dirección si es retiro, sin contacto si hay cuenta. */
export function checkoutPayload(form: CheckoutForm, isGuest: boolean): Partial<CheckoutForm> {
  const payload: Partial<CheckoutForm> = { shipping_method: form.shipping_method };
  if (isGuest) {
    payload.contact_name = form.contact_name.trim();
    payload.contact_email = form.contact_email.trim();
  }
  if (form.shipping_method === "domicilio") {
    Object.assign(payload, {
      street: form.street.trim(),
      comuna: form.comuna.trim(),
      region: form.region,
      phone: form.phone.trim(),
    });
  }
  return payload;
}

/**
 * Envía el navegador a la pasarela. Webpay exige un formulario POST con el
 * campo `token_ws`; el simulador usa una URL normal (GET).
 */
export function goToPayment(payment: PaymentRedirect): void {
  if (payment.method === "GET") {
    window.location.assign(payment.url);
    return;
  }
  const form = document.createElement("form");
  form.method = "POST";
  form.action = payment.url;
  const input = document.createElement("input");
  input.type = "hidden";
  input.name = payment.token_field ?? "token_ws";
  input.value = payment.token;
  form.appendChild(input);
  document.body.appendChild(form);
  form.submit();
}
