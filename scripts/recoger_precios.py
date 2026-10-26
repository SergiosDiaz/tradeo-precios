#!/usr/bin/env python3
"""Recoge cada día de TCGdex todas las cartas de todas las expansiones publicadas en España y en Japón, con el
precio general de Cardmarket, y publica tres cosas en la carpeta de datos (por defecto ./data, en GitHub la rama `data`):

- sets/<expansión>.json      ficha completa de la expansión (cartas, nombres, rarezas, imágenes, precios de hoy),
                             en el mismo formato que usan la app y la web: así abren un álbum con un solo archivo.
- history/<expansión>.json   historial de precios:
    {"set": "30th", "updated": "...", "dates": ["2026-10-21", ...],
     "cards": {"30th-001": [0.05, ...]},                  # tendencia de Cardmarket de cada día (null si no había)
     "latest": {"30th-001": [0.06, 0.05, 0.06, 0.08]}}    # hoy: tendencia, media 1 día, 7 días, 30 días
- index/cards.json           índice de búsqueda:
    {"updated": "...", "sets": {"30th": ["Celebración 30.º Aniversario", "me", "es"]},
     "cards": [["30th-001", "30th", "001", "Exeggcute", "Común", 0.05, 1], ...]}
                # id, expansión, número, nombre, rareza, precio de hoy,
                # imagen: 1 si TCGdex la tiene, la URL si se ha encontrado en otro sitio (ver imagenes.py; con "~"
                # delante si es provisional), 0 si no hay
                # y, solo en las japonesas, un 8.º campo: el nombre en español del Pokémon (para buscarlas)

Las expansiones japonesas (las que TCGdex tiene en japonés) llevan "ja-" delante del id de TCGdex, también sus
cartas ("ja-M6", "ja-M6-001"): así no chocan con las de aquí (TCGdex usa "neo1" en los dos idiomas, y "SM9"/"sm9"
serían el mismo archivo en un disco que no distingue mayúsculas). En el índice su idioma es "ja". Para poder buscarlas
sin saber japonés, cada carta de Pokémon lleva el nombre en español de su especie (de index/pokedex.json, que se
rellena con las cartas en español: número de la Pokédex -> nombre).

Si una expansión falla (no se puede descargar tras varios intentos, o llega sin los precios que tenía ayer),
esa expansión se queda con los datos del día anterior y el resto se publica. Si fallan demasiadas a la vez
(TCGdex caído), no escribe nada y termina con error.

Las expansiones que fallan se vuelven a intentar al final, tras una espera larga (a veces TCGdex tarda en volver a
tener los precios de una expansión). Con --repaso solo se recogen las expansiones que hoy aún no se han actualizado
(la segunda pasada de la tarde); las demás se quedan como están.

Uso:  python3 scripts/recoger_precios.py [carpeta de datos] [--repaso]
"""
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import imagenes

API = "https://api.tcgdex.net/v2"
OFICIAL = "https://assets.pokemon.com/static-assets/content-assets/cms2-es-es/img/cards/web"
UA = {"User-Agent": "tradeo-precios (https://github.com/SergiosDiaz/tradeo-precios)"}
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
REPASO = "--repaso" in sys.argv
# Solo estas expansiones (prueba rápida); las demás se quedan como están.
SOLO = {s for s in os.environ.get("SOLO", "").replace(" ", "").split(",") if s}
DATA = ARGS[0] if ARGS else os.path.join(os.path.dirname(__file__), "..", "data")
WORKERS = 8      # pocas peticiones a la vez: TCGdex es un servicio gratuito y comunitario
SET_VERSION = 6  # versión del formato de sets/<expansión>.json (la misma que espera la app)
MAX_FALLOS = 0.2 # si falla más de esta parte de las expansiones, TCGdex debe de estar caído: no se publica nada
ESPERA_FINAL = 60 if os.environ.get("SOLO") else 900  # segundos antes de reintentar al final las expansiones que han fallado
JAPON = "ja-"    # delante de los ids de las expansiones y cartas japonesas

