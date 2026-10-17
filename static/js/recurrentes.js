/**
 * static/js/recurrentes.js - Pestaña "Fijos y MSI": nómina, gastos fijos y compras a meses.
 */

import { apiFetch, escapeHTML, estado, fmt, formatErrorDetail, recargar, toast } from './core.js';


const FRECUENCIA_TXT = { semanal: 'Semanal', quincenal: 'Quincenal', mensual: 'Mensual' };


function modoActual() {
    return document.querySelector('input[name="rec-modo"]:checked')?.value || 'gasto';
}

function mesesElegidos() {
    const sel = document.getElementById('rec-meses').value;
    if (sel === 'otro') return parseInt(document.getElementById('rec-meses-otro').value, 10) || 0;
    return parseInt(sel, 10);
}


// -----------------------------------------------------------------------------
// Formulario
// -----------------------------------------------------------------------------

function llenarCategoriasRec() {
    const sel = document.getElementById('rec-categoria');
    if (!sel) return;
    const modo = modoActual();
    const tipo = modo === 'ingreso' ? 'ingreso' : 'gasto';
    const actual = sel.value;
    const cats = (estado.cache.categorias || []).filter(c => c.tipo === tipo);
    sel.innerHTML = cats.map(c => `<option value="${c.id}">${escapeHTML(c.nombre)}</option>`).join('');
    if (actual && [...sel.options].some(o => o.value === actual)) sel.value = actual;
}

function actualizarVistaModo() {
    const msi = modoActual() === 'msi';
    document.getElementById('rec-campos-fijo').classList.toggle('hidden', msi);
    document.getElementById('rec-campos-msi').classList.toggle('hidden', !msi);
    document.getElementById('rec-monto').required = !msi;
    document.getElementById('rec-total').required = msi;
    document.getElementById('rec-desc').placeholder = msi ? 'Ej. Laptop, Celular' : 'Ej. Nómina, Renta, Netflix';
    llenarCategoriasRec();
    actualizarPreview();
}

function actualizarPreview() {
    const prev = document.getElementById('rec-preview');
    const otro = document.getElementById('rec-meses-otro-wrap');
    const sel = document.getElementById('rec-meses').value;
    otro.classList.toggle('hidden', sel !== 'otro');
    if (modoActual() !== 'msi' || !prev) return;
    const total = parseFloat(document.getElementById('rec-total').value);
    const meses = mesesElegidos();
    if (!total || total <= 0 || !meses || meses < 2) {
        prev.textContent = '';
        return;
    }
    prev.textContent = `${meses} pagos de ${fmt(Math.round((total / meses) * 100) / 100)}`;
}

async function guardarRecurrente(e) {
    e.preventDefault();
    const btn = document.getElementById('btn-guardar-recurrente');
    const modo = modoActual();
    const descripcion = document.getElementById('rec-desc').value.trim();
    const fecha = document.getElementById('rec-fecha').value;
    const categoriaId = Number(document.getElementById('rec-categoria').value) || undefined;

    let body;
    if (modo === 'msi') {
        const total = parseFloat(document.getElementById('rec-total').value);
        const meses = mesesElegidos();
        if (!total || total <= 0) return toast('Ingresa el monto total de la compra.', 'error');
        if (!meses || meses < 2 || meses > 60) return toast('Los meses deben estar entre 2 y 60.', 'error');
        body = { descripcion, monto_total: total, meses, fecha_inicio: fecha, categoria_id: categoriaId };
    } else {
        const monto = parseFloat(document.getElementById('rec-monto').value);
        if (!monto || monto <= 0) return toast('Ingresa un monto mayor a 0.', 'error');
        body = {
            descripcion,
            tipo: modo === 'ingreso' ? 'ingreso' : 'gasto',
            frecuencia: document.getElementById('rec-frecuencia').value,
            monto,
            fecha_inicio: fecha,
            categoria_id: categoriaId
        };
    }

    btn.disabled = true;
    try {
        const res = await apiFetch('/api/recurrentes', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            toast(formatErrorDetail(err.detail, 'No se pudo guardar el registro.'), 'error');
            return;
        }
        toast(modo === 'msi' ? 'Compra a meses registrada.' : 'Registro fijo guardado.', 'ok');
        document.getElementById('form-recurrente').reset();
        document.getElementById('rec-frecuencia').value = 'mensual';
        document.getElementById('rec-meses').value = '12';
        restaurarFechaHoy();
        actualizarVistaModo();
        recargar();
    } catch (error) {
        toast('Error de conexión al guardar.', 'error');
    } finally {
        btn.disabled = false;
    }
}


// -----------------------------------------------------------------------------
// Listas y tarjetas
// -----------------------------------------------------------------------------

