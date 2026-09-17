from fastapi import FastAPI, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Literal, Optional
import sqlite3
from datetime import datetime
from database import init_db

app = FastAPI(title="Finanzas Personales API", version="1.0")

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def leer_raiz():
    return FileResponse("static/index.html")

# --- MODELOS PYDANTIC ---

class Transaccion(BaseModel):
    fecha: str
    monto: float
    tipo: str
    categoria_id: Optional[int] = None
    descripcion: Optional[str] = None

class ApartadoCreate(BaseModel):
    nombre: str
    tipo: Literal['libre', 'meta']
    meta_monto: Optional[float] = None

class MovimientoApartado(BaseModel):
    monto: float = Field(..., gt=0)
    accion: Literal['depositar', 'retirar']

# --- HELPER CONEXIÓN ---

def get_db():
    conn = sqlite3.connect("finanzas.db")
    conn.row_factory = sqlite3.Row
    return conn

@app.on_event("startup")
def startup_event():
    init_db()

# --- ENDPOINTS TRANSACCIONES ---

@app.post("/api/transacciones")
def crear_transaccion(t: Transaccion):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO transacciones (fecha, monto, tipo, categoria_id, descripcion) 
        VALUES (?, ?, ?, ?, ?)
        """,
        (t.fecha, t.monto, t.tipo, t.categoria_id, t.descripcion)
    )
    conn.commit()
    conn.close()
    return {"mensaje": "Transacción guardada con éxito"}

@app.delete("/api/transacciones/{id_transaccion}")
def eliminar_transaccion(id_transaccion: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transacciones WHERE id = ?", (id_transaccion,))
    conn.commit()
    conn.close()
    return {"mensaje": "Transacción eliminada"}

@app.get("/api/resumen")
def obtener_resumen():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(monto) as total FROM transacciones WHERE tipo='ingreso'")
    ingresos = cursor.fetchone()["total"] or 0.0
    
    cursor.execute("SELECT SUM(monto) as total FROM transacciones WHERE tipo='gasto'")
    gastos = cursor.fetchone()["total"] or 0.0
    
    conn.close()
    return {
        "ingresos": ingresos,
        "gastos": gastos,
        "balance": ingresos - gastos
    }

@app.get("/api/resumen-mensual")
def resumen_mensual():
    conn = get_db()
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
    conn.close()
    return [dict(fila) for fila in filas]

@app.get("/api/transacciones")
def listar_transacciones():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, fecha, monto, tipo, descripcion FROM transacciones ORDER BY fecha DESC, id DESC")
    filas = cursor.fetchall()
    conn.close()
    return [dict(fila) for fila in filas]

# --- ENDPOINTS APARTADOS Y METAS (FASE 6.2) ---

@app.post("/api/apartados", status_code=status.HTTP_201_CREATED)
def crear_apartado(item: ApartadoCreate):
    if item.tipo == 'meta' and (item.meta_monto is None or item.meta_monto <= 0):
        raise HTTPException(status_code=400, detail="Una meta requiere un monto objetivo mayor a cero.")
    
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO apartados (nombre, tipo, monto_actual, meta_monto) VALUES (?, ?, 0.0, ?)",
            (item.nombre, item.tipo, item.meta_monto if item.tipo == 'meta' else None)
        )
        conn.commit()
        nuevo_id = cursor.lastrowid
        conn.close()
        return {"id": nuevo_id, "mensaje": "Apartado creado exitosamente"}
    except Exception:
        conn.close()
        raise HTTPException(status_code=400, detail="Ya existe un apartado con ese nombre.")

@app.get("/api/apartados")
def listar_apartados():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM apartados ORDER BY id DESC")
    filas = cursor.fetchall()
    conn.close()
    
    resultado = []
    for fila in filas:
        item = dict(fila)
        if item["tipo"] == "meta" and item["meta_monto"] and item["meta_monto"] > 0:
            item["porcentaje"] = round((item["monto_actual"] / item["meta_monto"]) * 100, 2)
        else:
            item["porcentaje"] = None
        resultado.append(item)
    return resultado

@app.delete("/api/apartados/{apartado_id}")
def eliminar_apartado(apartado_id: int):
    conn = get_db()  # <-- Usamos tu función correcta aquí
    cursor = conn.cursor()
    
    # Verificamos si existe
    apartado = cursor.execute('SELECT * FROM apartados WHERE id = ?', (apartado_id,)).fetchone()
    if not apartado:
        conn.close()
        raise HTTPException(status_code=404, detail="Apartado no encontrado")
        
    cursor.execute('DELETE FROM apartados WHERE id = ?', (apartado_id,))
    conn.commit()
    conn.close()
    
    return {"status": "ok", "mensaje": "Apartado eliminado"}

@app.post("/api/apartados/{apartado_id}/movimiento")
def movimiento_apartado(apartado_id: int, mov: MovimientoApartado):
    conn = get_db()
    cursor = conn.cursor()
    
    apartado = cursor.execute('SELECT * FROM apartados WHERE id = ?', (apartado_id,)).fetchone()
    if not apartado:
        conn.close()
        raise HTTPException(status_code=404, detail="Apartado no encontrado")
        
    nuevo_saldo = apartado['monto_actual']
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
    
    if mov.accion == 'depositar':
        # 1. Calcular el balance real disponible (Ingresos - Gastos totales)
        ingresos_row = cursor.execute("SELECT SUM(monto) as total FROM transacciones WHERE tipo='ingreso'").fetchone()
        gastos_row = cursor.execute("SELECT SUM(monto) as total FROM transacciones WHERE tipo='gasto'").fetchone()
        
        total_ingresos = ingresos_row['total'] if ingresos_row and ingresos_row['total'] else 0.0
        total_gastos = gastos_row['total'] if gastos_row and gastos_row['total'] else 0.0
        balance_disponible = total_ingresos - total_gastos
        
        # 2. Bloquear si intentas guardar dinero que no tienes
        if mov.monto > balance_disponible:
            conn.close()
            raise HTTPException(
                status_code=400, 
                detail=f"No puedes guardar dinero que no tienes. Tu balance disponible es de ${balance_disponible:.2f}"
            )
            
        # 3. Si hay dinero, procedemos con el depósito
        nuevo_saldo += mov.monto
        desc = f"Ahorro destinado a: {apartado['nombre']}"
        cursor.execute(
            'INSERT INTO transacciones (fecha, monto, tipo, categoria_id, descripcion) VALUES (?, ?, ?, ?, ?)',
            (fecha_hoy, mov.monto, 'gasto', 1, desc)
        )
        
    elif mov.accion == 'retirar':
        if mov.monto > nuevo_saldo:
            conn.close()
            raise HTTPException(status_code=400, detail="No puedes retirar más de lo que hay en este apartado")
        
        nuevo_saldo -= mov.monto
        desc = f"Retiro de ahorro: {apartado['nombre']}"
        cursor.execute(
            'INSERT INTO transacciones (fecha, monto, tipo, categoria_id, descripcion) VALUES (?, ?, ?, ?, ?)',
            (fecha_hoy, mov.monto, 'ingreso', 1, desc)
        )
    
    # Actualizar el saldo del apartado
    cursor.execute('UPDATE apartados SET monto_actual = ? WHERE id = ?', (nuevo_saldo, apartado_id))
    conn.commit()
    conn.close()
    
    return {"status": "ok", "nuevo_saldo": nuevo_saldo}

    cursor.execute("UPDATE apartados SET monto_actual = ? WHERE id = ?", (nuevo_monto, apartado_id))
    conn.commit()
    conn.close()
    return {"id": apartado_id, "nuevo_monto": nuevo_monto, "mensaje": "Movimiento realizado con éxito."}
