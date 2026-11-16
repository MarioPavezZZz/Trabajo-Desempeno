"""Tests de la API del catálogo contra la base temporal con el catálogo de ejemplo."""

import pytest

from tests.conftest import sample_catalog

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]

ALL = sample_catalog().products


async def _items(client, **params):
    resp = await client.get("/api/products", params={"page_size": 60, **params})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _all_items(client, **params):
    """Recorre todas las páginas de un listado."""
    first = await _items(client, **params)
    items = list(first["items"])
    for page in range(2, first["total_pages"] + 1):
        items += (await _items(client, page=page, **params))["items"]
    return first["total"], items


# ---------------------------------------------------------------- salud
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok" and resp.json()["db"] == "ok"


# ---------------------------------------------------------------- listado
async def test_listado_por_defecto(client):
    resp = await client.get("/api/products")
    data = resp.json()
    assert resp.status_code == 200
    assert data["page"] == 1 and data["page_size"] == 24
    assert data["total"] == len(ALL)
    assert len(data["items"]) == 24
    fechas = [i["created_at"] for i in data["items"]]
    assert fechas == sorted(fechas, reverse=True)  # orden por defecto: novedades


@pytest.mark.parametrize("size", [0, 61, 1000])
async def test_page_size_fuera_de_rango_es_422(client, size):
    resp = await client.get("/api/products", params={"page_size": size})
    assert resp.status_code == 422


async def test_paginacion_cubre_todo_sin_repetir(client):
    total, items = await _all_items(client, sort="name")
    ids = [i["id"] for i in items]
    assert total == len(ALL) == len(ids) == len(set(ids))


async def test_pagina_mas_alla_del_final_viene_vacia(client):
    data = await _items(client, page=500)
    assert data["items"] == [] and data["total"] == len(ALL)


@pytest.mark.parametrize(
    ("params", "check"),
    [
        ({"type": "carta"}, lambda i: i["product_type"] == "carta"),
        ({"type": "accesorio"}, lambda i: i["product_type"] == "accesorio"),
        ({"game": "pokemon"}, lambda i: i["game"] == "pokemon"),
        ({"rarity": "legendaria"}, lambda i: i["rarity_tier"] == "legendaria"),
        ({"condition": ["NM", "LP"]}, lambda i: i["condition"] in ("NM", "LP")),
        ({"lang": "ES"}, lambda i: i["language"] == "ES"),
        ({"foil": "true"}, lambda i: i["is_foil"]),
        ({"min_price": 5000, "max_price": 20000}, lambda i: 5000 <= i["price_clp"] <= 20000),
        ({"in_stock": "true"}, lambda i: i["stock"] > 0),
        ({"on_sale": "true"}, lambda i: i["discount_pct"] and i["discount_pct"] > 0),
    ],
)
async def test_filtros(client, params, check):
    total, items = await _all_items(client, **params)
    assert total > 0 and total == len(items)
    assert all(check(i) for i in items)


async def test_filtros_combinados_son_interseccion(client):
    total_game, _ = await _all_items(client, game="magic")
    total_both, items = await _all_items(client, game="magic", type="carta", condition="NM")
    assert 0 < total_both < total_game
    assert all(i["game"] == "magic" and i["condition"] == "NM" for i in items)


async def test_filtro_por_set(client):
    sets = (await client.get("/api/sets", params={"game": "yugioh"})).json()
    target = sets[0]
    _, items = await _all_items(client, set=target["id"])
    assert items and all(i["set_name"] == target["name"] for i in items)


async def test_juego_inexistente_no_devuelve_nada(client):
    assert (await _items(client, game="digimon"))["total"] == 0


@pytest.mark.parametrize(
    "params", [{"condition": "XX"}, {"rarity": "mega"}, {"type": "otro"}, {"sort": "random"}]
)
async def test_valores_invalidos_son_422(client, params):
    assert (await client.get("/api/products", params=params)).status_code == 422


