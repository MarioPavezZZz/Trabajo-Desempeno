/**
 * Cliente mínimo de la API (fetch nativo, sin librerías extra).
 *
 * - Cada petición lleva X-Traffic-Type para que el backend y Nginx separen
 *   en sus logs el tráfico real del generado por las pruebas de carga.
 * - Las cookies de sesión y carrito son httpOnly: el navegador las envía solo
 *   (misma origen), el código JavaScript nunca las lee.
 */
import { getTrafficType } from "../analytics/trafficType";
import type {
  Cart,
  CheckoutForm,
  CheckoutOptions,
  CheckoutStart,
  Facets,
  Order,
  OrderSummary,
  GameOut,
  HomeData,
  ProductDetail,
  ProductPage,
  ProductSummary,
  SetOut,
  User,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";

/** Error de la API con el código HTTP y el `detail` que envió el backend. */
export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(`La API respondió ${status}`);
  }
}

async function request<T>(method: string, path: string, body?: unknown, params?: URLSearchParams): Promise<T> {
  const query = params && params.toString() ? `?${params}` : "";
  const resp = await fetch(`${API_BASE}${path}${query}`, {
    method,
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      // Mismo valor que recibe GA4: API, Nginx y GA4 clasifican igual la visita.
      "X-Traffic-Type": getTrafficType(),
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) {
    let detail: unknown = null;
    try {
      detail = (await resp.json()).detail;
    } catch {
      /* respuesta sin JSON */
    }
    throw new ApiError(resp.status, detail);
  }
  return (resp.status === 204 ? null : await resp.json()) as T;
}

const get = <T>(path: string, params?: URLSearchParams) => request<T>("GET", path, undefined, params);

export const api = {
  // Catálogo
  home: () => get<HomeData>("/home"),
  newArrivals: (game?: string) =>
    get<ProductSummary[]>("/home/new-arrivals", game ? new URLSearchParams({ game }) : undefined),
  games: () => get<GameOut[]>("/games"),
  sets: () => get<SetOut[]>("/sets"),
  products: (params: URLSearchParams) => get<ProductPage>("/products", params),
  facets: (params: URLSearchParams) => get<Facets>("/products/facets", params),
  product: (slug: string) => get<ProductDetail>(`/products/${encodeURIComponent(slug)}`),
  related: (slug: string) => get<ProductSummary[]>(`/products/${encodeURIComponent(slug)}/related`),

  // Cuenta
  /** Usuario conectado o `null` sin sesión (el backend responde 200 en ambos casos). */
  me: () => get<User | null>("/auth/me"),
  register: (data: { full_name: string; email: string; password: string }) =>
    request<User>("POST", "/auth/register", data),
  login: (data: { email: string; password: string }) => request<User>("POST", "/auth/login", data),
  logout: () => request<null>("POST", "/auth/logout"),

  // Carrito
  cart: () => get<Cart>("/cart"),
  addToCart: (productId: number, quantity: number) =>
    request<Cart>("POST", "/cart/items", { product_id: productId, quantity }),
  updateCartItem: (itemId: number, quantity: number) =>
    request<Cart>("PATCH", `/cart/items/${itemId}`, { quantity }),
  removeCartItem: (itemId: number) => request<Cart>("DELETE", `/cart/items/${itemId}`),

  // Checkout y pedidos
  checkoutOptions: () => get<CheckoutOptions>("/checkout/options"),
  checkout: (data: Partial<CheckoutForm>) => request<CheckoutStart>("POST", "/checkout", data),
  order: (transactionId: string, key: string | null) =>
    get<Order>(
      `/orders/${encodeURIComponent(transactionId)}`,
      key ? new URLSearchParams({ clave: key }) : undefined,
    ),
  orders: () => get<OrderSummary[]>("/orders"),
};

const FIELD_HINTS: Record<string, string> = {
  email: "Escribe un correo válido, por ejemplo nombre@correo.cl.",
  password: "La contraseña debe tener entre 8 y 72 caracteres.",
  full_name: "Escribe tu nombre (al menos 2 letras).",
  quantity: "La cantidad debe estar entre 1 y 99.",
  contact_email: "Escribe un correo válido, por ejemplo nombre@correo.cl.",
  contact_name: "Escribe tu nombre.",
  phone: "Revisa el teléfono (máximo 20 caracteres).",
};

/**
 * Convierte un error de la API en un mensaje para la persona usuaria.
 * Soporta los tres formatos de `detail`: texto, `{message}` y la lista de
 * errores de validación (422) de FastAPI.
 */
export function errorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "No pudimos conectar con la tienda. Revisa tu conexión e inténtalo de nuevo.";
  }
  const { detail } = error;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    return String((detail as { message: unknown }).message);
  }
  if (Array.isArray(detail)) {
    const hints = detail
      .map((d) => {
        const loc = (d as { loc?: unknown[] }).loc ?? [];
        return FIELD_HINTS[String(loc[loc.length - 1])];
      })
      .filter(Boolean);
    if (hints.length) return [...new Set(hints)].join(" ");
  }
  return error.status >= 500
    ? "La tienda tuvo un problema al procesar la solicitud. Inténtalo de nuevo en unos segundos."
    : "No pudimos completar la solicitud.";
}
