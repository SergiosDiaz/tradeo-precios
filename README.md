# tradeo-precios

Historial diario de precios de Cardmarket (vía [TCGdex](https://tcgdex.dev)) de las cartas que colecciona el grupo en la app **Tradeo** y en la web del álbum.

- Cada hora, [`precios.yml`](.github/workflows/precios.yml) ejecuta [`scripts/recoger_precios.py`](scripts/recoger_precios.py):
  lee de Firebase (solo lectura) qué expansiones coleccionáis entre todos y, si una expansión aún no tiene el precio de hoy, añade el precio del día de cada carta a `history/<expansión>.json`.
  Así los precios se actualizan una vez al día y una expansión recién añadida se recoge en menos de una hora.
- La app y la web leen esos archivos desde `https://raw.githubusercontent.com/SergiosDiaz/tradeo-precios/main/history/<expansión>.json`.
- Para lanzarlo a mano: pestaña **Actions → Precios diarios → Run workflow**.

Formato de cada archivo:

```json
{
  "set": "30th",
  "updated": "2026-10-21T05:30:00Z",
  "dates": ["2026-10-21", "2026-10-22"],
  "cards": { "30th-001": [0.05, 0.06] },
  "latest": { "30th-001": [0.06, 0.05, 0.06, 0.08] }
}
```

`cards` tiene la tendencia de Cardmarket de cada día (en el mismo orden que `dates`, `null` si ese día no había precio).
`latest` tiene los precios de hoy: tendencia, media de 1 día, de 7 días y de 30 días.