function renderListaMsi(items) {
    const cont = document.getElementById('lista-msi');
    if (!cont) return;
    if (items.length === 0) {
        cont.innerHTML = '<p class="empty-state">No tienes compras a meses. Registra una laptop, celular o cualquier compra en cuotas.</p>';
        return;
    }
    cont.innerHTML = '';
    items.forEach(r => {
        const card = document.createElement('div');
        card.className = 'rec-item';
        const terminado = r.cuotas_generadas >= r.total_cuotas;
        card.innerHTML = `
            <div class="rec-item-head">
                <strong>${escapeHTML(r.descripcion)}</strong>
                <span class="badge-tag badge-msi">${terminado ? 'Terminado' : `Cuota ${r.cuotas_generadas} de ${r.total_cuotas}`}</span>
            </div>
            <div class="progress-bar-bg"><div class="progress-bar-fill"></div></div>
            <div class="rec-item-meta">
                <span>Pendiente: <strong>${fmt(r.deuda_pendiente)}</strong></span>
                <span>${terminado ? 'Compra liquidada' : `Próximo pago: ${escapeHTML(r.proxima_fecha)}`}</span>
            </div>
            <div class="rec-item-actions">
                <button type="button" class="btn-secondary btn-sm" data-accion="eliminar" data-id="${r.id}">Eliminar</button>
            </div>`;
        card.querySelector('.progress-bar-fill').style.width = `${Math.min(100, r.progreso_pct || 0)}%`;
        cont.appendChild(card);
    });
}

function renderListaFijos(items) {
    const cont = document.getElementById('lista-fijos');
    if (!cont) return;
    if (items.length === 0) {
        cont.innerHTML = '<p class="empty-state">Aún no tienes ingresos ni gastos fijos. Agrega tu nómina o tu renta para ver tu libre al mes.</p>';
        return;
    }
    cont.innerHTML = '';
    items.forEach(r => {
        const card = document.createElement('div');
        card.className = 'rec-item';
        const esIngreso = r.tipo === 'ingreso';
        card.innerHTML = `
            <div class="rec-item-head">
                <strong>${escapeHTML(r.descripcion)}</strong>
                <span class="badge-tag ${r.activo ? 'badge-fijo' : ''}">${r.activo ? (esIngreso ? 'Ingreso' : 'Gasto') : 'Pausado'}</span>
            </div>
            <div class="rec-item-meta">
                <span>${fmt(r.monto)} · ${FRECUENCIA_TXT[r.frecuencia] || r.frecuencia}</span>
                <span>Próxima fecha: ${escapeHTML(r.proxima_fecha)}</span>
            </div>
            <div class="rec-item-actions">
                <button type="button" class="btn-secondary btn-sm" data-accion="${r.activo ? 'pausar' : 'reanudar'}" data-id="${r.id}">${r.activo ? 'Pausar' : 'Reanudar'}</button>
                <button type="button" class="btn-secondary btn-sm" data-accion="eliminar" data-id="${r.id}">Eliminar</button>
            </div>`;
        cont.appendChild(card);
    });
}

async function accionRecurrente(e) {
    const btn = e.target.closest('button[data-accion]');
    if (!btn) return;
    const id = btn.dataset.id;
    const accion = btn.dataset.accion;
    if (accion === 'eliminar') {
        if (!confirm('¿Eliminar este registro? Los movimientos ya generados se conservan.')) return;
        const res = await apiFetch(`/api/recurrentes/${id}`, { method: 'DELETE' });
        if (!res.ok) return toast('No se pudo eliminar el registro.', 'error');
    } else {
        const res = await apiFetch(`/api/recurrentes/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ activo: accion === 'reanudar' })
        });
        if (!res.ok) return toast('No se pudo actualizar el registro.', 'error');
    }
    recargar();
}


// -----------------------------------------------------------------------------
// Carga
// -----------------------------------------------------------------------------

export async function cargarRecurrentes() {
    try {
        const [resRec, resResumen] = await Promise.all([
            apiFetch('/api/recurrentes'),
            apiFetch(`/api/resumen?moneda_base=${encodeURIComponent(estado.monedaGlobal)}`)
        ]);
        const items = await resRec.json();
        const resumen = await resumenJson(resResumen);
        estado.cache.recurrentes = items;

        const ingreso = Number(resumen.ingreso_fijo_mensual) || 0;
        const gasto = Number(resumen.gasto_fijo_mensual) || 0;
        const setTxt = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = fmt(v); };
        setTxt('lbl-rec-ingreso', ingreso);
        setTxt('lbl-rec-gasto', gasto);
        setTxt('lbl-rec-deuda', resumen.deuda_msi || 0);
        setTxt('lbl-rec-libre', ingreso - gasto);

        renderListaMsi(items.filter(r => r.es_msi && r.cuotas_generadas < r.total_cuotas));
        renderListaFijos(items.filter(r => !r.es_msi));
        llenarCategoriasRec();
    } catch (error) {
        console.error('No se pudieron cargar los fijos y MSI:', error);
    }
}

async function resumenJson(res) {
    return res.ok ? res.json() : {};
}


function restaurarFechaHoy() {
    const fecha = document.getElementById('rec-fecha');
    if (!fecha) return;
    const d = new Date();
    fecha.value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function inicializarRecurrentes() {
    document.querySelectorAll('input[name="rec-modo"]').forEach(r => r.addEventListener('change', actualizarVistaModo));
    ['rec-total', 'rec-meses', 'rec-meses-otro'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('input', actualizarPreview);
        if (el) el.addEventListener('change', actualizarPreview);
    });
    const form = document.getElementById('form-recurrente');
    if (form) form.addEventListener('submit', guardarRecurrente);
    const listas = ['lista-msi', 'lista-fijos'].map(id => document.getElementById(id)).filter(Boolean);
    listas.forEach(l => l.addEventListener('click', accionRecurrente));
    const fecha = document.getElementById('rec-fecha');
    restaurarFechaHoy();
    actualizarVistaModo();
}

inicializarRecurrentes();
