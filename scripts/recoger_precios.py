#!/usr/bin/env python3
"""Recoge cada día el precio de Cardmarket (vía TCGdex) de TODAS las cartas de todas las expansiones
en español y genera el índice de búsqueda de cartas.

Escribe en la carpeta de datos (por defecto ./data, que en GitHub es la rama `data`):

- history/<expansión>.json   historial de precios de esa expansión
    {
      "set": "30th",
      "updated": "2026-10-22T02:30:00Z",
      "dates": ["2026-10-21", "2026-10-22"],             # un día por columna
      "cards": {"30th-001": [0.05, 0.06], ...},           # tendencia de Cardmarket de cada día (null si no había)
      "latest": {"30th-001": [0.06, 0.05, 0.06, 0.08]}    # hoy: tendencia, media 1 día, 7 días, 30 días
    }
- index/cards.json           índice de búsqueda con todas las cartas
    {
      "updated": "2026-10-22",
      "sets": {"30th": ["Celebración 30.º Aniversario", "me", "es"], ...},   # nombre, serie, idioma de los datos
      "cards": [["30th-001", "30th", "001", "Exeggcute", "Común", 0.05, 1], ...]
                # id, expansión, número, nombre, rareza, precio de hoy, 1 si TCGdex tiene imagen
    }

Uso:  python3 scripts/recoger_precios.py [carpeta de datos]
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://api.tcgdex.net/v2"
UA = {"User-Agent": "tradeo-precios (https://github.com/SergiosDiaz/tradeo-precios)"}
DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "data")
WORKERS = 8   # pocas peticiones a la vez: TCGdex es un servicio gratuito y comunitario

RAREZAS_EN = {
    "Common": "Común", "Uncommon": "Infrecuente", "Rare": "Rara", "Rare Holo": "Rara Holo",
    "Double rare": "Rara Doble", "Ultra Rare": "Ultra Rara", "Illustration rare": "Rara Ilustración",
    "Special illustration rare": "Rara Ilustración Especial", "Hyper rare": "Rara Híper",
    "Secret Rare": "Rara Secreta", "Pikachu Rare": "Rara Pikachu", "RGB Rare": "Rara RGB",
    "Futuristic Rare": "Rara Futurista", "None": "—", "Ninguno": "—",
}


def get(url, retries=2):
    for intento in range(retries + 1):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            if intento == retries:
                raise
        except Exception:
            if intento == retries:
                raise
        time.sleep(2 * (intento + 1))


def precios(card):
    markets = [(card.get("pricing") or {}).get("cardmarket")]
    markets += [(v.get("pricing") or {}).get("cardmarket") for v in card.get("variants_detailed") or []]

    def pick(*keys):
        for cm in markets:
            for k in keys:
                if cm and cm.get(k):
                    return round(cm[k], 2)
        return None

    return [pick("trend", "avg30", "avg"), pick("avg1"), pick("avg7"), pick("avg30")]


def expansiones():
    series = [s["id"] for s in get(f"{API}/es/series") if s["id"] != "tcgp"]   # TCG Pocket es digital
    out = []
    for sid in series:
        for x in get(f"{API}/es/series/{sid}").get("sets", []):
            out.append((x["id"], x.get("name", x["id"]), sid))
    return out


def cartas_de(set_id):
    """Cartas de una expansión en español; si TCGdex no la tiene en español, en inglés."""
    for lang in ("es", "en"):
        try:
            cards = get(f"{API}/{lang}/sets/{urllib.parse.quote(set_id)}").get("cards") or []
        except Exception:
            cards = []
        if cards:
            return lang, cards
    return None, []


def ficha(lang, brief):
    try:
        return brief, get(f"{API}/{lang}/cards/{urllib.parse.quote(brief['id'])}")
    except Exception:
        return brief, None


def guardar_historial(set_id, hoy, latest):
    path = os.path.join(DATA, "history", f"{set_id}.json")
    data = json.load(open(path)) if os.path.exists(path) else {"set": set_id, "dates": [], "cards": {}}
    dates, cards = data["dates"], data["cards"]
    if hoy in dates:
        col = dates.index(hoy)
    else:
        dates.append(hoy)
        col = len(dates) - 1
        for serie in cards.values():
            serie.append(None)
    for cid, p in latest.items():
        serie = cards.setdefault(cid, [None] * len(dates))
        serie.extend([None] * (len(dates) - len(serie)))
        serie[col] = p[0]
    data["latest"] = latest
    data["updated"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"), sort_keys=True)


def main():
    hoy = dt.date.today().isoformat()
    os.makedirs(os.path.join(DATA, "history"), exist_ok=True)
    os.makedirs(os.path.join(DATA, "index"), exist_ok=True)
    inicio = time.time()
    index_sets, index_cards, total = {}, [], 0

    for set_id, nombre, serie in expansiones():
        lang, briefs = cartas_de(set_id)
        if not briefs:
            print(f"{set_id}: sin cartas en TCGdex")
            continue
        index_sets[set_id] = [nombre, serie, lang]
        with ThreadPoolExecutor(WORKERS) as ex:
            fichas = list(ex.map(lambda b: ficha(lang, b), briefs))
        latest = {}
        for brief, d in fichas:
            d = d or brief
            p = precios(d)
            if p[0] is not None:
                latest[brief["id"]] = p
            rareza = d.get("rarity")
            index_cards.append([brief["id"], set_id, brief.get("localId", ""), d.get("name", brief.get("name", "")),
                                RAREZAS_EN.get(rareza, rareza) if rareza else "—", p[0], 1 if brief.get("image") else 0])
        if latest:
            guardar_historial(set_id, hoy, latest)
        total += len(briefs)
        print(f"{set_id} ({lang}): {len(latest)}/{len(briefs)} con precio")

    with open(os.path.join(DATA, "index", "cards.json"), "w", encoding="utf-8") as f:
        json.dump({"updated": hoy, "sets": index_sets, "cards": index_cards}, f, ensure_ascii=False, separators=(",", ":"))
    print(f"\n{len(index_sets)} expansiones, {total} cartas en {time.time() - inicio:.0f} s")


if __name__ == "__main__":
    main()
