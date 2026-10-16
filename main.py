"""
main.py - Servidor Principal de la Aplicación de Finanzas Personales Multi-Tenant

Este módulo implementa:
1. Arquitectura Multi-Tenant Dinámica con aislamiento físico de base de datos por usuario (SQLite).
2. Autenticación y Autorización basada en JSON Web Tokens (JWT).
3. Panel de Administración de Usuarios con control de acceso por roles (RBAC) y métricas KPI.
4. Endpoints financieros transparentes (gastos, apartados, inversiones, rendimientos y cotizaciones).
5. Exportación de reportes a Excel (.xlsx) y respaldos físicos de base de datos por tenant.
"""

from fastapi import FastAPI, HTTPException, status, Depends, Request, BackgroundTasks, UploadFile, File
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
import shutil
import tempfile
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

# Control de exposición de documentación técnica (Swagger UI / ReDoc / OpenAPI)
# Por seguridad en producción, queda completamente deshabilitado (404) a menos que ENABLE_DOCS=true
ENABLE_DOCS = os.environ.get("ENABLE_DOCS", "false").strip().lower() in ("true", "1", "yes")

# Inicialización de la aplicación FastAPI
app = FastAPI(
    title="Finanzas Personales API Multi-Tenant",
    description="Plataforma SaaS Multi-Tenant para control financiero personal e inversiones con bases de datos aisladas.",
    version="2.0",
    docs_url="/docs" if ENABLE_DOCS else None,
    redoc_url="/redoc" if ENABLE_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_DOCS else None
)

# Montar recursos estáticos (HTML, CSS, JS)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Control en memoria de intentos fallidos de autenticación (freno anti fuerza bruta)
_intentos_fallidos_login: Dict[str, List[float]] = {}

def registrar_fallo_login(clave: str):
    ahora = time.time()
    intentos = [t for t in _intentos_fallidos_login.get(clave, []) if ahora - t < 300]
    intentos.append(ahora)
    _intentos_fallidos_login[clave] = intentos

def verificar_tasa_login(clave: str):
    ahora = time.time()
    intentos = [t for t in _intentos_fallidos_login.get(clave, []) if ahora - t < 300]
    _intentos_fallidos_login[clave] = intentos
    if len(intentos) >= 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos fallidos. Por seguridad, espera 5 minutos antes de volver a intentar."
        )

def limpiar_fallos_login(clave: str):
    _intentos_fallidos_login.pop(clave, None)

@app.middleware("http")
async def add_security_and_cache_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.url.path.startswith("/static/") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

@app.get("/", summary="Página principal SPA")
@app.get("/login", summary="Página de acceso")
@app.get("/app", summary="Aplicación principal")
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
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$", description="Nombre de usuario alfanumérico")
    password: str = Field(..., min_length=4, max_length=72, description="Contraseña de acceso")
    role: Literal['admin', 'user'] = Field('user', description="Rol del usuario: 'admin' o 'user'")
    email: Optional[str] = Field(None, max_length=120, description="Correo electrónico para recuperación de contraseña")

class UserStatusRequest(BaseModel):
    is_active: bool = Field(..., description="Estado activo (True) o suspendido (False)")

