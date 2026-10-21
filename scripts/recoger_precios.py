#!/usr/bin/env python3
"""Recoge cada día de TCGdex todas las cartas de todas las expansiones publicadas en España, con el precio
general de Cardmarket, y publica tres cosas en la carpeta de datos (por defecto ./data, en GitHub la rama `data`):

- sets/<expansión>.json      ficha completa de la expansión (cartas, nombres, rarezas, imágenes, precios de hoy),
                             en el mismo formato que usan la app y la web: así abren un álbum con un solo archivo.
- history/<expansión>.json   historial de precios:
    {"set": "30th", "updated": "...", "dates": ["2026-10-21", ...],
     "cards": {"30th-001": [0.05, ...]},                  # tendencia de Cardmarket de cada día (null si no había)
     "latest": {"30th-001": [0.06, 0.05, 0.06, 0.08]}}    # hoy: tendencia, media 1 día, 7 días, 30 días
- index/cards.json           índice de búsqueda:
    {"updated": "...", "sets": {"30th": ["Celebración 30.º Aniversario", "me", "es"]},
     "cards": [["30th-001", "30th", "001", "Exeggcute", "Común", 0.05, 1], ...]}
                # id, expansión, número, nombre, rareza, precio de hoy, 1 si TCGdex tiene imagen

Si algo falla (una expansión o una carta que no se puede descargar tras varios intentos), no escribe nada y
termina con error: así nunca se publica un índice o un historial a medias.

Uso:  python3 scripts/recoger_precios.py [carpeta de datos]
"""
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://api.tcgdex.net/v2"
OFICIAL = "https://assets.pokemon.com/static-assets/content-assets/cms2-es-es/img/cards/web"
UA = {"User-Agent": "tradeo-precios (https://github.com/SergiosDiaz/tradeo-precios)"}
DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "data")
WORKERS = 8      # pocas peticiones a la vez: TCGdex es un servicio gratuito y comunitario
SET_VERSION = 5  # versión del formato de sets/<expansión>.json (la misma que espera la app)

RAREZAS = {
    "Common": "Común", "Uncommon": "Infrecuente", "Rare": "Rara", "Rare Holo": "Rara Holo",
    "Double rare": "Rara Doble", "Ultra Rare": "Ultra Rara", "Illustration rare": "Rara Ilustración",
    "Special illustration rare": "Rara Ilustración Especial", "Hyper rare": "Rara Híper",
    "Secret Rare": "Rara Secreta", "Pikachu Rare": "Rara Pikachu", "RGB Rare": "Rara RGB",
    "Futuristic Rare": "Rara Futurista", "None": "—", "Ninguno": "—",
}
TIPOS = {
    "Grass": "Planta", "Fire": "Fuego", "Water": "Agua", "Lightning": "Rayo", "Psychic": "Psíquica",
    "Fighting": "Lucha", "Darkness": "Oscura", "Metal": "Metálica", "Dragon": "Dragón",
    "Colorless": "Incolora", "Fairy": "Hada", "Psíquico": "Psíquica",
}


class Fallo(Exception):
    pass


def get(url, retries=3):
    """JSON de una URL. Devuelve None si no existe (404); lanza Fallo si no se puede descargar."""
    for intento in range(retries + 1):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            error = f"HTTP {e.code}"
        except Exception as e:  # red, timeout, JSON roto…
            error = str(e)
        if intento < retries:
            time.sleep(3 * (intento + 1))
    raise Fallo(f"{url}: {error}")


def mercado(card):
    markets = [(card.get("pricing") or {}).get("cardmarket")]
    markets += [(v.get("pricing") or {}).get("cardmarket") for v in card.get("variants_detailed") or []]

    def pick(*keys):
        for cm in markets:
            for k in keys:
                if cm and cm.get(k):
                    return round(cm[k], 2)
        return None

    ids = [m.get("idProduct") for m in markets if m] + [(v.get("thirdParty") or {}).get("cardmarket")
                                                         for v in card.get("variants_detailed") or []]
    return [pick("trend", "avg30", "avg"), pick("avg1"), pick("avg7"), pick("avg30")], next((i for i in ids if i), None)


def imagen_oficial(set_id, local):
    """pokemon.com: me02 -> ME02/ME02_ES_125.png, sv03.5 -> SV3PT5/SV3PT5_ES_199.png"""
    if not local.isdigit():
        return None
    code = set_id.upper()
    if "." in code:
        m = re.fullmatch(r"([A-Z]+)0*(\d+)\.(\d+)", code)
        if m:
            code = f"{m.group(1)}{m.group(2)}PT{m.group(3)}"
    return f"{OFICIAL}/{code}/{code}_ES_{int(local)}.png"


