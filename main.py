"""
main.py - Servidor Principal de la Aplicación de Finanzas Personales

Este módulo implementa la API RESTful completa con FastAPI y sirve la interfaz web estática.
Funcionalidades principales:
1. Control de Flujo de Efectivo (Ingresos, Gastos y Balances Mensuales).
2. Sistema de Sobres Virtuales y Metas de Ahorro (Apartados con protección de saldo).
3. Portafolio Bursátil e Inversiones (ETFs, Acciones, COTIZACIONES en vivo de Yahoo Finance).
4. Motor Multidivisa (Conversión dinámica entre MXN y USD con tipos de cambio en vivo y caché).
5. Sistema de Respaldos (Descarga de archivo SQLite) y Exportación a Excel (.xlsx) con Gráficas.
"""

from fastapi import FastAPI, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from typing import Literal, Optional
import json
import urllib.request
import urllib.parse
import sqlite3
import os
import time
from datetime import datetime
from database import init_db

# Inicialización de la aplicación FastAPI
app = FastAPI(
    title="Finanzas Personales API",
    description="API para la gestión patrimonial integral: gastos, ahorros, inversiones y exportación contable.",
    version="1.0"
)

# Montar carpeta de archivos estáticos (HTML, CSS, JavaScript del frontend)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", summary="Página principal")
def leer_raiz():
    """Sirve la interfaz gráfica SPA (Single Page Application) desde static/index.html."""
    return FileResponse("static/index.html")

def ahora_local() -> datetime:
    """
    Retorna la fecha y hora actual en la zona horaria de México (CST / UTC-6).
    
    Evita discrepancias de fecha cuando el contenedor Docker corre con hora UTC estándar,
    asegurando que los movimientos registrados reflejen el día local real del usuario.
    """
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Mexico_City"))
    except Exception:
        return datetime.now()

# =============================================================================
# MODELOS DE VALIDACIÓN PYDANTIC
# =============================================================================

class Transaccion(BaseModel):
    """Modelo de validación para registrar un nuevo movimiento de caja."""
    fecha: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Fecha en formato ISO YYYY-MM-DD")
    monto: float = Field(..., gt=0, description="Monto monetario positivo mayor a 0")
    tipo: Literal['gasto', 'ingreso'] = Field(..., description="Tipo de movimiento: gasto o ingreso")
    categoria_id: Optional[int] = Field(1, description="ID de categoría (por defecto 1: General)")
    descripcion: Optional[str] = Field(None, description="Nota o concepto opcional del movimiento")

class TransaccionUpdate(BaseModel):
    """Modelo de validación para editar un movimiento existente."""
    fecha: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="Nueva fecha ISO YYYY-MM-DD")
    monto: Optional[float] = Field(None, gt=0, description="Nuevo monto mayor a cero")
    tipo: Optional[Literal['gasto', 'ingreso']] = Field(None, description="Nuevo tipo de flujo")
    categoria_id: Optional[int] = Field(None, description="ID de categoría")
    descripcion: Optional[str] = Field(None, description="Nueva descripción")

class ApartadoCreate(BaseModel):
    """Modelo de validación para crear un nuevo sobre o meta de ahorro."""
    nombre: str = Field(..., min_length=1, description="Nombre único identificador del apartado")
    tipo: Literal['libre', 'meta'] = Field(..., description="Tipo: libre (sin tope) o meta (con objetivo)")
    meta_monto: Optional[float] = Field(None, description="Monto objetivo obligatorio si el tipo es meta")

class MovimientoApartado(BaseModel):
    """Modelo de validación para ingresar o retirar fondos de un sobre de ahorro."""
    monto: float = Field(..., gt=0, description="Cantidad a transferir mayor a 0")
    accion: Literal['depositar', 'retirar'] = Field(..., description="Operación: depositar o retirar")

