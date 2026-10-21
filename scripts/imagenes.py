"""Imagen para las cartas que TCGdex no tiene (promos, subcolecciones, kits de entrenador, McDonald's…).

Se prueba, por orden, hasta encontrar una que exista:
  1. la oficial en español de pokemon.com
  2. Limitless en español (promos y energías recientes)
  3. la de TCGdex en inglés
  4. Limitless en inglés
  5. pokemontcg.io (en inglés)
  6. último recurso: la imagen de otra versión de la misma carta (mismo nombre, otra expansión; si no hay
     ninguna, se busca por nombre en pokemontcg.io). La carta se marca con "approx" para que la app y la web
     avisen de que es provisional.

Lo encontrado se guarda en imagenes.json para no repetir la búsqueda cada día. Las provisionales y las que no
tienen imagen se vuelven a mirar a diario por si ya ha salido la buena. Nada de esto hace fallar al robot.
"""
import json
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = {"User-Agent": "tradeo-precios (https://github.com/SergiosDiaz/tradeo-precios)"}
LIMITLESS = "https://limitlesstcg.nyc3.cdn.digitaloceanspaces.com/tpci"
PTCG_API = "https://api.pokemontcg.io/v2/cards"

# Expansión de TCGdex -> código de Limitless (y cómo pasar el número: "SWSH251" -> "251").
LIMITLESS_SETS = {"svp": "SVP", "sve": "SVE", "mep": "MEP", "mee": "MEE", "swshp": "SP"}
# Expansión de TCGdex -> expansión de pokemontcg.io.
PTCG_SETS = {
    "swsh4.5sv": "swsh45sv", "sm7.5": "sm75", "swsh12.5gg": "swsh12pt5gg", "smp": "smp", "swshp": "swshp",
    "swsh9tg": "swsh9tg", "swsh10tg": "swsh10tg", "swsh11tg": "swsh11tg", "swsh12tg": "swsh12tg", "sve": "sve",
    "svp": "svp", "2011bw": "mcd11", "2012bw": "mcd12", "2021swsh": "mcd21", "2022swsh": "mcd22",
    "cel25cc": "cel25c", "cel25": "cel25", "tk-ex-latia": "tk1a", "tk-ex-latio": "tk1b", "tk-ex-p": "tk2a",
    "tk-ex-m": "tk2b", "hgssp": "hsp", "xyp": "xyp", "bwp": "bwp", "exu": "ex10",
}
WORKERS = 8


