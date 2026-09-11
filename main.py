from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import sqlite3
from database import init_db

app = FastAPI(title="Finanzas Personales API", version="1.0")

app.mount("/static", StaticFiles(directory="static"), name="static")

class Transaccion(BaseModel):
    fecha: str
    monto: float
    tipo: str
    categoria_id: int = None
    descripcion: str = None

def get_db():
    conn = sqlite3.connect("finanzas.db")
    conn.row_factory = sqlite3.Row
    return conn

@app.on_event("startup")
def startup_event():
    init_db()

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
