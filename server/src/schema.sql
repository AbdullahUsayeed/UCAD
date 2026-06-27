CREATE TABLE IF NOT EXISTS licenses (
    key TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    payer_name TEXT DEFAULT '',
    txn_id TEXT UNIQUE,
    max_activations INTEGER DEFAULT 3,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT
);

CREATE TABLE IF NOT EXISTS activations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    license_key TEXT NOT NULL,
    machine_id TEXT NOT NULL,
    machine_name TEXT DEFAULT '',
    activated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (license_key) REFERENCES licenses(key)
);

CREATE INDEX IF NOT EXISTS idx_activations_key ON activations(license_key);
CREATE INDEX IF NOT EXISTS idx_activations_machine ON activations(machine_id);
CREATE INDEX IF NOT EXISTS idx_licenses_txn ON licenses(txn_id);
