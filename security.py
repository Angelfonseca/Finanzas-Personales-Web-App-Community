"""
security.py - Capa de Seguridad, Criptografía y Middleware JWT para FastAPI

Este módulo implementa:
1. Hashing seguro de contraseñas con bcrypt (salt automático).
2. Generación y verificación de tokens JWT (algoritmo HS256).
3. Dependencias de seguridad para FastAPI:
   - verify_token: Valida el JWT y verifica que el usuario permanezca activo en master_db.
   - verify_admin: Valida que el rol del usuario sea estrictamente 'admin'.
   - get_tenant_db: Inyecta la conexión a la base de datos específica del tenant autenticado.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Generator
import sqlite3
import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from database import get_tenant_conn
import master_db

# Clave secreta para firma de tokens JWT (puede sobreescribirse mediante variable de entorno)
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "finanzas_secret_key_super_segura_2026_jwt_token_sign")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 8

# Esquema OAuth2 con auto_error=False para personalizar la respuesta 401
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

def hash_password(plain_password: str) -> str:
    """Genera un hash seguro utilizando bcrypt con salt automático."""
    pwd_bytes = plain_password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica si una contraseña en texto plano coincide con el hash almacenado."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Genera un token JWT firmado.
    Incluye en los claims: sub (user_id en string), username, role, db_name y timestamp exp.
    """
    to_encode = data.copy()
    if "sub" in to_encode:
        to_encode["sub"] = str(to_encode["sub"])
    now_utc = datetime.now(timezone.utc)
    if expires_delta:
        expire = now_utc + expires_delta
    else:
        expire = now_utc + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
        
    to_encode.update({
        "exp": expire,
        "iat": now_utc
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decodifica y valida la firma y vigencia de un token JWT."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except (jwt.PyJWTError, Exception):
        return None

async def verify_token(token: Optional[str] = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """
    Dependencia de seguridad que autentica al usuario:
    1. Verifica la presencia y firma del token Bearer.
    2. Comprueba la existencia y estado activo (is_active == 1) en master_db.
    3. Retorna la información actualizada del usuario.
    """
    cred_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales de autenticación inválidas o expiradas.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if not token:
        raise cred_exception
        
    payload = decode_access_token(token)
    if not payload:
        raise cred_exception
        
    user_id = payload.get("sub")
    if not user_id:
        raise cred_exception
        
    try:
        user_id_int = int(user_id)
    except ValueError:
        raise cred_exception
        
    # Verificar en master_db para revocar acceso inmediato si fue desactivado
    user = master_db.get_user_by_id(user_id_int)
    if not user:
        raise cred_exception
        
    if not user.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu cuenta ha sido desactivada por el administrador."
        )
        
    return {
        "id": user["id"],
        "sub": str(user["id"]),
        "username": user["username"],
        "role": user["role"],
        "db_name": user["db_name"],
        "is_active": user["is_active"]
    }

async def verify_admin(current_user: Dict[str, Any] = Depends(verify_token)) -> Dict[str, Any]:
    """Dependencia que valida que el usuario autenticado posea estrictamente el rol 'admin'."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso restringido exclusivamente a administradores."
        )
    return current_user

def get_tenant_db(current_user: Dict[str, Any] = Depends(verify_token)) -> Generator[sqlite3.Connection, None, None]:
    """
    Dependencia FastAPI que resuelve dinámicamente la conexión a la base de datos
    específica del tenant autenticado ('data/tenants/{db_name}').
    """
    db_name = current_user.get("db_name", "user_1.db")
    conn = get_tenant_conn(db_name)
    try:
        yield conn
    finally:
        conn.close()
