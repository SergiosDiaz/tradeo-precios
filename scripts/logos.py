#!/usr/bin/env python3
"""Logo de cada expansión (las de aquí y las japonesas), guardado en la propia rama `data`, y en cada idioma.

Cada día, después de los precios, mira las expansiones del índice (index/cards.json). Las que aún no tienen logo
guardado lo buscan, lo descargan y lo guardan en logos/<archivo>; así la app y la web no dependen de que la fuente
lo siga teniendo. Publica logos.json:

    {"updated": "2026-11-09", "logos": {"swsh8": "logos/swsh8-1a2b3c.webp", "ja-S12a": "logos/ja-S12a-4d5e6f.png"},
     "info": {"swsh8": {"src": "<url de origen>", "aprox": false, "at": "2026-11-09"}},
     "idiomas": {"es": {"me06": "logos/me06-…-es.webp"}, "en": {"me06": "logos/me06-…-en.webp"}, "fr": {…}, …},
     "info_idiomas": {"es:me06": {"src": "<url de origen>", "at": "2026-11-12"}}, "pokemon": {"me06": "me_series/me06"}}

`logos` es el de siempre (el que usan las versiones de la app de antes de los idiomas): en las de aquí, el español si lo
hay. `idiomas` es el logo de cada expansión en cada idioma, para que cada álbum lleve el del idioma en que se colecciona
(«Dominio Delta» en español, «Delta Reign» en inglés): la app usa el de su idioma, si no el inglés y si no `logos`.

De dónde sale el logo:
- En cada idioma (español, inglés, francés, alemán e italiano): el oficial de pokemon.com, que los tiene todos desde
  Sol y Luna (2017) con una dirección fija por expansión (ver POKEMON). En español, si no: el de WikiDex (la wiki en
  español: tiene también las antiguas) y si no el de TCGdex en español. En inglés, si no: el de TCGdex en inglés, el
  de pokemontcg.io o el de Scrydex. Lo que falte en un idioma se vuelve a buscar cada día durante los dos meses
  siguientes a que salga la expansión (y después, los lunes): el español suele llegar unos días más tarde.
- `logos` (de aquí): el español; si no, el de TCGdex en español; si no, el inglés; para unas pocas, uno fijado a mano.
- Japonesas (TCGdex no tiene ningún logo suyo): el japonés de Scrydex. Primero por el código («S12a» es «swsh12a_ja»);
  si no, por la fecha de salida y el número de cartas, comprobando que el nombre japonés sale en su ficha.
- Si no se encuentra el suyo, el de la expansión principal de su serie (marcado `aprox`): así todas tienen logo, y los
  aproximados se vuelven a buscar cada día por si ya ha salido el bueno.

Los que se descargan nuevos se guardan en webp de 600 px como mucho (si está Pillow), para que la rama no crezca.

Al final avisa (en la ejecución de GitHub) de las expansiones con logo aproximado.

Uso:  python3 scripts/logos.py [carpeta de datos]
"""
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "data")
API = "https://api.tcgdex.net/v2"
UA = {"User-Agent": "tradeo-precios (https://github.com/SergiosDiaz/tradeo-precios)"}
SCRYDEX = "https://images.scrydex.com/pokemon/{}-logo/logo"
SCRYDEX_JP = "https://scrydex.com/pokemon/jp/expansions"
WORKERS = 8

# Emparejamientos que no salen por el nombre (expansión de aquí -> id de pokemontcg.io / Scrydex).
MANUAL = {"30th": "me55", "30th-c": "me55c", "2023sv": "mcd23", "2024sv": "mcd24", "exu": "ex10",
          "tk-bw-e": "tk5b", "tk-bw-z": "tk5a", "tk-dp-l": "tk3b", "tk-dp-m": "tk3a", "tk-hs-g": "tk4b", "tk-hs-r": "tk4a",
          "tk-sm-l": "tk10a", "tk-sm-r": "tk10b", "tk-xy-b": "tk7b", "tk-xy-latia": "tk8b", "tk-xy-latio": "tk8a",
          "rc": "bw11", "tk-xy-n": "tk6b", "tk-xy-p": "tk9b", "tk-xy-su": "tk9a", "tk-xy-sy": "tk6a", "tk-xy-w": "tk7a"}