RAREZAS = {
    "Common": "Común", "Uncommon": "Infrecuente", "Rare": "Rara", "Rare Holo": "Rara Holo",
    "Double rare": "Rara Doble", "Ultra Rare": "Ultra Rara", "Illustration rare": "Rara Ilustración",
    "Special illustration rare": "Rara Ilustración Especial", "Hyper rare": "Rara Híper",
    "Secret Rare": "Rara Secreta", "Pikachu Rare": "Rara Pikachu", "RGB Rare": "Rara RGB",
    "Futuristic Rare": "Rara Futurista", "None": "—", "Ninguno": "—",
    # Las que solo hay en Japón.
    "Art Rare": "Rara Ilustración", "Special Art Rare": "Rara Ilustración Especial", "Super Rare": "Súper Rara",
    "Character Rare": "Rara Personaje", "Character Super Rare": "Súper Rara Personaje", "Shiny Rare": "Rara Variocolor",
    "Shiny Super Rare": "Súper Rara Variocolor", "Shiny Ultra Rare": "Ultra Rara Variocolor", "Mega Hyper Rare": "Rara Híper Mega",
    "Black White Rare": "Rara Blanco y Negro", "Ace Spec Rare": "AS TÁCTICO", "Amazing Rare": "Rara Asombrosa",
    "Crown": "Corona", "Rare Holo LV.X": "Rara Holo LV.X", "Rare PRIME": "Rara PRIME", "LEGEND": "LEYENDA",
}

# Número de la Pokédex -> nombre en español (lo más corto visto: "Pikachu" antes que "Pikachu ex").
POKEDEX = {}
# Código de TCGdex -> nombre de aquí de las expansiones japonesas (se rellena al empezar).
NOMBRES_JA = {}

# Nombre occidental de las expansiones japonesas. Las modernas salen de Limitless (lista de expansiones japonesas
# con su nombre en inglés y el mismo código que TCGdex); las antiguas y las de promos, de esta tabla.
LIMITLESS_JP = "https://limitlesstcg.com/cards/jp"
NOMBRES_JA_FIJOS = {
    "PMCG1": "Expansion Pack", "PMCG2": "Pokémon Jungle", "PMCG3": "Mystery of the Fossils", "PMCG4": "Rocket Gang",
    "PMCG5": "Leaders' Stadium", "PMCG6": "Challenge from the Darkness",
    "neo1": "Gold, Silver, to a New World...", "neo2": "Crossing the Ruins...", "neo3": "Awakening Legends",
    "neo4": "Darkness, and to Light...", "VS1": "Pokémon Card ★VS", "web1": "Pokémon Card ★web",
    "E1": "Base Expansion Pack", "E2": "The Town on No Map", "E3": "Wind from the Sea", "E4": "Split Earth",
    "E5": "Mysterious Mountains",
    "PCG1": "Flight of Legends", "PCG2": "Clash of the Blue Sky", "PCG3": "Rocket Gang Strikes Back",
    "PCG4": "Golden Sky, Silvery Ocean", "PCG5": "Mirage Forest", "PCG6": "Holon Research Tower", "PCG7": "Holon Phantom",
    "PCG8": "Miracle Crystal", "PCG9": "Offense and Defense of the Furthest Ends",
    "SV-P": "Scarlet & Violet Promos", "M-P": "MEGA Promos",
}
# Series japonesas con su nombre de aquí.
SERIES_JA = {
    "PMCG": "Pokémon Card Game (original)", "neo": "Neo", "VS": "VS", "web": "web", "e": "e-Card", "ADV": "ADV",
    "PCG": "PCG", "L": "LEGEND", "XY": "XY", "XYb": "XY BREAK", "SM": "Sol y Luna", "S": "Espada y Escudo",
    "M": "Megaevolución", "SV": "Escarlata y Púrpura",
}


def nombres_japonesas(anteriores):
    """{código de TCGdex: nombre en inglés} de las expansiones japonesas. Si Limitless no responde, los de ayer."""
    nombres = dict(anteriores)
    try:
        req = urllib.request.Request(LIMITLESS_JP, headers={**UA, "User-Agent": "Mozilla/5.0 (tradeo-precios)"})
        with urllib.request.urlopen(req, timeout=60) as r:
            pagina = r.read().decode("utf-8", "ignore")
        for code, dentro in re.findall(r'href="/cards/jp/([A-Za-z0-9\-]+)"[^>]*>(.*?)</a>', pagina, re.S):
            texto = html.unescape(" ".join(re.sub(r"<[^>]+>", " ", dentro).split()))
            if texto.endswith(" " + code):   # «Storm Emeralda M6»: el nombre y el código
                nombres[code] = texto[: -len(code) - 1].strip()
    except Exception as e:
        print(f"::warning title=nombres::no se pudo leer Limitless ({e}); se usan los nombres de ayer")
    nombres.update(NOMBRES_JA_FIJOS)
    return nombres


def es_japonesa(set_id):
    return set_id.startswith(JAPON)


