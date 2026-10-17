"""routers/recurrentes.py - Ingresos y gastos fijos, y compras a meses (MSI)."""

import sqlite3
from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from finanzas_core import (
    ahora_local,
    deuda_pendiente,
    materializar_recurrentes,
    mensualizar,
    primera_fecha_quincenal,
)
from routers.movimientos import validar_categoria
from security import get_tenant_db

router = APIRouter()


class RecurrenteCreate(BaseModel):
    descripcion: str = Field(..., min_length=1, max_length=100)
    tipo: Literal['ingreso', 'gasto'] = 'gasto'
    frecuencia: Literal['semanal', 'quincenal', 'mensual'] = 'mensual'
    monto: Optional[float] = Field(None, gt=0, le=1e12, description="Monto por ocurrencia (fijos)")
    monto_total: Optional[float] = Field(None, gt=0, le=1e12, description="Monto total de la compra (MSI)")
    meses: Optional[int] = Field(None, ge=2, le=60, description="Número de meses (MSI)")
    fecha_inicio: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    categoria_id: Optional[int] = None


class RecurrenteUpdate(BaseModel):
    descripcion: Optional[str] = Field(None, min_length=1, max_length=100)
    monto: Optional[float] = Field(None, gt=0, le=1e12)
    activo: Optional[bool] = None
    categoria_id: Optional[int] = None


def _categoria_compras_a_meses(cursor) -> int:
    fila = cursor.execute(
        "SELECT id FROM categorias WHERE nombre = 'Compras a meses' AND tipo = 'gasto' LIMIT 1"
    ).fetchone()
    return fila["id"] if fila else 1


def _serializar(fila) -> dict:
    d = dict(fila)
    es_msi = d["total_cuotas"] is not None
    d["es_msi"] = es_msi
    d["deuda_pendiente"] = deuda_pendiente(fila)
    d["mensual"] = round(mensualizar(d["monto"], d["frecuencia"]), 2)
    d["progreso_pct"] = round(d["cuotas_generadas"] / d["total_cuotas"] * 100, 1) if es_msi else None
    d["activo"] = bool(d["activo"])
    return d


@router.get("/api/recurrentes", summary="Listar fijos y compras a meses")
def listar_recurrentes(conn: sqlite3.Connection = Depends(get_tenant_db)):
    cursor = conn.cursor()
    filas = cursor.execute("SELECT * FROM recurrentes ORDER BY activo DESC, proxima_fecha ASC, id ASC").fetchall()
    return [_serializar(f) for f in filas]


@router.post("/api/recurrentes", status_code=201, summary="Crear fijo o compra a meses")
def crear_recurrente(req: RecurrenteCreate, conn: sqlite3.Connection = Depends(get_tenant_db)):
    cursor = conn.cursor()
    try:
        fecha = date.fromisoformat(req.fecha_inicio)
    except ValueError:
        raise HTTPException(status_code=400, detail="La fecha de inicio no es válida.")

    if req.meses:
        if req.monto_total is None:
            raise HTTPException(status_code=400, detail="Una compra a meses requiere el monto total.")
        tipo, frecuencia = 'gasto', 'mensual'
        total_cuotas = req.meses
        monto = round(req.monto_total / req.meses, 2)
        monto_total = req.monto_total
        categoria_id = req.categoria_id or _categoria_compras_a_meses(cursor)
    else:
        if req.monto is None:
            raise HTTPException(status_code=400, detail="Un fijo requiere el monto por ocurrencia.")
        tipo, frecuencia = req.tipo, req.frecuencia
        total_cuotas = None
        monto = req.monto
        monto_total = None
        categoria_id = req.categoria_id or 1

    validar_categoria(cursor, categoria_id)
    proxima = primera_fecha_quincenal(fecha) if frecuencia == 'quincenal' else fecha
    cursor.execute(
        """
        INSERT INTO recurrentes (descripcion, tipo, monto, frecuencia, dia, proxima_fecha,
                                 total_cuotas, cuotas_generadas, monto_total, categoria_id, activo)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, 1)
        """,
        (req.descripcion.strip(), tipo, monto, frecuencia, fecha.day, proxima.isoformat(),
         total_cuotas, monto_total, categoria_id)
    )
    nuevo_id = cursor.lastrowid
    conn.commit()
    materializar_recurrentes(conn, ahora_local().date())
    fila = cursor.execute("SELECT * FROM recurrentes WHERE id = ?", (nuevo_id,)).fetchone()
    return _serializar(fila)


@router.patch("/api/recurrentes/{recurrente_id}", summary="Editar fijo o compra a meses")
def editar_recurrente(recurrente_id: int, req: RecurrenteUpdate, conn: sqlite3.Connection = Depends(get_tenant_db)):
    cursor = conn.cursor()
    fila = cursor.execute("SELECT * FROM recurrentes WHERE id = ?", (recurrente_id,)).fetchone()
    if not fila:
        raise HTTPException(status_code=404, detail="Registro no encontrado.")
    es_msi = fila["total_cuotas"] is not None
    if req.monto is not None and es_msi:
        raise HTTPException(status_code=400, detail="Una compra a meses no admite cambiar el monto por cuota.")
    validar_categoria(cursor, req.categoria_id)

    campos, valores = [], []
    if req.descripcion is not None:
        campos.append("descripcion = ?"); valores.append(req.descripcion.strip())
    if req.monto is not None:
        campos.append("monto = ?"); valores.append(req.monto)
    if req.activo is not None:
        campos.append("activo = ?"); valores.append(1 if req.activo else 0)
    if req.categoria_id is not None:
        campos.append("categoria_id = ?"); valores.append(req.categoria_id)
    if campos:
        valores.append(recurrente_id)
        cursor.execute(f"UPDATE recurrentes SET {', '.join(campos)} WHERE id = ?", valores)
        conn.commit()
    fila = cursor.execute("SELECT * FROM recurrentes WHERE id = ?", (recurrente_id,)).fetchone()
    return _serializar(fila)


@router.delete("/api/recurrentes/{recurrente_id}", summary="Eliminar fijo o compra a meses")
def eliminar_recurrente(recurrente_id: int, conn: sqlite3.Connection = Depends(get_tenant_db)):
    cursor = conn.cursor()
    if not cursor.execute("SELECT 1 FROM recurrentes WHERE id = ?", (recurrente_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Registro no encontrado.")
    # Las transacciones ya generadas se conservan (ON DELETE SET NULL)
    cursor.execute("DELETE FROM recurrentes WHERE id = ?", (recurrente_id,))
    conn.commit()
    return {"mensaje": "Registro eliminado. Los movimientos ya generados se conservaron."}
