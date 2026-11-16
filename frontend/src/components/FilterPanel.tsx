/**
 * Panel de filtros del listado.
 *
 * Las opciones de juego, rareza, estado e idioma son fijas (siempre visibles,
 * así se pueden combinar varias); los conteos vienen de /api/products/facets y
 * reflejan todos los filtros activos. Una opción con 0 resultados se atenúa
 * pero sigue disponible.
 */
import { type FormEvent, type ReactNode, useEffect, useState } from "react";
import { CONDITION, GAME_NAMES, LANGUAGE, RARITY } from "../lib/format";
import {
  activeFilterCount,
  clearFilters,
  type ListingState,
  type MultiKey,
  toggleValue,
} from "../lib/filters";
import type { Facets, SetOut } from "../lib/types";
import type { FilterGroup } from "../pages/sections";
import { RarityPips } from "./Indicators";

interface Props {
  state: ListingState;
  facets: Facets | undefined;
  sets: SetOut[] | undefined;
  groups: FilterGroup[];
  onChange: (next: ListingState) => void;
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="border-t border-felt-line py-4">
      <legend className="float-left mb-2 w-full text-sm font-semibold text-ivory">{title}</legend>
      <div className="clear-left space-y-1.5">{children}</div>
    </fieldset>
  );
}

interface Option {
  value: string;
  label: ReactNode;
}

function CheckboxList({
  name,
  options,
  state,
  counts,
  onChange,
}: {
  name: MultiKey;
  options: Option[];
  state: ListingState;
  counts: Map<string, number>;
  onChange: (next: ListingState) => void;
}) {
  return (
    <>
      {options.map((o) => {
        const checked = state.multi[name].includes(o.value);
        const count = counts.get(o.value) ?? 0;
        return (
          <label
            key={o.value}
            className={`flex cursor-pointer items-center gap-2 text-sm ${
              count === 0 && !checked ? "text-ivory-dim/60" : "text-ivory"
            }`}
          >
            <input
              type="checkbox"
              checked={checked}
              onChange={() => onChange(toggleValue(state, name, o.value))}
              className="h-4 w-4 accent-[#B8913A]"
            />
            <span className="flex-1">{o.label}</span>
            <span className="price text-xs text-ivory-dim">{count}</span>
          </label>
        );
      })}
    </>
  );
}

function countsOf(values: { value: string; count: number }[] | undefined) {
  return new Map((values ?? []).map((v) => [v.value, v.count]));
}

function PriceRange({ state, onChange }: { state: ListingState; onChange: (s: ListingState) => void }) {
  const [min, setMin] = useState(state.minPrice?.toString() ?? "");
  const [max, setMax] = useState(state.maxPrice?.toString() ?? "");
  useEffect(() => {
    setMin(state.minPrice?.toString() ?? "");
    setMax(state.maxPrice?.toString() ?? "");
  }, [state.minPrice, state.maxPrice]);

  function apply(event: FormEvent) {
    event.preventDefault();
    const parse = (v: string) => (v.trim() === "" ? null : Math.max(0, Number.parseInt(v, 10) || 0));
    onChange({ ...state, minPrice: parse(min), maxPrice: parse(max), page: 1 });
  }

  const inputClass =
    "price w-full rounded-sm border border-felt-line bg-felt px-2 py-1.5 text-sm text-ivory focus:border-brass";
  return (
    <form onSubmit={apply} className="space-y-2">
      <div className="flex items-center gap-2">
        <label className="sr-only" htmlFor="precio-min">Precio mínimo</label>
        <input id="precio-min" inputMode="numeric" placeholder="Desde $" value={min} onChange={(e) => setMin(e.target.value)} className={inputClass} />
        <span className="text-ivory-dim">a</span>
        <label className="sr-only" htmlFor="precio-max">Precio máximo</label>
        <input id="precio-max" inputMode="numeric" placeholder="Hasta $" value={max} onChange={(e) => setMax(e.target.value)} className={inputClass} />
      </div>
      <button type="submit" className="w-full rounded-sm border border-brass py-1.5 text-sm font-semibold text-brass hover:bg-brass hover:text-felt">
        Aplicar precio
      </button>
    </form>
  );
}

