"""
master_db.py - Gestión de la Base de Datos Maestra y Usuarios Multi-Tenant

Este módulo centraliza:
1. El esquema de la base de datos maestra ('data/master.db').
2. Las operaciones CRUD de usuarios (administradores y usuarios estándar).
3. El registro de auditoría de actividad (last_login, login_count).
4. El cálculo de métricas de almacenamiento físico de cada tenant.
5. El seed inicial del primer Administrador y la migración sin pérdidas de datos.
"""

import os
import shutil
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from database import DATA_DIR, TENANTS_DIR, get_tenant_path, provision_tenant_db, init_tenant_db

MASTER_DB_PATH = os.path.join(DATA_DIR, "master.db")

def get_master_conn() -> sqlite3.Connection:
    """Crea y retorna una conexión a la base de datos maestra con WAL mode."""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(MASTER_DB_PATH, timeout=15.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_master_db() -> None:
    """Crea la tabla 'users' e índices en la base de datos maestra."""
    conn = get_master_conn()
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            role TEXT CHECK(role IN ('admin', 'user')) NOT NULL DEFAULT 'user',
            is_active INTEGER NOT NULL DEFAULT 1,
            db_name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP DEFAULT NULL,
            login_count INTEGER NOT NULL DEFAULT 0
        )
    """)
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);")
    conn.commit()
    conn.close()

def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Busca un usuario por su nombre de usuario (insensible a mayúsculas)."""
    conn = get_master_conn()
    cursor = conn.cursor()
    row = cursor.execute("SELECT * FROM users WHERE username = ?", (username.strip(),)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Busca un usuario por su ID único."""
    conn = get_master_conn()
    cursor = conn.cursor()
    row = cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def create_user_entry(username: str, password_hash: str, role: str = 'user', is_active: int = 1) -> Dict[str, Any]:
    """
    Crea un nuevo usuario en la base maestra y dispara el aprovisionamiento automático
    de su base de datos tenant individual ('user_{id}.db').
    """
    username_clean = username.strip()
    conn = get_master_conn()
    cursor = conn.cursor()
    
    # 1. Insertar inicialmente con un placeholder temporal de db_name
    cursor.execute(
        """
        INSERT INTO users (username, password_hash, role, is_active, db_name)
        VALUES (?, ?, ?, ?, ?)
        """,
        (username_clean, password_hash, role, is_active, f"temp_{os.urandom(4).hex()}")
    )
    new_id = cursor.lastrowid
    
    # 2. Aprovisionar la base de datos física del tenant
    db_name = provision_tenant_db(new_id)
    
    # 3. Asignar el db_name definitivo
    cursor.execute("UPDATE users SET db_name = ? WHERE id = ?", (db_name, new_id))
    conn.commit()
    
    # Recuperar el registro completo
    user_row = cursor.execute("SELECT * FROM users WHERE id = ?", (new_id,)).fetchone()
    conn.close()
    return dict(user_row)

def update_login_activity(user_id: int, timestamp_str: str) -> None:
    """Actualiza la fecha/hora del último inicio de sesión e incrementa el contador de logins."""
    conn = get_master_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE users 
        SET last_login = ?, login_count = login_count + 1 
        WHERE id = ?
        """,
        (timestamp_str, user_id)
    )
    conn.commit()
    conn.close()

def set_user_status(user_id: int, is_active: int) -> None:
    """Activa o suspende el acceso de un usuario."""
    conn = get_master_conn()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if is_active else 0, user_id))
    conn.commit()
    conn.close()

