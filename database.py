"""
database.py - Módulo de Gestión de Esquemas Tenant, Conexiones LRU y Migraciones Automáticas

Este módulo implementa:
1. Aislamiento físico multi-tenant en SQLite ('data/tenants/user_{id}.db').
2. Configuración obligatoria de PRAGMAs en cada conexión abierta:
   - journal_mode = WAL
   - synchronous = NORMAL
   - foreign_keys = ON
   - busy_timeout = 5000
3. Gestor de conexiones con caché LRU (TenantConnectionManager) para no saturar memoria ni descriptores de archivo.
4. Migraciones automáticas bajo demanda (lazy migrations) verificando PRAGMA user_version al conectar.
5. Respaldos y exportaciones en caliente exclusivamente mediante VACUUM INTO o la API nativa de backup de SQLite.
"""

import os
import sqlite3
import threading
from collections import OrderedDict
from contextlib import contextmanager
from typing import Tuple, Optional, Generator

# =============================================================================
# 1. CONSTANTES Y RUTAS DE ALMACENAMIENTO MULTI-TENANT
# =============================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
TENANTS_DIR = os.path.join(DATA_DIR, "tenants")

# Versión actual del esquema de base de datos de cada tenant
CURRENT_TENANT_SCHEMA_VERSION = 3

# Capacidad por defecto del caché LRU de conexiones abiertas
DEFAULT_LRU_CACHE_CAPACITY = int(os.environ.get("TENANT_CONN_CACHE_SIZE", "32"))


# =============================================================================
# 2. GESTIÓN DE DIRECTORIOS Y RUTAS
# =============================================================================

def ensure_tenant_directories() -> None:
    """Garantiza la existencia física de los directorios 'data' y 'data/tenants'."""
    os.makedirs(TENANTS_DIR, exist_ok=True)

def get_tenant_path(db_name_or_path: str) -> str:
    """
    Retorna la ruta absoluta al archivo SQLite del tenant.
    Sanitiza nombres de archivo para evitar Directory Traversal si se pasa un db_name relativo.
    """
    ensure_tenant_directories()
    if os.path.isabs(db_name_or_path):
        return db_name_or_path
    nombre_limpio = os.path.basename(db_name_or_path.strip())
    return os.path.join(TENANTS_DIR, nombre_limpio)

def get_tenant_path_by_id(user_id: int) -> str:
    """Retorna la ruta absoluta canónica '/data/tenants/user_{id}.db'."""
    ensure_tenant_directories()
    return os.path.join(TENANTS_DIR, f"user_{user_id}.db")


# =============================================================================
# 3. CONFIGURACIÓN OBLIGATORIA DE PRAGMAS SQLITE
# =============================================================================

def configure_sqlite_pragmas(conn: sqlite3.Connection) -> None:
    """
    Aplica obligatoriamente los PRAGMAs requeridos por la arquitectura multi-tenant:
    - journal_mode = WAL: Concurrencia real (lectores no bloquean escritores).
    - synchronous = NORMAL: Durabilidad sin I/O innecesario en cada transacción.
    - foreign_keys = ON: Integridad referencial forzada.
    - busy_timeout = 5000: Espera de hasta 5 segundos ante contención antes de emitir error.
    """
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")


# =============================================================================
# 4. MIGRACIONES AUTOMÁTICAS BAJO DEMANDA (LAZY MIGRATIONS)
# =============================================================================