class UserUpdateRequest(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$", description="Nuevo nombre de usuario")
    password: Optional[str] = Field(None, min_length=4, max_length=72, description="Nueva contraseña (dejar en blanco para no cambiar)")
    role: Optional[Literal['admin', 'user']] = Field(None, description="Rol del usuario: 'admin' o 'user'")
    email: Optional[str] = Field(None, max_length=120, description="Correo electrónico del usuario")

class ForgotPasswordRequest(BaseModel):
    identifier: str = Field(..., min_length=2, max_length=120, description="Nombre de usuario o correo electrónico")

class ResetPasswordRequest(BaseModel):
    identifier: str = Field(..., min_length=2, max_length=120, description="Nombre de usuario o correo electrónico")
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$", description="Código numérico de 6 dígitos")
    new_password: str = Field(..., min_length=4, max_length=72, description="Nueva contraseña")

# =============================================================================
# MODELOS PYDANTIC: TRANSACCIONES, APARTADOS E INVERSIONES
# =============================================================================

class Transaccion(BaseModel):
    fecha: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Fecha en formato ISO YYYY-MM-DD")
    monto: float = Field(..., gt=0, le=1e12, description="Monto mayor a 0")
    tipo: Literal['gasto', 'ingreso'] = Field(..., description="Tipo de movimiento")
    categoria_id: Optional[int] = Field(1, description="ID de categoría")
    descripcion: Optional[str] = Field(None, max_length=255, description="Concepto o detalle")

class TransaccionUpdate(BaseModel):
    fecha: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    monto: Optional[float] = Field(None, gt=0, le=1e12)
    tipo: Optional[Literal['gasto', 'ingreso']] = None
    categoria_id: Optional[int] = None
    descripcion: Optional[str] = Field(None, max_length=255)

class ApartadoCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    tipo: Literal['libre', 'meta']
    meta_monto: Optional[float] = Field(None, gt=0, le=1e12)

class MovimientoApartado(BaseModel):
    monto: float = Field(..., gt=0, le=1e12)
    accion: Literal['depositar', 'retirar']

class InversionCreate(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=15, pattern=r"^[A-Z0-9.\-=^]{1,15}$")
    cantidad: float = Field(..., gt=0, le=1e9)
    precio_promedio: float = Field(..., gt=0, le=1e12)
    precio_actual: Optional[float] = Field(None, gt=0, le=1e12)
    moneda: Optional[Literal['USD', 'MXN', 'EUR']] = "USD"

class InversionUpdate(BaseModel):
    cantidad: Optional[float] = Field(None, gt=0, le=1e9)
    precio_promedio: Optional[float] = Field(None, gt=0, le=1e12)
    precio_actual: Optional[float] = Field(None, gt=0, le=1e12)
    moneda: Optional[Literal['USD', 'MXN', 'EUR']] = None

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
    admin_default_pass = os.environ.get("DEFAULT_ADMIN_PASSWORD", "admin123")
    admin_default_hash = hash_password(admin_default_pass)
    migrado = master_db.seed_default_admin_and_migrate(admin_default_hash)
    if migrado:
        print(f"[STARTUP] Base de datos maestra inicializada. Administrador creado: {migrado['username']} (db: {migrado['db_name']})")
    else:
        print("[STARTUP] Base de datos maestra lista y verificada.")

    from email_service import esta_configurado_servicio_correo
    if esta_configurado_servicio_correo():
        print("[EMAIL] Servicio de correo transaccional (API / SMTP) configurado y activo.")
    else:
        print("[EMAIL ADVERTENCIA] El servicio de envío de correos NO está configurado en .env. La recuperación de contraseñas por correo permanecerá inactiva hasta definir RESEND_API_KEY o credenciales SMTP.")

# =============================================================================
# ENDPOINTS: AUTENTICACIÓN (LOGIN & PERFIL)
# =============================================================================

@app.post("/auth/login", summary="Iniciar sesión")
@app.post("/api/auth/login", summary="Iniciar sesión (alias API)")
def login(credentials: LoginRequest, request: Request):
    """
    Valida las credenciales del usuario:
    1. Comprueba usuario y contraseña con bcrypt en master.db.
    2. Aplica control de tasa contra ataques de fuerza bruta.
    3. Verifica que la cuenta esté activa (is_active == 1).
    4. Registra la auditoría: actualiza last_login e incrementa login_count.
    5. Emite el token JWT firmado con sub, username, role y db_name.
    """
    client_ip = request.client.host if request.client else "unknown"
    clave_tasa = f"{client_ip}:{credentials.username.strip().lower()}"
    verificar_tasa_login(clave_tasa)

    username = credentials.username.strip()
    user = master_db.get_user_by_username(username)
    
    if not user or not verify_password(credentials.password, user["password_hash"]):
        registrar_fallo_login(clave_tasa)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos."
        )
        
    limpiar_fallos_login(clave_tasa)

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
        "db_name": user["db_name"],
        "email": user.get("email")
    }
    token = create_access_token(payload)
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "db_name": user["db_name"],
            "email": user.get("email")
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
    Permite al usuario autenticado modificar su propio nombre de usuario, correo y/o contraseña.
    """
    user_id = current_user["id"]
    pwd_hash = hash_password(req.password) if (req.password and req.password.strip()) else None

    try:
        user_actualizado = master_db.update_user(
            user_id=user_id,
            username=req.username,
            password_hash=pwd_hash,
            role=None,  # No permitir auto-escalar rol
            email=req.email
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    nuevo_token = create_access_token({
        "sub": str(user_actualizado["id"]),
        "username": user_actualizado["username"],
        "role": user_actualizado["role"],
        "db_name": user_actualizado["db_name"],
        "email": user_actualizado.get("email")
    })

    return {
        "mensaje": "Perfil actualizado exitosamente.",
        "user": {
            "id": user_actualizado["id"],
            "username": user_actualizado["username"],
            "role": user_actualizado["role"],
            "db_name": user_actualizado["db_name"],
            "email": user_actualizado.get("email")
        },
        "new_token": nuevo_token
    }

@app.delete("/auth/delete-account", summary="Eliminar permanentemente la cuenta del usuario activo")
@app.delete("/api/auth/delete-account", summary="Eliminar permanentemente la cuenta del usuario activo (alias API)")
@app.delete("/auth/me", summary="Eliminar permanentemente la cuenta del usuario activo")
@app.delete("/api/auth/me", summary="Eliminar permanentemente la cuenta del usuario activo (alias API)")
def eliminar_mi_cuenta(current_user: Dict[str, Any] = Depends(verify_token)):
    """
    Permite a los usuarios estándar eliminar permanentemente su propia cuenta y su base de datos tenant.
    Regla de Seguridad: Los administradores NO pueden eliminar su propia cuenta a través de este endpoint.
    """
    user_id = current_user["id"]

    # Bloquear estrictamente si es administrador o cuenta principal
    if (
        current_user.get("role") == "admin"
        or user_id == 1
        or current_user.get("username", "").lower() == "admin"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Los administradores del sistema no pueden eliminar su propia cuenta."
        )

    eliminado = master_db.delete_user_and_tenant(user_id)
    if not eliminado:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo procesar la eliminación de tu cuenta."
        )

    return {"mensaje": "Tu cuenta y toda tu información financiera han sido eliminadas permanentemente."}

# =============================================================================
# ENDPOINTS: RECUPERACIÓN DE CONTRASEÑA POR EMAIL
# =============================================================================

@app.get("/api/public/email-status", summary="Consultar estado de configuración del correo")
@app.get("/auth/email-status", summary="Consultar estado de configuración del correo (alias)")
def get_email_status():
    """Retorna si el servicio de correo transaccional (API o SMTP) está configurado en el servidor."""
    from email_service import esta_configurado_servicio_correo
    return {"configured": esta_configurado_servicio_correo()}

@app.post("/auth/forgot-password", summary="Solicitar código de restablecimiento de contraseña")
@app.post("/api/auth/forgot-password", summary="Solicitar código de restablecimiento (alias API)")
def forgot_password(req: ForgotPasswordRequest, background_tasks: BackgroundTasks, request: Request):
    """
    Solicita un código de recuperación de contraseña de 6 dígitos:
    1. Verifica si el servicio de correo está configurado.
    2. Aplica rate limiting para prevenir spam.
    3. Busca al usuario por username o email.
    4. Si tiene email registrado, genera código y lo envía en segundo plano por correo/SMTP.
    5. Responde con un mensaje neutro para evitar enumeración de usuarios.
    """
    from email_service import esta_configurado_servicio_correo, enviar_correo_codigo_recuperacion
    if not esta_configurado_servicio_correo():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El servicio de envío de correos no está configurado en este servidor. Por favor, solicita asistencia directamente al administrador del sistema para restablecer tu contraseña."
        )

    client_ip = request.client.host if request.client else "unknown"
    clave_tasa = f"forgot:{client_ip}"
    verificar_tasa_login(clave_tasa)

    user = master_db.get_user_by_identifier(req.identifier)
    if user and user.get("email") and user.get("is_active"):
        intentos = master_db.count_recent_reset_requests(user["id"], hours=24)
        if intentos >= 2:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Has alcanzado el límite máximo de 2 intentos de recuperación de contraseña para este usuario en las últimas 24 horas. Por seguridad, solicita asistencia al administrador del sistema."
            )
        codigo = master_db.create_password_reset_code(user["id"])
        background_tasks.add_task(
            enviar_correo_codigo_recuperacion,
            user["email"],
            user["username"],
            codigo
        )
    else:
        registrar_fallo_login(clave_tasa)

    return {
        "mensaje": "Si el usuario o correo electrónico existe y tiene una dirección registrada, hemos enviado un código de recuperación de 6 dígitos (válido por 15 minutos)."
    }

@app.post("/auth/reset-password", summary="Restablecer contraseña con código de 6 dígitos")
@app.post("/api/auth/reset-password", summary="Restablecer contraseña (alias API)")
def reset_password(req: ResetPasswordRequest, request: Request):
    """
    Restablece la contraseña utilizando el código de 6 dígitos recibido por correo.
    Aplica una política de seguridad estricta: máximo 2 intentos fallidos antes de invalidar el código.
    """
    client_ip = request.client.host if request.client else "unknown"
    clave_tasa = f"reset:{client_ip}"
    verificar_tasa_login(clave_tasa)

    nuevo_hash = hash_password(req.new_password)
    user, error_msg = master_db.verify_and_use_reset_code(req.identifier, req.code, nuevo_hash)
    if not user:
        registrar_fallo_login(clave_tasa)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg or "El código de recuperación es incorrecto, ya ha sido utilizado o ha expirado (vigencia de 15 minutos)."
        )

    limpiar_fallos_login(clave_tasa)
    return {
        "mensaje": f"¡Contraseña actualizada exitosamente para '{user['username']}'! Ya puedes iniciar sesión con tu nueva contraseña."
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
    try:
        nuevo_usuario = master_db.create_user_entry(
            username=username,
            password_hash=pwd_hash,
            role=req.role,
            is_active=1,
            email=req.email
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    return {
        "mensaje": f"Usuario '{username}' creado exitosamente con su base de datos individual.",
        "user": {
            "id": nuevo_usuario["id"],
            "username": nuevo_usuario["username"],
            "role": nuevo_usuario["role"],
            "db_name": nuevo_usuario["db_name"],
            "email": nuevo_usuario.get("email")
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

    if user["id"] == 1 or user["username"].lower() == "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede suspender la cuenta del Administrador principal."
        )
        
    master_db.set_user_status(user_id, 1 if req.is_active else 0)
    estado_str = "activado" if req.is_active else "suspendido"
    return {"mensaje": f"El usuario '{user['username']}' ha sido {estado_str}.", "is_active": req.is_active}

@app.patch("/admin/users/{user_id}", summary="Editar usuario (nombre, contraseña y rol)")
@app.patch("/api/admin/users/{user_id}", summary="Editar usuario (alias API)")
@app.put("/admin/users/{user_id}", summary="Editar usuario")
@app.put("/api/admin/users/{user_id}", summary="Editar usuario (alias API)")
def admin_editar_usuario(user_id: int, req: UserUpdateRequest, admin: Dict[str, Any] = Depends(verify_admin)):
    """
    Permite al administrador modificar el nombre de usuario, correo, contraseña y/o rol de cualquier cuenta.
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
            role=req.role,
            email=req.email
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    resp = {
        "mensaje": f"Usuario '{user_actualizado['username']}' actualizado exitosamente.",
        "user": {
            "id": user_actualizado["id"],
            "username": user_actualizado["username"],
            "role": user_actualizado["role"],
            "db_name": user_actualizado["db_name"],
            "email": user_actualizado.get("email")
        }
    }

    # Si se modificó la cuenta activa del admin, renovar su JWT
    if user_id == admin["id"]:
        nuevo_token = create_access_token({
            "sub": str(user_actualizado["id"]),
            "username": user_actualizado["username"],
            "role": user_actualizado["role"],
            "db_name": user_actualizado["db_name"],
            "email": user_actualizado.get("email")
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
    stats = master_db.get_admin_stats(ahora_local())
    from email_service import esta_configurado_servicio_correo
    stats["email_service_configured"] = esta_configurado_servicio_correo()
    return stats

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
    trans = cursor.execute("SELECT * FROM transacciones WHERE id = ?", (id_transaccion,)).fetchone()
    if not trans:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")

    desc = (trans["descripcion"] or "").strip()
    if desc.startswith("Ahorro destinado a:") or desc.startswith("Retiro de ahorro:"):
        raise HTTPException(
            status_code=400,
            detail="Este movimiento está vinculado a un sobre o meta de ahorro. Para modificarlo o retirar los fondos, utiliza los controles (+) o (-) dentro de la sección Metas / Apartados."
        )

    cursor.execute("DELETE FROM transacciones WHERE id = ?", (id_transaccion,))
    conn.commit()
    return {"mensaje": "Transacción eliminada"}

@app.put("/api/transacciones/{id_transaccion}", summary="Editar movimiento")
def actualizar_transaccion(id_transaccion: int, t: TransaccionUpdate, conn: sqlite3.Connection = Depends(get_tenant_db)):
    cursor = conn.cursor()
    trans = cursor.execute("SELECT * FROM transacciones WHERE id = ?", (id_transaccion,)).fetchone()
    if not trans:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")

    desc = (trans["descripcion"] or "").strip()
    if desc.startswith("Ahorro destinado a:") or desc.startswith("Retiro de ahorro:"):
        if (t.monto is not None and round(float(t.monto), 2) != round(float(trans["monto"]), 2)) or (t.tipo is not None and t.tipo != trans["tipo"]):
            raise HTTPException(
                status_code=400,
                detail="No puedes alterar el monto ni el tipo de un movimiento vinculado a un apartado de ahorro. Utiliza la sección Metas / Apartados."
            )

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
    except sqlite3.IntegrityError:
        conn.rollback()
        raise HTTPException(status_code=400, detail="Ya existe un apartado con ese nombre.")
    except Exception:
        conn.rollback()
        raise HTTPException(status_code=500, detail="Error interno al registrar el apartado.")

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

    saldo_actual = round(float(apartado["monto_actual"] or 0), 2)
    if saldo_actual > 0:
        raise HTTPException(
            status_code=400,
            detail=f"No puedes eliminar un apartado con saldo disponible (${saldo_actual:.2f}). Retira los fondos al balance disponible primero."
        )
        
    cursor.execute('DELETE FROM apartados WHERE id = ?', (apartado_id,))
    conn.commit()
    return {"status": "ok", "mensaje": "Apartado eliminado"}

@app.post("/api/apartados/{apartado_id}/movimiento", summary="Depositar o retirar en un apartado")
def movimiento_apartado(apartado_id: int, mov: MovimientoApartado, conn: sqlite3.Connection = Depends(get_tenant_db)):
    # Transacción inmediata para evitar condiciones de carrera en saldos concurrentes
    conn.execute("BEGIN IMMEDIATE")
    cursor = conn.cursor()
    try:
        apartado = cursor.execute('SELECT * FROM apartados WHERE id = ?', (apartado_id,)).fetchone()
        if not apartado:
            conn.rollback()
            raise HTTPException(status_code=404, detail="Apartado no encontrado")
            
        monto_actual = round(float(apartado['monto_actual'] or 0), 2)
        fecha_hoy = ahora_local().strftime('%Y-%m-%d')
        
        if mov.accion == 'depositar':
            ingresos_row = cursor.execute("SELECT SUM(monto) as total FROM transacciones WHERE tipo='ingreso'").fetchone()
            gastos_row = cursor.execute("SELECT SUM(monto) as total FROM transacciones WHERE tipo='gasto'").fetchone()
            
            total_ingresos = float(ingresos_row['total']) if (ingresos_row and ingresos_row['total']) else 0.0
            total_gastos = float(gastos_row['total']) if (gastos_row and gastos_row['total']) else 0.0
            balance_disponible = round(total_ingresos - total_gastos, 2)
            
            if round(mov.monto, 2) > balance_disponible:
                conn.rollback()
                raise HTTPException(
                    status_code=400, 
                    detail=f"No puedes guardar dinero que no tienes. Tu balance disponible es de ${balance_disponible:.2f}"
                )
                
            nuevo_saldo = round(monto_actual + mov.monto, 2)
            desc = f"Ahorro destinado a: {apartado['nombre']}"
            cursor.execute(
                'INSERT INTO transacciones (fecha, monto, tipo, categoria_id, descripcion) VALUES (?, ?, ?, ?, ?)',
                (fecha_hoy, mov.monto, 'gasto', 1, desc)
            )
            
        elif mov.accion == 'retirar':
            if round(mov.monto, 2) > monto_actual:
                conn.rollback()
                raise HTTPException(status_code=400, detail="No puedes retirar más de lo que hay en este apartado")
            
            nuevo_saldo = round(monto_actual - mov.monto, 2)
            desc = f"Retiro de ahorro: {apartado['nombre']}"
            cursor.execute(
                'INSERT INTO transacciones (fecha, monto, tipo, categoria_id, descripcion) VALUES (?, ?, ?, ?, ?)',
                (fecha_hoy, mov.monto, 'ingreso', 1, desc)
            )
        
        cursor.execute('UPDATE apartados SET monto_actual = ? WHERE id = ?', (nuevo_saldo, apartado_id))
        conn.commit()
        return {"status": "ok", "nuevo_saldo": nuevo_saldo}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail="Error inesperado al procesar el movimiento del apartado.")

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

    pendientes = []
    for fila in filas:
        t = fila["ticker"]
        precio, moneda = consultar_precio_y_moneda_mercado(t)
        if precio is not None:
            moneda_actualizada = moneda or ("MXN" if t.endswith(".MX") else "USD")
            pendientes.append((precio, moneda_actualizada, fila["id"]))
            actualizados.append({"ticker": t, "precio": precio, "moneda": moneda_actualizada})
        else:
            no_actualizados.append(t)

    if pendientes:
        cursor.executemany(
            """
            UPDATE inversiones 
            SET precio_actual = ?, moneda = ?, actualizado_en = CURRENT_TIMESTAMP 
            WHERE id = ?
            """,
            pendientes
        )
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

@app.get("/api/public/tipo-cambio", summary="Consultar tipos de cambio públicos")
def get_tipo_cambio_publico():
    """Retorna las tasas de cambio de moneda (MXN/USD) sin requerir autenticación para la página de presentación."""
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
def descargar_backup(background_tasks: BackgroundTasks, current_user: Dict[str, Any] = Depends(verify_token)):
    """Descarga una copia consistente en SQLite propio del usuario autenticado incluyendo cambios en WAL."""
    db_name = current_user.get("db_name", "user_1.db")
    db_path = get_tenant_path(db_name)
    if not os.path.exists(db_path):
        raise HTTPException(status_code=404, detail="Base de datos del usuario no encontrada.")
        
    fecha_str = ahora_local().strftime("%Y%m%d_%H%M%S")
    username_safe = "".join(c for c in current_user.get("username", "user") if c.isalnum() or c in ("-", "_"))
    
    # Crear respaldo consistente usando la API de backup de SQLite (consolida páginas de WAL)
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".db")
    os.close(tmp_fd)
    
    src = get_tenant_conn(db_name)
    try:
        dst = sqlite3.connect(tmp_path)
        src.backup(dst)
        dst.close()
    finally:
        src.close()
        
    background_tasks.add_task(os.unlink, tmp_path)
    
    return FileResponse(
        tmp_path,
        filename=f"finanzas_{username_safe}_{fecha_str}.db",
        media_type="application/octet-stream"
    )

