import sqlite3

DB_NAME = "finanzas.db"

def get_db():
    conn = sqlite3.connect(DB_NAME, timeout=15.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    
    # Tabla de categorías
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            tipo TEXT NOT NULL -- 'gasto' o 'ingreso'
        )
    """)

    # Categoría por defecto para integridad referencial
    cursor.execute("""
        INSERT OR IGNORE INTO categorias (id, nombre, tipo)
        VALUES (1, 'General', 'gasto')
    """)
    
    # Tabla de transacciones
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transacciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            monto REAL NOT NULL,
            tipo TEXT NOT NULL, -- 'gasto' o 'ingreso'
            categoria_id INTEGER,
            descripcion TEXT,
            FOREIGN KEY (categoria_id) REFERENCES categorias (id)
        )
    """)
    
    # Tabla de apartados (Sobres libres y metas)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS apartados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            tipo TEXT CHECK(tipo IN ('libre', 'meta')) NOT NULL,
            monto_actual REAL NOT NULL DEFAULT 0.0,
            meta_monto REAL DEFAULT NULL,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabla de inversiones (Fase 7: ETFs, Tickers y Portafolio)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inversiones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL UNIQUE,
            cantidad REAL NOT NULL,
            precio_promedio REAL NOT NULL,
            precio_actual REAL NOT NULL,
            moneda TEXT NOT NULL DEFAULT 'USD',
            actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Migración segura: agregar columna 'moneda' si la tabla ya existía sin ella
    try:
        cursor.execute("ALTER TABLE inversiones ADD COLUMN moneda TEXT NOT NULL DEFAULT 'USD'")
    except sqlite3.OperationalError:
        pass

    # Corregir tickers de la Bolsa Mexicana (.MX) que por defecto se asignaron a USD
    try:
        cursor.execute("UPDATE inversiones SET moneda = 'MXN' WHERE (ticker LIKE '%.MX' OR ticker LIKE '%.mx') AND moneda = 'USD'")
    except sqlite3.OperationalError:
        pass
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Base de datos y tablas actualizadas con éxito.")