# Serie internacional de cada serie japonesa de TCGdex (para el logo de serie, si una no tiene el suyo).
SERIE_INTERNACIONAL = {"PMCG": "base", "neo": "neo", "e": "ecard", "ADV": "ex", "PCG": "ex", "L": "hgss", "BW": "bw",
                       "XY": "xy", "XYb": "xy", "SM": "sm", "S": "swsh", "SV": "sv", "M": "me", "VS": "neo", "web": "neo"}
# Logos fijados a mano (promos sin logo en TCGdex ni en pokemontcg.io).
FIJOS = {"svp": "https://images.pokemontcg.io/svp/logo.png",
         "mep": SCRYDEX.format("mep")}

IDIOMAS = ("es", "en", "fr", "de", "it")
# Logos oficiales de pokemon.com: …/cms2-es-es/img/trading-card-game/series/me_series/me06/me06_logo_169_es.png
POKEMON = "https://www.pokemon.com/static-assets/content-assets/{cms}/img/trading-card-game/series/{code}/{name}_logo_169_{lang}.png"
POKEMON_CMS = {"es": "cms2-es-es", "en": "cms2", "fr": "cms2-fr-fr", "de": "cms2-de-de", "it": "cms2-it-it"}
# Las que pokemon.com no llama como TCGdex (las demás salen solas: «sv03.5» es «sv035», «sm1» es «sm01»…). Pokémon GO
# (swsh10.5) no: el suyo es el de las dos marcas juntas, pequeño; mejor el de WikiDex.
POKEMON_MANUAL = {"30th": "me_series/30th", "swsh10.5": None}
# Las de WikiDex que no se llaman como en TCGdex (TCGdex: «Albor de Guadianes»).
WIKIDEX = "https://www.wikidex.net/api.php"
# (Y las antiguas, que TCGdex solo tiene en inglés.)
WIKIDEX_MANUAL = {"sm2": "Albor de Guardianes", "hgss1": "HeartGold y SoulSilver",
                  "sv10.5b": "Fulgor Negro y Llama Blanca", "sv10.5w": "Fulgor Negro y Llama Blanca",
                  "g1": "Generaciones", "base2": "Jungla", "base3": "Fósil", "bw11": "Tesoros Legendarios"}
ANCHO = 600


def get_json(url, retries=3):
    for i in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.load(r)
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(2 * (i + 1))


