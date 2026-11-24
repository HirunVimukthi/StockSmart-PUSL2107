PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin','manager','warehouse','cashier','customer')),
    is_locked INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS products (
    sku TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    stock_qty INTEGER NOT NULL DEFAULT 0,
    reorder_threshold INTEGER NOT NULL DEFAULT 0,
    shelf_location TEXT NOT NULL,
    unit_price REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER,
    order_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    total_amount REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(customer_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    FOREIGN KEY(order_id) REFERENCES orders(id),
    FOREIGN KEY(sku) REFERENCES products(sku)
);

CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    contact_encrypted TEXT,
    email TEXT
);

CREATE TABLE IF NOT EXISTS purchase_quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL,
    supplier_id INTEGER NOT NULL,
    requested_qty INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(sku) REFERENCES products(sku),
    FOREIGN KEY(supplier_id) REFERENCES suppliers(id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT NOT NULL,
    sku TEXT,
    qty_change INTEGER,
    flagged_anomaly INTEGER NOT NULL DEFAULT 0,
    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

INSERT OR IGNORE INTO users (id, full_name, email, password_hash, role) VALUES
 (1, 'Alice Admin', 'admin@stocksmart.local', '$2b$12$stocksmart-placeholder', 'admin'),
 (2, 'Mason Manager', 'manager@stocksmart.local', '$2b$12$stocksmart-placeholder', 'manager'),
 (3, 'Wendy Warehouse', 'warehouse@stocksmart.local', '$2b$12$stocksmart-placeholder', 'warehouse'),
 (4, 'Charlie Cashier', 'cashier@stocksmart.local', '$2b$12$stocksmart-placeholder', 'cashier'),
 (5, 'Casey Customer', 'customer@stocksmart.local', '$2b$12$stocksmart-placeholder', 'customer');

INSERT OR IGNORE INTO products (sku, name, category, stock_qty, reorder_threshold, shelf_location, unit_price) VALUES
 ('MLK-001', 'Fresh Milk 1L', 'Dairy', 48, 20, 'A-01-02', 3.49),
 ('BRD-001', 'Whole Wheat Bread', 'Bakery', 35, 15, 'B-02-01', 2.99),
 ('EGG-012', 'Free Range Eggs 12', 'Dairy', 24, 12, 'A-02-03', 5.49),
 ('APL-001', 'Royal Gala Apples 1kg', 'Produce', 60, 25, 'C-01-01', 4.25),
 ('RCE-500', 'Basmati Rice 500g', 'Pantry', 18, 10, 'D-03-04', 2.75),
 ('COK-330', 'Cola 330ml', 'Beverages', 72, 30, 'E-01-02', 1.49),
 ('CHP-200', 'Sea Salt Chips 200g', 'Snacks', 22, 12, 'F-04-01', 3.25),
 ('SOAP-01', 'Hand Soap 250ml', 'Household', 40, 15, 'G-02-03', 2.20);

INSERT OR IGNORE INTO suppliers (id, name, contact_encrypted, email) VALUES
 (1, 'GreenFields Dairy', 'ENCRYPTED_AT_STARTUP', 'orders@greenfields.example'),
 (2, 'Harvest Bread Co.', 'ENCRYPTED_AT_STARTUP', 'supply@harvest.example'),
 (3, 'Prime Produce Wholesale', 'ENCRYPTED_AT_STARTUP', 'trade@primeproduce.example'),
 (4, 'Global Pantry Distributors', 'ENCRYPTED_AT_STARTUP', 'quotes@globalpantry.example');

INSERT OR IGNORE INTO purchase_quotes (id, sku, supplier_id, requested_qty, status) VALUES
 (1, 'RCE-500', 4, 30, 'pending'),
 (2, 'EGG-012', 1, 24, 'approved');