class InversionCreate(BaseModel):
    """Modelo de validación para dar de alta una posición bursátil en el portafolio."""
    ticker: str = Field(..., min_length=1, description="Símbolo del activo (ej. VOO, AAPL, WALMEX.MX)")
    cantidad: float = Field(..., gt=0, description="Número de títulos o acciones")
    precio_promedio: float = Field(..., gt=0, description="Precio de compra ponderado en moneda original")
    precio_actual: Optional[float] = Field(None, description="Precio actual de mercado (opcional, se autocompleta)")
    moneda: Optional[str] = Field("USD", description="Moneda del activo: 'USD' o 'MXN'")

class InversionUpdate(BaseModel):
    """Modelo de validación para modificar títulos o costo promedio de una posición."""
    cantidad: Optional[float] = Field(None, gt=0, description="Nueva cantidad de títulos")
    precio_promedio: Optional[float] = Field(None, gt=0, description="Nuevo precio promedio de adquisición")
    precio_actual: Optional[float] = Field(None, gt=0, description="Nuevo precio actual de mercado")
    moneda: Optional[str] = Field(None, description="Divisa del activo ('USD' o 'MXN')")

# =============================================================================
# HELPER DE CONEXIÓN A BASE DE DATOS
# =============================================================================

def get_db() -> sqlite3.Connection:
    """
    Retorna una conexión a SQLite configurada con 15 segundos de timeout y row_factory dict-like.
    """
    conn = sqlite3.connect("finanzas.db", timeout=15.0)
    conn.row_factory = sqlite3.Row
    return conn

@app.on_event("startup")
def startup_event():
    """Ejecuta la inicialización de la base de datos y migraciones al arrancar FastAPI."""
    init_db()

# =============================================================================
# ENDPOINTS: GESTIÓN DE TRANSACCIONES (FLUJO DE EFECTIVO)
# =============================================================================

@app.post("/api/transacciones", summary="Registrar nuevo movimiento")
def crear_transaccion(t: Transaccion):
    """Registra una transacción de ingreso o gasto en la base de datos."""
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

@app.delete("/api/transacciones/{id_transaccion}", summary="Eliminar movimiento")
def eliminar_transaccion(id_transaccion: int):
    """Elimina una transacción existente por su ID. Lanza 404 si no se encuentra."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transacciones WHERE id = ?", (id_transaccion,))
    filas = cursor.rowcount
    conn.commit()
    conn.close()
    if filas == 0:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    return {"mensaje": "Transacción eliminada"}

@app.put("/api/transacciones/{id_transaccion}", summary="Editar movimiento")
def actualizar_transaccion(id_transaccion: int, t: TransaccionUpdate):
    """
    Actualiza selectivamente los campos modificados de una transacción existente.
    Conserva los valores anteriores si no se envían nuevos parámetros.
    """
    conn = get_db()
    cursor = conn.cursor()
    trans = cursor.execute("SELECT * FROM transacciones WHERE id = ?", (id_transaccion,)).fetchone()
    if not trans:
        conn.close()
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
    conn.close()
    return {"mensaje": "Transacción actualizada con éxito"}

@app.get("/api/resumen", summary="Resumen patrimonial consolidado")
def obtener_resumen(moneda_base: str = "MXN"):
    """
    Calcula las métricas consolidadas del patrimonio:
    - Balance disponible en efectivo (Ingresos - Gastos).
    - Total acumulado en sobres de ahorro y metas.
    - Valor total de mercado del portafolio bursátil con cotizaciones en vivo.
    - Patrimonio Neto unificado = Balance + Sobres + Inversiones.
    
    Aplica conversión automática multimoneda según la moneda base solicitada ('MXN' o 'USD').
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(monto) as total FROM transacciones WHERE tipo='ingreso'")
    ingresos = cursor.fetchone()["total"] or 0.0
    
    cursor.execute("SELECT SUM(monto) as total FROM transacciones WHERE tipo='gasto'")
    gastos = cursor.fetchone()["total"] or 0.0
    
    cursor.execute("SELECT SUM(monto_actual) as total FROM apartados")
    apartados = cursor.fetchone()["total"] or 0.0

    filas_inv = cursor.execute("SELECT cantidad, precio_actual, moneda FROM inversiones").fetchall()
    conn.close()

    # Obtener tipo de cambio en tiempo real (o desde caché)
    tasas = obtener_tasas_cambio()
    tasa_usd_mxn = tasas.get("MXN", 18.40)
    moneda_base_upper = moneda_base.upper()

    # Valorar cada posición bursátil en la moneda base seleccionada
    inversiones_total = 0.0
    for inv in filas_inv:
        cant = float(inv["cantidad"])
        p_act = float(inv["precio_actual"])
        m_act = (inv["moneda"] or "USD").upper()
        val = cant * p_act
        
        # Conversión de activos según divisa origen vs divisa base:
        # Activo USD -> Moneda Base MXN: multiplicar por tipo de cambio USD/MXN
        # Activo MXN -> Moneda Base USD: dividir entre tipo de cambio USD/MXN
        # Misma divisa: factor 1.0
        if m_act == "USD" and moneda_base_upper == "MXN":
            val *= tasa_usd_mxn
        elif m_act == "MXN" and moneda_base_upper == "USD":
            val /= tasa_usd_mxn if tasa_usd_mxn > 0 else 1.0

        inversiones_total += val

    # Las transacciones y apartados locales están denominados en pesos mexicanos (MXN).
    # Si la moneda solicitada es USD, se convierten dividiendo entre la tasa USD/MXN.
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
def resumen_mensual():
    """
    Agrupa ingresos y gastos por mes (formato YYYY-MM) para alimentar la gráfica
    de barras y el listado histórico cronológico descendente.
    """
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