def anotar_pokedex(d):
    """Con una carta en español, apunta el nombre de su Pokémon (solo si es de una sola especie)."""
    dex = d.get("dexId") or []
    nombre = (d.get("name") or "").strip()
    if len(dex) == 1 and nombre:
        k = str(dex[0])
        if k not in POKEDEX or len(nombre) < len(POKEDEX[k]):
            POKEDEX[k] = nombre


def alias_espanol(d):
    """Nombre en español para buscar una carta japonesa: su Pokémon («Pikachu») y lo que lleve en letras latinas
    («ex», «V», «VMAX»…), con «Mega» si es una megaevolución. Vacío si no es un Pokémon conocido."""
    nombres = [POKEDEX[str(n)] for n in d.get("dexId") or [] if str(n) in POKEDEX]
    if not nombres:
        return ""
    nombre = d.get("name") or ""
    extra = [w for w in re.findall(r"[A-Za-z][A-Za-z.]*", nombre) if w.lower() not in {n.lower() for n in nombres}]
    return " ".join((["Mega"] if nombre.startswith("メガ") else []) + nombres + extra)
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
    japonesa = es_japonesa(set_id)
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
    # Japonesas: solo la imagen de TCGdex (si no la tiene, la busca imagenes.py).
    base = d.get("image") or (f"https://assets.tcgdex.net/en/{serie}/{set_id}/{local}" if serie and not japonesa else None)
    official = imagen_oficial(set_id, local) if lang == "es" else None
    alts = [a for a in [official if base else None,
                        base.replace("/es/", "/en/") + "/low.webp" if base and "/es/" in base else None] if a]
    precios, cm = mercado(d)
    rareza = d.get("rarity")
    ficha = {
        "id": (JAPON if japonesa else "") + d["id"], "num": local, "name": d.get("name", ""),
        "rarity": RAREZAS.get(rareza, rareza) if rareza else "—", "type": tipo, "set": set_id,
        "img": base + "/low.webp" if base else official, "imgHi": base + "/high.webp" if base else official,
        "alts": alts or None, "price": precios[0], "p1": precios[1], "p7": precios[2], "p30": precios[3],
        "cm": cm, "artist": d.get("illustrator"),
    }
    if japonesa:
        alias = alias_espanol(d)
        if alias:
            ficha["alias"] = alias
    else:
        anotar_pokedex(d)
    return ficha, precios


def orden(c):
    n = c["num"]
    if n.isdigit():
        return (0, int(n), "")
    digits = re.sub(r"\D", "", n)
    return (1, int(digits) if digits else 0, n)


def expansion(set_id, serie):
    """Ficha completa de una expansión (en español; si TCGdex no la tiene en español, en inglés).
    Las japonesas ("ja-…"), en japonés."""
    japonesa = es_japonesa(set_id)
    tcg_id = set_id[len(JAPON):] if japonesa else set_id
    for lang in (("ja",) if japonesa else ("es", "en")):
        info = get(f"{API}/{lang}/sets/{urllib.parse.quote(tcg_id)}")
        if info and info.get("cards"):
            break
    else:
        return None
    briefs = info["cards"]

    def ficha(b):
        return b, get(f"{API}/{lang}/cards/{urllib.parse.quote(b['id'])}")

    with ThreadPoolExecutor(WORKERS) as ex:
        fichas = list(ex.map(ficha, briefs))   # si una carta falla, Fallo se propaga y se aborta todo
    if briefs and not japonesa and not any(mercado(d or b)[0][0] is not None for b, d in fichas):
        diagnostico(briefs[0]["id"])
    cards, latest, index = [], {}, []
    for brief, d in fichas:
        c, p = carta(d or brief, set_id, serie, lang)
        cards.append(c)
        if p[0] is not None:
            latest[c["id"]] = p
        fila = [c["id"], set_id, c["num"], c["name"], c["rarity"], p[0], 1 if brief.get("image") else 0]
        if c.get("alias"):
            fila.append(c["alias"])
        index.append(fila)
    cards.sort(key=orden)
    nombre = info.get("name", set_id)
    if japonesa and NOMBRES_JA.get(tcg_id):
        nombre = NOMBRES_JA[tcg_id]   # el de aquí; el japonés se queda en nameJa
    ficha_set = {
        "id": set_id, "name": nombre, "serie": serie, "logo": info.get("logo"),
        "official": (info.get("cardCount") or {}).get("official", 0), "lang": lang, "cards": cards,
        "at": time.time(), "v": SET_VERSION,
    }
    if japonesa:
        ficha_set["nameJa"] = info.get("name", set_id)
    return ficha_set, latest, index, lang


