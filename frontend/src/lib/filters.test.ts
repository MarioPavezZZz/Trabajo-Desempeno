import { describe, expect, it } from "vitest";
import {
  activeFilterCount,
  clearFilters,
  parseListing,
  serializeListing,
  toApiParams,
  toFacetParams,
  toggleValue,
} from "./filters";

const parse = (qs: string) => parseListing(new URLSearchParams(qs));

describe("parseListing", () => {
  it("lee filtros múltiples, rango de precio y página", () => {
    const s = parse("game=magic&game=pokemon&condition=NM&min_price=1000&max_price=5000&page=3");
    expect(s.multi.game).toEqual(["magic", "pokemon"]);
    expect(s.multi.condition).toEqual(["NM"]);
    expect([s.minPrice, s.maxPrice, s.page]).toEqual([1000, 5000, 3]);
  });

  it("ignora valores inválidos en lugar de fallar", () => {
    const s = parse("page=-2&min_price=abc&sort=azar&foil=quizas&in_stock=1");
    expect(s.page).toBe(1);
    expect(s.minPrice).toBeNull();
    expect(s.sort).toBeNull();
    expect(s.foil).toBeNull();
    expect(s.inStock).toBe(false);
  });

  it("elimina valores repetidos", () => {
    expect(parse("lang=ES&lang=ES").multi.lang).toEqual(["ES"]);
  });
});

describe("serializeListing", () => {
  it("es estable: el mismo estado produce siempre la misma URL", () => {
    const a = serializeListing(parse("game=pokemon&game=magic&q=dragon"));
    const b = serializeListing(parse("q=dragon&game=magic&game=pokemon"));
    expect(a.toString()).toBe(b.toString());
  });

  it("omite la página 1 y los filtros vacíos", () => {
    expect(serializeListing(parse("page=1")).toString()).toBe("");
  });

  it("ida y vuelta sin pérdida", () => {
    const qs = "q=dragon&game=magic&rarity=epica&foil=true&min_price=100&in_stock=true&sort=name&page=2";
    expect(serializeListing(parse(qs)).toString()).toBe(qs);
  });
});

describe("parámetros para la API", () => {
  it("agrega el preset de la sección y el tamaño de página", () => {
    const p = toApiParams(parse("game=magic"), { type: "carta", onSale: true }, 24);
    expect(p.get("type")).toBe("carta");
    expect(p.get("on_sale")).toBe("true");
    expect(p.get("page_size")).toBe("24");
  });

  it("las facetas no llevan orden ni paginación", () => {
    const p = toFacetParams(parse("game=magic&sort=name&page=4"), { type: "carta" });
    expect(p.has("sort") || p.has("page") || p.has("page_size")).toBe(false);
    expect(p.get("game")).toBe("magic");
  });
});

describe("cambios de filtros", () => {
  it("toggle agrega, quita y vuelve a la página 1", () => {
    const base = parse("page=5");
    const on = toggleValue(base, "rarity", "rara");
    expect(on.multi.rarity).toEqual(["rara"]);
    expect(on.page).toBe(1);
    expect(toggleValue(on, "rarity", "rara").multi.rarity).toEqual([]);
  });

  it("cuenta filtros activos y los limpia conservando búsqueda y orden", () => {
    const s = parse("q=x&sort=name&game=magic&lang=ES&in_stock=true&min_price=10");
    expect(activeFilterCount(s)).toBe(4);
    const cleared = clearFilters(s);
    expect(activeFilterCount(cleared)).toBe(0);
    expect([cleared.q, cleared.sort]).toEqual(["x", "name"]);
  });
});