@app.get("/api/transacciones", summary="Listar todas las transacciones")
def listar_transacciones():
    """Retorna la lista completa de transacciones ordenadas de la más reciente a la más antigua."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, fecha, monto, tipo, descripcion FROM transacciones ORDER BY fecha DESC, id DESC")
    filas = cursor.fetchall()
    conn.close()
    return [dict(fila) for fila in filas]

# =============================================================================
# ENDPOINTS: SOBRES VIRTUALES Y METAS DE AHORRO (APARTADOS)
# =============================================================================

@app.post("/api/apartados", status_code=status.HTTP_201_CREATED, summary="Crear apartado o meta")
def crear_apartado(item: ApartadoCreate):
    """
    Crea un nuevo sobre de ahorro.
    Valida que las metas tengan un monto objetivo estrictamente mayor a 0.
    Garantiza que no existan nombres duplicados.
    """
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

@app.get("/api/apartados", summary="Listar apartados con avance")
def listar_apartados():
    """
    Retorna la lista de apartados calculando el porcentaje de cumplimiento
    alcanzado en caso de tratarse de una meta con monto objetivo.
    """
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

@app.delete("/api/apartados/{apartado_id}", summary="Eliminar apartado")
def eliminar_apartado(apartado_id: int):
    """
    Elimina un apartado.
    Regla de Integridad Patrimonial: Bloquea la eliminación si el sobre aún tiene
    fondos acumulados (> 0), obligando al usuario a retirarlos primero para no
    perder rastro de ese dinero en el flujo de caja.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    apartado = cursor.execute('SELECT * FROM apartados WHERE id = ?', (apartado_id,)).fetchone()
    if not apartado:
        conn.close()
        raise HTTPException(status_code=404, detail="Apartado no encontrado")

    if apartado["monto_actual"] > 0:
        saldo = float(apartado["monto_actual"])
        conn.close()
        raise HTTPException(
            status_code=400,
            detail=f"No puedes eliminar un apartado con saldo disponible (${saldo:.2f}). Retira los fondos al balance disponible primero."
        )
        
    cursor.execute('DELETE FROM apartados WHERE id = ?', (apartado_id,))
    conn.commit()
    conn.close()
    
    return {"status": "ok", "mensaje": "Apartado eliminado"}

