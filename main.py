"""
main.py - Servidor Principal de la Aplicación de Finanzas Personales Multi-Tenant

Este módulo implementa:
1. Arquitectura Multi-Tenant Dinámica con aislamiento físico de base de datos por usuario (SQLite).
2. Autenticación y Autorización basada en JSON Web Tokens (JWT).
3. Panel de Administración de Usuarios con control de acceso por roles (RBAC) y métricas KPI.
4. Endpoints financieros transparentes (gastos, apartados, inversiones, rendimientos y cotizaciones).
5. Exportación de reportes a Excel (.xlsx) y respaldos físicos de base de datos por tenant.
"""

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Literal, Optional
import os

from database import (
    ensure_tenant_directories
)
import master_db
from security import (
    hash_password
)
from routers import auth, admin, movimientos, apartados, inversiones, respaldo

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

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(movimientos.router)
app.include_router(apartados.router)
app.include_router(inversiones.router)
app.include_router(respaldo.router)

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
