import sqlite3

DB_NAME = "finanzas.db"

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Tabla de categorías
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            tipo TEXT NOT NULL -- 'gasto' o 'ingreso'
        )
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
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Base de datos y tablas actualizadas con éxito.")