@pytest.mark.parametrize(
    ("sort", "key", "reverse"),
    [("price_asc", "price_clp", False), ("price_desc", "price_clp", True), ("name", "name", False)],
)
async def test_orden(client, sort, key, reverse):
    _, items = await _all_items(client, sort=sort)
    values = [i[key] for i in items]
    assert values == sorted(values, reverse=reverse)


# ---------------------------------------------------------------- búsqueda
async def test_busqueda_por_prefijo(client):
    _, items = await _all_items(client, q="playm")
    assert items and all("Playmat" in i["name"] for i in items)


async def test_busqueda_tolera_errores_de_tipeo(client):
    _, items = await _all_items(client, q="plymat")
    assert items and all("Playmat" in i["name"] for i in items)


async def test_busqueda_con_simbolos_no_rompe_la_consulta(client):
    resp = await client.get("/api/products", params={"q": "' OR 1=1; -- & | ! :*"})
    assert resp.status_code == 200


async def test_busqueda_vacia_de_palabras_no_filtra(client):
    assert (await _items(client, q="!!!"))["total"] == len(ALL)


# ---------------------------------------------------------------- facetas
async def test_facetas_coinciden_con_el_listado(client):
    facets = (await client.get("/api/products/facets")).json()
    assert facets["total"] == len(ALL)
    assert sum(f["count"] for f in facets["product_types"]) == len(ALL)
    assert {g["value"] for g in facets["games"]} == {"pokemon", "magic", "yugioh"}
    cards = sum(1 for p in ALL if p.product_type == "carta")
    assert sum(f["count"] for f in facets["conditions"]) == cards
    assert facets["price"]["min"] == min(p.price_clp for p in ALL)
    assert facets["price"]["max"] == max(p.price_clp for p in ALL)


async def test_facetas_respetan_filtros(client):
    facets = (await client.get("/api/products/facets", params={"game": "magic"})).json()
    total, _ = await _all_items(client, game="magic")
    assert facets["total"] == total
    assert [g["value"] for g in facets["games"]] == ["magic"] or len(facets["games"]) == 1


# ---------------------------------------------------------------- detalle
async def test_detalle_y_404(client):
    slug = (await _items(client, type="carta"))["items"][0]["slug"]
    resp = await client.get(f"/api/products/{slug}")
    data = resp.json()
    assert resp.status_code == 200
    assert data["slug"] == slug and data["image"].startswith("/media/")
    assert data["set"]["name"] == data["set_name"] and data["game_name"]
    assert (await client.get("/api/products/no-existe")).status_code == 404
    assert (await client.get("/api/products/no-existe/related")).status_code == 404


async def test_relacionados(client):
    product = (await _items(client, type="carta", game="pokemon"))["items"][0]
    related = (await client.get(f"/api/products/{product['slug']}/related")).json()
    assert 0 < len(related) <= 8
    assert all(r["id"] != product["id"] and r["stock"] > 0 for r in related)
    assert all(r["game"] == "pokemon" for r in related)


# ---------------------------------------------------------------- home
async def test_home(client):
    data = (await client.get("/api/home")).json()
    assert len(data["hero"]) == 3  # un lanzamiento por juego
    assert all(h["products"] for h in data["hero"])
    assert {g["slug"] for g in data["games"]} == {"pokemon", "magic", "yugioh"}
    assert all(i["product_type"] == "carta" and i["stock"] > 0 for i in data["new_arrivals"])
    assert all(i["product_type"] == "sellado" for i in data["featured_sealed"])
    discounts = [i["discount_pct"] for i in data["offers"]]
    assert discounts == sorted(discounts, reverse=True)
    changes = [abs(m["change_pct"]) for m in data["price_movers"]]
    assert changes and changes == sorted(changes, reverse=True)


async def test_novedades_por_juego(client):
    items = (await client.get("/api/home/new-arrivals", params={"game": "yugioh"})).json()
    assert items and all(i["game"] == "yugioh" for i in items)
