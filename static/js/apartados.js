/**
 * static/js/apartados.js - Apartados y metas de ahorro.
 */

import { apiFetch, escapeHTML, formatErrorDetail, recargar } from './core.js';


// =============================================================================
// 6. APARTADOS Y METAS DE AHORRO
// =============================================================================

export function toggleMetaInput() {
    const tipo = document.getElementById('tipo-apartado').value;
    const metaGroup = document.getElementById('group-meta-monto');
    if (metaGroup) metaGroup.style.display = tipo === 'meta' ? 'block' : 'none';
}


export async function cargarApartados() {
    try {
        const res = await apiFetch('/api/apartados');
        const apartados = await res.json();
        const contenedor = document.getElementById('contenedor-apartados');
        if (!contenedor) return;
        contenedor.innerHTML = '';

        if (!apartados || apartados.length === 0) {
            contenedor.innerHTML = '<p style="color: var(--text-muted); font-size: 0.9rem; margin-top: 10px;">No hay apartados o metas aún.</p>';
            return;
        }

        apartados.forEach(item => {
            const card = document.createElement('div');
            card.className = 'card-apartado';
            
            let contenidoMeta = '';
            if (item.tipo === 'meta') {
                const porcentaje = Math.min(item.porcentaje || 0, 100);
                contenidoMeta = `
                    <p style="margin: 5px 0;"><small>Meta: $${Number(item.meta_monto).toFixed(2)} (${item.porcentaje}%)</small></p>
                    <div class="progress-bar-bg">
                        <div class="progress-bar-fill" style="width: ${porcentaje}%;"></div>
                    </div>
                `;
            }

            card.innerHTML = `
                <button type="button" class="btn-eliminar-apartado" onclick="eliminarApartado(${item.id})" title="Eliminar">×</button>
                <h3 style="margin: 0 20px 8px 0;">${escapeHTML(item.nombre)} <small style="font-weight: normal; font-size: 0.8rem;">(${escapeHTML(item.tipo)})</small></h3>
                <p style="margin: 5px 0;"><strong>Saldo:</strong> $${Number(item.monto_actual).toFixed(2)}</p>
                ${contenidoMeta}
                <div class="acciones-apartado">
                    <input type="number" id="monto-acc-${item.id}" step="0.01" min="0.01" placeholder="Monto">
                    <button type="button" onclick="realizarMovimiento(${item.id}, 'depositar')">+</button>
                    <button type="button" onclick="realizarMovimiento(${item.id}, 'retirar')">-</button>
                </div>
            `;
            contenedor.appendChild(card);
        });
    } catch (error) {
        console.error("Error al cargar apartados:", error);
    }
}


export let guardandoApartado = false;


export async function guardarNuevoApartado(e) {
    if (e) e.preventDefault();
    if (guardandoApartado) return;

    const nombreInput = document.getElementById('nombre-apartado');
    const tipoInput = document.getElementById('tipo-apartado');
    const metaInput = document.getElementById('meta-monto');

    const nombre = nombreInput ? nombreInput.value.trim() : '';
    const tipo = tipoInput ? tipoInput.value : 'libre';
    const meta_monto = (tipo === 'meta' && metaInput && metaInput.value) ? parseFloat(metaInput.value) : null;

    if (!nombre) {
        alert("Ingresa un nombre para el apartado.");
        return;
    }

    if (tipo === 'meta' && (meta_monto === null || isNaN(meta_monto) || meta_monto <= 0)) {
        alert("Una meta requiere un monto objetivo válido mayor a cero.");
        return;
    }

    guardandoApartado = true;
    const btnSubmit = document.querySelector('#form-apartado button[type="submit"]');
    const origHTML = btnSubmit ? btnSubmit.innerHTML : '';
    if (btnSubmit) {
        btnSubmit.disabled = true;
        btnSubmit.innerHTML = '<span>Creando...</span>';
    }

    try {
        const res = await apiFetch('/api/apartados', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ nombre, tipo, meta_monto })
        });

        if (res.ok) {
            cerrarModalCrearApartado();
            await cargarApartados();
            recargar();
        } else {
            const error = await res.json();
            alert(error.detail || 'Error al crear apartado');
        }
    } catch (err) {
        alert("Error al conectar con el servidor.");
    } finally {
        guardandoApartado = false;
        if (btnSubmit) {
            btnSubmit.disabled = false;
            btnSubmit.innerHTML = origHTML || '<span>Crear Apartado</span>';
        }
    }
}


