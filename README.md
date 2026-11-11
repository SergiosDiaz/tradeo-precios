# tradeo-precios

Precios diarios de Cardmarket (las cartas, de [TCGdex](https://tcgdex.dev)) de **todas** las cartas Pokémon TCG en español y en japonés, para la app **Tradeo** y la web del álbum.

- Cada día de madrugada, [`precios.yml`](.github/workflows/precios.yml) ejecuta [`scripts/recoger_precios.py`](scripts/recoger_precios.py):
  recorre las expansiones en español (unas 150, 17.000 cartas) y después las japonesas (unas 190, 18.000 cartas), con pocas peticiones a la vez para no cargar TCGdex,
  guarda la ficha de cada expansión, añade el precio del día de cada carta a su historial y genera el índice de búsqueda.
- Primero lo descarga todo y después publica **lo que ha ido bien**. Si una expansión falla (no se puede descargar tras
  varios intentos, o llega sin los precios que tenía ayer porque TCGdex la sirve a medio actualizar), esa expansión se
  queda con los datos del día anterior y sale un aviso en la ejecución de GitHub. Si falla más del 20 % de las
  expansiones (TCGdex caído), no se publica nada y la ejecución termina con error.
- **Precios: directamente de Cardmarket.** TCGdex no tiene precios propios: copia la guía de precios que Cardmarket
  publica cada día, pero a veces con uno o más días de retraso o a medio actualizar. Así que el robot descarga el
  catálogo y la guía de precios públicos de Cardmarket ([`scripts/cardmarket.py`](scripts/cardmarket.py)) y pone el
  precio de cada carta desde ahí (tendencia, media de 1, 7 y 30 días). TCGdex se usa para saber qué cartas hay (número,
  nombre, rareza, imagen) y qué producto de Cardmarket es cada una. Si un día no se puede descargar Cardmarket, se usan
  los precios de TCGdex, y las cartas que el robot había corregido o enlazado se quedan con su producto y precio de ayer.
  - TCGdex a veces le pone a la versión secreta de una carta el producto de la normal (Growlithe 106 de Dominio Delta
    salía con el de la 018: 0,04 € en vez de 9 €). Cuando varias cartas con el mismo nombre comparten producto y en
    Cardmarket hay tantas versiones como cartas, la normal se queda la más barata y las demás van en el orden de
    Cardmarket. Si no cuadra, se deja como está y sale en el registro. El historial de una carta que cambia de producto
    se empieza de cero (lo de antes era el precio de otra carta).
  - Y a unas 800 cartas no les pone producto (Disposición del Profesor Oak 201 y 233 de Eclipse Cósmico). Se buscan por
    su nombre en inglés entre los productos de esa expansión en Cardmarket que no tienen carta: solo si hay tantos como
    cartas, son versiones de la misma carta y se dieron de alta a la vez que el resto de la expansión (unas 150 cartas).
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

`logos.json` y `logos/`: el logo de cada expansión (todas las de TCGdex, aquí y en Japón), descargado y guardado en la
propia rama para no depender de la fuente (ver [`scripts/logos.py`](scripts/logos.py)). `logos.json` = `{"logos": {"swsh8":
"logos/swsh8-1a2b3c.webp"}, "info": {"swsh8": {"src": "...", "aprox": false}}}`. Las japonesas salen de Scrydex; las que
no tienen el suyo en ninguna parte llevan el de su serie (`aprox`) y se vuelven a buscar cada día. Las expansiones nuevas
lo cogen solas al día siguiente de salir en TCGdex.

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
Después puede venir el nombre en español (solo en las japonesas; `null` en las demás) y, si es distinto, el nombre en inglés, que la cámara usa para reconocer las cartas impresas en inglés.
`sets` da el nombre de cada expansión, su serie y el idioma de los datos (`en` si TCGdex no la tiene en español, `ja` en las japonesas). Las cartas sueltas que TCGdex no tiene en español se publican en inglés.

`index/nombres.json`: el nombre de cada carta en inglés, francés, alemán, italiano y portugués, solo los distintos del índice, para reconocerla con la cámara y buscarla en cualquier idioma:

```json
{ "sv07-166": { "en": "Lacey", "fr": "Taro", "de": "Tara", "it": "Rupi", "pt": "Tarsila" } }
```

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

Los precios son la tendencia general de Cardmarket (mezcla todos los idiomas y estados), también directamente de su guía.
