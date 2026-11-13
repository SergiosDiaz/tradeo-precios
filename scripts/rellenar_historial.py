#!/usr/bin/env python3
"""Rellena hacia atrás el historial de precios con las guías de Cardmarket que guardó archive.org.

Cardmarket solo publica la guía del día (price_guide_6.json se sobrescribe cada mañana), así que el robot solo tiene
historial desde que empezó (21/10/2026). archive.org (la Wayback Machine) guardó copias de esa misma guía muchos días
antes. Este script las descarga y, para cada carta, pone el precio de ese día según su producto de Cardmarket de hoy
(`cm` en sets/<expansión>.json), igual que hace el robot cada mañana (cardmarket.Catalogo.precios: la tendencia).

- Los días que no estaban en el historial se añaden (en orden).
- Los días que ya estaban se corrigen con la guía de ese día si la carta sale en ella: hasta el 11/11/2026 el precio
  venía de TCGdex, que a veces se quedaba días sin actualizar una carta (el Mew B/RGB del 30.º, a 2180,28 € del 29/10
  al 11/11).
Solo se usan las guías desde el 1/9/2026 (la de junio es suelta y daría una recta de tres meses en la gráfica).

Uso:  python3 scripts/rellenar_historial.py <carpeta de datos> <carpeta para guardar las guías descargadas>
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from cardmarket import Catalogo  # noqa: E402

GUIA = "https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json"
CDX = "https://web.archive.org/cdx/search/cdx?url=" + GUIA.split("://")[1] + "&output=json&from=20260901&filter=statuscode:200"
UA = {"User-Agent": "tradeo-precios (https://github.com/SergiosDiaz/tradeo-precios)"}
DESDE = "2026-09-01"


def get(url, intentos=5):
    for i in range(intentos):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
                return r.read()
        except Exception as e:
            if i == intentos - 1:
                raise
            print(f"  reintento ({e})")
            time.sleep(15 * (i + 1))


def guias(cache):
    """{día: {idProduct: precio}} de todas las copias de archive.org (una por día, la de createdAt)."""
    filas = json.loads(get(CDX))[1:]
    out = {}
    for fila in filas:
        ts = fila[1]
        f = os.path.join(cache, f"{ts}.json")
        if not os.path.exists(f):
            print(f"descargando la copia {ts}")
            try:
                d = json.loads(get(f"https://web.archive.org/web/{ts}id_/{GUIA}"))
            except Exception as e:
                print(f"  no se pudo: {e}")
                continue
            cat = Catalogo([], d["priceGuides"])
            precios = {pid: cat.precios(pid)[0] for pid in cat.guia}
            with open(f, "w") as fh:
                json.dump({"createdAt": d.get("createdAt", ""), "precios": {str(k): v for k, v in precios.items() if v is not None}}, fh)
            time.sleep(2)
        g = json.load(open(f))
        dia = g["createdAt"][:10]
        if dia >= DESDE:
            out[dia] = {int(k): v for k, v in g["precios"].items()}
    return out


def main():
    data, cache = sys.argv[1], sys.argv[2]
    os.makedirs(cache, exist_ok=True)
    por_dia = guias(cache)
    print(f"{len(por_dia)} días de guía: {min(por_dia)} … {max(por_dia)}")
    nuevos_total = corregidos_total = 0
    for nombre in sorted(os.listdir(os.path.join(data, "history"))):
        sid = nombre[:-5]
        hpath = os.path.join(data, "history", nombre)
        spath = os.path.join(data, "sets", nombre)
        if not os.path.exists(spath):
            continue
        cm = {c["id"]: c["cm"] for c in json.load(open(spath)).get("cards", []) if c.get("cm")}
        if not cm:
            continue
        h = json.load(open(hpath))
        dates, cards = h["dates"], h["cards"]
        # Columna de cada día, con los días nuevos en su sitio.
        todos = sorted(set(dates) | set(por_dia))
        viejo = {d: i for i, d in enumerate(dates)}
        nuevas = {}
        for cid in set(cards) | set(cm):
            serie = cards.get(cid, [])
            fila = []
            for d in todos:
                v = serie[viejo[d]] if d in viejo and viejo[d] < len(serie) else None
                g = por_dia.get(d, {}).get(cm.get(cid)) if cid in cm else None
                if g is not None and v != g:
                    if d in viejo:
                        corregidos_total += 1
                    else:
                        nuevos_total += 1
                    v = g
                fila.append(v)
            if any(x is not None for x in fila):
                nuevas[cid] = fila
        h["dates"], h["cards"] = todos, nuevas
        with open(hpath + ".tmp", "w", encoding="utf-8") as f:
            json.dump(h, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        os.replace(hpath + ".tmp", hpath)
    print(f"precios añadidos (días nuevos): {nuevos_total}; corregidos (días que ya estaban): {corregidos_total}")


if __name__ == "__main__":
    main()