export default function FilterPanel({ state, facets, sets, groups, onChange }: Props) {
  const show = (g: FilterGroup) => groups.includes(g);
  const visibleSets = (sets ?? []).filter(
    (s) => state.multi.game.length === 0 || state.multi.game.includes(s.game),
  );

  return (
    <div>
      <div className="flex items-center justify-between pb-3">
        <p className="font-display text-xl">Filtros</p>
        {activeFilterCount(state) > 0 && (
          <button type="button" onClick={() => onChange(clearFilters(state))} className="text-sm font-semibold text-brass hover:text-brass-bright">
            Quitar filtros
          </button>
        )}
      </div>

      {show("stock") && (
        <div className="border-t border-felt-line py-4">
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={state.inStock}
              onChange={() => onChange({ ...state, inStock: !state.inStock, page: 1 })}
              className="h-4 w-4 accent-[#B8913A]"
            />
            Solo productos con stock
          </label>
        </div>
      )}

      {show("game") && (
        <Group title="Juego">
          <CheckboxList
            name="game"
            state={state}
            onChange={onChange}
            counts={countsOf(facets?.games)}
            options={Object.entries(GAME_NAMES).map(([value, label]) => ({ value, label }))}
          />
        </Group>
      )}

      {show("set") && visibleSets.length > 0 && (
        <Group title="Expansión">
          <div className="max-h-64 space-y-1.5 overflow-y-auto pr-1">
            <CheckboxList
              name="set"
              state={state}
              onChange={onChange}
              counts={countsOf(facets?.sets)}
              options={visibleSets.map((s) => ({ value: String(s.id), label: s.name }))}
            />
          </div>
        </Group>
      )}

      {show("rarity") && (
        <Group title="Rareza">
          <CheckboxList
            name="rarity"
            state={state}
            onChange={onChange}
            counts={countsOf(facets?.rarity_tiers)}
            options={Object.entries(RARITY).map(([value, r]) => ({
              value,
              label: (
                <span className="flex items-center gap-2">
                  <RarityPips tier={value as keyof typeof RARITY} />
                  {r.label}
                </span>
              ),
            }))}
          />
        </Group>
      )}

      {show("condition") && (
        <Group title="Estado">
          <CheckboxList
            name="condition"
            state={state}
            onChange={onChange}
            counts={countsOf(facets?.conditions)}
            options={Object.entries(CONDITION).map(([value, c]) => ({ value, label: `${c.label} (${value})` }))}
          />
        </Group>
      )}

      {show("lang") && (
        <Group title="Idioma">
          <CheckboxList
            name="lang"
            state={state}
            onChange={onChange}
            counts={countsOf(facets?.languages)}
            options={Object.entries(LANGUAGE).map(([value, label]) => ({ value, label }))}
          />
        </Group>
      )}

      {show("foil") && (
        <Group title="Acabado">
          {[
            { value: null, label: "Todos" },
            { value: "true" as const, label: "Solo foil" },
            { value: "false" as const, label: "Solo normal" },
          ].map((o) => (
            <label key={o.label} className="flex cursor-pointer items-center gap-2 text-sm">
              <input
                type="radio"
                name="foil"
                checked={state.foil === o.value}
                onChange={() => onChange({ ...state, foil: o.value, page: 1 })}
                className="h-4 w-4 accent-[#B8913A]"
              />
              {o.label}
            </label>
          ))}
        </Group>
      )}

      {show("price") && (
        <Group title="Precio">
          <PriceRange state={state} onChange={onChange} />
        </Group>
      )}
    </div>
  );
}