def carta(d, set_id, serie, lang):
    """Carta en el formato de la app y la web."""
    local = d.get("localId", "")
    types = d.get("types") or []
    cat = d.get("category") or ""
    if types:
        tipo = TIPOS.get(types[0], types[0])
    elif re.search("entren|trainer", cat, re.I):
        tipo = "Entrenador"
    elif re.search("energ", cat, re.I):
        tipo = "Energía"
    else:
        tipo = "Incolora"
    base = d.get("image") or (f"https://assets.tcgdex.net/en/{serie}/{set_id}/{local}" if serie else None)
    official = imagen_oficial(set_id, local) if lang == "es" else None
    alts = [a for a in [official if base else None,
                        base.replace("/es/", "/en/") + "/low.webp" if base and "/es/" in base else None] if a]
    precios, cm = mercado(d)
    rareza = d.get("rarity")
    return {
        "id": d["id"], "num": local, "name": d.get("name", ""),
        "rarity": RAREZAS.get(rareza, rareza) if rareza else "—", "type": tipo, "set": set_id,
        "img": base + "/low.webp" if base else official, "imgHi": base + "/high.webp" if base else official,
        "alts": alts or None, "price": precios[0], "p1": precios[1], "p7": precios[2], "p30": precios[3],
        "cm": cm, "artist": d.get("illustrator"),
    }, precios


def orden(c):
    n = c["num"]
    if n.isdigit():
        return (0, int(n), "")
    digits = re.sub(r"\D", "", n)
    return (1, int(digits) if digits else 0, n)


def expansion(set_id, serie):
    """Ficha completa de una expansión (en español; si TCGdex no la tiene en español, en inglés)."""
    for lang in ("es", "en"):
        info = get(f"{API}/{lang}/sets/{urllib.parse.quote(set_id)}")
        if info and info.get("cards"):
            break
    else:
        return None
    briefs = info["cards"]

    def ficha(b):
        return b, get(f"{API}/{lang}/cards/{urllib.parse.quote(b['id'])}")

    with ThreadPoolExecutor(WORKERS) as ex:
        fichas = list(ex.map(ficha, briefs))   # si una carta falla, Fallo se propaga y se aborta todo
    cards, latest, index = [], {}, []
    for brief, d in fichas:
        c, p = carta(d or brief, set_id, serie, lang)
        cards.append(c)
        if p[0] is not None:
            latest[c["id"]] = p
        index.append([c["id"], set_id, c["num"], c["name"], c["rarity"], p[0], 1 if brief.get("image") else 0])
    cards.sort(key=orden)
    ficha_set = {
        "id": set_id, "name": info.get("name", set_id), "serie": serie, "logo": info.get("logo"),
        "official": (info.get("cardCount") or {}).get("official", 0), "lang": lang, "cards": cards,
        "at": time.time(), "v": SET_VERSION,
    }
    return ficha_set, latest, index, lang


def historial(set_id, hoy, latest):
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
    return data


def escribir(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    os.replace(tmp, path)


def main():
    hoy = dt.date.today().isoformat()
    inicio = time.time()
    series = [s["id"] for s in get(f"{API}/es/series") if s["id"] != "tcgp"]   # TCG Pocket es digital
    expansiones = [(x["id"], sid) for sid in series for x in (get(f"{API}/es/series/{sid}") or {}).get("sets", [])]

    # Primero se descarga todo en memoria; solo si no hay ningún fallo se escribe.
    resultados, fallos = [], []
    for set_id, serie in expansiones:
        try:
            r = expansion(set_id, serie)
        except Fallo as e:
            fallos.append(f"{set_id}: {e}")
            print(f"✗ {set_id}: {e}")
            continue
        if not r:
            print(f"{set_id}: sin cartas en TCGdex")
            continue
        resultados.append((set_id, *r))
        print(f"{set_id} ({r[3]}): {len(r[1])}/{len(r[0]['cards'])} con precio")

    if fallos:
        print(f"\n{len(fallos)} expansiones con errores: no se publica nada hoy.")
        sys.exit(1)

    index_sets, index_cards = {}, []
    for set_id, ficha_set, latest, index, lang in resultados:
        escribir(os.path.join(DATA, "sets", f"{set_id}.json"), ficha_set)
        if latest:
            escribir(os.path.join(DATA, "history", f"{set_id}.json"), historial(set_id, hoy, latest))
        index_sets[set_id] = [ficha_set["name"], ficha_set["serie"], lang]
        index_cards += index
    escribir(os.path.join(DATA, "index", "cards.json"), {"updated": hoy, "sets": index_sets, "cards": index_cards})
    print(f"\n{len(index_sets)} expansiones, {len(index_cards)} cartas en {time.time() - inicio:.0f} s")


if __name__ == "__main__":
    main()
