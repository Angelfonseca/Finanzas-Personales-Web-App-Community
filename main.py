"""
main.py - Servidor Principal de la Aplicación de Finanzas Personales Multi-Tenant

Este módulo implementa:
1. Arquitectura Multi-Tenant Dinámica con aislamiento físico de base de datos por usuario (SQLite).
2. Autenticación y Autorización basada en JSON Web Tokens (JWT).
3. Panel de Administración de Usuarios con control de acceso por roles (RBAC) y métricas KPI.
4. Endpoints financieros transparentes (gastos, apartados, inversiones, rendimientos y cotizaciones).
5. Exportación de reportes a Excel (.xlsx) y respaldos físicos de base de datos por tenant.
"""

from fastapi import FastAPI, HTTPException, status, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Dict, Any
import json
import urllib.request
import urllib.parse
import sqlite3
import os
import time
from datetime import datetime

# Módulos de infraestructura interna
from database import init_tenant_db, get_tenant_conn, get_tenant_path, ensure_tenant_directories
import master_db
from security import (
    hash_password,
    verify_password,
    create_access_token,
    verify_token,
    verify_admin,
    get_tenant_db
)

# Inicialización de la aplicación FastAPI
app = FastAPI(
    title="Finanzas Personales API Multi-Tenant",
    description="Plataforma SaaS Multi-Tenant para control financiero personal e inversiones con bases de datos aisladas.",
    version="2.0"
)