def apply_lazy_migrations(conn: sqlite3.Connection) -> None:
    """
    Verifica PRAGMA user_version en la base de datos del usuario y aplica
    automáticamente los cambios de esquema pendientes al vuelo (lazy migrations).
    Se ejecuta de forma transparente en la primera conexión al tenant.
    """
    cursor = conn.cursor()
    res = cursor.execute("PRAGMA user_version;").fetchone()
    current_version = res[0] if res else 0

    if current_version >= CURRENT_TENANT_SCHEMA_VERSION:
        return

    # -------------------------------------------------------------
    # Versión 1: Esquema base financiero (cuentas, categorias, transacciones, apartados, inversiones)
    # -------------------------------------------------------------
    if current_version < 1:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cuentas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                tipo TEXT NOT NULL DEFAULT 'efectivo',
                saldo_inicial REAL NOT NULL DEFAULT 0.0,
                moneda TEXT NOT NULL DEFAULT 'MXN',
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO cuentas (id, nombre, tipo, saldo_inicial, moneda)
            VALUES (1, 'Cuenta Principal', 'efectivo', 0.0, 'MXN');
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categorias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                tipo TEXT NOT NULL
            );
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO categorias (id, nombre, tipo)
            VALUES (1, 'General', 'gasto');
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transacciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                monto REAL NOT NULL,
                tipo TEXT NOT NULL,
                categoria_id INTEGER,
                cuenta_id INTEGER DEFAULT 1,
                descripcion TEXT,
                FOREIGN KEY (categoria_id) REFERENCES categorias (id),
                FOREIGN KEY (cuenta_id) REFERENCES cuentas (id)
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS apartados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL UNIQUE,
                tipo TEXT CHECK(tipo IN ('libre', 'meta')) NOT NULL,
                monto_actual REAL NOT NULL DEFAULT 0.0,
                meta_monto REAL DEFAULT NULL,
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inversiones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL UNIQUE,
                cantidad REAL NOT NULL,
                precio_promedio REAL NOT NULL,
                precio_actual REAL NOT NULL,
                moneda TEXT NOT NULL DEFAULT 'USD',
                actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("PRAGMA user_version = 1;")
        current_version = 1

    # -------------------------------------------------------------
    # Versión 2: Ajuste de monedas, tickers mexicanos y cuenta_id
    # -------------------------------------------------------------
    if current_version < 2:
        try:
            cursor.execute("ALTER TABLE inversiones ADD COLUMN moneda TEXT NOT NULL DEFAULT 'USD';")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("UPDATE inversiones SET moneda = 'MXN' WHERE (ticker LIKE '%.MX' OR ticker LIKE '%.mx') AND moneda = 'USD';")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE transacciones ADD COLUMN cuenta_id INTEGER DEFAULT 1 REFERENCES cuentas(id);")
        except sqlite3.OperationalError:
            pass

        cursor.execute("PRAGMA user_version = 2;")
        current_version = 2

    # -------------------------------------------------------------
    # Versión 3: Integridad de cuentas e índices de alto rendimiento
    # -------------------------------------------------------------
    if current_version < 3:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cuentas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                tipo TEXT NOT NULL DEFAULT 'efectivo',
                saldo_inicial REAL NOT NULL DEFAULT 0.0,
                moneda TEXT NOT NULL DEFAULT 'MXN',
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO cuentas (id, nombre, tipo, saldo_inicial, moneda)
            VALUES (1, 'Cuenta Principal', 'efectivo', 0.0, 'MXN');
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transacciones_fecha ON transacciones(fecha);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transacciones_tipo ON transacciones(tipo);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transacciones_cat ON transacciones(categoria_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_inversiones_ticker ON inversiones(ticker);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_apartados_nombre ON apartados(nombre);")
        cursor.execute("PRAGMA user_version = 3;")
        current_version = 3

    conn.commit()


# =============================================================================
# 5. GESTOR DE CONEXIONES CON POLÍTICA DE DESALOJO LRU
# =============================================================================

class TenantConnectionManager:
    """
    Gestor thread-safe de conexiones a bases de datos tenant con política de
    desalojo LRU (Least Recently Used) para optimizar memoria RAM y descriptores de archivo.
    """
    def __init__(self, max_connections: int = DEFAULT_LRU_CACHE_CAPACITY):
        self.max_connections = max_connections
        self._cache: OrderedDict[str, sqlite3.Connection] = OrderedDict()
        self._lock = threading.Lock()

    def get_connection(self, db_name_or_path: str) -> sqlite3.Connection:
        """
        Retorna una conexión activa para el tenant. Si existe en el caché LRU y sigue viva,
        la reutiliza y la marca como recientemente usada. En caso contrario, abre una nueva,
        aplica los PRAGMAs obligatorios y ejecuta las lazy migrations correspondientes.
        """
        db_path = get_tenant_path(db_name_or_path)

        with self._lock:
            # 1. Comprobar si ya existe en caché
            if db_path in self._cache:
                conn = self._cache[db_path]
                try:
                    conn.execute("SELECT 1;")
                    self._cache.move_to_end(db_path)
                    return conn
                except Exception:
                    # Conexión dañada o cerrada externamente
                    self._cache.pop(db_path, None)

            # 2. Desalojar la conexión menos recientemente utilizada (LRU) si se llegó al tope
            while len(self._cache) >= self.max_connections:
                evicted_path, evicted_conn = self._cache.popitem(last=False)
                try:
                    evicted_conn.close()
                except Exception:
                    pass

            # 3. Establecer nueva conexión bajo demanda
            ensure_tenant_directories()
            conn = sqlite3.connect(db_path, timeout=5.0, check_same_thread=False)
            conn.row_factory = sqlite3.Row

            # 4. Configurar PRAGMAs obligatorios
            configure_sqlite_pragmas(conn)

            # 5. Aplicar migraciones automáticas al vuelo (lazy migrations)
            apply_lazy_migrations(conn)

            # 6. Almacenar en caché LRU
            self._cache[db_path] = conn
            return conn

    def release_connection(self, db_name_or_path: str, conn: sqlite3.Connection) -> None:
        """Mantiene la conexión en el caché LRU para próximas consultas."""
        pass

    def close_connection(self, db_name_or_path: str) -> None:
        """Cierra y purga del caché la conexión del tenant (por ejemplo, al eliminar su cuenta)."""
        db_path = get_tenant_path(db_name_or_path)
        with self._lock:
            conn = self._cache.pop(db_path, None)
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def close_all(self) -> None:
        """Cierra todas las conexiones cacheadas al apagar el servidor."""
        with self._lock:
            while self._cache:
                _, conn = self._cache.popitem()
                try:
                    conn.close()
                except Exception:
                    pass


# Instancia singleton del gestor de conexiones
tenant_conn_manager = TenantConnectionManager()


def get_tenant_conn(db_name: str) -> sqlite3.Connection:
    """Helper canónico para obtener la conexión al tenant gestionada por el caché LRU."""
    return tenant_conn_manager.get_connection(db_name)

def release_tenant_conn(db_name: str, conn: sqlite3.Connection) -> None:
    """Helper canónico para liberar la conexión al tenant en el gestor."""
    tenant_conn_manager.release_connection(db_name, conn)

@contextmanager
def get_tenant_connection_context(db_name: str) -> Generator[sqlite3.Connection, None, None]:
    """Context manager para operaciones atómicas bajo demanda con liberación garantizada."""
    conn = get_tenant_conn(db_name)
    try:
        yield conn
    finally:
        release_tenant_conn(db_name, conn)


# =============================================================================
# 6. APROVISIONAMIENTO Y MIGRACIÓN INICIAL DE TENANTS
# =============================================================================

def init_tenant_db(db_path: str) -> None:
    """
    Inicializa una base de datos tenant aplicando los PRAGMAs obligatorios
    y las migraciones del esquema financiero completo.
    """
    ensure_tenant_directories()
    conn = sqlite3.connect(db_path, timeout=5.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        configure_sqlite_pragmas(conn)
        apply_lazy_migrations(conn)
    finally:
        conn.close()

def provision_tenant_db(user_id: int) -> Tuple[str, str]:
    """
    Aprovisiona de forma automática la base de datos SQLite independiente de un usuario:
    1. Define el archivo 'user_{user_id}.db' en 'data/tenants/'.
    2. Aplica PRAGMAs y migraciones iniciales.
    3. Retorna (db_name, db_path).
    """
    db_name = f"user_{user_id}.db"
    db_path = get_tenant_path_by_id(user_id)
    init_tenant_db(db_path)
    return db_name, db_path


# =============================================================================
# 7. RESPALDOS EN CALIENTE CON VACUUM INTO / BACKUP API NATIVA
# =============================================================================

def backup_tenant_db_hot(db_name_or_path: str, dest_path: str, prefer_vacuum: bool = True) -> str:
    """
    Ejecuta un respaldo consistente en caliente de la base de datos SQLite del tenant.
    Utiliza exclusivamente VACUUM INTO o la API nativa de backup de SQLite (conn.backup),
    lo que consolida las páginas activas del archivo Write-Ahead Log (WAL) y garantiza
    la integridad de los datos sin corromper lecturas ni escrituras concurrentes.
    """
    db_path = get_tenant_path(db_name_or_path)
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Base de datos tenant no encontrada: {db_path}")

    # Si el destino previo existe, eliminarlo antes de VACUUM INTO
    if os.path.exists(dest_path):
        try:
            os.unlink(dest_path)
        except Exception:
            pass

    # Usamos una conexión transaccional con PRAGMAs estándar
    conn = sqlite3.connect(db_path, timeout=5.0, check_same_thread=False)
    configure_sqlite_pragmas(conn)
    try:
        if prefer_vacuum:
            try:
                # VACUUM INTO genera un archivo nuevo, compacto y consistente en caliente
                conn.execute("VACUUM INTO ?", (dest_path,))
                return dest_path
            except Exception:
                # Fallback seguro a la API nativa si VACUUM INTO no está disponible en la versión
                if os.path.exists(dest_path):
                    try:
                        os.unlink(dest_path)
                    except Exception:
                        pass

        # API nativa de respaldo de SQLite (sqlite3.Connection.backup)
        dst = sqlite3.connect(dest_path, timeout=5.0)
        try:
            conn.backup(dst)
        finally:
            dst.close()
    finally:
        conn.close()
        
    return dest_path


# =============================================================================
# 8. COMPATIBILIDAD CON CÓDIGO HEREDADO
# =============================================================================

def get_db(db_name: str = "user_1.db") -> sqlite3.Connection:
    """Helper de compatibilidad que retorna conexión al tenant solicitado."""
    return get_tenant_conn(db_name)

def init_db():
    """Inicializa la base de datos del tenant 1 por defecto."""
    ensure_tenant_directories()
    tenant_1 = get_tenant_path("user_1.db")
    init_tenant_db(tenant_1)