export function abrirModalCrearApartado() {
    const modal = document.getElementById('modal-crear-apartado');
    if (modal) {
        modal.style.display = 'flex';
        setTimeout(() => {
            const input = document.getElementById('nombre-apartado');
            if (input) input.focus();
        }, 50);
    }
}


export function cerrarModalCrearApartado() {
    const modal = document.getElementById('modal-crear-apartado');
    if (modal) modal.style.display = 'none';
    const form = document.getElementById('form-apartado');
    if (form) form.reset();
    toggleMetaInput();
}


export let procesandoMovimientoApartado = false;

export async function realizarMovimiento(id, accion) {
    if (procesandoMovimientoApartado) return;
    const input = document.getElementById(`monto-acc-${id}`);
    const monto = parseFloat(input?.value);

    if (isNaN(monto) || monto <= 0) {
        alert("Ingresa un monto válido mayor a 0");
        return;
    }

    procesandoMovimientoApartado = true;
    const btnContainer = input ? input.parentElement : null;
    const btns = btnContainer ? btnContainer.querySelectorAll('button') : [];
    btns.forEach(b => b.disabled = true);

    try {
        const res = await apiFetch(`/api/apartados/${id}/movimiento`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ monto, accion })
        });

        if (res.ok) {
            if (input) input.value = '';
            await cargarApartados();
            recargar();
        } else {
            let errorMsg = 'Error en la operación';
            try {
                const error = await res.json();
                errorMsg = formatErrorDetail(error.detail, errorMsg);
            } catch (_) {}
            alert(errorMsg);
        }
    } catch (err) {
        console.error("Error al realizar movimiento en apartado:", err);
        alert("Error de conexión al procesar el movimiento.");
    } finally {
        procesandoMovimientoApartado = false;
        btns.forEach(b => b.disabled = false);
    }
}


export async function eliminarApartado(id) {
    if (!confirm("¿Seguro que deseas eliminar este apartado? Se perderá el registro de este sobre.")) return;
    
    // Feedback visual inmediato en la tarjeta
    const btnEliminar = document.querySelector(`.card-apartado button[onclick*="eliminarApartado(${id})"]`);
    const card = btnEliminar ? btnEliminar.closest('.card-apartado') : null;
    if (card) {
        card.style.opacity = '0.3';
        card.style.pointerEvents = 'none';
        card.style.transition = 'opacity 0.2s ease, transform 0.2s ease';
    }

    try {
        const res = await apiFetch(`/api/apartados/${id}`, { method: 'DELETE' });
        if (res.ok) {
            if (card) card.remove();
            await cargarApartados();
            recargar();
        } else {
            if (card) {
                card.style.opacity = '1';
                card.style.pointerEvents = 'auto';
            }
            const error = await res.json();
            alert(error.detail || "No se pudo eliminar el apartado.");
        }
    } catch (error) {
        if (card) {
            card.style.opacity = '1';
            card.style.pointerEvents = 'auto';
        }
        console.error("Error al eliminar:", error);
        alert("Error de conexión al eliminar el apartado.");
    }
}

Object.assign(window, {
    abrirModalCrearApartado,
    cerrarModalCrearApartado,
    eliminarApartado,
    guardarNuevoApartado,
    realizarMovimiento,
    toggleMetaInput
});
