-- Initial schema: parts, MPN options, supplier offers, designs, usage, tags,
-- full-text search, and the view that KiCad's .kicad_dbl file points at.

CREATE TABLE manufacturers (
  id   INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE
);

CREATE TABLE categories (
  id         INTEGER PRIMARY KEY,
  name       TEXT NOT NULL UNIQUE,           -- 'Resistor', 'Capacitor', 'IC - MCU'
  ipn_prefix TEXT NOT NULL UNIQUE,           -- 'RES', 'CAP', 'ICM'
  next_seq   INTEGER NOT NULL DEFAULT 1      -- counter for IPNs; never decremented, so IPNs are never reused
);

CREATE TABLE parts (
  id            INTEGER PRIMARY KEY,
  ipn           TEXT NOT NULL UNIQUE,        -- internal part number, e.g. RES-0001
  category_id   INTEGER NOT NULL REFERENCES categories(id),
  description   TEXT NOT NULL,
  value         TEXT,                        -- '10k', '100nF'
  package       TEXT,                        -- '0402', 'SOT-23-5'
  attributes    TEXT NOT NULL DEFAULT '{}',  -- JSON object: tolerance, voltage, power, dielectric
  symbol_ref    TEXT NOT NULL,               -- 'Device:R'
  footprint_ref TEXT NOT NULL,               -- 'Resistor_SMD:R_0402_1005Metric'
  datasheet_url TEXT,
  lifecycle     TEXT NOT NULL DEFAULT 'active'
                CHECK (lifecycle IN ('active', 'nrnd', 'eol', 'obsolete')),
  preferred     INTEGER NOT NULL DEFAULT 0,
  notes         TEXT,
  created_at    TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE mpn_options (
  id              INTEGER PRIMARY KEY,
  part_id         INTEGER NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
  manufacturer_id INTEGER NOT NULL REFERENCES manufacturers(id),
  mpn             TEXT NOT NULL,
  rank            INTEGER NOT NULL DEFAULT 1,  -- 1 = primary source, 2+ = alternates
  UNIQUE (manufacturer_id, mpn)
);
CREATE INDEX idx_mpn_options_part ON mpn_options(part_id);
CREATE INDEX idx_mpn_options_mpn ON mpn_options(mpn);

CREATE TABLE suppliers (
  id   INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE                  -- 'DigiKey', 'Mouser'
);

CREATE TABLE offers (                        -- cache, refreshed by the supplier sync job
  id            INTEGER PRIMARY KEY,
  mpn_option_id INTEGER NOT NULL REFERENCES mpn_options(id) ON DELETE CASCADE,
  supplier_id   INTEGER NOT NULL REFERENCES suppliers(id),
  spn           TEXT NOT NULL,
  stock         INTEGER,
  price_breaks  TEXT,                        -- JSON array of {qty, usd}
  fetched_at    TEXT NOT NULL,
  UNIQUE (supplier_id, spn)
);

CREATE TABLE designs (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  revision    TEXT NOT NULL,
  designed_on TEXT,
  repo_url    TEXT,
  UNIQUE (name, revision)
);

CREATE TABLE design_usage (
  design_id INTEGER NOT NULL REFERENCES designs(id) ON DELETE CASCADE,
  part_id   INTEGER NOT NULL REFERENCES parts(id),
  qty       INTEGER NOT NULL,
  refdes    TEXT,                            -- 'R1,R2,R7'
  notes     TEXT,
  PRIMARY KEY (design_id, part_id)
);
CREATE INDEX idx_design_usage_part ON design_usage(part_id);

CREATE TABLE tags (
  id   INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE
);

CREATE TABLE part_tags (
  part_id INTEGER NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
  tag_id  INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY (part_id, tag_id)
);

-- Full-text search over the fields the plugin searches by.
CREATE VIRTUAL TABLE parts_fts USING fts5(
  ipn, description, value, package, content='parts', content_rowid='id'
);

CREATE TRIGGER parts_ai AFTER INSERT ON parts BEGIN
  INSERT INTO parts_fts(rowid, ipn, description, value, package)
  VALUES (new.id, new.ipn, new.description, new.value, new.package);
END;

CREATE TRIGGER parts_ad AFTER DELETE ON parts BEGIN
  INSERT INTO parts_fts(parts_fts, rowid, ipn, description, value, package)
  VALUES ('delete', old.id, old.ipn, old.description, old.value, old.package);
END;

CREATE TRIGGER parts_au AFTER UPDATE ON parts BEGIN
  INSERT INTO parts_fts(parts_fts, rowid, ipn, description, value, package)
  VALUES ('delete', old.id, old.ipn, old.description, old.value, old.package);
  INSERT INTO parts_fts(rowid, ipn, description, value, package)
  VALUES (new.id, new.ipn, new.description, new.value, new.package);
END;

-- The one object the KiCad .kicad_dbl file points at.
CREATE VIEW kicad_parts AS
SELECT p.ipn           AS ipn,
       p.symbol_ref    AS symbol,
       p.footprint_ref AS footprint,
       p.value         AS value,
       p.description   AS description,
       p.datasheet_url AS datasheet,
       c.name          AS category,
       p.lifecycle     AS lifecycle,
       m.name          AS manufacturer,
       mo.mpn          AS mpn
FROM parts p
JOIN categories c ON c.id = p.category_id
LEFT JOIN mpn_options mo ON mo.part_id = p.id AND mo.rank = 1
LEFT JOIN manufacturers m ON m.id = mo.manufacturer_id;
