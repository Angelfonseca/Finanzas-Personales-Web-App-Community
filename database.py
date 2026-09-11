import sqlite3

DB_NAME = "finanzas.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Tabla de categorías (Ej: Comida, Sueldo, Transporte)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            tipo TEXT NOT NULL -- 'gasto' o 'ingreso'
        )
    """)
    
    # Tabla de transacciones (Los movimientos de dinero)
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
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Base de datos y tablas creadas exitosamente.")
