# tradeo-precios

Precios diarios de Cardmarket (vía [TCGdex](https://tcgdex.dev)) de **todas** las cartas Pokémon TCG en español, para la app **Tradeo** y la web del álbum.

- Cada día de madrugada, [`precios.yml`](.github/workflows/precios.yml) ejecuta [`scripts/recoger_precios.py`](scripts/recoger_precios.py):
  recorre las 145 expansiones en español (unas 17.000 cartas, con pocas peticiones a la vez para no cargar TCGdex),
  guarda la ficha de cada expansión, añade el precio del día de cada carta a su historial y genera el índice de búsqueda.
- Primero lo descarga todo; solo si **no ha fallado nada** escribe y publica. Si una expansión o una carta no se puede
  descargar tras varios intentos, el robot termina con error y los datos del día anterior se quedan como estaban.
- Los datos se publican en la rama [`data`](https://github.com/SergiosDiaz/tradeo-precios/tree/data), que se reescribe cada día como un único commit: así el repositorio no crece guardando versiones antiguas.
- Para lanzarlo a mano: pestaña **Actions → Precios diarios → Run workflow**.

## Archivos (rama `data`)

`sets/<expansión>.json`: ficha completa de una expansión (nombre, logo, cartas con número, nombre, rareza, tipo, imágenes,
ilustrador y precios de hoy), en el mismo formato que usan la app y la web. Así abrir un álbum por primera vez es
descargar un solo archivo en vez de hacer cientos de peticiones a TCGdex.

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

Cada carta: id, expansión, número, nombre, rareza, precio de hoy y `1` si TCGdex tiene su imagen.
`sets` da el nombre de cada expansión, su serie y el idioma de los datos (`en` si TCGdex no la tiene en español).

Los precios son la tendencia general de Cardmarket (mezcla todos los idiomas y estados).