def diagnostico(card_id):
    """Qué responde TCGdex para una carta que llega sin precio (para entender los fallos en GitHub)."""
    for lang in ("es", "en"):
        url = f"{API}/{lang}/cards/{urllib.parse.quote(card_id)}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                d = json.load(r)
                cabeceras = {k: v for k, v in r.headers.items() if k.lower() in ("server", "via", "x-served-by", "cf-ray", "age", "date")}
            print(f"  diagnóstico {lang} {card_id}: HTTP 200, claves={sorted(d.keys())[:12]}, "
                  f"pricing={json.dumps(d.get('pricing'))[:200]}, cabeceras={cabeceras}")
        except urllib.error.HTTPError as e:
            print(f"  diagnóstico {lang} {card_id}: HTTP {e.code}")
        except Exception as e:
            print(f"  diagnóstico {lang} {card_id}: {e}")


def precios_de_ayer(set_id):
    """Cuántas cartas de la expansión tenían precio en la última publicación."""
    path = os.path.join(DATA, "history", f"{set_id}.json")
    try:
        return len(json.load(open(path)).get("latest") or {})
    except (OSError, ValueError):
        return 0


def actualizada_hoy(set_id, hoy):
    """Si el historial de la expansión ya tiene el día de hoy (para el repaso de la tarde)."""
    try:
        return hoy in json.load(open(os.path.join(DATA, "history", f"{set_id}.json"))).get("dates", [])
    except (OSError, ValueError):
        return False


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


def indice_anterior():
    """Expansiones y filas del índice publicado la última vez, por expansión."""
    try:
        j = json.load(open(os.path.join(DATA, "index", "cards.json")))
    except (OSError, ValueError):
        return {}, {}
    filas = {}
    for c in j.get("cards", []):
        filas.setdefault(c[1], []).append(c)
    return j.get("sets", {}), filas


