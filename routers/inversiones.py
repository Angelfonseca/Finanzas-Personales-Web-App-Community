"""routers/inversiones.py - Inversiones bursátiles, cotizaciones y tipos de cambio."""

from fastapi import APIRouter
from fastapi import HTTPException, status, Depends
from pydantic import BaseModel, Field
from typing import Literal, Optional, Dict, Any
import sqlite3

from finanzas_core import ahora_local, valorar_posiciones
from mercado import consultar_precio_y_moneda_mercado, buscar_tickers_mercado, obtener_tasas_cambio, cotizar_varios
from security import (
    verify_token,
    get_tenant_db
)

router = APIRouter()

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
# ENDPOINTS MULTI-TENANT: INVERSIONES & ASSET ALLOCATION
# =============================================================================

@router.get("/api/inversiones", summary="Listar portafolio con rendimientos del tenant")
def listar_inversiones(moneda_base: str = "MXN", conn: sqlite3.Connection = Depends(get_tenant_db)):
    cursor = conn.cursor()
    filas = cursor.execute("SELECT * FROM inversiones ORDER BY id DESC").fetchall()
    tasa_usd_mxn = obtener_tasas_cambio().get("MXN", 18.40)
    return valorar_posiciones(filas, moneda_base, tasa_usd_mxn)

@router.post("/api/inversiones", status_code=status.HTTP_201_CREATED, summary="Registrar posición bursátil")
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

@router.put("/api/inversiones/{inversion_id}", summary="Actualizar posición bursátil")
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

@router.delete("/api/inversiones/{inversion_id}", summary="Eliminar posición bursátil")
def eliminar_inversion(inversion_id: int, conn: sqlite3.Connection = Depends(get_tenant_db)):
    cursor = conn.cursor()
    inv = cursor.execute("SELECT * FROM inversiones WHERE id = ?", (inversion_id,)).fetchone()
    if not inv:
        raise HTTPException(status_code=404, detail="Inversión no encontrada")

    cursor.execute("DELETE FROM inversiones WHERE id = ?", (inversion_id,))
    conn.commit()
    return {"mensaje": "Inversión eliminada."}

@router.post("/api/inversiones/sincronizar", summary="Sincronizar cotizaciones en vivo")
def sincronizar_precios(conn: sqlite3.Connection = Depends(get_tenant_db)):
    cursor = conn.cursor()
    filas = cursor.execute("SELECT id, ticker FROM inversiones").fetchall()
    actualizados = []
    no_actualizados = []

    pendientes = []
    cotizaciones = cotizar_varios([fila["ticker"] for fila in filas])
    for fila in filas:
        t = fila["ticker"]
        precio, moneda = cotizaciones[t]
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

@router.get("/api/inversiones/cotizar/{ticker}", summary="Cotización individual en tiempo real")
def cotizar_ticker(ticker: str, _user: Dict[str, Any] = Depends(verify_token)):
    precio, moneda = consultar_precio_y_moneda_mercado(ticker)
    if precio is None:
        raise HTTPException(status_code=404, detail=f"No se pudo consultar la cotización para {ticker.upper()}")
    return {"ticker": ticker.upper(), "precio": precio, "moneda": moneda}

@router.get("/api/inversiones/buscar", summary="Buscador predictivo de tickers")
def api_buscar_ticker(q: str = "", _user: Dict[str, Any] = Depends(verify_token)):
    if not q or len(q.strip()) < 1:
        return []
    return buscar_tickers_mercado(q)

# =============================================================================
# TIPOS DE CAMBIO (ver mercado.py)
# =============================================================================

@router.get("/api/tipo-cambio", summary="Consultar tipos de cambio vigentes")
def get_tipo_cambio(_user: Dict[str, Any] = Depends(verify_token)):
    tasas = obtener_tasas_cambio()
    return {
        "base": "USD",
        "tasas": tasas,
        "actualizado_en": ahora_local().strftime("%Y-%m-%d %H:%M:%S")
    }

@router.get("/api/public/tipo-cambio", summary="Consultar tipos de cambio públicos")
def get_tipo_cambio_publico():
    """Retorna las tasas de cambio de moneda (MXN/USD) sin requerir autenticación para la página de presentación."""
    tasas = obtener_tasas_cambio()
    return {
        "base": "USD",
        "tasas": tasas,
        "actualizado_en": ahora_local().strftime("%Y-%m-%d %H:%M:%S")
    }