@app.post("/api/apartados/{apartado_id}/movimiento", summary="Depositar o retirar en un apartado")
def movimiento_apartado(apartado_id: int, mov: MovimientoApartado):
    """
    Ejecuta un depósito o retiro en un sobre de ahorro:
    - Al depositar: Valida que el usuario tenga balance libre disponible suficiente.
      Crea automáticamente una transacción de tipo 'gasto' para descontarlo de caja.
    - Al retirar: Valida que no se retire más de lo acumulado en el apartado.
      Crea automáticamente una transacción de tipo 'ingreso' para retornarlo a caja.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    apartado = cursor.execute('SELECT * FROM apartados WHERE id = ?', (apartado_id,)).fetchone()
    if not apartado:
        conn.close()
        raise HTTPException(status_code=404, detail="Apartado no encontrado")
        
    nuevo_saldo = apartado['monto_actual']
    fecha_hoy = ahora_local().strftime('%Y-%m-%d')
    
    if mov.accion == 'depositar':
        # 1. Calcular el balance real disponible en caja (Ingresos - Gastos)
        ingresos_row = cursor.execute("SELECT SUM(monto) as total FROM transacciones WHERE tipo='ingreso'").fetchone()
        gastos_row = cursor.execute("SELECT SUM(monto) as total FROM transacciones WHERE tipo='gasto'").fetchone()
        
        total_ingresos = ingresos_row['total'] if ingresos_row and ingresos_row['total'] else 0.0
        total_gastos = gastos_row['total'] if gastos_row and gastos_row['total'] else 0.0
        balance_disponible = total_ingresos - total_gastos
        
        # 2. Bloquear si se intenta apartar más dinero del disponible en caja
        if mov.monto > balance_disponible:
            conn.close()
            raise HTTPException(
                status_code=400, 
                detail=f"No puedes guardar dinero que no tienes. Tu balance disponible es de ${balance_disponible:.2f}"
            )
            
        # 3. Sumar al apartado y registrar la salida en el historial de transacciones
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
    
    # Persistir el nuevo saldo del apartado
    cursor.execute('UPDATE apartados SET monto_actual = ? WHERE id = ?', (nuevo_saldo, apartado_id))
    conn.commit()
    conn.close()
    
    return {"status": "ok", "nuevo_saldo": nuevo_saldo}

# =============================================================================
# MÓDULO DE INVERSIONES Y ASSET ALLOCATION (ETFs, ACCIONES Y COTIZACIONES)
# =============================================================================

def consultar_precio_y_moneda_mercado(ticker: str):
    """
    Consulta la cotización actual y divisa de un ticker directamente en la API de Yahoo Finance.
    
    Implementa:
    - Sanitización del símbolo (mayúsculas y sin espacios).
    - Doble endpoint con fallback automático (query1 y query2).
    - Headers con User-Agent moderno para evitar bloqueos por rate-limiting.
    - Detección automática de moneda (ej. activos con sufijo .MX asignados a MXN).
    
    Retorna: (precio: float | None, moneda: str)
    """
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
    """Consulta únicamente el valor numérico del precio de mercado de un ticker."""
    precio, _ = consultar_precio_y_moneda_mercado(ticker)
    return precio

@app.get("/api/inversiones", summary="Listar portafolio con rendimientos y Asset Allocation")
def listar_inversiones(moneda_base: str = "MXN"):
    """
    Calcula la valuación integral del portafolio bursátil:
    - Capital invertido en divisa de origen y convertido a moneda base.
    - Valor actual de mercado.
    - PnL (Ganancia / Pérdida) monetario y porcentual por activo y agregado.
    - Ponderación porcentual de Asignación de Activos (Asset Allocation % Peso).
    """
    conn = get_db()
    cursor = conn.cursor()
    filas = cursor.execute("SELECT * FROM inversiones ORDER BY id DESC").fetchall()
    conn.close()

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

        # Factor de conversión hacia la divisa base del reporte
        if moneda_activo == "USD" and moneda_base_upper == "MXN":
            factor = tasa_usd_mxn
        elif moneda_activo == "MXN" and moneda_base_upper == "USD":
            factor = (1.0 / tasa_usd_mxn) if tasa_usd_mxn > 0 else 1.0
        else:
            factor = 1.0

        # Montos en divisa nativa
        cap_invertido_orig = round(cant * costo_prom, 2)
        val_act_orig = round(cant * precio_act, 2)

        # Montos unificados en moneda base
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

    # Calcular peso porcentual de cada activo sobre el portafolio total
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
def crear_inversion(item: InversionCreate):
    """
    Registra un activo bursátil.
    Si no se especifica precio actual, intenta consultarlo en vivo a Yahoo Finance;
    en caso de no responder, utiliza como respaldo el precio promedio de compra.
    """
    ticker = item.ticker.strip().upper()
    precio_actual = item.precio_actual
    moneda = (item.moneda or "USD").strip().upper()
    
    # Si no se envía cotización actual, consultarla en vivo
    if precio_actual is None or precio_actual <= 0:
        precio_mercado, moneda_mercado = consultar_precio_y_moneda_mercado(ticker)
        precio_actual = precio_mercado if precio_mercado else item.precio_promedio
        if not item.moneda:
            moneda = moneda_mercado

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO inversiones (ticker, cantidad, precio_promedio, precio_actual, moneda) VALUES (?, ?, ?, ?, ?)",
            (ticker, item.cantidad, item.precio_promedio, precio_actual, moneda)
        )
        conn.commit()
        nuevo_id = cursor.lastrowid
        conn.close()
        return {"id": nuevo_id, "mensaje": f"Inversión {ticker} ({moneda}) agregada con éxito."}
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Ya tienes una posición con el ticker {ticker}. Puedes editarla.")

@app.put("/api/inversiones/{inversion_id}", summary="Actualizar posición bursátil")
def actualizar_inversion(inversion_id: int, item: InversionUpdate):
    """
    Permite modificar las unidades en posesión y el precio promedio de adquisición de una posición.
    """
    conn = get_db()
    cursor = conn.cursor()
    inv = cursor.execute("SELECT * FROM inversiones WHERE id = ?", (inversion_id,)).fetchone()
    if not inv:
        conn.close()
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
    conn.close()
    return {"mensaje": "Inversión actualizada con éxito."}

@app.delete("/api/inversiones/{inversion_id}", summary="Eliminar posición bursátil")
def eliminar_inversion(inversion_id: int):
    """Elimina una posición del portafolio bursátil."""
    conn = get_db()
    cursor = conn.cursor()
    inv = cursor.execute("SELECT * FROM inversiones WHERE id = ?", (inversion_id,)).fetchone()
    if not inv:
        conn.close()
        raise HTTPException(status_code=404, detail="Inversión no encontrada")

    cursor.execute("DELETE FROM inversiones WHERE id = ?", (inversion_id,))
    conn.commit()
    conn.close()
    return {"mensaje": "Inversión eliminada."}

@app.post("/api/inversiones/sincronizar", summary="Sincronizar cotizaciones en vivo")
def sincronizar_precios():
    """
    Recorre todas las posiciones activas en cartera y consulta su cotización más reciente
    en Yahoo Finance para mantener los rendimientos actualizados al instante.
    """
    conn = get_db()
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
    conn.close()
    return {
        "actualizados": actualizados,
        "no_actualizados": no_actualizados,
        "mensaje": f"Se sincronizaron {len(actualizados)} de {len(filas)} posiciones."
    }

@app.get("/api/inversiones/cotizar/{ticker}", summary="Cotización individual en tiempo real")
def cotizar_ticker(ticker: str):
    """Obtiene la cotización y moneda actual de un activo bursátil para autocompletar formularios."""
    precio, moneda = consultar_precio_y_moneda_mercado(ticker)
    if precio is None:
        raise HTTPException(status_code=404, detail=f"No se pudo consultar la cotización para {ticker.upper()}")
    return {"ticker": ticker.upper(), "precio": precio, "moneda": moneda}

def buscar_tickers_mercado(query: str):
    """
    Realiza una búsqueda predictiva en la API de autocompletado de Yahoo Finance
    para sugerir nombres de empresas, ETFs y bolsas correspondientes al texto ingresado.
    """
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
def api_buscar_ticker(q: str = ""):
    """Endpoint público para el autocompletado dinámico del campo de búsqueda de activos."""
    if not q or len(q.strip()) < 1:
        return []
    return buscar_tickers_mercado(q)

# =============================================================================
# GESTOR DE TIPOS DE CAMBIO CON MEMORIA CACHÉ (TTL)
# =============================================================================

# Estructura de caché en memoria para proteger los límites de la API externa
_CACHE_TASAS = {
    "datos": None,
    "expira_en": 0.0
}

def obtener_tasas_cambio():
    """
    Consulta los tipos de cambio de referencia contra USD con una memoria caché (TTL de 5 minutos).
    
    Pares consultados:
    - USDMXN=X: Tipo de cambio USD a pesos mexicanos.
    - EURUSD=X: Tipo de cambio EUR a dólares estadounidenses.
    
    Si la consulta externa falla o hay problemas de red, retorna valores seguros de respaldo.
    """
    ahora = time.time()
    if _CACHE_TASAS["datos"] is not None and ahora < _CACHE_TASAS["expira_en"]:
        return _CACHE_TASAS["datos"]

    # Valores de referencia por defecto ante caídas de conexión
    tasas = {
        "USD": 1.0,
        "MXN": 18.40,
        "EUR": 0.89
    }
    try:
        # Cotización USD a MXN
        precio_mxn = consultar_precio_mercado("USDMXN=X")
        if precio_mxn and precio_mxn > 0:
            tasas["MXN"] = round(precio_mxn, 4)
            
        # Cotización EUR a USD (1 EUR = X USD -> 1 USD = 1/X EUR)
        precio_eur = consultar_precio_mercado("EURUSD=X")
        if precio_eur and precio_eur > 0:
            tasas["EUR"] = round(1.0 / precio_eur, 4)

        _CACHE_TASAS["datos"] = tasas
        _CACHE_TASAS["expira_en"] = ahora + 300  # Válido por 5 minutos (300 segundos)
    except Exception:
        if _CACHE_TASAS["datos"] is not None:
            return _CACHE_TASAS["datos"]
        _CACHE_TASAS["datos"] = tasas
        _CACHE_TASAS["expira_en"] = ahora + 60

    return _CACHE_TASAS["datos"]

@app.get("/api/tipo-cambio", summary="Consultar tipos de cambio vigentes")
def get_tipo_cambio():
    """Retorna las tasas de conversión cambiaria actuales y su marca temporal."""
    tasas = obtener_tasas_cambio()
    return {
        "base": "USD",
        "tasas": tasas,
        "actualizado_en": ahora_local().strftime("%Y-%m-%d %H:%M:%S")
    }

# =============================================================================
# COPIAS DE SEGURIDAD Y EXPORTACIÓN A EXCEL
# =============================================================================

@app.get("/api/backup", summary="Descargar respaldo directo de base de datos")
def descargar_backup():
    """
    Permite descargar una copia de seguridad directa del archivo SQLite 'finanzas.db'
    con un nombre de archivo timestamped para fácil archivado y restauración.
    """
    if not os.path.exists("finanzas.db"):
        raise HTTPException(status_code=404, detail="Base de datos no encontrada.")
    fecha_str = ahora_local().strftime("%Y%m%d_%H%M%S")
    return FileResponse(
        "finanzas.db",
        filename=f"finanzas_backup_{fecha_str}.db",
        media_type="application/octet-stream"
    )

@app.get("/api/exportar-excel", summary="Descargar reporte contable completo en Excel")
def exportar_excel(moneda_base: str = "MXN"):
    """
    Invoca el servicio de exportación (export_service.py) para generar y descargar
    el libro de Excel (.xlsx) con:
    - Hoja 1: Resumen General y Métricas Patrimoniales.
    - Hoja 2: Historial completo de Movimientos (Ingresos y Gastos).
    - Hoja 3: Portafolio de Inversiones con cotizaciones y Gráfica de Pastel (Asset Allocation).
    """
    from export_service import generar_reporte_excel
    buf = generar_reporte_excel(moneda_base)
    fecha_str = ahora_local().strftime("%Y%m%d_%H%M%S")
    nombre_archivo = f"reporte_financiero_{moneda_base.upper()}_{fecha_str}.xlsx"
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{nombre_archivo}"'
        }
    )
