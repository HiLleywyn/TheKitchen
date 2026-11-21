# TheKitchen

A brewing assistant that keeps its numbers honest. Beer, mead and wine: recipes,
batches, fermentation and racking records, inventory, purchases, and reference
notes that remember where they came from.

The point of the project is one rule, enforced in code rather than in good
intentions: **a value is never presented as stronger evidence than it is.**

- A hydrometer reading is `measured`, and carries the temperature it was taken at.
- An ABV is `estimated`, because ABV is always derived from two gravities. It is
  never stored or displayed as a measurement.
- Attenuation is `calculated` from measured gravities.
- A batch status you did not set yourself is `inferred`, and says so.
- Reference knowledge carries a source URL, or it does not get stored.

## Quick start

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"

python -m kitchen --port 8000
```

Open http://127.0.0.1:8000. The database is a single SQLite file (`kitchen.db`)
created on first run. Bind to `127.0.0.1` unless you have a reason not to: there
is no authentication, because this is a one-person tool.

## Tests

```bash
pytest
```

## What it does today

| Area | State |
| --- | --- |
| Recipes with ingredients | working |
| Batches, status, provenance | working |
| Hydrometer readings with temperature correction | working |
| Gravity, Plato, gravity points, blends | working |
| ABV and attenuation from readings | working |
| Racking and transfer log | working |
| Inventory | working |
| Purchases, invoices, spend by vendor | working |
| Reference notes with source URLs | working |
| Assistant tool registry (deterministic) | working |
| Conversational LLM front end | not wired up |
| Packaging, carbonation, water chemistry | not built |
| Multi-user, auth, sync | deliberately not built |

## Layout

```
src/kitchen/
  provenance.py   Value type: kind, method, source. Cannot be upgraded.
  brewing.py      Calculations, each returning a provenance-tagged Value.
  store.py        SQLite persistence, append-only readings, batch summary.
  schema.sql      Tables and the triggers that block edits to readings.
  tools.py        The deterministic tool surface for an assistant.
  api.py          FastAPI routes.
  static/         One page of vanilla JS, no build step.
tests/            Provenance invariants, brewing math, storage, HTTP.
docs/             Design notes and the provenance rules.
```

## Design notes

- [docs/DESIGN.md](docs/DESIGN.md): why this stack, and what it deliberately
  does not do.
- [docs/PROVENANCE.md](docs/PROVENANCE.md): the four kinds, and the cases that
  are easy to get wrong.

## License

MIT. See [LICENSE](LICENSE).
