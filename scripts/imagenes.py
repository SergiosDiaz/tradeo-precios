"""Imagen para las cartas que TCGdex no tiene (promos, subcolecciones, kits de entrenador, McDonald's…).

Se prueba, por orden, hasta encontrar una que exista:
  1. la oficial en español de pokemon.com
  2. Limitless en español (promos y energías recientes)
  3. la de TCGdex en inglés
  4. Limitless en inglés
  5. pokemontcg.io (en inglés)
  Las japonesas, en Limitless en japonés (tiene casi todas las de 2010 en adelante, y las promos) y, si no, en
  jp.pokellector.com (las primeras expansiones, Neo, VS y las secretas de SM/S que Limitless no tiene).
  6. último recurso: la imagen de otra versión de la misma carta (mismo nombre, otra expansión; si no hay
     ninguna, se busca por nombre en pokemontcg.io). La carta se marca con "approx" para que la app y la web
     avisen de que es provisional.

Lo encontrado se guarda en imagenes.json para no repetir la búsqueda cada día. Las provisionales y las que no
tienen imagen se vuelven a mirar a diario por si ya ha salido la buena. Nada de esto hace fallar al robot.
"""
import difflib
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
LIMITLESS_JP = "https://limitlesstcg.nyc3.cdn.digitaloceanspaces.com/tpc"
PTCG_API = "https://api.pokemontcg.io/v2/cards"