# Montar recursos estáticos (HTML, CSS, JS)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.middleware("http")
async def add_no_cache_static_header(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

@app.get("/", summary="Página principal SPA")
def leer_raiz():
    """Sirve la interfaz web estática desde static/index.html."""
    return FileResponse("static/index.html")

def ahora_local() -> datetime:
    """Retorna la fecha y hora actual en la zona horaria de México (CST / UTC-6)."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Mexico_City"))
    except Exception:
        return datetime.now()

# =============================================================================
# MODELOS PYDANTIC: AUTENTICACIÓN Y ADMINISTRACIÓN
# =============================================================================

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, description="Nombre de usuario")
    password: str = Field(..., min_length=1, description="Contraseña en texto plano")

class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, pattern=r"^[a-zA-Z0-9_-]+$", description="Nombre de usuario alfanumérico")
    password: str = Field(..., min_length=4, description="Contraseña de acceso")
    role: Literal['admin', 'user'] = Field('user', description="Rol del usuario: 'admin' o 'user'")

class UserStatusRequest(BaseModel):
    is_active: bool = Field(..., description="Estado activo (True) o suspendido (False)")

class UserUpdateRequest(BaseModel):
    username: Optional[str] = Field(None, min_length=3, pattern=r"^[a-zA-Z0-9_-]+$", description="Nuevo nombre de usuario")
    password: Optional[str] = Field(None, min_length=4, description="Nueva contraseña (dejar en blanco para no cambiar)")
    role: Optional[Literal['admin', 'user']] = Field(None, description="Rol del usuario: 'admin' o 'user'")

# =============================================================================
# MODELOS PYDANTIC: TRANSACCIONES, APARTADOS E INVERSIONES
# =============================================================================

class Transaccion(BaseModel):
    fecha: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Fecha en formato ISO YYYY-MM-DD")
    monto: float = Field(..., gt=0, description="Monto mayor a 0")
    tipo: Literal['gasto', 'ingreso'] = Field(..., description="Tipo de movimiento")
    categoria_id: Optional[int] = Field(1, description="ID de categoría")
    descripcion: Optional[str] = Field(None, description="Concepto o detalle")

class TransaccionUpdate(BaseModel):
    fecha: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    monto: Optional[float] = Field(None, gt=0)
    tipo: Optional[Literal['gasto', 'ingreso']] = None
    categoria_id: Optional[int] = None
    descripcion: Optional[str] = None

class ApartadoCreate(BaseModel):
    nombre: str = Field(..., min_length=1)
    tipo: Literal['libre', 'meta']
    meta_monto: Optional[float] = None

class MovimientoApartado(BaseModel):
    monto: float = Field(..., gt=0)
    accion: Literal['depositar', 'retirar']

class InversionCreate(BaseModel):
    ticker: str = Field(..., min_length=1)
    cantidad: float = Field(..., gt=0)
    precio_promedio: float = Field(..., gt=0)
    precio_actual: Optional[float] = None
    moneda: Optional[str] = "USD"

class InversionUpdate(BaseModel):
    cantidad: Optional[float] = Field(None, gt=0)
    precio_promedio: Optional[float] = Field(None, gt=0)
    precio_actual: Optional[float] = Field(None, gt=0)
    moneda: Optional[str] = None

# =============================================================================
# CICLO DE VIDA: INICIALIZACIÓN, SEED Y MIGRACIÓN SIN PÉRDIDAS
# =============================================================================

@app.on_event("startup")
def startup_event():
    """
    Rutina de arranque de la plataforma:
    1. Asegura los directorios 'data/' y 'data/tenants/'.
    2. Inicializa la base de datos maestra ('master.db').
    3. Si es la primera ejecución, crea el Administrador por defecto ('admin') y
       migra automáticamente el archivo 'finanzas.db' existente a 'data/tenants/user_1.db'.
    """
    ensure_tenant_directories()
    # Clave inicial de respaldo si no hay usuarios en master.db
    admin_default_hash = hash_password("admin123")
    migrado = master_db.seed_default_admin_and_migrate(admin_default_hash)
    if migrado:
        print(f"[STARTUP] Base de datos maestra inicializada. Administrador creado: {migrado['username']} (db: {migrado['db_name']})")
    else:
        print("[STARTUP] Base de datos maestra lista y verificada.")

# =============================================================================
# ENDPOINTS: AUTENTICACIÓN (LOGIN & PERFIL)
# =============================================================================

@app.post("/auth/login", summary="Iniciar sesión")
@app.post("/api/auth/login", summary="Iniciar sesión (alias API)")
def login(credentials: LoginRequest):
    """
    Valida las credenciales del usuario:
    1. Comprueba usuario y contraseña con bcrypt en master.db.
    2. Verifica que la cuenta esté activa (is_active == 1).
    3. Registra la auditoría: actualiza last_login e incrementa login_count.
    4. Emite el token JWT firmado con sub, username, role y db_name.
    """
    username = credentials.username.strip()
    user = master_db.get_user_by_username(username)
    
    if not user or not verify_password(credentials.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos."
        )
        
    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu cuenta ha sido desactivada por el administrador."
        )
        
    # Actualizar métricas de auditoría
    timestamp_hoy = ahora_local().strftime("%Y-%m-%d %H:%M:%S")
    master_db.update_login_activity(user["id"], timestamp_hoy)
    
    # Generar token JWT
    payload = {
        "sub": str(user["id"]),
        "username": user["username"],
        "role": user["role"],
        "db_name": user["db_name"]
    }
    token = create_access_token(payload)
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "db_name": user["db_name"]
        }
    }

@app.get("/auth/me", summary="Datos del usuario activo")
@app.get("/api/auth/me", summary="Datos del usuario activo (alias API)")
def get_mi_perfil(current_user: Dict[str, Any] = Depends(verify_token)):
    """Retorna la información del usuario en sesión a partir de su JWT."""
    return {"user": current_user}

@app.patch("/auth/profile", summary="Editar perfil del usuario activo")
@app.patch("/api/auth/profile", summary="Editar perfil del usuario activo (alias API)")
@app.put("/auth/profile", summary="Editar perfil del usuario activo")
@app.put("/api/auth/profile", summary="Editar perfil del usuario activo (alias API)")
def editar_mi_perfil(req: UserUpdateRequest, current_user: Dict[str, Any] = Depends(verify_token)):
    """
    Permite al usuario autenticado modificar su propio nombre de usuario y/o contraseña.
    """
    user_id = current_user["id"]
    pwd_hash = hash_password(req.password) if (req.password and req.password.strip()) else None

    try:
        user_actualizado = master_db.update_user(
            user_id=user_id,
            username=req.username,
            password_hash=pwd_hash,
            role=None  # No permitir auto-escalar rol
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    nuevo_token = create_access_token({
        "sub": str(user_actualizado["id"]),
        "username": user_actualizado["username"],
        "role": user_actualizado["role"],
        "db_name": user_actualizado["db_name"]
    })

    return {
        "mensaje": "Perfil actualizado exitosamente.",
        "user": {
            "id": user_actualizado["id"],
            "username": user_actualizado["username"],
            "role": user_actualizado["role"],
            "db_name": user_actualizado["db_name"]
        },
        "new_token": nuevo_token
    }

# =============================================================================
# ENDPOINTS: ADMINISTRACIÓN DE USUARIOS (SOLO ADMIN)
# =============================================================================

@app.get("/admin/users", summary="Listar usuarios con métricas")
@app.get("/api/admin/users", summary="Listar usuarios con métricas (alias API)")
def admin_listar_usuarios(_admin: Dict[str, Any] = Depends(verify_admin)):
    """Retorna todos los usuarios registrados con su actividad y tamaño en disco de su BD."""
    return master_db.list_users_with_metrics()

@app.post("/admin/users", status_code=status.HTTP_201_CREATED, summary="Crear nuevo usuario")
@app.post("/api/admin/users", status_code=status.HTTP_201_CREATED, summary="Crear nuevo usuario (alias API)")
def admin_crear_usuario(req: UserCreateRequest, _admin: Dict[str, Any] = Depends(verify_admin)):
    """
    Crea un nuevo usuario en la base maestra y dispara el aprovisionamiento
    automático de su base de datos individual en data/tenants/user_{id}.db.
    """
    username = req.username.strip()
    if master_db.get_user_by_username(username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El nombre de usuario '{username}' ya está registrado."
        )
        
    pwd_hash = hash_password(req.password)
    nuevo_usuario = master_db.create_user_entry(
        username=username,
        password_hash=pwd_hash,
        role=req.role,
        is_active=1
    )
    
    return {
        "mensaje": f"Usuario '{username}' creado exitosamente con su base de datos individual.",
        "user": {
            "id": nuevo_usuario["id"],
            "username": nuevo_usuario["username"],
            "role": nuevo_usuario["role"],
            "db_name": nuevo_usuario["db_name"]
        }
    }

@app.patch("/admin/users/{user_id}/status", summary="Cambiar estado de usuario")
@app.patch("/api/admin/users/{user_id}/status", summary="Cambiar estado de usuario (alias API)")
def admin_cambiar_estado(user_id: int, req: UserStatusRequest, admin: Dict[str, Any] = Depends(verify_admin)):
    """
    Activa o desactiva la cuenta de un usuario.
    Regla de Seguridad: El administrador no puede desactivar su propia cuenta.
    """
    if user_id == admin["id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes desactivar tu propia cuenta de administrador."
        )
        
    user = master_db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")
        
    master_db.set_user_status(user_id, 1 if req.is_active else 0)
    estado_str = "activado" if req.is_active else "suspendido"
    return {"mensaje": f"El usuario '{user['username']}' ha sido {estado_str}.", "is_active": req.is_active}

@app.patch("/admin/users/{user_id}", summary="Editar usuario (nombre, contraseña y rol)")
@app.patch("/api/admin/users/{user_id}", summary="Editar usuario (alias API)")
@app.put("/admin/users/{user_id}", summary="Editar usuario")
@app.put("/api/admin/users/{user_id}", summary="Editar usuario (alias API)")
def admin_editar_usuario(user_id: int, req: UserUpdateRequest, admin: Dict[str, Any] = Depends(verify_admin)):
    """
    Permite al administrador modificar el nombre de usuario, contraseña y/o rol de cualquier cuenta.
    Si se edita la propia cuenta del administrador en sesión, se genera y retorna un nuevo token JWT.
    """
    user = master_db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")

    # Si se intenta cambiar el rol del admin a 'user' para su propia cuenta
    if req.role and req.role != user["role"] and user["role"] == "admin":
        if user_id == admin["id"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No puedes remover tu propio rol de administrador."
            )

    pwd_hash = hash_password(req.password) if (req.password and req.password.strip()) else None

    try:
        user_actualizado = master_db.update_user(
            user_id=user_id,
            username=req.username,
            password_hash=pwd_hash,
            role=req.role
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    resp = {
        "mensaje": f"Usuario '{user_actualizado['username']}' actualizado exitosamente.",
        "user": {
            "id": user_actualizado["id"],
            "username": user_actualizado["username"],
            "role": user_actualizado["role"],
            "db_name": user_actualizado["db_name"]
        }
    }

    # Si se modificó la cuenta activa del admin, renovar su JWT
    if user_id == admin["id"]:
        nuevo_token = create_access_token({
            "sub": str(user_actualizado["id"]),
            "username": user_actualizado["username"],
            "role": user_actualizado["role"],
            "db_name": user_actualizado["db_name"]
        })
        resp["new_token"] = nuevo_token

    return resp

@app.delete("/admin/users/{user_id}", summary="Eliminar usuario y su base de datos")
@app.delete("/api/admin/users/{user_id}", summary="Eliminar usuario y su base de datos (alias API)")
def admin_eliminar_usuario(user_id: int, admin: Dict[str, Any] = Depends(verify_admin)):
    """
    Elimina permanentemente a un usuario de master_db y borra físicamente su base de datos tenant.
    Regla de Seguridad: No se puede eliminar ningún usuario con rol 'admin' ni la cuenta principal 'admin'.
    """
    if user_id == admin["id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes eliminar tu propia cuenta de administrador."
        )
        
    user = master_db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")

    if user["id"] == 1 or user["username"].lower() == "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede eliminar la cuenta principal del Administrador."
        )
        
    eliminado = master_db.delete_user_and_tenant(user_id)
    if not eliminado:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al eliminar los archivos del usuario.")
        
    return {"mensaje": f"Usuario '{user['username']}' y su base de datos eliminados con éxito."}

@app.get("/admin/stats", summary="Métricas y KPIs globales del sistema")
@app.get("/api/admin/stats", summary="Métricas y KPIs globales del sistema (alias API)")
def admin_estadisticas_globales(_admin: Dict[str, Any] = Depends(verify_admin)):
    """Calcula las métricas de usuarios activos, logins acumulados y espacio total en disco."""
    return master_db.get_admin_stats(ahora_local())

# =============================================================================
# ENDPOINTS MULTI-TENANT: MOVIMIENTOS (TRANSACCIONES DE CAJA)
# =============================================================================

@app.post("/api/transacciones", summary="Registrar nuevo movimiento")
def crear_transaccion(t: Transaccion, conn: sqlite3.Connection = Depends(get_tenant_db)):
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO transacciones (fecha, monto, tipo, categoria_id, descripcion) 
        VALUES (?, ?, ?, ?, ?)
        """,
        (t.fecha, t.monto, t.tipo, t.categoria_id, t.descripcion)
    )
    conn.commit()
    return {"mensaje": "Transacción guardada con éxito"}

