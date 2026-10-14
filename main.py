from fastapi import FastAPI, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
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

class TransaccionUpdate(BaseModel):
    fecha: Optional[str] = None
    monto: Optional[float] = Field(None, gt=0)
    tipo: Optional[Literal['gasto', 'ingreso']] = None
    categoria_id: Optional[int] = None
    descripcion: Optional[str] = None

class ApartadoCreate(BaseModel):
    nombre: str
    tipo: Literal['libre', 'meta']
    meta_monto: Optional[float] = None

class MovimientoApartado(BaseModel):
    monto: float = Field(..., gt=0)
    accion: Literal['depositar', 'retirar']

class InversionCreate(BaseModel):
    ticker: str
    cantidad: float = Field(..., gt=0)
    precio_promedio: float = Field(..., gt=0)
    precio_actual: Optional[float] = None
    moneda: Optional[str] = "USD"

class InversionUpdate(BaseModel):
    cantidad: Optional[float] = Field(None, gt=0)
    precio_promedio: Optional[float] = Field(None, gt=0)
    precio_actual: Optional[float] = Field(None, gt=0)
    moneda: Optional[str] = None

# --- HELPER CONEXIÓN ---

def get_db():
    conn = sqlite3.connect("finanzas.db", timeout=15.0)
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

@app.put("/api/transacciones/{id_transaccion}")
def actualizar_transaccion(id_transaccion: int, t: TransaccionUpdate):
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

@app.get("/api/resumen")
def obtener_resumen(moneda_base: str = "MXN"):
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

    tasas = obtener_tasas_cambio()
    tasa_usd_mxn = tasas.get("MXN", 18.40)
    moneda_base_upper = moneda_base.upper()

    inversiones_total = 0.0
    for inv in filas_inv:
        cant = float(inv["cantidad"])
        p_act = float(inv["precio_actual"])
        m_act = (inv["moneda"] or "USD").upper()
        val = cant * p_act
        
        # Si el activo está en USD y la moneda base es MXN, se multiplica por el tipo de cambio
        # Si el activo ya está en MXN, NO se multiplica (factor 1.0)
        if m_act == "USD" and moneda_base_upper == "MXN":
            val *= tasa_usd_mxn
        elif m_act == "MXN" and moneda_base_upper == "USD":
            val /= tasa_usd_mxn if tasa_usd_mxn > 0 else 1.0

        inversiones_total += val

    # Las transacciones de flujo de efectivo y apartados están denominadas en MXN.
    # Si la moneda base solicitada es USD, se convierten dividiendo entre la tasa de cambio USD/MXN.
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
    conn = get_db()
    cursor = conn.cursor()
    
    # Verificamos si existe
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


# --- MÓDULO DE INVERSIONES Y ASSET ALLOCATION (FASE 7) ---

def consultar_precio_y_moneda_mercado(ticker: str):
    """Consulta la cotización actual y divisa de un ticker en Yahoo Finance API."""
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
    """Consulta únicamente el precio numérico."""
    precio, _ = consultar_precio_y_moneda_mercado(ticker)
    return precio

@app.get("/api/inversiones")
def listar_inversiones(moneda_base: str = "MXN"):
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

        # Determinar factor de conversión hacia la moneda base seleccionada
        # Si la acción está en USD y la moneda base es MXN -> se multiplica por el tipo de cambio
        # Si la acción ya está en MXN y la moneda base es MXN -> factor 1.0 (NO se multiplica)
        if moneda_activo == "USD" and moneda_base_upper == "MXN":
            factor = tasa_usd_mxn
        elif moneda_activo == "MXN" and moneda_base_upper == "USD":
            factor = (1.0 / tasa_usd_mxn) if tasa_usd_mxn > 0 else 1.0
        else:
            factor = 1.0

        # Montos en su divisa original
        cap_invertido_orig = round(cant * costo_prom, 2)
        val_act_orig = round(cant * precio_act, 2)

        # Montos convertidos a la moneda base unificada
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

    # Asset allocation: cálculo de peso % de cada activo sobre el portafolio total
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

