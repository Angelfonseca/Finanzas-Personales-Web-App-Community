"""
database.py - Módulo de Gestión de Esquemas Tenant y Conexiones Dinámicas

Este módulo gestiona:
1. La estructura de directorios aislados ('data/tenants/').
2. La inicialización y aprovisionamiento de bases de datos individuales de usuarios (tenants).
3. La conexión dinámica a la base de datos de cada tenant ('user_{id}.db') con WAL mode y timeout.
"""

import os
import sqlite3

# Rutas base para almacenamiento multi-tenant
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
TENANTS_DIR = os.path.join(DATA_DIR, "tenants")

def ensure_tenant_directories():
    """Garantiza que existan los directorios 'data' y 'data/tenants'."""
    os.makedirs(TENANTS_DIR, exist_ok=True)

def get_tenant_path(db_name: str) -> str:
    """Retorna la ruta absoluta al archivo SQLite del tenant dado su db_name."""
    ensure_tenant_directories()
    # Sanitizar el nombre del archivo para evitar Directory Traversal
    nombre_limpio = os.path.basename(db_name.strip())
    return os.path.join(TENANTS_DIR, nombre_limpio)

def get_tenant_conn(db_name: str) -> sqlite3.Connection:
    """
    Crea y retorna una nueva conexión a la base de datos SQLite específica del tenant.
    
    Configuraciones:
    - timeout=15.0s para evitar bloqueos por concurrencia.
    - row_factory = sqlite3.Row para acceso tipo diccionario.
    """
    db_path = get_tenant_path(db_name)
    conn = sqlite3.connect(db_path, timeout=15.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_tenant_db(db_path: str) -> None:
    """
    Inicializa el esquema financiero completo en la base de datos de un tenant:
    - Activa el modo WAL (Write-Ahead Logging).
    - Crea las tablas 'categorias', 'transacciones', 'apartados' e 'inversiones'.
    - Inserta la categoría por defecto 'General'.
    - Aplica migraciones defensivas (moneda multicurrency y corrección .MX).
    """
    ensure_tenant_directories()
    conn = sqlite3.connect(db_path, timeout=15.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Activar WAL mode para concurrencia
    cursor.execute("PRAGMA journal_mode=WAL;")
    
    # -------------------------------------------------------------
    # Tabla: categorias
    # -------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            tipo TEXT NOT NULL
        )
    """)

    cursor.execute("""
        INSERT OR IGNORE INTO categorias (id, nombre, tipo)
        VALUES (1, 'General', 'gasto')
    """)
    
    # -------------------------------------------------------------
    # Tabla: transacciones
    # -------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transacciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            monto REAL NOT NULL,
            tipo TEXT NOT NULL,
            categoria_id INTEGER,
            descripcion TEXT,
            FOREIGN KEY (categoria_id) REFERENCES categorias (id)
        )
    """)
    
    # -------------------------------------------------------------
    # Tabla: apartados (sobres libres y metas)
    # -------------------------------------------------------------
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
    
    # -------------------------------------------------------------
    # Tabla: inversiones (ETFs, acciones y rendimientos)
    # -------------------------------------------------------------
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

    # Migraciones defensivas
    try:
        cursor.execute("ALTER TABLE inversiones ADD COLUMN moneda TEXT NOT NULL DEFAULT 'USD'")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("UPDATE inversiones SET moneda = 'MXN' WHERE (ticker LIKE '%.MX' OR ticker LIKE '%.mx') AND moneda = 'USD'")
    except sqlite3.OperationalError:
        pass
    
    conn.commit()
    conn.close()

def provision_tenant_db(user_id: int) -> str:
    """
    Aprovisiona automáticamente la base de datos para un nuevo usuario:
    1. Genera el nombre del archivo 'user_{user_id}.db'.
    2. Inicializa el esquema completo.
    3. Retorna el nombre del archivo 'db_name'.
    """
    db_name = f"user_{user_id}.db"
    db_path = get_tenant_path(db_name)
    init_tenant_db(db_path)
    return db_name

# Compatibilidad hacia atrás durante la transición
def get_db(db_name: str = "user_1.db") -> sqlite3.Connection:
    """Helper de compatibilidad que retorna conexión al tenant principal o específico."""
    ensure_tenant_directories()
    # Si aún existe finanzas.db en la raíz y no en tenants, usa la raíz temporalmente
    tenant_1 = get_tenant_path("user_1.db")
    if not os.path.exists(tenant_1) and os.path.exists(os.path.join(BASE_DIR, "finanzas.db")):
        conn = sqlite3.connect(os.path.join(BASE_DIR, "finanzas.db"), timeout=15.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    return get_tenant_conn(db_name)

def init_db():
    """Inicializa directorios y la base de datos del tenant 1 por defecto."""
    ensure_tenant_directories()
    tenant_1 = get_tenant_path("user_1.db")
    init_tenant_db(tenant_1)
