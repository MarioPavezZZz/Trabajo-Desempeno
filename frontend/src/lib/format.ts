/**
 * Formatos y etiquetas visibles en la interfaz.
 */
import type { Condition, Language, RarityTier } from "./types";

const clpFormatter = new Intl.NumberFormat("es-CL", {
  style: "currency",
  currency: "CLP",
  maximumFractionDigits: 0,
});

/** 164990 -> "$164.990" (formato chileno, sin decimales). */
export function formatCLP(amount: number): string {
  // Intl puede usar un espacio duro entre símbolo y cifra según el entorno; se normaliza.
  return clpFormatter.format(amount).replace(/\s/g, "");
}

/** Variación porcentual con signo y coma decimal: 72.2 -> "+72,2 %". */
export function formatChange(pct: number): string {
  const sign = pct > 0 ? "+" : pct < 0 ? "−" : "";
  return `${sign}${Math.abs(pct).toFixed(1).replace(".", ",")} %`;
}

export const GAME_NAMES: Record<string, string> = {
  pokemon: "Pokémon",
  magic: "Magic",
  yugioh: "Yu-Gi-Oh!",
};

export const RARITY: Record<RarityTier, { label: string; level: number }> = {
  comun: { label: "Común", level: 1 },
  infrecuente: { label: "Infrecuente", level: 2 },
  rara: { label: "Rara", level: 3 },
  epica: { label: "Épica", level: 4 },
  legendaria: { label: "Legendaria", level: 5 },
};

export const CONDITION: Record<Condition, { label: string; short: string }> = {
  NM: { label: "Near Mint", short: "NM" },
  LP: { label: "Lightly Played", short: "LP" },
  MP: { label: "Moderately Played", short: "MP" },
  HP: { label: "Heavily Played", short: "HP" },
};

export const LANGUAGE: Record<Language, string> = {
  EN: "Inglés",
  ES: "Español",
  JA: "Japonés",
};

export const SEALED_TYPE: Record<string, string> = {
  sobre: "Sobre",
  display: "Display",
  caja_entrenador: "Caja de entrenador",
  mazo_estructura: "Mazo",
};

export const ACCESSORY_TYPE: Record<string, string> = {
  fundas: "Fundas",
  carpeta: "Carpeta",
  deck_box: "Deck box",
  playmat: "Playmat",
  toploader: "Toploaders",
};

/** Fecha ISO -> "8 nov 2024". */
export function formatDate(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(`${iso.slice(0, 10)}T12:00:00`);
  return date.toLocaleDateString("es-CL", { day: "numeric", month: "short", year: "numeric" });
}
