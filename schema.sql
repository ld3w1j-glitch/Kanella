PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL COLLATE NOCASE, password_hash TEXT NOT NULL,
 name TEXT NOT NULL, phone TEXT NOT NULL, is_admin INTEGER NOT NULL DEFAULT 0 CHECK(is_admin IN (0,1)),
 points INTEGER NOT NULL DEFAULT 0 CHECK(points >= 0), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS services (id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL, price INTEGER NOT NULL CHECK(price>=0), duration INTEGER NOT NULL CHECK(duration>0 AND duration%30=0));
CREATE TABLE IF NOT EXISTS products (id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL, price INTEGER NOT NULL CHECK(price>=0), category TEXT NOT NULL, stock INTEGER NOT NULL CHECK(stock>=0));
CREATE TABLE IF NOT EXISTS product_images (product_id TEXT PRIMARY KEY REFERENCES products(id) ON DELETE CASCADE, image BLOB NOT NULL, digest TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS archived_catalog (kind TEXT NOT NULL CHECK(kind IN ('service','product')), item_id TEXT NOT NULL, PRIMARY KEY(kind,item_id));
CREATE TABLE IF NOT EXISTS loyalty_settings (id INTEGER PRIMARY KEY CHECK(id=1), earn_amount INTEGER NOT NULL DEFAULT 1000, points_required INTEGER NOT NULL DEFAULT 100, discount_percent INTEGER NOT NULL DEFAULT 10);
INSERT OR IGNORE INTO loyalty_settings(id) VALUES(1);
CREATE TABLE IF NOT EXISTS pix_settings (id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)), pix_key TEXT NOT NULL DEFAULT '', name TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '');
INSERT OR IGNORE INTO pix_settings(id) VALUES(1);
CREATE TABLE IF NOT EXISTS bookings (
 id TEXT PRIMARY KEY, token TEXT NOT NULL UNIQUE, user_id TEXT REFERENCES users(id), date TEXT NOT NULL, time TEXT NOT NULL,
 name TEXT NOT NULL, phone TEXT NOT NULL, services TEXT NOT NULL, total INTEGER NOT NULL, duration INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','confirmed','rejected','completed','cancelled')),
 payment TEXT NOT NULL DEFAULT 'local', paid INTEGER NOT NULL DEFAULT 0, notification_status TEXT NOT NULL DEFAULT 'manual',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS bookings_user ON bookings(user_id);
CREATE TABLE IF NOT EXISTS booking_slots (date TEXT NOT NULL,time TEXT NOT NULL,booking_id TEXT NOT NULL REFERENCES bookings(id),PRIMARY KEY(date,time));
CREATE TABLE IF NOT EXISTS booking_cancellation_notifications (
 booking_id TEXT PRIMARY KEY REFERENCES bookings(id), status TEXT NOT NULL CHECK(status IN ('pending','accepted','failed','unconfigured'))
);
CREATE TABLE IF NOT EXISTS orders (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), items TEXT NOT NULL, subtotal INTEGER NOT NULL,
 discount INTEGER NOT NULL, total INTEGER NOT NULL, points_spent INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','pickedup','cancelled')),created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1),name TEXT NOT NULL DEFAULT 'Kanella Barber Shop',whatsapp TEXT NOT NULL DEFAULT '');
INSERT OR IGNORE INTO settings(id) VALUES(1);
CREATE TABLE IF NOT EXISTS rate_limits (key TEXT PRIMARY KEY, count INTEGER NOT NULL, reset_at REAL NOT NULL);