@app.post("/api/restore", summary="Restaurar base de datos individual del tenant")
async def restaurar_backup(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(verify_token)
):
    """
    Restaura la base de datos SQLite del tenant autenticado (administrador o usuario normal)
    a partir de un archivo de respaldo .db subido.
    Aplica controles estrictos de seguridad y validación:
    1. Límite de tamaño máximo (50 MB).
    2. Cabecera válida SQLite 3 ('SQLite format 3\\x00').
    3. PRAGMA integrity_check.
    4. Verificación y migración del esquema financiero (init_tenant_db).
    5. Copia de seguridad preventiva (.bak) antes del reemplazo.
    """
    filename = file.filename or ""
    if not (filename.lower().endswith(".db") or filename.lower().endswith(".sqlite") or filename.lower().endswith(".sqlite3")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo seleccionado debe ser una base de datos SQLite válida con extensión .db."
        )

    MAX_SIZE = 50 * 1024 * 1024
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo excede el tamaño máximo permitido (50 MB)."
        )
        
    if len(content) < 100 or content[:16] != b"SQLite format 3\x00":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo proporcionado no es una base de datos SQLite válida o está dañado."
        )

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".db")
    try:
        with os.fdopen(tmp_fd, "wb") as f_tmp:
            f_tmp.write(content)

        # 1. Comprobar integridad con PRAGMA integrity_check
        test_conn = sqlite3.connect(tmp_path, timeout=5.0)
        try:
            cursor_test = test_conn.cursor()
            res_integrity = cursor_test.execute("PRAGMA integrity_check;").fetchone()
            if not res_integrity or res_integrity[0] != "ok":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="La base de datos presenta errores de integridad interna o corrupción."
                )

            # 2. Comprobar que contiene el esquema de la aplicación
            tables_row = cursor_test.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name IN ('transacciones', 'apartados', 'inversiones', 'categorias')"
            ).fetchone()
            if not tables_row or tables_row[0] < 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El archivo no corresponde a un respaldo válido de la aplicación de finanzas."
                )
        finally:
            test_conn.close()

        # 3. Aplicar migraciones defensivas a la BD temporal
        init_tenant_db(tmp_path)

        # 4. Copia de seguridad automática preventiva de la BD actual
        db_name = current_user.get("db_name", "user_1.db")
        target_path = get_tenant_path(db_name)
        if os.path.exists(target_path):
            bak_path = target_path + ".bak"
            try:
                shutil.copy2(target_path, bak_path)
            except Exception:
                pass

        # 5. Reemplazo seguro mediante SQLite backup API
        src = sqlite3.connect(tmp_path)
        dst = get_tenant_conn(db_name)
        try:
            src.backup(dst)
        finally:
            src.close()
            dst.close()

        # 6. Re-aplicar esquema final en la base destino
        init_tenant_db(target_path)

        return {
            "status": "ok",
            "mensaje": f"Base de datos de '{current_user['username']}' restaurada con éxito.",
            "archivo": filename
        }

    finally:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

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
    username_safe = "".join(c for c in current_user.get("username", "user") if c.isalnum() or c in ("-", "_"))
    nombre_archivo = f"reporte_{username_safe}_{moneda_base.upper()}_{fecha_str}.xlsx"
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{nombre_archivo}"'
        }
    )