@app.delete("/api/transacciones/{id_transaccion}", summary="Eliminar movimiento")
def eliminar_transaccion(id_transaccion: int, conn: sqlite3.Connection = Depends(get_tenant_db)):
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transacciones WHERE id = ?", (id_transaccion,))
    filas = cursor.rowcount
    conn.commit()
    if filas == 0:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    return {"mensaje": "Transacción eliminada"}

@app.put("/api/transacciones/{id_transaccion}", summary="Editar movimiento")
def actualizar_transaccion(id_transaccion: int, t: TransaccionUpdate, conn: sqlite3.Connection = Depends(get_tenant_db)):
    cursor = conn.cursor()
    trans = cursor.execute("SELECT * FROM transacciones WHERE id = ?", (id_transaccion,)).fetchone()
    if not trans:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")

    nueva_fecha = t.fecha if t.fecha is not None else trans["fecha"]
    nuevo_monto = t.monto if t.monto is not None else trans["monto"]
    nuevo_tipo = t.tipo if t.tipo is not None else trans["tipo"]
    nueva_desc = t.descripcion if t.descripcion is not None else trans["descripcion"]
    nueva_cat = t.categoria_id if t.categoria_id is not None else trans["categoria_id"]

    cursor.execute(
        """
        UPDATE transacciones 
        SET fecha = ?, monto = ?, tipo = ?, categoria_id = ?, descripcion = ?
        WHERE id = ?
        """,
        (nueva_fecha, nuevo_monto, nuevo_tipo, nueva_cat, nueva_desc, id_transaccion)
    )
    conn.commit()
    return {"mensaje": "Transacción actualizada con éxito"}