def update_user(
    user_id: int, 
    username: Optional[str] = None, 
    password_hash: Optional[str] = None, 
    role: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Actualiza datos de un usuario (nombre de usuario, contraseña hasheada y/o rol).
    Valida que el nuevo nombre no esté duplicado con otro usuario.
    """
    user = get_user_by_id(user_id)
    if not user:
        return None

    conn = get_master_conn()
    cursor = conn.cursor()

    fields = []
    params = []

    if username is not None:
        clean_user = username.strip()
        if len(clean_user) < 3:
            conn.close()
            raise ValueError("El nombre de usuario debe tener al menos 3 caracteres.")
        # Verificar que no exista otro usuario con ese nombre
        existing = cursor.execute("SELECT id FROM users WHERE LOWER(username) = LOWER(?) AND id != ?", (clean_user, user_id)).fetchone()
        if existing:
            conn.close()
            raise ValueError(f"El nombre de usuario '{clean_user}' ya está en uso por otra cuenta.")
        fields.append("username = ?")
        params.append(clean_user)

    if password_hash is not None and password_hash.strip():
        fields.append("password_hash = ?")
        params.append(password_hash.strip())

    if role is not None and role.strip():
        fields.append("role = ?")
        params.append(role.strip())

    if not fields:
        conn.close()
        return user

    params.append(user_id)
    sql = f"UPDATE users SET {', '.join(fields)} WHERE id = ?"
    cursor.execute(sql, tuple(params))
    conn.commit()

    updated = cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(updated) if updated else None

def delete_user_and_tenant(user_id: int) -> bool:
    """
    Elimina permanentemente a un usuario de la base maestra y borra
    su archivo físico de base de datos tenant (.db, -wal, -shm).
    Protege las cuentas con rol admin para que no puedan ser borradas.
    """
    user = get_user_by_id(user_id)
    if not user:
        return False
        
    # Regla: No se puede eliminar la cuenta principal del sistema (ID 1 o usuario 'admin')
    if user["id"] == 1 or user["username"].lower() == "admin":
        return False
        
    db_name = user["db_name"]
    conn = get_master_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    
    # Eliminar archivos físicos del tenant
    db_path = get_tenant_path(db_name)
    for path in [db_path, f"{db_path}-wal", f"{db_path}-shm"]:
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
    return True

def get_tenant_file_size(db_name: str) -> int:
    """Calcula el tamaño total en bytes del tenant (archivo principal + WAL + SHM)."""
    db_path = get_tenant_path(db_name)
    total_bytes = 0
    for path in [db_path, f"{db_path}-wal", f"{db_path}-shm"]:
        if os.path.exists(path):
            try:
                total_bytes += os.path.getsize(path)
            except Exception:
                pass
    return total_bytes

def format_bytes(size_bytes: int) -> str:
    """Convierte bytes a formato legible (KB o MB)."""
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.2f} MB"

def list_users_with_metrics() -> List[Dict[str, Any]]:
    """Retorna la lista de todos los usuarios con métricas de actividad y peso de su BD."""
    conn = get_master_conn()
    cursor = conn.cursor()
    rows = cursor.execute(
        """
        SELECT id, username, role, is_active, db_name, created_at, last_login, login_count 
        FROM users 
        ORDER BY id ASC
        """
    ).fetchall()
    conn.close()
    
    usuarios = []
    for r in rows:
        u = dict(r)
        bytes_ocupados = get_tenant_file_size(u["db_name"])
        u["db_size_bytes"] = bytes_ocupados
        u["db_size_formatted"] = format_bytes(bytes_ocupados)
        usuarios.append(u)
    return usuarios

def get_admin_stats(ahora: datetime) -> Dict[str, Any]:
    """Calcula las métricas globales para las tarjetas KPI del Panel de Administración."""
    conn = get_master_conn()
    cursor = conn.cursor()
    
    total_users = cursor.execute("SELECT COUNT(*) as total FROM users").fetchone()["total"]
    inactive_users = cursor.execute("SELECT COUNT(*) as total FROM users WHERE is_active = 0").fetchone()["total"]
    total_logins = cursor.execute("SELECT SUM(login_count) as total FROM users").fetchone()["total"] or 0
    
    # Usuarios activos hoy (mismo día YYYY-MM-DD)
    hoy_str = ahora.strftime("%Y-%m-%d")
    activos_hoy = cursor.execute(
        "SELECT COUNT(*) as total FROM users WHERE last_login LIKE ? AND is_active = 1",
        (f"{hoy_str}%",)
    ).fetchone()["total"]
    
    # Usuarios activos últimos 7 días
    siete_dias_atras = (ahora - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    activos_7d = cursor.execute(
        "SELECT COUNT(*) as total FROM users WHERE last_login >= ? AND is_active = 1",
        (siete_dias_atras,)
    ).fetchone()["total"]
    
    # Sumar tamaño en disco de todas las bases de datos en data/tenants
    total_disk_bytes = 0
    if os.path.exists(TENANTS_DIR):
        for f in os.listdir(TENANTS_DIR):
            f_path = os.path.join(TENANTS_DIR, f)
            if os.path.isfile(f_path):
                total_disk_bytes += os.path.getsize(f_path)
                
    conn.close()
    
    return {
        "total_users": total_users,
        "active_users_today": activos_hoy,
        "active_users_7d": activos_7d,
        "inactive_users": inactive_users,
        "total_logins": total_logins,
        "total_disk_bytes": total_disk_bytes,
        "total_disk_formatted": format_bytes(total_disk_bytes)
    }

def seed_default_admin_and_migrate(default_password_hash: str) -> Optional[Dict[str, Any]]:
    """
    Rutina de inicio:
    - Inicializa 'master.db'.
    - Si la tabla 'users' está vacía:
      1. Crea el usuario Administrador por defecto 'admin'.
      2. Migra el archivo 'finanzas.db' existente de la raíz a 'data/tenants/user_1.db'
         para conservar al 100% los datos históricos del usuario.
    """
    init_master_db()
    conn = get_master_conn()
    cursor = conn.cursor()
    cant = cursor.execute("SELECT COUNT(*) as total FROM users").fetchone()["total"]
    
    if cant > 0:
        conn.close()
        return None
        
    # Tabla vacía: crear usuario Administrador 'admin'
    base_dir = os.path.dirname(DATA_DIR)
    root_finanzas_db = os.path.join(base_dir, "finanzas.db")
    target_tenant_1 = get_tenant_path("user_1.db")
    
    os.makedirs(TENANTS_DIR, exist_ok=True)
    
    # Migrar archivo existente o inicializar uno nuevo (sin sobreescribir datos existentes)
    if os.path.exists(root_finanzas_db) and not os.path.exists(target_tenant_1):
        shutil.copy2(root_finanzas_db, target_tenant_1)
        # Aplicar migraciones por seguridad
        init_tenant_db(target_tenant_1)
    else:
        init_tenant_db(target_tenant_1)
        
    cursor.execute(
        """
        INSERT INTO users (username, password_hash, role, is_active, db_name)
        VALUES (?, ?, 'admin', 1, 'user_1.db')
        """,
        ("admin", default_password_hash)
    )
    conn.commit()
    user_row = cursor.execute("SELECT * FROM users WHERE id = 1").fetchone()
    conn.close()
    return dict(user_row)