def fetch(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
            return r.read() if r.status == 200 else None
    except Exception:
        return None


def ext_of(data):
    """Extensión si son los bytes de una imagen de verdad (y no una página de error)."""
    if not data or len(data) < 600:
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    return None


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = s.replace("&", "and").replace("pokemon", "")
    return re.sub(r"[^a-z0-9]+", "", s)


def archivo(sid, ext):
    """Nombre de archivo seguro y único (hay ids que solo cambian en mayúsculas o llevan «+» y «.»)."""
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", sid)
    return f"logos/{safe}-{hashlib.md5(sid.encode()).hexdigest()[:6]}.{ext}"


def transparente(data):
    """Si el logo tiene el fondo transparente. pokemon.com tiene alguno con fondo blanco (Juntos de Aventuras, Choque
    Rebelde) y WikiDex los de McDonald's: en la app saldría un rectángulo blanco. Sin Pillow, se da por bueno."""
    try:
        import io
        from PIL import Image
        img = Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception:
        return True
    w, h = img.size
    esquinas = [(1, 1), (w - 2, 1), (1, h - 2), (w - 2, h - 2)]
    return sum(img.getpixel(x)[3] > 250 for x in esquinas) < 3


def guardar(sid, data, lang=None):
    """Guarda un logo nuevo (en webp de ANCHO px como mucho si está Pillow) y devuelve su ruta en la rama."""
    try:
        import io
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        img.load()
        if img.width > ANCHO:
            img = img.resize((ANCHO, round(img.height * ANCHO / img.width)), Image.LANCZOS)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
        out = io.BytesIO()
        img.save(out, "WEBP", quality=88)
        data = out.getvalue()
    except Exception:
        pass   # sin Pillow (o una imagen rara): tal cual
    rel = archivo(sid + (f"@{lang}" if lang else ""), ext_of(data))
    with open(os.path.join(DATA, rel), "wb") as f:
        f.write(data)
    return rel


# ---------- en cada idioma ----------

def codigos_pokemon(sid, serie):
    """Cómo puede llamar pokemon.com a una expansión de TCGdex: «sv03.5» -> «sv_series/sv035»,
    «sm1» -> «sm_series/sm01», «sv06.5» -> «sv_series/sv6pt5», «me02.5» -> «me_series/me2pt5»."""
    if sid in POKEMON_MANUAL:
        return [POKEMON_MANUAL[sid]] if POKEMON_MANUAL[sid] else []
    m = re.match(r"^([a-z]+)0*(\d+)(\.5)?$", sid)
    if not m:
        return [f"{serie}_series/{sid}"]
    pre, n, half = m.group(1), int(m.group(2)), m.group(3)
    if half:
        names = [f"{pre}{n:02d}5", f"{pre}{n}pt5", f"{pre}{n}5"]
    else:
        names = [f"{pre}{n:02d}", f"{pre}{n}"]
    return [f"{serie}_series/{x}" for x in dict.fromkeys(names)]


def pokemon(code, lang):
    url = POKEMON.format(cms=POKEMON_CMS[lang], code=code, name=code.split("/")[-1], lang=lang)
    data = fetch(url)
    return (url, data) if ext_of(data) and transparente(data) else None


def existe_pokemon(code):
    """Si pokemon.com tiene esa expansión (su logo en inglés, aunque tenga fondo)."""
    return bool(ext_of(fetch(POKEMON.format(cms=POKEMON_CMS["en"], code=code, name=code.split("/")[-1], lang="en"))))


def wikidex_tabla():
    """Logos de expansiones de WikiDex: nombre normalizado -> título del archivo («Logo Dominio Delta (TCG).png»)."""
    out, cont = {}, {}
    while True:
        q = {"action": "query", "list": "allimages", "aiprefix": "Logo_", "ailimit": "500", "format": "json", **cont}
        try:
            d = get_json(WIKIDEX + "?" + urllib.parse.urlencode(q))
        except Exception as e:
            print(f"::warning::WikiDex: {e}")
            return out
        for i in d["query"]["allimages"]:
            m = re.match(r"^Logo_(.+)_\(TCG\)\.(png|jpg|webp)$", i["name"])
            if m:
                out[norm(m.group(1).replace("_", " "))] = i["name"]
        if "continue" not in d:
            return out
        cont = d["continue"]


def wikidex(nombre_archivo):
    """El logo de WikiDex, en miniatura de ANCHO px (los originales llegan a 4000 px)."""
    q = {"action": "query", "titles": "Archivo:" + nombre_archivo, "prop": "imageinfo", "iiprop": "url",
         "iiurlwidth": str(ANCHO), "format": "json"}
    try:
        pages = get_json(WIKIDEX + "?" + urllib.parse.urlencode(q))["query"]["pages"]
        info = next(iter(pages.values()))["imageinfo"][0]
    except Exception:
        return None
    for url in (info.get("thumburl"), info.get("url")):
        data = fetch(url) if url else None
        if ext_of(data):
            return (url, data) if transparente(data) else None
    return None


# Scrydex responde con el logo genérico de Pokémon a lo que no tiene: se reconoce por su huella.
GENERIC = set()


def scrydex(code):
    data = fetch(SCRYDEX.format(code))
    if ext_of(data) and hashlib.md5(data).hexdigest() not in GENERIC:
        return SCRYDEX.format(code), data
    return None


# ---------- japonesas ----------

def scrydex_jp_table():
    """Expansiones japonesas de Scrydex: código (sin «_ja» no: el del logo), nombre en inglés, cartas y fecha."""
    page = fetch(SCRYDEX_JP)
    if not page:
        return []
    s = page.decode("utf-8", "ignore")
    rows = re.findall(r'src="https://images\.scrydex\.com/pokemon/([^"/]+)-logo/logo" /></div><span[^>]*>([^<]*)</span>'
                      r'</div></td><td[^>]*><span[^>]*>([^<]*)</span></td><td[^>]*><span[^>]*>(\d+)</span></td>'
                      r'<td[^>]*><span[^>]*>([\d/]+)</span>', s)
    links = dict((code, path) for path, code in re.findall(r'href="(/pokemon/expansions/[^"/]+/([^"/]+))"', s))
    return [{"code": r[0], "name": html.unescape(r[1]), "total": int(r[3]), "date": r[4].replace("/", "-"),
             "page": "https://scrydex.com" + links[r[0]] if r[0] in links else None} for r in rows]


_paginas = {}
# Palabras del tipo de producto, que salen en las fichas de muchas expansiones: no sirven para reconocer una.
TIPOS_DE_SOBRE = {"拡張パック", "強化拡張パック", "強化パック", "ハイクラスパック", "スペシャルパック", "コンセプトパック",
                  "スターターセット", "スターターデッキ", "構築デッキ", "デッキビルドBOX", "プレミアムトレーナーボックス",
                  "コレクション", "ポケモンカードゲーム", "ポケモンカード"}


def nombre_en_ficha(fila, nombre_ja):
    """¿Sale el nombre japonés de la expansión en su ficha de Scrydex? (para no confundir dos que salieron el mismo día)."""
    if not fila["page"] or not nombre_ja:
        return False
    if fila["page"] not in _paginas:
        data = fetch(fila["page"])
        _paginas[fila["page"]] = data.decode("utf-8", "ignore") if data else ""
    page = _paginas[fila["page"]]
    if nombre_ja in page:
        return True
    # «強化パック ロストリンク»: basta con la parte propia del nombre («ロストリンク»), no la del tipo de sobre.
    partes = [p for p in re.split(r"[\s　・「」『』()（）]+", nombre_ja) if len(p) >= 3 and p not in TIPOS_DE_SOBRE]
    return any(p in page for p in partes)


def codigos_ja(tid):
    """Cómo llama Scrydex a una japonesa de TCGdex: «S12a» -> «swsh12a_ja», «SM1+» -> «sm1p_ja», «SV-P» -> «svp_ja»."""
    base = tid.lower().replace("-", "").replace("+", "p")
    out = [base + "_ja", tid.lower() + "_ja"]
    if re.match(r"^s\d", base):
        out.insert(0, "swsh" + base[1:] + "_ja")
    return list(dict.fromkeys(out))


def logo_ja(tid, tabla, detalle):
    for code in codigos_ja(tid):
        hit = scrydex(code)
        if hit:
            return hit
    if not detalle or not detalle.get("releaseDate"):
        return None
    fecha = dt.date.fromisoformat(detalle["releaseDate"][:10])
    total = (detalle.get("cardCount") or {}).get("total")
    oficial = (detalle.get("cardCount") or {}).get("official")

    def dias(f):
        try:
            return abs((dt.date.fromisoformat(f["date"]) - fecha).days)
        except ValueError:
            return 9999
    # Las fuentes no siempre dan el mismo día de salida: las de dos meses alrededor, de la más cercana en fecha y
    # número de cartas a la más lejana, y siempre comprobando que el nombre japonés sale en su ficha.
    mismos = sorted((f for f in tabla if dias(f) <= 60),
                    key=lambda f: (dias(f), f["total"] not in (total, oficial), abs(f["total"] - (total or 0))))
    for f in mismos:
        if nombre_en_ficha(f, detalle.get("name")):
            return scrydex(f["code"])
    return None


# ---------- de aquí ----------

def logo_es(sid, ficha, en_nombre, ptcg, serie):
    if sid in FIJOS:
        data = fetch(FIJOS[sid])
        if ext_of(data):
            return FIJOS[sid], data
    logo = (ficha or {}).get("logo")
    for url in ([logo + ".webp", logo + ".png"] if logo else []):
        data = fetch(url)
        if ext_of(data):
            return url, data
    return logo_en(sid, en_nombre, ptcg, serie)


def logo_en(sid, en_nombre, ptcg, serie):
    """El inglés (sin pokemon.com): TCGdex en inglés, pokemontcg.io o Scrydex."""
    url = f"https://assets.tcgdex.net/en/{serie}/{sid}/logo.webp"
    data = fetch(url)
    if ext_of(data):
        return url, data
    hit = ptcg.get(MANUAL.get(sid, "")) or ptcg.get(norm(en_nombre))
    if hit and hit.get("images", {}).get("logo"):
        data = fetch(hit["images"]["logo"])
        if ext_of(data):
            return hit["images"]["logo"], data
    for code in [MANUAL.get(sid), hit and hit["id"], sid]:
        if code:
            found = scrydex(code)
            if found:
                return found
    return None


def cargar_ptcg():
    """Expansiones de pokemontcg.io, por id y por nombre normalizado."""
    sets, page = [], 1
    while True:
        try:
            d = get_json(f"https://api.pokemontcg.io/v2/sets?page={page}&pageSize=250")
        except Exception:
            break
        sets += d["data"]
        if len(sets) >= d["totalCount"] or not d["data"]:
            break
        page += 1
    ptcg = {s["id"]: s for s in sets}
    ptcg.update({norm(s["name"]): s for s in sets})
    return ptcg


def main():
    hoy = dt.date.today().isoformat()
    os.makedirs(os.path.join(DATA, "logos"), exist_ok=True)
    path = os.path.join(DATA, "logos.json")
    prev = json.load(open(path)) if os.path.exists(path) else {"logos": {}, "info": {}}
    logos, info = prev.get("logos", {}), prev.get("info", {})

    # Los logos por idioma con fondo (no transparente), fuera: se vuelven a buscar hoy mismo en otra fuente.
    forzar = set()
    for lang, m in prev.get("idiomas", {}).items():
        for sid, rel in list(m.items()):
            f = os.path.join(DATA, rel)
            if os.path.exists(f) and not transparente(open(f, "rb").read()):
                del m[sid]
                prev.get("info_idiomas", {}).pop(f"{lang}:{sid}", None)
                forzar.add(sid)
                if logos.get(sid) == rel:   # `logos` era ese mismo: se busca otra vez el de siempre
                    logos.pop(sid)
                    info.pop(sid, None)
    if forzar:
        print(f"logos con fondo, quitados: {', '.join(sorted(forzar))}")

    # Todas las expansiones que se pueden añadir en la app y la web: las del índice y todas las de TCGdex (aquí y Japón).
    index = dict(json.load(open(os.path.join(DATA, "index", "cards.json")))["sets"])  # sid -> [nombre, serie, idioma]
    for lang, prefix in (("es", ""), ("ja", "ja-")):
        try:
            series = [x["id"] for x in get_json(f"{API}/{lang}/series")]
        except Exception as e:
            print(f"::warning::no se pudo leer la lista de series de TCGdex ({lang}): {e}")
            continue
        for serie in series:
            if serie == "tcgp":   # Pokémon TCG Pocket: no son cartas físicas
                continue
            try:
                for x in get_json(f"{API}/{lang}/series/{urllib.parse.quote(serie)}").get("sets", []):
                    index.setdefault(prefix + x["id"], [x.get("name") or x["id"], serie, lang])
            except Exception as e:
                print(f"::warning::serie {serie} ({lang}): {e}")
    GENERIC.add(hashlib.md5(fetch(SCRYDEX.format("no-existe-tradeo")) or b"").hexdigest())
    GENERIC.add(hashlib.md5(fetch(SCRYDEX.format("no-existe-tradeo_ja")) or b"").hexdigest())

    # Ya tienen el suyo (y el archivo está): no se tocan. Las demás (nuevas o aproximadas) se buscan.
    pendientes = [sid for sid in index
                  if not (sid in logos and not info.get(sid, {}).get("aprox") and os.path.exists(os.path.join(DATA, logos[sid])))]
    print(f"{len(index)} expansiones, {len(pendientes)} por buscar logo")

    ja = [sid for sid in pendientes if sid.startswith("ja-")]
    es = [sid for sid in pendientes if not sid.startswith("ja-")]
    tabla = scrydex_jp_table() if ja else []
    ptcg = cargar_ptcg() if es else {}

    def buscar(sid):
        nombre, serie = index[sid][0], index[sid][1]
        try:
            if sid.startswith("ja-"):
                tid = sid[3:]
                detalle = get_json(f"{API}/ja/sets/{urllib.parse.quote(tid)}")
                return sid, logo_ja(tid, tabla, detalle)
            ficha_path = os.path.join(DATA, "sets", f"{sid}.json")
            ficha = json.load(open(ficha_path)) if os.path.exists(ficha_path) else None
            try:
                en = get_json(f"{API}/en/sets/{urllib.parse.quote(sid)}").get("name")
            except Exception:
                en = nombre
            return sid, logo_es(sid, ficha, en, ptcg, serie)
        except Exception as e:
            print(f"::warning::logo de {sid}: {e}")
            return sid, None

    with ThreadPoolExecutor(WORKERS) as ex:
        found = dict(ex.map(buscar, pendientes))

    for sid, hit in found.items():
        if not hit:
            continue
        url, data = hit
        rel = archivo(sid, ext_of(data))
        with open(os.path.join(DATA, rel), "wb") as f:
            f.write(data)
        logos[sid] = rel
        info[sid] = {"src": url, "aprox": False, "at": hoy}

    # Las que siguen sin el suyo: el de la expansión principal de su serie (marcado como aproximado y se reintenta
    # cada día). Primero una hermana de la misma serie e idioma (no unas promos); si no, el logo de la serie en TCGdex
    # (las japonesas, el de su serie internacional: «PCG» es la de EX, «e» la de e-Card…).
    def real(s):
        return s in logos and not info.get(s, {}).get("aprox")

    serie_logo = {}

    def logo_de_serie(serie):
        if serie not in serie_logo:
            serie_logo[serie] = None
            try:
                url = get_json(f"{API}/en/series/{serie}").get("logo")
            except Exception:
                url = None
            data = fetch(url + ".webp") if url else None
            if ext_of(data):
                rel = archivo("serie:" + serie, ext_of(data))
                with open(os.path.join(DATA, rel), "wb") as f:
                    f.write(data)
                serie_logo[serie] = (rel, url + ".webp")
        return serie_logo[serie]

    for sid in index:
        if real(sid):
            continue
        nombre, serie, lang = index[sid]
        hermanas = [s for s in index if s != sid and index[s][1] == serie and index[s][2] == lang and real(s)]
        hermanas.sort(key=lambda s: ("promo" in index[s][0].lower(), norm(index[s][0]) != norm(serie), s))
        if hermanas:
            logos[sid] = logos[hermanas[0]]
            info[sid] = {"src": f"aprox:{hermanas[0]}", "aprox": True, "at": hoy}
            continue
        hit = logo_de_serie(SERIE_INTERNACIONAL.get(serie, serie) if lang == "ja" else serie)
        if hit:
            logos[sid] = hit[0]
            info[sid] = {"src": hit[1], "aprox": True, "at": hoy}

    # ---------- en cada idioma ----------
    idiomas = {lang: dict(prev.get("idiomas", {}).get(lang, {})) for lang in IDIOMAS}
    info_l, codigos = prev.get("info_idiomas", {}), prev.get("pokemon", {})
    vistas = prev.get("vistas", {})
    primera_vez = "idiomas" not in prev
    lunes = dt.date.today().weekday() == 0
    aqui = [sid for sid in index if not sid.startswith("ja-")]
    for sid in aqui:   # la primera vez, las que ya había cuentan como antiguas (solo se reintentan los lunes)
        vistas.setdefault(sid, "2000-01-01" if primera_vez else hoy)

    def falta(sid, lang):
        p = idiomas[lang].get(sid)
        return not (p and os.path.exists(os.path.join(DATA, p)))

    def reciente(sid):
        return (dt.date.today() - dt.date.fromisoformat(vistas[sid])).days <= 60

    # Lo que falta en algún idioma se busca cada día los dos primeros meses de la expansión (el español suele llegar
    # unos días más tarde que el inglés) y después los lunes (las antiguas en francés, alemán o italiano no van a salir).
    por_buscar = [sid for sid in aqui if any(falta(sid, lang) for lang in IDIOMAS)
                  and (primera_vez or lunes or reciente(sid) or sid in forzar)]
    print(f"logos por idioma: {len(por_buscar)} expansiones por buscar")
    wd = wikidex_tabla() if any(falta(sid, "es") for sid in por_buscar) else {}
    ptcg_l = ptcg or (cargar_ptcg() if por_buscar else {})

    def de_aqui(sid, *trozos):
        src = info.get(sid, {}).get("src", "")
        return sid in logos and not info.get(sid, {}).get("aprox") and any(t in src for t in trozos)

    def buscar_idiomas(sid):
        nombre, serie = index[sid][0], index[sid][1]
        code, res = codigos.get(sid), {}
        try:
            if not code:
                code = next((c for c in codigos_pokemon(sid, serie) if existe_pokemon(c)), None)
            for lang in IDIOMAS:
                if not falta(sid, lang):
                    continue
                hit = pokemon(code, lang) if code else None
                if not hit and lang == "es":
                    t = wd.get(norm(WIKIDEX_MANUAL.get(sid) or nombre))
                    hit = wikidex(t) if t else None
                    if not hit and de_aqui(sid, "assets.tcgdex.net/es/"):
                        hit = ("igual", logos[sid])
                if not hit and lang == "en":
                    if de_aqui(sid, "assets.tcgdex.net/en/", "pokemontcg.io", "scrydex.com"):
                        hit = ("igual", logos[sid])
                    else:
                        try:
                            en = get_json(f"{API}/en/sets/{urllib.parse.quote(sid)}").get("name") or nombre
                        except Exception:
                            en = nombre
                        hit = logo_en(sid, en, ptcg_l, serie)
                if hit:
                    res[lang] = hit
        except Exception as e:
            print(f"::warning::logos por idioma de {sid}: {e}")
        return sid, code, res

    with ThreadPoolExecutor(WORKERS) as ex:
        hechos = list(ex.map(buscar_idiomas, por_buscar))
    nuevos = defaultdict(int)
    for sid, code, res in hechos:
        if code:
            codigos[sid] = code
        for lang, (url, data) in res.items():
            if url == "igual":   # el de `logos` ya es de ese idioma: el mismo archivo
                idiomas[lang][sid] = data
                info_l[f"{lang}:{sid}"] = {"src": info[sid]["src"], "at": hoy}
            else:
                idiomas[lang][sid] = guardar(sid, data, lang)
                info_l[f"{lang}:{sid}"] = {"src": url, "at": hoy}
            nuevos[lang] += 1
    # `logos` (el de las versiones de la app sin idiomas), en las de aquí: el español.
    for sid in aqui:
        es_path = idiomas["es"].get(sid)
        if es_path and logos.get(sid) != es_path:
            logos[sid] = es_path
            info[sid] = {"src": info_l.get(f"es:{sid}", {}).get("src", ""), "aprox": False, "at": hoy}
        elif not es_path and info.get(sid, {}).get("aprox") and idiomas["en"].get(sid):
            # Sin el suyo pero con el inglés: mejor el inglés que el de su serie.
            logos[sid] = idiomas["en"][sid]
            info[sid] = {"src": info_l.get(f"en:{sid}", {}).get("src", ""), "aprox": False, "at": hoy}
    print("logos por idioma nuevos: " + (", ".join(f"{k} {v}" for k, v in nuevos.items()) or "ninguno") + "; "
          + ", ".join(f"{lang} {len(idiomas[lang])}" for lang in IDIOMAS) + f" de {len(aqui)}")

    # Archivos que ya no usa nadie, fuera.
    usados = set(logos.values()) | {p for d in idiomas.values() for p in d.values()}
    for name in os.listdir(os.path.join(DATA, "logos")):
        if f"logos/{name}" not in usados:
            os.remove(os.path.join(DATA, "logos", name))

    sin = sorted(s for s in index if s not in logos)
    aprox = sorted(s for s in index if info.get(s, {}).get("aprox"))
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"updated": hoy, "logos": dict(sorted(logos.items())), "info": dict(sorted(info.items())),
                   "idiomas": {lang: dict(sorted(d.items())) for lang, d in idiomas.items()},
                   "info_idiomas": dict(sorted(info_l.items())), "pokemon": dict(sorted(codigos.items())),
                   "vistas": dict(sorted(vistas.items()))}, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(index) - len(sin) - len(aprox)} con su logo, {len(aprox)} con el de su serie, {len(sin)} sin logo")
    if aprox:
        print(f"::warning::{len(aprox)} expansiones con el logo de su serie (se reintentará mañana): {', '.join(aprox)}")
    if sin:
        print(f"::warning::{len(sin)} expansiones sin logo: {', '.join(sin)}")


if __name__ == "__main__":
    main()