@app.get("/api/resumen", summary="Resumen patrimonial consolidado del tenant")
def obtener_resumen(moneda_base: str = "MXN", conn: sqlite3.Connection = Depends(get_tenant_db)):
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(monto) as total FROM transacciones WHERE tipo='ingreso'")
    ingresos = cursor.fetchone()["total"] or 0.0
    
    cursor.execute("SELECT SUM(monto) as total FROM transacciones WHERE tipo='gasto'")
    gastos = cursor.fetchone()["total"] or 0.0
    
    cursor.execute("SELECT SUM(monto_actual) as total FROM apartados")
    apartados = cursor.fetchone()["total"] or 0.0

    filas_inv = cursor.execute("SELECT cantidad, precio_actual, moneda FROM inversiones").fetchall()

    tasas = obtener_tasas_cambio()
    tasa_usd_mxn = tasas.get("MXN", 18.40)
    moneda_base_upper = moneda_base.upper()

    inversiones_total = 0.0
    for inv in filas_inv:
        cant = float(inv["cantidad"])
        p_act = float(inv["precio_actual"])
        m_act = (inv["moneda"] or "USD").upper()
        val = cant * p_act
        
        if m_act == "USD" and moneda_base_upper == "MXN":
            val *= tasa_usd_mxn
        elif m_act == "MXN" and moneda_base_upper == "USD":
            val /= tasa_usd_mxn if tasa_usd_mxn > 0 else 1.0

        inversiones_total += val

    factor_mxn_a_base = (1.0 / tasa_usd_mxn) if (moneda_base_upper == "USD" and tasa_usd_mxn > 0) else 1.0

    ingresos_conv = ingresos * factor_mxn_a_base
    gastos_conv = gastos * factor_mxn_a_base
    balance_conv = (ingresos - gastos) * factor_mxn_a_base
    apartados_conv = apartados * factor_mxn_a_base

    patrimonio = balance_conv + apartados_conv + inversiones_total

    return {
        "moneda_base": moneda_base_upper,
        "tasa_usd_mxn": tasa_usd_mxn,
        "ingresos": round(ingresos_conv, 2),
        "gastos": round(gastos_conv, 2),
        "balance": round(balance_conv, 2),
        "apartados": round(apartados_conv, 2),
        "inversiones": round(inversiones_total, 2),
        "patrimonio_neto": round(patrimonio, 2)
    }