def main():
    hoy = dt.date.today().isoformat()
    inicio = time.time()
    series = [s["id"] for s in get(f"{API}/es/series") if s["id"] != "tcgp"]   # TCG Pocket es digital
    expansiones = [(x["id"], sid) for sid in series for x in (get(f"{API}/es/series/{sid}") or {}).get("sets", [])]
    # Las japonesas, después: así ya se conoce el nombre en español de cada Pokémon.
    series_ja = [s["id"] for s in get(f"{API}/ja/series") or []]
    expansiones += [(JAPON + x["id"], sid) for sid in series_ja
                    for x in (get(f"{API}/ja/series/{urllib.parse.quote(sid)}") or {}).get("sets", [])]
    sets_ayer, filas_ayer = indice_anterior()
    nombres_path = os.path.join(DATA, "index", "nombres_ja.json")
    try:
        anteriores = json.load(open(nombres_path)).get("sets", {})
    except (OSError, ValueError):
        anteriores = {}
    NOMBRES_JA.update(nombres_japonesas(anteriores))
    pokedex_path = os.path.join(DATA, "index", "pokedex.json")
    try:
        POKEDEX.update(json.load(open(pokedex_path)))
    except (OSError, ValueError):
        pass

    # Primero se descarga todo en memoria y después se escribe.
    resultados, fallos, al_dia = {}, {}, set()

    def recoger(set_id, serie, esperas):
        """Descarga una expansión. TCGdex a veces la devuelve a medio actualizar, sin precios: si ayer tenía
        precios y hoy faltan más de la mitad, se reintenta tras cada espera; si sigue igual, es un fallo."""
        try:
            r = expansion(set_id, serie)
            if not r and set_id in sets_ayer:
                raise Fallo("TCGdex no devuelve ninguna carta")
            antes = precios_de_ayer(set_id)
            for espera in esperas:
                if not r or antes < 5 or len(r[1]) >= antes / 2:
                    break
                print(f"… {set_id}: {len(r[1])} precios (ayer {antes}); se reintenta en {espera} s")
                time.sleep(espera)
                r = expansion(set_id, serie)
            if r and antes >= 5 and len(r[1]) < antes / 2:
                raise Fallo(f"solo {len(r[1])} cartas con precio (ayer {antes})")
        except Fallo as e:
            fallos[set_id] = str(e)
            print(f"✗ {set_id}: {e}")
            return
        fallos.pop(set_id, None)
        if not r:
            print(f"{set_id}: sin cartas en TCGdex")
            return
        resultados[set_id] = r
        print(f"{set_id} ({r[3]}): {len(r[1])}/{len(r[0]['cards'])} con precio")

    for set_id, serie in expansiones:
        if (REPASO and actualizada_hoy(set_id, hoy)) or (SOLO and set_id not in SOLO):
            al_dia.add(set_id)
            continue
        recoger(set_id, serie, (60, 180))

    # Las que han fallado se reintentan al final, con más margen.
    if fallos and len(fallos) <= len(expansiones) * MAX_FALLOS:
        pendientes = [(s, serie) for s, serie in expansiones if s in fallos]
        print(f"\n{len(pendientes)} expansiones con fallos: se reintentan en {ESPERA_FINAL} s")
        time.sleep(ESPERA_FINAL)
        for set_id, serie in pendientes:
            recoger(set_id, serie, (120, 300))
    if REPASO:
        print(f"Repaso: {len(al_dia)} expansiones ya estaban al día, {len(expansiones) - len(al_dia)} recogidas de nuevo")

    # Si falla mucho a la vez, lo más probable es que TCGdex esté caído: mejor no tocar nada.
    if len(fallos) > (len(expansiones) - len(al_dia)) * MAX_FALLOS and not (REPASO and len(fallos) <= 3):
        print(f"\n{len(fallos)} de {len(expansiones)} expansiones con errores: no se publica nada hoy.")
        sys.exit(1)

    # Imagen para las cartas que TCGdex no tiene. Si algo falla aquí, se publica igual (con las de TCGdex).
    tiene_tcgdex = {fila[0] for r in resultados.values() for fila in r[2] if fila[6]}
    try:
        resueltas, tiene_tcgdex = imagenes.resolver({sid: r[0] for sid, r in resultados.items()}, tiene_tcgdex,
                                                    imagen_oficial, DATA, hoy)
    except Exception as e:
        print(f"::warning title=imágenes::no se pudieron buscar imágenes extra: {e}")
        resueltas = {}
    for r in resultados.values():
        for fila in r[2]:
            # En el índice: 1 si TCGdex tiene imagen, la URL si se ha encontrado en otro sitio ("~" delante si es
            # provisional, de otra versión de la carta), 0 si no hay.
            fila[6] = 1 if fila[0] in tiene_tcgdex else resueltas.get(fila[0], 0)

    # Lo que ha ido bien se publica; lo que ha fallado se queda con los datos del día anterior.
    index_sets, index_cards = {}, []
    for set_id, _ in expansiones:
        if set_id in resultados:
            ficha_set, latest, index, lang = resultados[set_id]
            escribir(os.path.join(DATA, "sets", f"{set_id}.json"), ficha_set)
            if latest:
                escribir(os.path.join(DATA, "history", f"{set_id}.json"), historial(set_id, hoy, latest))
            index_sets[set_id] = [ficha_set["name"], ficha_set["serie"], lang]
            index_cards += index
        elif set_id in al_dia and set_id in sets_ayer:
            # Repaso: ya se publicó hoy por la mañana.
            index_sets[set_id] = sets_ayer[set_id]
            index_cards += filas_ayer.get(set_id, [])
        elif set_id in fallos:
            if set_id in sets_ayer:
                index_sets[set_id] = sets_ayer[set_id]
                index_cards += filas_ayer.get(set_id, [])
                aviso = "se quedan los datos del día anterior"
            else:
                aviso = "aún no tenía datos publicados, hoy no se publica"
            print(f"::warning title={set_id}::{fallos[set_id]}: {aviso}")   # aviso visible en GitHub Actions
    # Las japonesas, con su nombre de aquí (también las que hoy no se han recogido y vienen de ayer).
    for set_id, fila in index_sets.items():
        if es_japonesa(set_id) and NOMBRES_JA.get(set_id[len(JAPON):]):
            index_sets[set_id] = [NOMBRES_JA[set_id[len(JAPON):]]] + list(fila[1:])
    escribir(os.path.join(DATA, "index", "cards.json"), {"updated": hoy, "sets": index_sets, "cards": index_cards})
    escribir(nombres_path, {"sets": NOMBRES_JA, "series": SERIES_JA})
    escribir(pokedex_path, POKEDEX)
    print(f"\n{len(index_sets)} expansiones ({len(fallos)} con los datos del día anterior), "
          f"{len(index_cards)} cartas en {time.time() - inicio:.0f} s")


if __name__ == "__main__":
    main()