def existe(url):
    """True si la imagen existe (se piden solo los primeros bytes)."""
    try:
        req = urllib.request.Request(url, headers={**UA, "Range": "bytes=0-1023"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status in (200, 206) and "image" in (r.headers.get("Content-Type") or "image")
    except Exception:
        return False


def num_limitless(set_id, num):
    n = re.sub(r"^SWSH", "", num) if set_id == "swshp" else num
    return n.zfill(3) if n.isdigit() else n


def candidatos(c, set_lang, serie, oficial):
    """Imágenes exactas de la carta, de mejor a peor: [(pequeña, grande), …]."""
    out = []
    if set_lang == "es" and oficial:
        out.append((oficial, oficial))
    code = LIMITLESS_SETS.get(c["set"])
    if code:
        n = num_limitless(c["set"], c["num"])
        out.append((f"{LIMITLESS}/{code}/{code}_{n}_R_ES_SM.png", f"{LIMITLESS}/{code}/{code}_{n}_R_ES_LG.png"))
    if serie:
        base = f"https://assets.tcgdex.net/en/{serie}/{c['set']}/{c['num']}"
        out.append((base + "/low.webp", base + "/high.webp"))
    if code:
        n = num_limitless(c["set"], c["num"])
        out.append((f"{LIMITLESS}/{code}/{code}_{n}_R_EN_SM.png", f"{LIMITLESS}/{code}/{code}_{n}_R_EN_LG.png"))
    return out


class PokemonTCG:
    """Imágenes de pokemontcg.io por expansión (una petición por expansión y ejecución)."""

    def __init__(self):
        self.sets = {}

    def buscar(self, c):
        pid = PTCG_SETS.get(c["set"])
        if not pid:
            return None
        if pid not in self.sets:
            self.sets[pid] = []
            url = f"{PTCG_API}?q=set.id:{pid}&select=number,name,images&pageSize=250"
            for intento in range(4):   # su API es lenta y a veces da 500/502
                try:
                    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                        self.sets[pid] = json.load(r).get("data") or []
                    break
                except Exception:
                    time.sleep(5 * (intento + 1))
        norm = lambda n: urllib.parse.unquote(n).lstrip("0") or "0"
        cards = self.sets[pid]
        hit = next((x for x in cards if norm(x.get("number", "")) == norm(c["num"])), None)
        if not hit:
            mismo = [x for x in cards if x.get("name", "").lower() == c["name"].lower()]
            hit = mismo[0] if len(mismo) == 1 else None
        imgs = (hit or {}).get("images") or {}
        return (imgs["small"], imgs.get("large") or imgs["small"]) if imgs.get("small") else None

    def por_nombre(self, nombre):
        """Otra versión de la carta en pokemontcg.io, buscando por nombre (sin tildes): la más reciente."""
        limpio = unicodedata.normalize("NFD", nombre.replace("’", "'")).encode("ascii", "ignore").decode().replace('"', "")
        variantes = [limpio] + [re.sub(rf" {s}$", f"-{s}", limpio) for s in ("EX", "GX") if limpio.endswith(f" {s}")]
        for nombre_buscado in variantes:
            url = (f"{PTCG_API}?q=" + urllib.parse.quote(f'name:"{nombre_buscado}"')
                   + "&select=id,images,set&orderBy=-set.releaseDate&pageSize=5")
            data = []
            for intento in range(3):
                try:
                    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                        data = json.load(r).get("data") or []
                    break
                except Exception:
                    time.sleep(5 * (intento + 1))
            for x in data:
                imgs = x.get("images") or {}
                if imgs.get("small"):
                    return imgs["small"], imgs.get("large") or imgs["small"], x["id"]
        return None


def resolver(fichas, tiene_tcgdex, oficial, data_dir, hoy):
    """Pone imagen a las cartas de `fichas` ({set_id: ficha}) que TCGdex no tiene.

    tiene_tcgdex: ids de las cartas con imagen propia en TCGdex. oficial(set_id, número): URL de pokemon.com.
    Devuelve {id: url pequeña} de las resueltas (para el índice de búsqueda)."""
    path = os.path.join(data_dir, "imagenes.json")
    try:
        guardado = json.load(open(path)).get("cards", {})
    except (OSError, ValueError):
        guardado = {}

    # Para el último recurso: cartas con imagen de TCGdex por nombre, en orden (las más nuevas al final).
    por_nombre = {}
    for ficha in fichas.values():
        for c in ficha["cards"]:
            if c["id"] in tiene_tcgdex and c.get("img"):
                por_nombre.setdefault(c["name"].lower(), []).append((ficha.get("serie"), c))

    pendientes = []
    for ficha in fichas.values():
        for c in ficha["cards"]:
            if c["id"] in tiene_tcgdex:
                continue
            g = guardado.get(c["id"])
            if g and g.get("img") and not g.get("approx"):
                continue   # ya resuelta con su imagen exacta
            pendientes.append((ficha, c))

    ptcg = PokemonTCG()

    def exacta(item):
        ficha, c = item
        for small, big in candidatos(c, ficha.get("lang"), ficha.get("serie"), oficial(c["set"], c["num"])):
            if existe(small):
                return c["id"], {"img": small, "hi": big if big == small or existe(big) else small}
        return c["id"], None

    with ThreadPoolExecutor(WORKERS) as ex:
        exactas = dict(ex.map(exacta, pendientes))
    # pokemontcg.io, de una en una por expansión (no hace falta más velocidad y su API es delicada).
    for ficha, c in pendientes:
        if not exactas.get(c["id"]):
            hit = ptcg.buscar(c)
            if hit and existe(hit[0]):
                exactas[c["id"]] = {"img": hit[0], "hi": hit[1]}

    for ficha, c in pendientes:
        r = exactas.get(c["id"])
        if r:
            guardado[c["id"]] = {**r, "nombre": c["name"].lower(), "fecha": hoy}
            continue
        # Último recurso: otra versión de la misma carta, mejor de la misma serie y lo más reciente posible.
        otras = por_nombre.get(c["name"].lower(), [])
        otras = sorted(otras, key=lambda x: x[0] == ficha.get("serie"))   # las de la misma serie, al final
        if otras:
            o = otras[-1][1]
            guardado[c["id"]] = {"img": o["img"], "hi": o.get("imgHi") or o["img"], "approx": o["id"], "nombre": c["name"].lower(), "fecha": hoy}
            continue
        hit = ptcg.por_nombre(c["name"])
        if hit and existe(hit[0]):
            guardado[c["id"]] = {"img": hit[0], "hi": hit[1], "approx": hit[2], "nombre": c["name"].lower(), "fecha": hoy}
            continue
        # La de otra carta con el mismo nombre que ya tenga imagen encontrada (p. ej. las 4 piezas de un V-UNIÓN).
        hermana = next((k for k, v in guardado.items() if k != c["id"] and v.get("nombre") == c["name"].lower()), None)
        if hermana:
            guardado[c["id"]] = {**guardado[hermana], "approx": guardado[hermana].get("approx") or hermana, "fecha": hoy}
        else:
            guardado.pop(c["id"], None)

    # Se aplica a las fichas.
    resueltas = {}
    for ficha in fichas.values():
        for c in ficha["cards"]:
            g = guardado.get(c["id"]) if c["id"] not in tiene_tcgdex else None
            if not g:
                continue
            previas = [u for u in [c.get("img")] + (c.get("alts") or []) if u and u != g["img"]]
            c["img"], c["imgHi"] = g["img"], g["hi"]
            c["alts"] = previas or None
            if g.get("approx"):
                c["approx"] = g["approx"]   # id de la carta de la que se toma la imagen
            resueltas[c["id"]] = g["img"]

    # Fuera las que TCGdex ya tiene (las de expansiones que hoy han fallado se quedan para mañana).
    guardado = {k: v for k, v in guardado.items() if k not in tiene_tcgdex}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"updated": hoy, "cards": guardado}, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    os.replace(tmp, path)
    n_aprox = sum(1 for v in guardado.values() if v.get("approx"))
    sin = sum(1 for f in fichas.values() for c in f["cards"] if c["id"] not in tiene_tcgdex and c["id"] not in resueltas)
    print(f"Imágenes: {len(resueltas)} cartas sin imagen en TCGdex resueltas ({n_aprox} provisionales), {sin} sin ninguna")
    return resueltas
