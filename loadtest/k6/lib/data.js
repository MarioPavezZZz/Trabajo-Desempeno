/**
 * Datos que usan los recorridos, obtenidos una vez al inicio (setup) desde la
 * propia API: productos con stock por tipo, sets y términos de búsqueda.
 * Así las pruebas funcionan con cualquier catálogo cargado.
 */
import { get, json, qs } from "./api.js";

const GAMES = ["pokemon", "magic", "yugioh"];

/** Quita una letra al azar (simula un error de tipeo: "charizard" -> "charzard"). */
function typo(word) {
  if (word.length < 5) return word;
  const i = 1 + Math.floor(Math.random() * (word.length - 2));
  return word.slice(0, i) + word.slice(i + 1);
}

export function loadCatalog() {
  const products = { carta: [], sellado: [], accesorio: [] };
  for (const type of Object.keys(products)) {
    for (let page = 1; page <= 4; page++) {
      const res = get(
        `/api/products${qs({ type, in_stock: "true", page_size: 60, page, sort: "name" })}`,
        "GET /api/products",
        "setup",
      );
      const body = json(res);
      if (!body || !body.items.length) break;
      for (const p of body.items) {
        products[type].push({ id: p.id, slug: p.slug, game: p.game, thumb: p.thumb, stock: p.stock });
      }
      if (page >= body.total_pages) break;
    }
  }
  if (!products.carta.length) {
    throw new Error("No hay productos con stock: ¿se cargó el catálogo y se reinició el stock?");
  }

  const sets = (json(get("/api/sets", "GET /api/sets", "setup")) || []).map((s) => ({ id: s.id, game: s.game, name: s.name }));

  // Términos: palabras de nombres reales, algunas con error de tipeo, y nombres de set.
  const words = [];
  for (const p of products.carta.slice(0, 120)) {
    const w = p.slug.split("-")[0];
    if (w.length >= 4) words.push(w);
  }
  const terms = [
    ...words.slice(0, 40),
    ...words.slice(40, 55).map(typo),
    ...sets.map((s) => s.name.split(" ")[0].toLowerCase()),
    "dragon",
    "ex",
    "sobre",
    "display",
    "fundas",
  ];

  return { products, sets, terms, games: GAMES };
}
