#!/usr/bin/env python3
"""Recoge cada día los precios de Cardmarket (vía TCGdex) de las cartas de los álbumes del grupo.

- Lee de Firestore (solo lectura) qué álbumes coleccionáis entre todos.
- Para cada álbum descarga el precio de cada carta y lo añade a history/<álbum>.json:
    {
      "set": "30th",
      "updated": "2026-10-21T07:30:00Z",
      "dates": ["2026-10-21", ...],                 # un día por columna
      "cards": {"30th-001": [0.05, ...], ...},       # tendencia de Cardmarket de cada día (null si no había)
      "latest": {"30th-001": [0.05, 0.06, 0.07, 0.08], ...}   # hoy: tendencia, media 1 día, 7 días, 30 días
    }
La app y la web leen estos archivos; no se guarda nada en Firebase.
"""
import datetime as dt
import json
import os
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://api.tcgdex.net/v2"
FIRESTORE = ("https://firestore.googleapis.com/v1/projects/poketcg-d9699/databases/(default)/documents/players"
             "?pageSize=300&key=AIzaSyBiHj-DDHwU76C93TXyPX525GYnF2e9y8I&mask.fieldPaths=albums")
DEFAULT_ALBUMS = ["30th", "30th-c"]          # quien no ha elegido álbumes colecciona estos
ALWAYS = ["30th", "30th-c", "mep"]            # se siguen siempre
ROOT = os.path.join(os.path.dirname(__file__), "..")
UA = {"User-Agent": "tradeo-precios"}


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.load(r)


def albums_del_grupo():
    ids = set(ALWAYS)
    for doc in get(FIRESTORE).get("documents", []):
        values = doc.get("fields", {}).get("albums", {}).get("arrayValue", {}).get("values")
        ids.update(v["stringValue"] for v in values or []) if values is not None else ids.update(DEFAULT_ALBUMS)
    return sorted(ids)


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


def cartas_de(set_id):
    for lang in ("es", "en"):
        try:
            cards = get(f"{API}/{lang}/sets/{set_id}").get("cards") or []
        except Exception:
            cards = []
        if cards:
            return lang, [c["id"] for c in cards]
    return None, []


def precio_carta(lang, cid):
    try:
        return cid, precios(get(f"{API}/{lang}/cards/{urllib.parse.quote(cid)}"))
    except Exception:
        return cid, None


def actualizar(set_id, hoy):
    path = os.path.join(ROOT, "history", f"{set_id}.json")
    if os.path.exists(path) and hoy in json.load(open(path)).get("dates", []):
        return False  # ya tiene los precios de hoy (el robot pasa cada hora para recoger expansiones nuevas)
    lang, ids = cartas_de(set_id)
    if not ids:
        print(f"{set_id}: sin cartas en TCGdex")
        return False
    with ThreadPoolExecutor(16) as ex:
        latest = {cid: p for cid, p in ex.map(lambda c: precio_carta(lang, c), ids) if p and p[0] is not None}

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
    print(f"{set_id}: {len(latest)}/{len(ids)} cartas con precio, {len(dates)} días")
    return True


def main():
    hoy = dt.date.today().isoformat()
    sets = albums_del_grupo()
    cambios = [s for s in sets if actualizar(s, hoy)]
    index = os.path.join(ROOT, "history", "index.json")
    previo = json.load(open(index)) if os.path.exists(index) else {}
    if cambios or previo.get("sets") != sets:
        with open(index, "w", encoding="utf-8") as f:
            json.dump({"updated": hoy, "sets": sets}, f, separators=(",", ":"))
    print("Actualizadas:", ", ".join(cambios) or "ninguna (todo al día)")


if __name__ == "__main__":
    main()
