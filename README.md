# tradeo-precios

Precios diarios de Cardmarket (vía [TCGdex](https://tcgdex.dev)) de **todas** las cartas Pokémon TCG en español y en japonés, para la app **Tradeo** y la web del álbum.

- Cada día de madrugada, [`precios.yml`](.github/workflows/precios.yml) ejecuta [`scripts/recoger_precios.py`](scripts/recoger_precios.py):
  recorre las expansiones en español (unas 150, 17.000 cartas) y después las japonesas (unas 190, 18.000 cartas), con pocas peticiones a la vez para no cargar TCGdex,
  guarda la ficha de cada expansión, añade el precio del día de cada carta a su historial y genera el índice de búsqueda.
- Primero lo descarga todo y después publica **lo que ha ido bien**. Si una expansión falla (no se puede descargar tras
  varios intentos, o llega sin los precios que tenía ayer porque TCGdex la sirve a medio actualizar), esa expansión se
  queda con los datos del día anterior y sale un aviso en la ejecución de GitHub. Si falla más del 20 % de las
  expansiones (TCGdex caído), no se publica nada y la ejecución termina con error.
- Los datos se publican en la rama [`data`](https://github.com/SergiosDiaz/tradeo-precios/tree/data), que se reescribe cada día como un único commit: así el repositorio no crece guardando versiones antiguas.
- Para lanzarlo a mano: pestaña **Actions → Precios diarios → Run workflow**.

## Archivos (rama `data`)

`sets/<expansión>.json`: ficha completa de una expansión (nombre, logo, cartas con número, nombre, rareza, tipo, imágenes,
ilustrador y precios de hoy), en el mismo formato que usan la app y la web. Así abrir un álbum por primera vez es
descargar un solo archivo en vez de hacer cientos de peticiones a TCGdex.

`imagenes.json`: imagen encontrada fuera de TCGdex para las cartas que TCGdex no tiene (ver [`scripts/imagenes.py`](scripts/imagenes.py)):
oficial en español de pokemon.com, Limitless, TCGdex en inglés, pokemontcg.io (las japonesas, Limitless en japonés) o, como último recurso, la de otra
versión de la misma carta (marcada como provisional con `approx`). Se guarda para no repetir la búsqueda; las
provisionales se vuelven a mirar cada día por si ya ha salido la buena. También comprueba (una vez por carta) que existen
de verdad las imágenes que TCGdex dice tener; las que no, se buscan igual que las demás.

`history/<expansión>.json`: historial de precios de una expansión.

```json
{
  "set": "30th",
  "updated": "2026-10-22T02:30:00Z",
  "dates": ["2026-10-21", "2026-10-22"],
  "cards": { "30th-001": [0.05, 0.06] },
  "latest": { "30th-001": [0.06, 0.05, 0.06, 0.08] }
}
```

`cards` tiene la tendencia de Cardmarket de cada día (en el mismo orden que `dates`, `null` si ese día no había precio).
`latest` tiene los precios de hoy: tendencia, media de 1 día, de 7 días y de 30 días.

`index/cards.json`: índice de búsqueda con todas las cartas.

```json
{
  "updated": "2026-10-22",
  "sets": { "30th": ["Celebración 30.º Aniversario", "me", "es"] },
  "cards": [["30th-001", "30th", "001", "Exeggcute", "Común", 0.05, 1]]
}
```

Cada carta: id, expansión, número, nombre, rareza, precio de hoy e imagen: `1` si TCGdex la tiene, la URL si se ha encontrado en otro sitio (con `~` delante si es provisional), `0` si no hay ninguna.
`sets` da el nombre de cada expansión, su serie y el idioma de los datos (`en` si TCGdex no la tiene en español, `ja` en las japonesas).

## Expansiones japonesas

Son las que TCGdex tiene en japonés (las nuevas, como «ストームエメラルダ», entran solas en cuanto TCGdex las publica).
Llevan `ja-` delante del id de TCGdex, también sus cartas (`ja-M6`, `ja-M6-001`), para no chocar con las de aquí
(TCGdex usa `neo1` en los dos idiomas, y `SM9`/`sm9` serían el mismo archivo en un disco que no distingue mayúsculas).

Cada expansión japonesa lleva su nombre de aquí (en inglés, como se conoce fuera: «Storm Emeralda», «Mega Dream ex»;
el japonés se queda en `nameJa`). Salen de [Limitless](https://limitlesstcg.com/cards/jp), que tiene las japonesas con el
mismo código que TCGdex; las antiguas y las de promos, de una tabla en el script. Se publican en `index/nombres_ja.json`
(`sets`: código → nombre; `series`: serie → nombre de aquí), que también usa la app.

Los nombres de las cartas vienen en japonés. Para poder buscarlas, cada carta de Pokémon lleva en su ficha (`alias`) y como 8.º
campo del índice el nombre en español de su Pokémon («ヘラクロス» → «Heracross», «ヒートロトムex» → «Rotom ex»).
Sale de `index/pokedex.json` (número de la Pokédex → nombre en español), que el robot rellena con las cartas en español.

Las imágenes son las de TCGdex en japonés; si TCGdex aún no la tiene (expansiones recién salidas), la de otra versión
japonesa de la misma carta, marcada como provisional.

Los precios son la tendencia general de Cardmarket (mezcla todos los idiomas y estados).
