/**
 * Indicadores visuales de rareza, estado, idioma y precio.
 */
import { CONDITION, formatCLP, LANGUAGE, RARITY } from "../lib/format";
import type { Condition, Language, RarityTier } from "../lib/types";

/** Rareza como cinco rombos: los llenos indican el nivel (es una escala ordinal). */
export function RarityPips({ tier }: { tier: RarityTier }) {
  const { label, level } = RARITY[tier];
  return (
    <span className="inline-flex items-center gap-[3px]" role="img" aria-label={`Rareza: ${label}`} title={label}>
      {[1, 2, 3, 4, 5].map((i) => (
        <svg key={i} viewBox="0 0 8 8" className="h-2 w-2" aria-hidden="true">
          <path
            d="M4 0.5 7.5 4 4 7.5 0.5 4Z"
            className={i <= level ? "fill-brass" : "fill-none stroke-felt-line"}
            strokeWidth="1"
          />
        </svg>
      ))}
    </span>
  );
}

const CONDITION_STYLE: Record<Condition, string> = {
  NM: "border-cond-nm text-cond-nm",
  LP: "border-cond-lp text-cond-lp",
  MP: "border-cond-mp text-cond-mp",
  HP: "border-cond-hp text-cond-hp",
};

/** Estado de conservación con escala de color de NM (verde) a HP (rojo). */
export function ConditionChip({ condition }: { condition: Condition }) {
  return (
    <span
      className={`rounded-sm border px-1.5 text-xs font-semibold leading-5 ${CONDITION_STYLE[condition]}`}
      title={CONDITION[condition].label}
    >
      <span className="sr-only">Estado: </span>
      {condition}
    </span>
  );
}

export function LanguageTag({ language }: { language: Language }) {
  return (
    <span className="text-xs text-ivory-dim" title={LANGUAGE[language]}>
      <span className="sr-only">Idioma: </span>
      {language}
    </span>
  );
}

/** Precio actual; si hay oferta, el anterior tachado. */
export function Price({ price, before }: { price: number; before: number | null }) {
  return (
    <span className="price flex flex-wrap items-baseline gap-x-2">
      <span className="text-lg font-semibold text-brass">{formatCLP(price)}</span>
      {before && (
        <s className="text-sm text-ivory-dim">
          <span className="sr-only">Antes </span>
          {formatCLP(before)}
        </s>
      )}
    </span>
  );
}
