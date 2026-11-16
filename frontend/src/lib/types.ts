/**
 * Tipos de las respuestas de la API (espejo de backend/app/schemas/catalog.py).
 */

export type ProductType = "carta" | "sellado" | "accesorio";
export type RarityTier = "comun" | "infrecuente" | "rara" | "epica" | "legendaria";
export type Condition = "NM" | "LP" | "MP" | "HP";
export type Language = "EN" | "ES" | "JA";
export type SortOption = "relevance" | "newest" | "price_asc" | "price_desc" | "name";

export interface ProductSummary {
  id: number;
  slug: string;
  name: string;
  product_type: ProductType;
  game: string | null;
  set_name: string | null;
  thumb: string;
  price_clp: number;
  compare_at_price_clp: number | null;
  discount_pct: number | null;
  stock: number;
  rarity: string | null;
  rarity_tier: RarityTier | null;
  condition: Condition | null;
  language: Language | null;
  is_foil: boolean;
  sealed_type: string | null;
  accessory_type: string | null;
  created_at: string;
}

export interface SetOut {
  id: number;
  code: string;
  name: string;
  game: string;
  release_date: string | null;
  logo: string | null;
}

export interface GameOut {
  slug: string;
  name: string;
  product_count: number;
  logo: string | null;
}

export interface ProductPage {
  items: ProductSummary[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface FacetValue {
  value: string;
  label: string;
  count: number;
}

export interface Facets {
  total: number;
  product_types: FacetValue[];
  games: FacetValue[];
  sets: FacetValue[];
  rarity_tiers: FacetValue[];
  conditions: FacetValue[];
  languages: FacetValue[];
  foil: FacetValue[];
  price: { min: number | null; max: number | null };
}

export interface ProductDetail extends ProductSummary {
  image: string;
  description: string | null;
  card_number: string | null;
  card_type: string | null;
  units_per_item: number | null;
  attributes: Record<string, unknown>;
  set: SetOut | null;
  game_name: string | null;
}

export interface User {
  id: number;
  email: string;
  full_name: string;
  created_at: string;
}

export interface CartLine {
  id: number;
  quantity: number;
  unit_price_clp: number;
  added_price_clp: number;
  line_total_clp: number;
  product: ProductSummary;
}

export interface Cart {
  items: CartLine[];
  item_count: number;
  subtotal_clp: number;
  warnings: string[];
}

export type ShippingMethod = "retiro" | "domicilio";
export type OrderStatus = "pendiente" | "pagada" | "rechazada" | "anulada";

export interface CheckoutOptions {
  provider: "webpay" | "mock";
  shipping_home_clp: number;
  reservation_minutes: number;
}

export interface CheckoutForm {
  contact_name: string;
  contact_email: string;
  shipping_method: ShippingMethod;
  street: string;
  comuna: string;
  region: string;
  phone: string;
}

export interface PaymentRedirect {
  url: string;
  method: "GET" | "POST";
  token: string;
  token_field: string | null;
}

export interface CheckoutStart {
  transaction_id: string;
  access_key: string;
  total_clp: number;
  provider: string;
  payment: PaymentRedirect;
}

export interface Order {
  transaction_id: string;
  status: OrderStatus;
  created_at: string;
  paid_at: string | null;
  contact_name: string;
  contact_email: string;
  shipping_method: ShippingMethod;
  shipping_address: Partial<Record<"street" | "comuna" | "region" | "phone", string>>;
  subtotal_clp: number;
  shipping_clp: number;
  total_clp: number;
  items: {
    product_id: number;
    slug: string | null;
    thumb: string | null;
    name: string;
    quantity: number;
    unit_price_clp: number;
    line_total_clp: number;
  }[];
  payment: { provider: string; status: string; authorization_code: string | null; card_last4: string | null } | null;
}

export interface OrderSummary {
  transaction_id: string;
  status: OrderStatus;
  created_at: string;
  total_clp: number;
  item_count: number;
}

export interface HomeData {
  hero: { set: SetOut; products: ProductSummary[] }[];
  games: GameOut[];
  new_arrivals: ProductSummary[];
  featured_sealed: ProductSummary[];
  offers: ProductSummary[];
  price_movers: { product: ProductSummary; old_price_clp: number; change_pct: number }[];
}