@app.get("/api/resumen-mensual", summary="Historial agrupado por mes")
def resumen_mensual(conn: sqlite3.Connection = Depends(get_tenant_db)):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT strftime('%Y-%m', fecha) as mes,
               SUM(CASE WHEN tipo='ingreso' THEN monto ELSE 0 END) as ingresos,
               SUM(CASE WHEN tipo='gasto' THEN monto ELSE 0 END) as gastos
        FROM transacciones
        GROUP BY mes
        ORDER BY mes DESC
    """)
    filas = cursor.fetchall()
    return [dict(fila) for fila in filas]

@app.get("/api/transacciones", summary="Listar todas las transacciones del tenant")
def listar_transacciones(conn: sqlite3.Connection = Depends(get_tenant_db)):
    cursor = conn.cursor()
    cursor.execute("SELECT id, fecha, monto, tipo, descripcion FROM transacciones ORDER BY fecha DESC, id DESC")
    filas = cursor.fetchall()
    return [dict(fila) for fila in filas]

# =============================================================================
# ENDPOINTS MULTI-TENANT: SOBRES VIRTUALES Y METAS DE AHORRO
# =============================================================================

@app.post("/api/apartados", status_code=status.HTTP_201_CREATED, summary="Crear apartado o meta")
def crear_apartado(item: ApartadoCreate, conn: sqlite3.Connection = Depends(get_tenant_db)):
    if item.tipo == 'meta' and (item.meta_monto is None or item.meta_monto <= 0):
        raise HTTPException(status_code=400, detail="Una meta requiere un monto objetivo mayor a cero.")
    
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO apartados (nombre, tipo, monto_actual, meta_monto) VALUES (?, ?, 0.0, ?)",
            (item.nombre, item.tipo, item.meta_monto if item.tipo == 'meta' else None)
        )
        conn.commit()
        nuevo_id = cursor.lastrowid
        return {"id": nuevo_id, "mensaje": "Apartado creado exitosamente"}
    except Exception:
        raise HTTPException(status_code=400, detail="Ya existe un apartado con ese nombre.")

@app.get("/api/apartados", summary="Listar apartados del tenant")
def listar_apartados(conn: sqlite3.Connection = Depends(get_tenant_db)):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM apartados ORDER BY id DESC")
    filas = cursor.fetchall()
    
    resultado = []
    for fila in filas:
        item = dict(fila)
        if item["tipo"] == "meta" and item["meta_monto"] and item["meta_monto"] > 0:
            item["porcentaje"] = round((item["monto_actual"] / item["meta_monto"]) * 100, 2)
        else:
            item["porcentaje"] = None
        resultado.append(item)
    return resultado

@app.delete("/api/apartados/{apartado_id}", summary="Eliminar apartado")
def eliminar_apartado(apartado_id: int, conn: sqlite3.Connection = Depends(get_tenant_db)):
    cursor = conn.cursor()
    apartado = cursor.execute('SELECT * FROM apartados WHERE id = ?', (apartado_id,)).fetchone()
    if not apartado:
        raise HTTPException(status_code=404, detail="Apartado no encontrado")

    if apartado["monto_actual"] > 0:
        saldo = float(apartado["monto_actual"])
        raise HTTPException(
            status_code=400,
            detail=f"No puedes eliminar un apartado con saldo disponible (${saldo:.2f}). Retira los fondos al balance disponible primero."
        )
        
    cursor.execute('DELETE FROM apartados WHERE id = ?', (apartado_id,))
    conn.commit()
    return {"status": "ok", "mensaje": "Apartado eliminado"}

@app.post("/api/apartados/{apartado_id}/movimiento", summary="Depositar o retirar en un apartado")
def movimiento_apartado(apartado_id: int, mov: MovimientoApartado, conn: sqlite3.Connection = Depends(get_tenant_db)):
    cursor = conn.cursor()
    apartado = cursor.execute('SELECT * FROM apartados WHERE id = ?', (apartado_id,)).fetchone()
    if not apartado:
        raise HTTPException(status_code=404, detail="Apartado no encontrado")
        
    nuevo_saldo = apartado['monto_actual']
    fecha_hoy = ahora_local().strftime('%Y-%m-%d')
    
    if mov.accion == 'depositar':
        ingresos_row = cursor.execute("SELECT SUM(monto) as total FROM transacciones WHERE tipo='ingreso'").fetchone()
        gastos_row = cursor.execute("SELECT SUM(monto) as total FROM transacciones WHERE tipo='gasto'").fetchone()
        
        total_ingresos = ingresos_row['total'] if ingresos_row and ingresos_row['total'] else 0.0
        total_gastos = gastos_row['total'] if gastos_row and gastos_row['total'] else 0.0
        balance_disponible = total_ingresos - total_gastos
        
        if mov.monto > balance_disponible:
            raise HTTPException(
                status_code=400, 
                detail=f"No puedes guardar dinero que no tienes. Tu balance disponible es de ${balance_disponible:.2f}"
            )
            
        nuevo_saldo += mov.monto
        desc = f"Ahorro destinado a: {apartado['nombre']}"
        cursor.execute(
            'INSERT INTO transacciones (fecha, monto, tipo, categoria_id, descripcion) VALUES (?, ?, ?, ?, ?)',
            (fecha_hoy, mov.monto, 'gasto', 1, desc)
        )
        
    elif mov.accion == 'retirar':
        if mov.monto > nuevo_saldo:
            raise HTTPException(status_code=400, detail="No puedes retirar más de lo que hay en este apartado")
        
        nuevo_saldo -= mov.monto
        desc = f"Retiro de ahorro: {apartado['nombre']}"
        cursor.execute(
            'INSERT INTO transacciones (fecha, monto, tipo, categoria_id, descripcion) VALUES (?, ?, ?, ?, ?)',
            (fecha_hoy, mov.monto, 'ingreso', 1, desc)
        )
    
    cursor.execute('UPDATE apartados SET monto_actual = ? WHERE id = ?', (nuevo_saldo, apartado_id))
    conn.commit()
    return {"status": "ok", "nuevo_saldo": nuevo_saldo}

# =============================================================================
# ENDPOINTS MULTI-TENANT: INVERSIONES & ASSET ALLOCATION
# =============================================================================

def consultar_precio_y_moneda_mercado(ticker: str):
    ticker_clean = ticker.strip().upper()
    urls = [
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_clean}?interval=1d&range=1d",
        f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker_clean}?interval=1d&range=1d"
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    for url in urls:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode())
                    result = data.get("chart", {}).get("result", [])
                    if result:
                        meta = result[0].get("meta", {})
                        precio = meta.get("regularMarketPrice")
                        moneda = (meta.get("currency") or ("MXN" if ticker_clean.endswith(".MX") else "USD")).upper()
                        if precio is not None:
                            return round(float(precio), 2), moneda
        except Exception:
            continue
    moneda_def = "MXN" if ticker_clean.endswith(".MX") else "USD"
    return None, moneda_def

def consultar_precio_mercado(ticker: str) -> Optional[float]:
    precio, _ = consultar_precio_y_moneda_mercado(ticker)
    return precio

@app.get("/api/inversiones", summary="Listar portafolio con rendimientos del tenant")
def listar_inversiones(moneda_base: str = "MXN", conn: sqlite3.Connection = Depends(get_tenant_db)):
    cursor = conn.cursor()
    filas = cursor.execute("SELECT * FROM inversiones ORDER BY id DESC").fetchall()

    tasas = obtener_tasas_cambio()
    tasa_usd_mxn = tasas.get("MXN", 18.40)
    moneda_base_upper = moneda_base.upper()

    posiciones = []
    total_invertido = 0.0
    total_valor_actual = 0.0

    for fila in filas:
        item = dict(fila)
        cant = float(item["cantidad"])
        costo_prom = float(item["precio_promedio"])
        precio_act = float(item["precio_actual"])
        moneda_activo = (item.get("moneda") or "USD").upper()

        if moneda_activo == "USD" and moneda_base_upper == "MXN":
            factor = tasa_usd_mxn
        elif moneda_activo == "MXN" and moneda_base_upper == "USD":
            factor = (1.0 / tasa_usd_mxn) if tasa_usd_mxn > 0 else 1.0
        else:
            factor = 1.0

        cap_invertido_orig = round(cant * costo_prom, 2)
        val_act_orig = round(cant * precio_act, 2)

        cap_invertido_base = round(cap_invertido_orig * factor, 2)
        val_act_base = round(val_act_orig * factor, 2)
        pnl_base = round(val_act_base - cap_invertido_base, 2)
        pnl_pct = round(((val_act_orig - cap_invertido_orig) / cap_invertido_orig) * 100, 2) if cap_invertido_orig > 0 else 0.0

        total_invertido += cap_invertido_base
        total_valor_actual += val_act_base

        item["moneda"] = moneda_activo
        item["factor_conversion"] = factor
        item["capital_invertido_orig"] = cap_invertido_orig
        item["valor_actual_orig"] = val_act_orig
        item["capital_invertido"] = cap_invertido_base
        item["valor_actual"] = val_act_base
        item["pnl"] = pnl_base
        item["pnl_porcentaje"] = pnl_pct
        posiciones.append(item)

    total_pnl = round(total_valor_actual - total_invertido, 2)
    total_pnl_pct = round((total_pnl / total_invertido) * 100, 2) if total_invertido > 0 else 0.0

    for pos in posiciones:
        pos["peso_porcentaje"] = round((pos["valor_actual"] / total_valor_actual) * 100, 2) if total_valor_actual > 0 else 0.0

    return {
        "moneda_base": moneda_base_upper,
        "tasa_usd_mxn": tasa_usd_mxn,
        "resumen": {
            "total_invertido": round(total_invertido, 2),
            "total_valor_actual": round(total_valor_actual, 2),
            "total_pnl": total_pnl,
            "total_pnl_porcentaje": total_pnl_pct
        },
        "posiciones": posiciones
    }

@app.post("/api/inversiones", status_code=status.HTTP_201_CREATED, summary="Registrar posición bursátil")
def crear_inversion(item: InversionCreate, conn: sqlite3.Connection = Depends(get_tenant_db)):
    ticker = item.ticker.strip().upper()
    precio_actual = item.precio_actual
    moneda = (item.moneda or "USD").strip().upper()
    
    if precio_actual is None or precio_actual <= 0:
        precio_mercado, moneda_mercado = consultar_precio_y_moneda_mercado(ticker)
        precio_actual = precio_mercado if precio_mercado else item.precio_promedio
        if not item.moneda:
            moneda = moneda_mercado

    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO inversiones (ticker, cantidad, precio_promedio, precio_actual, moneda) VALUES (?, ?, ?, ?, ?)",
            (ticker, item.cantidad, item.precio_promedio, precio_actual, moneda)
        )
        conn.commit()
        nuevo_id = cursor.lastrowid
        return {"id": nuevo_id, "mensaje": f"Inversión {ticker} ({moneda}) agregada con éxito."}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail=f"Ya tienes una posición con el ticker {ticker}. Puedes editarla.")

@app.put("/api/inversiones/{inversion_id}", summary="Actualizar posición bursátil")
def actualizar_inversion(inversion_id: int, item: InversionUpdate, conn: sqlite3.Connection = Depends(get_tenant_db)):
    cursor = conn.cursor()
    inv = cursor.execute("SELECT * FROM inversiones WHERE id = ?", (inversion_id,)).fetchone()
    if not inv:
        raise HTTPException(status_code=404, detail="Inversión no encontrada")

    nueva_cant = item.cantidad if item.cantidad is not None else inv["cantidad"]
    nuevo_prom = item.precio_promedio if item.precio_promedio is not None else inv["precio_promedio"]
    nuevo_act = item.precio_actual if item.precio_actual is not None else inv["precio_actual"]
    nueva_moneda = item.moneda.upper() if item.moneda else (inv["moneda"] or "USD")

    cursor.execute(
        """
        UPDATE inversiones 
        SET cantidad = ?, precio_promedio = ?, precio_actual = ?, moneda = ?, actualizado_en = CURRENT_TIMESTAMP 
        WHERE id = ?
        """,
        (nueva_cant, nuevo_prom, nuevo_act, nueva_moneda, inversion_id)
    )
    conn.commit()
    return {"mensaje": "Inversión actualizada con éxito."}

@app.delete("/api/inversiones/{inversion_id}", summary="Eliminar posición bursátil")
def eliminar_inversion(inversion_id: int, conn: sqlite3.Connection = Depends(get_tenant_db)):
    cursor = conn.cursor()
    inv = cursor.execute("SELECT * FROM inversiones WHERE id = ?", (inversion_id,)).fetchone()
    if not inv:
        raise HTTPException(status_code=404, detail="Inversión no encontrada")

    cursor.execute("DELETE FROM inversiones WHERE id = ?", (inversion_id,))
    conn.commit()
    return {"mensaje": "Inversión eliminada."}

@app.post("/api/inversiones/sincronizar", summary="Sincronizar cotizaciones en vivo")
def sincronizar_precios(conn: sqlite3.Connection = Depends(get_tenant_db)):
    cursor = conn.cursor()
    filas = cursor.execute("SELECT id, ticker FROM inversiones").fetchall()
    actualizados = []
    no_actualizados = []

    for fila in filas:
        t = fila["ticker"]
        precio, moneda = consultar_precio_y_moneda_mercado(t)
        if precio is not None:
            moneda_actualizada = moneda or ("MXN" if t.endswith(".MX") else "USD")
            cursor.execute(
                """
                UPDATE inversiones 
                SET precio_actual = ?, moneda = ?, actualizado_en = CURRENT_TIMESTAMP 
                WHERE id = ?
                """,
                (precio, moneda_actualizada, fila["id"])
            )
            actualizados.append({"ticker": t, "precio": precio, "moneda": moneda_actualizada})
        else:
            no_actualizados.append(t)

    conn.commit()
    return {
        "actualizados": actualizados,
        "no_actualizados": no_actualizados,
        "mensaje": f"Se sincronizaron {len(actualizados)} de {len(filas)} posiciones."
    }

@app.get("/api/inversiones/cotizar/{ticker}", summary="Cotización individual en tiempo real")
def cotizar_ticker(ticker: str, _user: Dict[str, Any] = Depends(verify_token)):
    precio, moneda = consultar_precio_y_moneda_mercado(ticker)
    if precio is None:
        raise HTTPException(status_code=404, detail=f"No se pudo consultar la cotización para {ticker.upper()}")
    return {"ticker": ticker.upper(), "precio": precio, "moneda": moneda}

def buscar_tickers_mercado(query: str):
    q = urllib.parse.quote(query.strip())
    url = f"https://query1.finance.yahoo.com/v1/finance/search?q={q}&quotesCount=8&newsCount=0"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=4) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                quotes = data.get("quotes", [])
                resultados = []
                for item in quotes:
                    simbolo = item.get("symbol")
                    if not simbolo:
                        continue
                    nombre = item.get("shortname") or item.get("longname") or simbolo
                    tipo = item.get("quoteType") or item.get("typeDisp") or "ACTIVO"
                    bolsa = item.get("exchDisp") or item.get("exchange") or ""
                    resultados.append({
                        "symbol": simbolo,
                        "nombre": nombre,
                        "tipo": tipo,
                        "bolsa": bolsa
                    })
                return resultados
    except Exception:
        pass
    return []

@app.get("/api/inversiones/buscar", summary="Buscador predictivo de tickers")
def api_buscar_ticker(q: str = "", _user: Dict[str, Any] = Depends(verify_token)):
    if not q or len(q.strip()) < 1:
        return []
    return buscar_tickers_mercado(q)

# =============================================================================
# TIPOS DE CAMBIO CON MEMORIA CACHÉ
# =============================================================================

_CACHE_TASAS = {
    "datos": None,
    "expira_en": 0.0
}

def obtener_tasas_cambio():
    ahora = time.time()
    if _CACHE_TASAS["datos"] is not None and ahora < _CACHE_TASAS["expira_en"]:
        return _CACHE_TASAS["datos"]

    tasas = {
        "USD": 1.0,
        "MXN": 18.40,
        "EUR": 0.89
    }
    try:
        precio_mxn = consultar_precio_mercado("USDMXN=X")
        if precio_mxn and precio_mxn > 0:
            tasas["MXN"] = round(precio_mxn, 4)
            
        precio_eur = consultar_precio_mercado("EURUSD=X")
        if precio_eur and precio_eur > 0:
            tasas["EUR"] = round(1.0 / precio_eur, 4)

        _CACHE_TASAS["datos"] = tasas
        _CACHE_TASAS["expira_en"] = ahora + 300
    except Exception:
        if _CACHE_TASAS["datos"] is not None:
            return _CACHE_TASAS["datos"]
        _CACHE_TASAS["datos"] = tasas
        _CACHE_TASAS["expira_en"] = ahora + 60

    return _CACHE_TASAS["datos"]

@app.get("/api/tipo-cambio", summary="Consultar tipos de cambio vigentes")
def get_tipo_cambio(_user: Dict[str, Any] = Depends(verify_token)):
    tasas = obtener_tasas_cambio()
    return {
        "base": "USD",
        "tasas": tasas,
        "actualizado_en": ahora_local().strftime("%Y-%m-%d %H:%M:%S")
    }

# =============================================================================
# RESPALDO AISLADO Y EXPORTACIÓN A EXCEL POR TENANT
# =============================================================================

@app.get("/api/backup", summary="Descargar respaldo directo de base de datos del tenant")
def descargar_backup(current_user: Dict[str, Any] = Depends(verify_token)):
    """Descarga el archivo SQLite propio del usuario autenticado."""
    db_name = current_user.get("db_name", "user_1.db")
    db_path = get_tenant_path(db_name)
    if not os.path.exists(db_path):
        raise HTTPException(status_code=404, detail="Base de datos del usuario no encontrada.")
        
    fecha_str = ahora_local().strftime("%Y%m%d_%H%M%S")
    username_safe = current_user.get("username", "user")
    return FileResponse(
        db_path,
        filename=f"finanzas_{username_safe}_{fecha_str}.db",
        media_type="application/octet-stream"
    )

@app.get("/api/exportar-excel", summary="Descargar reporte en Excel del tenant")
def exportar_excel(
    moneda_base: str = "MXN",
    conn: sqlite3.Connection = Depends(get_tenant_db),
    current_user: Dict[str, Any] = Depends(verify_token)
):
    """Genera el reporte financiero en Excel exclusivamente con los datos del tenant activo."""
    from export_service import generar_reporte_excel
    buf = generar_reporte_excel(
        moneda_base=moneda_base,
        conn=conn,
        db_name=current_user.get("db_name", "user_1.db")
    )
    fecha_str = ahora_local().strftime("%Y%m%d_%H%M%S")
    username_safe = current_user.get("username", "user")
    nombre_archivo = f"reporte_{username_safe}_{moneda_base.upper()}_{fecha_str}.xlsx"
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{nombre_archivo}"'
        }
    )
