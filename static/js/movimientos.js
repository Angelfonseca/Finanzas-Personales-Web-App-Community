/**
 * static/js/movimientos.js - Formulario, tabla y edición de movimientos de caja.
 */

import { apiFetch, estado, formatErrorDetail, recargar } from './core.js';


// =============================================================================
// 5. CARGA DE DATOS FINANCIEROS DEL TENANT ACTIVO
// =============================================================================

export function obtenerFechaLocalISO() {
    const d = new Date();
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}


export const inputFecha = document.getElementById('fecha');

if (inputFecha) inputFecha.value = obtenerFechaLocalISO();


// Listener de registro de transacciones
export let guardandoTransaccion = false;

export const formTrans = document.getElementById('transaccion-form');

if (formTrans) {
    formTrans.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (guardandoTransaccion) return;

        const mensajeDiv = document.getElementById('mensaje');
        const btnSubmit = formTrans.querySelector('button[type="submit"]');
        const origHTML = btnSubmit ? btnSubmit.innerHTML : '';

        const montoVal = parseFloat(document.getElementById('monto').value);
        if (isNaN(montoVal) || montoVal <= 0) {
            if (mensajeDiv) {
                mensajeDiv.style.color = '#e74c3c';
                mensajeDiv.textContent = 'Ingresa un monto válido mayor a 0.';
            }
            return;
        }

        const datos = {
            fecha: document.getElementById('fecha').value,
            monto: montoVal,
            tipo: document.getElementById('tipo').value,
            descripcion: document.getElementById('descripcion').value.trim(),
            categoria_id: 1
        };

        guardandoTransaccion = true;
        if (btnSubmit) {
            btnSubmit.disabled = true;
            btnSubmit.innerHTML = '<span>Guardando...</span>';
        }

        try {
            const response = await apiFetch('/api/transacciones', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(datos)
            });

            if (response.ok) {
                if (mensajeDiv) {
                    mensajeDiv.style.color = '#2ecc71';
                    mensajeDiv.textContent = '¡Movimiento guardado!';
                }
                formTrans.reset();
                document.getElementById('fecha').value = obtenerFechaLocalISO();
                recargar();
            } else {
                let errText = 'Error al guardar.';
                try {
                    const err = await response.json();
                    errText = formatErrorDetail(err.detail, errText);
                } catch (_) {}
                if (mensajeDiv) {
                    mensajeDiv.style.color = '#e74c3c';
                    mensajeDiv.textContent = errText;
                }
            }
        } catch (error) {
            if (mensajeDiv) {
                mensajeDiv.style.color = '#e74c3c';
                mensajeDiv.textContent = 'Error de conexión.';
            }
        } finally {
            guardandoTransaccion = false;
            if (btnSubmit) {
                btnSubmit.disabled = false;
                btnSubmit.innerHTML = origHTML || '<span>Guardar Transacción</span>';
            }
        }
    });
}


export async function eliminarTransaccion(id) {
    if (!confirm("¿Eliminar este movimiento?")) return;
    try {
        const response = await apiFetch(`/api/transacciones/${id}`, { method: 'DELETE' });
        if (response.ok) {
            recargar();
        } else {
            const err = await response.json().catch(() => ({}));
            alert(err.detail || "No se pudo eliminar el movimiento.");
        }
    } catch (error) {
        console.error("Error al eliminar:", error);
    }
}


export function abrirModalEditarTransaccion(id, fecha, monto, tipo, descripcion) {
    const modal = document.getElementById('modal-editar-transaccion');
    if (!modal) return;

    document.getElementById('modal-edit-trans-id').value = id;
    document.getElementById('modal-edit-trans-fecha').value = fecha || '';
    document.getElementById('modal-edit-trans-tipo').value = tipo || 'gasto';
    document.getElementById('modal-edit-trans-monto').value = (monto !== undefined && monto !== null) ? monto : '';
    document.getElementById('modal-edit-trans-desc').value = descripcion || '';

    modal.style.display = 'flex';
    setTimeout(() => {
        const inputMonto = document.getElementById('modal-edit-trans-monto');
        if (inputMonto) {
            inputMonto.focus();
            inputMonto.select();
        }
    }, 50);
}


export function cerrarModalEditarTransaccion() {
    const modal = document.getElementById('modal-editar-transaccion');
    if (modal) modal.style.display = 'none';
}


export async function guardarEdicionTransaccion(e) {
    if (e) {
        e.preventDefault();
        e.stopPropagation();
    }

    const id = document.getElementById('modal-edit-trans-id').value;
    const fecha = document.getElementById('modal-edit-trans-fecha').value;
    const tipo = document.getElementById('modal-edit-trans-tipo').value;
    const monto = parseFloat(document.getElementById('modal-edit-trans-monto').value);
    const descripcion = document.getElementById('modal-edit-trans-desc').value.trim();

    if (!fecha || isNaN(monto) || monto <= 0 || !tipo) {
        alert("Por favor ingresa una fecha, tipo y monto numérico válido mayor a cero.");
        return;
    }

    try {
        const res = await apiFetch(`/api/transacciones/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ fecha, tipo, monto, descripcion })
        });

        if (res.ok) {
            cerrarModalEditarTransaccion();
            await recargar();
        } else {
            const err = await res.json();
            alert(err.detail || "Error al actualizar el movimiento.");
        }
    } catch (err) {
        alert("Error de red al intentar guardar los cambios.");
    }
}


// =============================================================================
// 13. EXPOSICIÓN GLOBAL DE FUNCIONES EN WINDOW
// =============================================================================

export function abrirModalEditarTransaccionPorId(id) {
    const t = estado.cache.transacciones[id];
    if (!t) return;
    abrirModalEditarTransaccion(t.id, t.fecha, t.monto, t.tipo, t.descripcion);
}

Object.assign(window, {
    abrirModalEditarTransaccion,
    abrirModalEditarTransaccionPorId,
    cerrarModalEditarTransaccion,
    eliminarTransaccion,
    guardarEdicionTransaccion
});
