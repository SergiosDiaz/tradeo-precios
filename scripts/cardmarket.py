"""Corrige las cartas a las que TCGdex les pone el producto de Cardmarket de otra versión.

En expansiones recién salidas (y en bastantes antiguas) TCGdex le da a la versión secreta de una carta el producto de
Cardmarket de la normal: Growlithe 106/103 (Rara Ilustración) de Dominio Delta salía con el de Growlithe 018 (común),
así que su precio era 0,04 € en vez de 9 € y el enlace llevaba a la otra carta.

Se nota porque varias cartas de la misma expansión comparten producto. Cardmarket publica cada día su catálogo y su
guía de precios (archivos públicos, ver CATALOGO y GUIA): en el catálogo, cada versión de una carta es un producto
distinto con la misma «metacarta» (el mismo texto) y la misma expansión, y se dan de alta en el orden del número de
la carta. Así que, si un grupo de cartas con el mismo nombre comparte producto y en Cardmarket hay exactamente tantas
versiones como cartas, se reparten: la de número más bajo (la normal) se queda la versión más barata y las demás van
en el orden en que Cardmarket las dio de alta; y se les pone el precio de la guía de Cardmarket. Si no cuadra (Pico Legendario 096/097 son dos cartas y un solo producto), se deja como está.
"""
import datetime
import json
import time
import urllib.request
from collections import defaultdict

CATALOGO = "https://downloads.s3.cardmarket.com/productCatalog/productList/products_singles_6.json"
GUIA = "https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json"
UA = {"User-Agent": "tradeo-precios (https://github.com/SergiosDiaz/tradeo-precios)"}


class Catalogo:
    def __init__(self, productos, guia):
        self.producto = {p["idProduct"]: p for p in productos}
        self.versiones = defaultdict(list)   # (expansión, metacarta) -> productos, del más antiguo al más nuevo
        for p in productos:
            self.versiones[(p.get("idExpansion"), p.get("idMetacard"))].append(p["idProduct"])
        for v in self.versiones.values():
            v.sort()
        self.guia = {g["idProduct"]: g for g in guia}

    def precios(self, id_producto):
        """[tendencia, media 1 día, 7 días, 30 días] como los de TCGdex (normal y, si no hay, holo)."""
        g = self.guia.get(id_producto) or {}

        def pick(*keys):
            for k in keys:
                for clave in (k, f"{k}-holo"):
                    if g.get(clave):
                        return round(g[clave], 2)
            return None
        return [pick("trend", "avg30", "avg"), pick("avg1"), pick("avg7"), pick("avg30")]


def cargar():
    """Catálogo y guía de precios de Cardmarket, o None si no se pueden descargar (entonces no se corrige nada)."""
    error = None
    for intento in range(4):
        try:
            datos = []
            for url in (CATALOGO, GUIA):
                with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
                    datos.append(json.load(r))
            cat = Catalogo(datos[0]["products"], datos[1]["priceGuides"])
            print(f"Cardmarket: {len(cat.producto)} productos, {len(cat.guia)} precios")
            return cat
        except Exception as e:
            error = e
            time.sleep(30 * (intento + 1))
    print(f"::warning title=Cardmarket::no se pudo descargar su catálogo; las cartas corregidas se quedan con el "
          f"producto y el precio de ayer: {error}")
    return None


def _numero(c):
    n = c["num"]
    return (0, int(n), "") if n.isdigit() else (1, 0, n)


def _a_la_vez(cat, versiones):
    """Si Cardmarket dio de alta todas esas versiones con menos de un año de diferencia (las muy antiguas no tienen
    fecha, «0000-00-00»: valen si ninguna la tiene)."""
    fechas = [cat.producto[i].get("dateAdded", "")[:10] for i in versiones]
    conocidas = [f for f in fechas if f[:4].isdigit() and f[:4] != "0000"]
    if not conocidas:
        return True
    if len(conocidas) != len(fechas):
        return False
    try:
        dias = [datetime.date.fromisoformat(f) for f in conocidas]
    except ValueError:
        return False
    return (max(dias) - min(dias)).days <= 365


def corregir(set_id, cards, cat):
    """Reparte los productos repetidos de una expansión. Cambia las cartas (cm y precios) en el sitio y devuelve
    {id de carta: precios nuevos} de las que ha cambiado."""
    if not cat:
        return {}
    grupos = defaultdict(list)
    for c in cards:
        if c.get("cm"):
            grupos[c["cm"]].append(c)
    cambios, dudosos = {}, []
    for cm, grupo in grupos.items():
        if len(grupo) < 2:
            continue
        grupo.sort(key=_numero)
        p = cat.producto.get(cm)
        versiones = cat.versiones.get((p.get("idExpansion"), p.get("idMetacard")), []) if p else []
        # Solo con números normales: en las promos (SM04, SM76, SM81) o las variantes con letra (43a, RC9) la de número
        # más bajo no tiene por qué ser la normal.
        # Y solo si Cardmarket las dio de alta a la vez (menos de un año entre la primera y la última): un producto
        # añadido años después (Mareep 75/76 de sm8: 2018 y 2023) suele ser otra edición, no la carta que falta.
        if (len({c["name"] for c in grupo}) != 1 or len(versiones) != len(grupo)
                or not all(c["num"].isdigit() for c in grupo) or not _a_la_vez(cat, versiones)):
            dudosos.append("/".join(c["num"] for c in grupo))
            continue
        # La normal (la de número más bajo) se queda la versión más barata: en Eclipse Cósmico (sm12) Cardmarket dio
        # de alta las normales después de las secretas, y en orden el Pikachu 241 secreto se quedaba con el de 1 €.
        # Las demás, en el orden de Cardmarket (en Dominio Delta, la 138 Rara Ilustración Especial antes que la 141).
        barata = min(versiones, key=lambda i: (cat.precios(i)[0] is None, cat.precios(i)[0] or 0, i))
        versiones = [barata] + [i for i in versiones if i != barata]
        for c, nuevo in zip(grupo, versiones):
            if c["cm"] == nuevo:
                continue
            precios = cat.precios(nuevo)
            c["cm"] = nuevo
            c["price"], c["p1"], c["p7"], c["p30"] = precios
            cambios[c["id"]] = precios
    if cambios:
        print(f"{set_id}: {len(cambios)} cartas con el producto de Cardmarket de otra versión, corregidas")
    if dudosos:
        print(f"{set_id}: productos de Cardmarket repetidos sin corregir (no cuadran con Cardmarket): {', '.join(dudosos)}")
    return cambios
