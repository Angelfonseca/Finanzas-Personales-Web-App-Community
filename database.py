"""
database.py - Módulo de Gestión y Conexión de Base de Datos SQLite

Este módulo centraliza:
1. La conexión a la base de datos local SQLite ('finanzas.db').
2. La configuración del modo WAL (Write-Ahead Logging) para soportar concurrencia.
3. La creación e inicialización de esquemas de tablas relacionales.
4. Las migraciones automáticas idempotentes de columnas y compatibilidad de divisas.
"""

import sqlite3

# Nombre del archivo de base de datos SQLite local
DB_NAME = "finanzas.db"

def get_db() -> sqlite3.Connection:
    """
    Crea y retorna una nueva conexión a la base de datos SQLite.
    
    Configuraciones clave:
    - timeout=15.0: Espera hasta 15 segundos si la base de datos está temporalmente
      bloqueada por una escritura antes de lanzar una excepción sqlite3.OperationalError.
    - row_factory = sqlite3.Row: Permite acceder a las columnas devueltas tanto por
      índice posicional (row[0]) como por nombre de columna dict-like (row['monto']).
    """
    conn = sqlite3.connect(DB_NAME, timeout=15.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    """
    Inicializa la base de datos:
    - Activa el modo WAL (Write-Ahead Logging) para permitir lecturas concurrentes sin bloquear escrituras.
    - Crea las tablas fundamentales ('categorias', 'transacciones', 'apartados', 'inversiones') si no existen.
    - Inserta registros de integridad por defecto (categoría 'General').
    - Ejecuta migraciones de esquema defensivas (ej. soporte multicurrency en inversiones).
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Activar modo WAL (Write-Ahead Logging):
    # Mejora significativamente el rendimiento y evita bloqueos (database is locked) en entornos web con FastAPI.
    cursor.execute("PRAGMA journal_mode=WAL;")
    
    # -------------------------------------------------------------
    # Tabla: categorias
    # Clasificación de transacciones en tipos de gasto o ingreso.
    # -------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            tipo TEXT NOT NULL -- Tipo de flujo: 'gasto' o 'ingreso'
        )
    """)

    # Registro de respaldo inicial para mantener integridad referencial en transacciones
    cursor.execute("""
        INSERT OR IGNORE INTO categorias (id, nombre, tipo)
        VALUES (1, 'General', 'gasto')
    """)
    
    # -------------------------------------------------------------
    # Tabla: transacciones
    # Registra cada movimiento financiero de flujo de efectivo (ingresos y gastos diarios).
    # -------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transacciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,                 -- Formato ISO: YYYY-MM-DD
            monto REAL NOT NULL,                 -- Monto del movimiento (positivo, mayor a 0)
            tipo TEXT NOT NULL,                  -- 'gasto' o 'ingreso'
            categoria_id INTEGER,               -- Clave foránea que referencia a 'categorias.id'
            descripcion TEXT,                    -- Concepto o detalle del movimiento
            FOREIGN KEY (categoria_id) REFERENCES categorias (id)
        )
    """)
    
    # -------------------------------------------------------------
    # Tabla: apartados
    # Sistema de sobres virtuales para separar dinero del balance disponible:
    # - 'libre': Fondos de reserva o emergencias sin techo fijo.
    # - 'meta': Objetivos específicos de ahorro con un monto objetivo ('meta_monto').
    # -------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS apartados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,                             -- Nombre único del sobre
            tipo TEXT CHECK(tipo IN ('libre', 'meta')) NOT NULL,     -- Validación estricta a nivel BD
            monto_actual REAL NOT NULL DEFAULT 0.0,                  -- Saldo acumulado en el sobre
            meta_monto REAL DEFAULT NULL,                            -- Objetivo financiero (obligatorio en 'meta')
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP            -- Fecha y hora de creación
        )
    """)
    
    # -------------------------------------------------------------
    # Tabla: inversiones
    # Seguimiento de activos bursátiles (ETFs, acciones individuales y fibras).
    # Incluye soporte multicurrency (USD y MXN) y valuación en tiempo real.
    # -------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inversiones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL UNIQUE,                             -- Símbolo de cotización único (ej. VOO, AAPL, WALMEX.MX)
            cantidad REAL NOT NULL,                                  -- Número de títulos o títulos fraccionados
            precio_promedio REAL NOT NULL,                           -- Costo promedio ponderado de adquisición en su moneda de origen
            precio_actual REAL NOT NULL,                             -- Última cotización de mercado registrada
            moneda TEXT NOT NULL DEFAULT 'USD',                      -- Divisa del activo bursátil: 'USD' o 'MXN'
            actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP       -- Marca temporal de la última actualización de precio
        )
    """)

    # -------------------------------------------------------------
    # MIGRACIONES DEFENSIVAS E IDEMPOTENTES
    # -------------------------------------------------------------
    # 1. Agregar columna 'moneda' en 'inversiones' si la base de datos proviene de una versión previa.
    try:
        cursor.execute("ALTER TABLE inversiones ADD COLUMN moneda TEXT NOT NULL DEFAULT 'USD'")
    except sqlite3.OperationalError:
        # La columna ya existe, se ignora de manera segura.
        pass

    # 2. Corregir automáticamente activos de la Bolsa Mexicana de Valores (.MX)
    # que por defecto se hayan registrado con USD en versiones anteriores.
    try:
        cursor.execute("UPDATE inversiones SET moneda = 'MXN' WHERE (ticker LIKE '%.MX' OR ticker LIKE '%.mx') AND moneda = 'USD'")
    except sqlite3.OperationalError:
        pass
    
    # Confirmar cambios y cerrar conexión
    conn.commit()
    conn.close()

if __name__ == "__main__":
    # Permite ejecutar manualmente 'python database.py' para inicializar o verificar la BD.
    init_db()
    print("Base de datos y tablas actualizadas con éxito.")
