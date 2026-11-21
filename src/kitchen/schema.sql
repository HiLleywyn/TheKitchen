-- TheKitchen schema. SQLite, single file, single user.
-- Readings are append-only: a correction is a new row, not an edit. The
-- triggers below make that a database rule rather than a convention.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS recipes (
    id             INTEGER PRIMARY KEY,
    name           TEXT NOT NULL,
    style          TEXT,
    batch_size_gal REAL,
    notes          TEXT,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recipe_ingredients (
    id              INTEGER PRIMARY KEY,
    recipe_id       INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    category        TEXT NOT NULL DEFAULT 'fermentable',
    amount          REAL NOT NULL,
    unit            TEXT NOT NULL,
    use_stage       TEXT,
    provenance_kind TEXT NOT NULL DEFAULT 'user_supplied',
    source          TEXT
);

CREATE TABLE IF NOT EXISTS batches (
    id            INTEGER PRIMARY KEY,
    recipe_id     INTEGER REFERENCES recipes(id),
    code          TEXT NOT NULL UNIQUE,
    name          TEXT,
    started_at    TEXT NOT NULL,
    volume_gal    REAL,
    status        TEXT,
    status_source TEXT NOT NULL DEFAULT 'inferred',
    notes         TEXT
);

CREATE TABLE IF NOT EXISTS readings (
    id              INTEGER PRIMARY KEY,
    batch_id        INTEGER NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
    taken_at        TEXT NOT NULL,
    kind            TEXT NOT NULL,
    amount          REAL NOT NULL,
    unit            TEXT NOT NULL,
    provenance_kind TEXT NOT NULL,
    method          TEXT,
    source          TEXT,
    note            TEXT,
    supersedes_id   INTEGER REFERENCES readings(id)
);

CREATE TABLE IF NOT EXISTS transfers (
    id          INTEGER PRIMARY KEY,
    batch_id    INTEGER NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
    occurred_at TEXT NOT NULL,
    from_vessel TEXT,
    to_vessel   TEXT,
    volume_gal  REAL,
    note        TEXT
);

CREATE TABLE IF NOT EXISTS inventory_items (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    category        TEXT NOT NULL DEFAULT 'other',
    amount          REAL NOT NULL DEFAULT 0,
    unit            TEXT NOT NULL DEFAULT 'each',
    provenance_kind TEXT NOT NULL DEFAULT 'user_supplied',
    source          TEXT,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS purchases (
    id           INTEGER PRIMARY KEY,
    vendor       TEXT NOT NULL,
    purchased_at TEXT NOT NULL,
    invoice_no   TEXT,
    total        REAL,
    currency     TEXT NOT NULL DEFAULT 'USD',
    source       TEXT
);

CREATE TABLE IF NOT EXISTS purchase_lines (
    id                INTEGER PRIMARY KEY,
    purchase_id       INTEGER NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
    inventory_item_id INTEGER REFERENCES inventory_items(id),
    description       TEXT NOT NULL,
    qty               REAL NOT NULL,
    unit              TEXT NOT NULL,
    unit_price        REAL,
    line_total        REAL
);

CREATE TABLE IF NOT EXISTS reference_notes (
    id           INTEGER PRIMARY KEY,
    title        TEXT NOT NULL,
    body         TEXT NOT NULL,
    source_url   TEXT,
    source_title TEXT,
    retrieved_at TEXT,
    license      TEXT
);

CREATE INDEX IF NOT EXISTS idx_readings_batch ON readings(batch_id, taken_at);
CREATE INDEX IF NOT EXISTS idx_transfers_batch ON transfers(batch_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_lines_purchase ON purchase_lines(purchase_id);

CREATE TRIGGER IF NOT EXISTS readings_no_update
BEFORE UPDATE ON readings
BEGIN
    SELECT RAISE(ABORT, 'readings are append-only: add a correcting reading instead');
END;

CREATE TRIGGER IF NOT EXISTS readings_no_delete
BEFORE DELETE ON readings
BEGIN
    SELECT RAISE(ABORT, 'readings are append-only: they cannot be deleted');
END;