@app.post("/api/inversiones", status_code=status.HTTP_201_CREATED)
def crear_inversion(item: InversionCreate):
    ticker = item.ticker.strip().upper()
    precio_actual = item.precio_actual
    moneda = (item.moneda or "USD").strip().upper()
    
    # Si no se envía precio actual, intentamos obtenerlo en vivo o usamos el precio promedio
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

@app.put("/api/inversiones/{inversion_id}")
def actualizar_inversion(inversion_id: int, item: InversionUpdate):
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
        "UPDATE inversiones SET cantidad = ?, precio_promedio = ?, precio_actual = ?, moneda = ?, actualizado_en = CURRENT_TIMESTAMP WHERE id = ?",
        (nueva_cant, nuevo_prom, nuevo_act, nueva_moneda, inversion_id)
    )
    conn.commit()
    conn.close()
    return {"mensaje": "Inversión actualizada con éxito."}

@app.delete("/api/inversiones/{inversion_id}")
def eliminar_inversion(inversion_id: int):
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

@app.post("/api/inversiones/sincronizar")
def sincronizar_precios():
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
                "UPDATE inversiones SET precio_actual = ?, moneda = ?, actualizado_en = CURRENT_TIMESTAMP WHERE id = ?",
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

@app.get("/api/inversiones/cotizar/{ticker}")
def cotizar_ticker(ticker: str):
    precio, moneda = consultar_precio_y_moneda_mercado(ticker)
    if precio is None:
        raise HTTPException(status_code=404, detail=f"No se pudo consultar la cotización para {ticker.upper()}")
    return {"ticker": ticker.upper(), "precio": precio, "moneda": moneda}

def buscar_tickers_mercado(query: str):
    """Busca tickers y activos sugeridos en Yahoo Finance API."""
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

@app.get("/api/inversiones/buscar")
def api_buscar_ticker(q: str = ""):
    if not q or len(q.strip()) < 1:
        return []
    return buscar_tickers_mercado(q)

_CACHE_TASAS = {
    "datos": None,
    "expira_en": 0.0
}

def obtener_tasas_cambio():
    """Consulta tipos de cambio de referencia contra USD con caché en memoria (TTL 5 min)."""
    ahora = time.time()
    if _CACHE_TASAS["datos"] is not None and ahora < _CACHE_TASAS["expira_en"]:
        return _CACHE_TASAS["datos"]

    # Valores base por defecto
    tasas = {
        "USD": 1.0,
        "MXN": 18.40,
        "EUR": 0.89
    }
    try:
        # USD a MXN
        precio_mxn = consultar_precio_mercado("USDMXN=X")
        if precio_mxn and precio_mxn > 0:
            tasas["MXN"] = round(precio_mxn, 4)
            
        # EUR/USD (1 EUR = X USD -> 1 USD = 1/X EUR)
        precio_eur = consultar_precio_mercado("EURUSD=X")
        if precio_eur and precio_eur > 0:
            tasas["EUR"] = round(1.0 / precio_eur, 4)

        _CACHE_TASAS["datos"] = tasas
        _CACHE_TASAS["expira_en"] = ahora + 300  # 5 minutos
    except Exception:
        if _CACHE_TASAS["datos"] is not None:
            return _CACHE_TASAS["datos"]
        _CACHE_TASAS["datos"] = tasas
        _CACHE_TASAS["expira_en"] = ahora + 60

    return _CACHE_TASAS["datos"]

@app.get("/api/tipo-cambio")
def get_tipo_cambio():
    tasas = obtener_tasas_cambio()
    return {
        "base": "USD",
        "tasas": tasas,
        "actualizado_en": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

@app.get("/api/backup")
def descargar_backup():
    """Permite descargar una copia de seguridad directa del archivo SQLite finanzas.db."""
    if not os.path.exists("finanzas.db"):
        raise HTTPException(status_code=404, detail="Base de datos no encontrada.")
    fecha_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    return FileResponse(
        "finanzas.db",
        filename=f"finanzas_backup_{fecha_str}.db",
        media_type="application/octet-stream"
    )



