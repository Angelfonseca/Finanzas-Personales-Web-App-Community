"""
finanzas_core.py - Lógica financiera compartida (sin FastAPI).

Reúne los cálculos que antes estaban duplicados en main.py y export_service.py:
- Conversión de moneda (convertir).
- Valuación de posiciones bursátiles (valorar_posiciones).
- Resumen patrimonial (calcular_resumen).
"""

from datetime import datetime
import sqlite3
from typing import Any, Dict, Iterable


def ahora_local() -> datetime:
    """Retorna la fecha y hora actual en la zona horaria de México (CST / UTC-6)."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Mexico_City"))
    except Exception:
        return datetime.now()


def convertir(monto: float, moneda_origen: str, moneda_base: str, tasa_usd_mxn: float) -> float:
    """Convierte un monto entre USD y MXN. Cualquier otro par devuelve el monto sin cambios."""
    origen = moneda_origen.upper()
    base = moneda_base.upper()
    if origen == "USD" and base == "MXN":
        return monto * tasa_usd_mxn
    if origen == "MXN" and base == "USD":
        return monto / tasa_usd_mxn if tasa_usd_mxn > 0 else monto
    return monto


def valorar_posiciones(filas: Iterable[Any], moneda_base: str, tasa_usd_mxn: float) -> Dict[str, Any]:
    """Valúa las posiciones bursátiles en la moneda base y calcula el PnL del portafolio."""
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

        cap_invertido_orig = round(cant * costo_prom, 2)
        val_act_orig = round(cant * precio_act, 2)

        cap_invertido_base = round(convertir(cap_invertido_orig, moneda_activo, moneda_base_upper, tasa_usd_mxn), 2)
        val_act_base = round(convertir(val_act_orig, moneda_activo, moneda_base_upper, tasa_usd_mxn), 2)
        pnl_base = round(val_act_base - cap_invertido_base, 2)
        pnl_pct = round(((val_act_orig - cap_invertido_orig) / cap_invertido_orig) * 100, 2) if cap_invertido_orig > 0 else 0.0

        total_invertido += cap_invertido_base
        total_valor_actual += val_act_base

        item["moneda"] = moneda_activo
        item["factor_conversion"] = convertir(1.0, moneda_activo, moneda_base_upper, tasa_usd_mxn)
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


def calcular_resumen(conn: sqlite3.Connection, moneda_base: str, tasa_usd_mxn: float) -> Dict[str, Any]:
    """Resumen patrimonial: balance + apartados + inversiones, en la moneda base."""
    moneda_base_upper = moneda_base.upper()
    cursor = conn.cursor()

    cursor.execute("SELECT SUM(monto) as total FROM transacciones WHERE tipo='ingreso'")
    ingresos = cursor.fetchone()["total"] or 0.0

    cursor.execute("SELECT SUM(monto) as total FROM transacciones WHERE tipo='gasto'")
    gastos = cursor.fetchone()["total"] or 0.0

    cursor.execute("SELECT SUM(monto_actual) as total FROM apartados")
    apartados = cursor.fetchone()["total"] or 0.0

    filas_inv = cursor.execute("SELECT cantidad, precio_actual, moneda FROM inversiones").fetchall()

    inversiones_total = 0.0
    for inv in filas_inv:
        val = float(inv["cantidad"]) * float(inv["precio_actual"])
        inversiones_total += convertir(val, (inv["moneda"] or "USD").upper(), moneda_base_upper, tasa_usd_mxn)

    ingresos_conv = convertir(ingresos, "MXN", moneda_base_upper, tasa_usd_mxn)
    gastos_conv = convertir(gastos, "MXN", moneda_base_upper, tasa_usd_mxn)
    balance_conv = convertir(ingresos - gastos, "MXN", moneda_base_upper, tasa_usd_mxn)
    apartados_conv = convertir(apartados, "MXN", moneda_base_upper, tasa_usd_mxn)

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