# Expansión de TCGdex -> código de Limitless (y cómo pasar el número: "SWSH251" -> "251").
LIMITLESS_SETS = {"svp": "SVP", "sve": "SVE", "mep": "MEP", "mee": "MEE", "swshp": "SP", "30th": "30C"}
# Expansión de TCGdex -> expansión de pokemontcg.io.
PTCG_SETS = {
    "swsh4.5sv": "swsh45sv", "sm7.5": "sm75", "swsh12.5gg": "swsh12pt5gg", "smp": "smp", "swshp": "swshp",
    "swsh9tg": "swsh9tg", "swsh10tg": "swsh10tg", "swsh11tg": "swsh11tg", "swsh12tg": "swsh12tg", "sve": "sve",
    "svp": "svp", "2011bw": "mcd11", "2012bw": "mcd12", "2021swsh": "mcd21", "2022swsh": "mcd22",
    "cel25cc": "cel25c", "cel25": "cel25", "tk-ex-latia": "tk1a", "tk-ex-latio": "tk1b", "tk-ex-p": "tk2a",
    "tk-ex-m": "tk2b", "hgssp": "hsp", "xyp": "xyp", "bwp": "bwp", "exu": "ex10",
}
# Expansión japonesa de TCGdex -> página de jp.pokellector.com (https://jp.pokellector.com/<página>-Expansion/).
POKELLECTOR_JP = {
    "ja-PMCG1": "Expansion-Pack", "ja-PMCG2": "Pokemon-Jungle", "ja-PMCG3": "Mystery-of-the-Fossils",
    "ja-PMCG4": "Rocket-Gang", "ja-PMCG5": "Leaders-Stadium", "ja-PMCG6": "Challenge-from-the-Darkness",
    "ja-neo1": "Gold-Silver-to-a-New-World", "ja-neo2": "Crossing-the-Ruins", "ja-neo3": "Awakening-Legends",
    "ja-neo4": "Darkness-and-to-Light", "ja-VS1": "Pokemon-VS", "ja-BW8a": "Thunder-Knuckle",
    "ja-M6a": "30th-Celebration-Japanese",
    "ja-SM1S": "Collection-Sun", "ja-SM1M": "Collection-Moon", "ja-SM1p": "Sun-Moon-Strengthening-Expansion",
    "ja-SM2K": "Islands-Awaiting-You", "ja-SM2L": "Alola-Moonlight",
    "ja-SM2p": "Strengthening-Expansion-Pack-Beyond-A-New-Challeng",
    "ja-SM3H": "Seen-the-Rainbow-Battle", "ja-SM3N": "Light-Consuming-Darkness",
    "ja-SM3p": "Strengthening-Expansion-Shining-Legends", "ja-SM4A": "The-Transdimensional-Beast",
    "ja-SM4S": "The-Awoken-Hero", "ja-SM4p": "GX-Battle-Boost", "ja-SM5S": "Ultra-Sun", "ja-SM5M": "Ultra-Moon",
    "ja-SM5p": "Ultra-Force", "ja-SM6": "Japanese-Forbidden-Light", "ja-SM6a": "Dragon-Storm",
    "ja-SM6b": "Champion-Road", "ja-SM7": "Charisma-of-the-Cracked-Sky", "ja-SM7a": "Thunderclap-Spark",
    "ja-SM7b": "Fairy-Rise", "ja-SM8": "Explosive-Impact", "ja-SM8a": "Dark-Order", "ja-SM8b": "Ultra-Shiny-GX",
    "ja-SM9": "Tag-Bolt", "ja-SM9a": "Night-Unison", "ja-SM9b": "Full-Metal-Wall", "ja-SM10": "Double-Blaze",
    "ja-SM10a": "GG-End", "ja-SM10b": "Sky-Legend", "ja-SM11": "Miracle-Twins", "ja-SM11a": "Remix-Bout",
    "ja-SM11b": "Dream-League", "ja-SM12": "Alter-Genesis", "ja-SM12a": "Tag-Team-GX-All-Stars",
    "ja-S5I": "Single-Strike-Master", "ja-S5R": "Rapid-Strike-Master", "ja-S6H": "Silver-Lance",
    "ja-S6K": "Jet-Black-Spirit", "ja-S7D": "Towering-Perfection", "ja-S8": "Fusion-ARTS",
    "ja-S8b": "VMAX-Climax", "ja-S12a": "VSTAR-Universe",
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
    if set_lang == "ja":
        # Limitless en japonés: el código de TCGdex sin «ja-» ni guiones («ja-SV-P» -> «SVP») y el número sin ceros.
        code = c["set"].removeprefix("ja-").replace("-", "")
        n = c["num"].lstrip("0") or "0"
        out.append((f"{LIMITLESS_JP}/{code}/{code}_{n}_R_JP_SM.png", f"{LIMITLESS_JP}/{code}/{code}_{n}_R_JP_LG.png"))
        return out   # si no, otra versión de la misma carta japonesa
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


def _plano(texto):
    return re.sub(r"[^a-z0-9]", "", (texto or "").lower())


def mismo_nombre(alias, nombre):
    """¿Es la misma carta? alias: nombre en inglés de TCGdex («Scyther R»); nombre: el de Pokellector
    («Rockets-Scyther»). Sin alias (entrenadores y energías) vale el número."""
    a, b = _plano(alias), _plano(nombre)
    if not a:
        return True
    if a in b or b in a or difflib.SequenceMatcher(None, a, b).ratio() >= 0.8:
        return True
    primera = _plano(alias.split()[0])   # el Pokémon, con el dueño delante o detrás («Bugsy's Pinsir»)
    return len(primera) >= 4 and primera in b


class Pokellector:
    """Imágenes de jp.pokellector.com para japonesas que no están en Limitless (una página por expansión)."""

    def __init__(self):
        self.sets = {}

    def _cartas(self, set_id, todas):
        """{número: [(nombre, url pequeña)]} de la expansión, o {} si su numeración no cuadra con la de TCGdex."""
        if set_id in self.sets:
            return self.sets[set_id]
        self.sets[set_id] = {}
        url = f"https://jp.pokellector.com/{POKELLECTOR_JP[set_id]}-Expansion/"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                html = r.read().decode("utf-8", "replace")
        except Exception:
            return {}
        cartas = {}
        for m in re.finditer(r'https://den-cards\.pokellector\.com/\d+/([^"/]+?)\.[A-Za-z0-9+-]+\.([A-Za-z0-9]+)(?:\.\d+)?\.thumb\.png', html):
            cartas.setdefault(m.group(2).lstrip("0") or "0", []).append((m.group(1), m.group(0)))
        # Solo si casi todas las cartas con nombre en inglés coinciden en número y nombre (si no, es otra numeración).
        con_alias = [c for c in todas if c.get("alias")]
        iguales = sum(1 for c in con_alias
                      if any(mismo_nombre(c["alias"], n) for n, _ in cartas.get(c["num"].lstrip("0") or "0", [])))
        if con_alias and iguales / len(con_alias) >= 0.8:
            self.sets[set_id] = cartas
        else:
            print(f"Pokellector: {set_id} no cuadra ({iguales}/{len(con_alias)}), no se usa")
        return self.sets[set_id]

    def buscar(self, c, todas):
        if c["set"] not in POKELLECTOR_JP:
            return None
        hits = self._cartas(c["set"], todas).get(c["num"].lstrip("0") or "0", [])
        url = next((u for n, u in hits if mismo_nombre(c.get("alias"), n)), None)
        return (url, url.replace(".thumb.png", ".png")) if url else None


def resolver(fichas, tiene_tcgdex, oficial, data_dir, hoy):
    """Pone imagen a las cartas de `fichas` ({set_id: ficha}) que TCGdex no tiene.

    tiene_tcgdex: ids de las cartas que según TCGdex tienen imagen. oficial(set_id, número): URL de pokemon.com.
    Devuelve ({id: url pequeña} de las resueltas, con "~" delante si es provisional; ids cuya imagen de TCGdex
    existe de verdad), para el índice de búsqueda."""
    path = os.path.join(data_dir, "imagenes.json")
    try:
        previo = json.load(open(path))
    except (OSError, ValueError):
        previo = {}
    guardado = previo.get("cards", {})
    verificadas = set(previo.get("ok", []))

    # TCGdex a veces dice que tiene la imagen y no existe: se comprueba una vez cada carta (y se recuerda).
    cartas = {c["id"]: c for f in fichas.values() for c in f["cards"]}
    por_mirar = [cid for cid in tiene_tcgdex if cid in cartas and cid not in verificadas and cartas[cid].get("img")]
    with ThreadPoolExecutor(WORKERS) as ex:
        for cid, ok in zip(por_mirar, ex.map(lambda cid: existe(cartas[cid]["img"]), por_mirar)):
            if ok:
                verificadas.add(cid)
    rotas = {cid for cid in por_mirar if cid not in verificadas}
    tiene_tcgdex = {cid for cid in tiene_tcgdex if cid not in rotas}
    if por_mirar:
        print(f"Imágenes de TCGdex comprobadas: {len(por_mirar)}, rotas: {len(rotas)}")

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
    pokellector = Pokellector()

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
    # Pokellector, también una página por expansión.
    for ficha, c in pendientes:
        if not exactas.get(c["id"]) and ficha.get("lang") == "ja":
            hit = pokellector.buscar(c, ficha["cards"])
            if hit and existe(hit[0]):
                exactas[c["id"]] = {"img": hit[0], "hi": hit[1] if existe(hit[1]) else hit[0]}

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
        hit = ptcg.por_nombre(c["name"]) if ficha.get("lang") != "ja" else None
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
            resueltas[c["id"]] = ("~" if g.get("approx") else "") + g["img"]

    # Fuera las que TCGdex ya tiene (las de expansiones que hoy han fallado se quedan para mañana).
    guardado = {k: v for k, v in guardado.items() if k not in tiene_tcgdex}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"updated": hoy, "cards": guardado, "ok": sorted(verificadas)}, f,
                  ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    os.replace(tmp, path)
    n_aprox = sum(1 for v in guardado.values() if v.get("approx"))
    sin = sum(1 for f in fichas.values() for c in f["cards"] if c["id"] not in tiene_tcgdex and c["id"] not in resueltas)
    print(f"Imágenes: {len(resueltas)} cartas sin imagen en TCGdex resueltas ({n_aprox} provisionales), {sin} sin ninguna")
    return resueltas, tiene_tcgdex
