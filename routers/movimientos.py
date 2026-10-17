"""routers/movimientos.py - Movimientos de caja y resúmenes patrimoniales."""

from fastapi import APIRouter
from fastapi import HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Literal, Optional
import sqlite3

from finanzas_core import ahora_local, calcular_resumen, materializar_recurrentes
from mercado import obtener_tasas_cambio
from security import (
    get_tenant_db
)

router = APIRouter()

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


# =============================================================================
# ENDPOINTS MULTI-TENANT: MOVIMIENTOS (TRANSACCIONES DE CAJA)
# =============================================================================

@router.post("/api/transacciones", summary="Registrar nuevo movimiento")
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

@router.delete("/api/transacciones/{id_transaccion}", summary="Eliminar movimiento")
def eliminar_transaccion(id_transaccion: int, conn: sqlite3.Connection = Depends(get_tenant_db)):
    cursor = conn.cursor()
    trans = cursor.execute("SELECT * FROM transacciones WHERE id = ?", (id_transaccion,)).fetchone()
    if not trans:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")

    if trans["apartado_id"] is not None:
        raise HTTPException(
            status_code=400,
            detail="Este movimiento está vinculado a un sobre o meta de ahorro. Para modificarlo o retirar los fondos, utiliza los controles (+) o (-) dentro de la sección Metas / Apartados."
        )

    cursor.execute("DELETE FROM transacciones WHERE id = ?", (id_transaccion,))
    conn.commit()
    return {"mensaje": "Transacción eliminada"}

@router.put("/api/transacciones/{id_transaccion}", summary="Editar movimiento")
def actualizar_transaccion(id_transaccion: int, t: TransaccionUpdate, conn: sqlite3.Connection = Depends(get_tenant_db)):
    cursor = conn.cursor()
    trans = cursor.execute("SELECT * FROM transacciones WHERE id = ?", (id_transaccion,)).fetchone()
    if not trans:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")

    if trans["apartado_id"] is not None:
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

@router.get("/api/resumen", summary="Resumen patrimonial consolidado del tenant")
def obtener_resumen(moneda_base: str = "MXN", conn: sqlite3.Connection = Depends(get_tenant_db)):
    hoy = ahora_local().date()
    materializar_recurrentes(conn, hoy)
    tasa_usd_mxn = obtener_tasas_cambio().get("MXN", 18.40)
    return calcular_resumen(conn, moneda_base, tasa_usd_mxn, hoy)

@router.get("/api/resumen-mensual", summary="Historial agrupado por mes")
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

@router.get("/api/transacciones", summary="Listar todas las transacciones del tenant")
def listar_transacciones(conn: sqlite3.Connection = Depends(get_tenant_db)):
    cursor = conn.cursor()
    cursor.execute("SELECT id, fecha, monto, tipo, descripcion FROM transacciones ORDER BY fecha DESC, id DESC")
    filas = cursor.fetchall()
    return [dict(fila) for fila in filas]
