/**
 * static/js/main.js - Punto de entrada: compone los módulos, escucha eventos globales y arranca la app.
 */

import { cerrarModalCrearUsuario, cerrarModalEditarUsuario } from './admin.js';
import { cargarApartados, cerrarModalCrearApartado } from './apartados.js';
import { cerrarModalRecuperarPassword, cerrarSesionLimpia, establecerSesionActiva, mostrarVistaLogin, verificarSesionInicial } from './auth.js';
import { apiFetch, escapeHTML, estado, fmt } from './core.js';
import { actualizarGrafica } from './dashboard.js';
import { cargarInversiones, cerrarModalEditarInversion, inicializarBuscadorTickers } from './inversiones.js';
import { cerrarModalEditarTransaccion } from './movimientos.js';
import { cerrarModalLegal, cerrarSidebarMobile, cerrarUserDropdown, inicializarEstadoSidebar, inicializarTabs } from './ui.js';
import './respaldo.js'; // registra handlers de Excel y respaldo en window


export async function cargarDatos() {
    try {

        // 1. Resumen Consolidado del Tenant
        const resResumen = await apiFetch(`/api/resumen?moneda_base=${encodeURIComponent(estado.monedaGlobal)}`);
        const dataResumen = await resResumen.json();
        
        if (document.getElementById('lbl-dash-patrimonio')) {
            document.getElementById('lbl-dash-patrimonio').textContent = `${fmt(dataResumen.patrimonio_neto)} ${estado.monedaGlobal}`;
            document.getElementById('lbl-dash-balance').textContent = `${fmt(dataResumen.balance)}`;
            document.getElementById('lbl-dash-apartados').textContent = `${fmt(dataResumen.apartados)}`;
            document.getElementById('lbl-dash-inversiones').textContent = `${fmt(dataResumen.inversiones)} ${estado.monedaGlobal}`;
            document.getElementById('lbl-dash-ingresos').textContent = `${fmt(dataResumen.ingresos)}`;
            document.getElementById('lbl-dash-gastos').textContent = `${fmt(dataResumen.gastos)}`;

            // Tira de Distribución de Activos (Asset Allocation estilo Kubera)
            const vBal = Math.max(0, Number(dataResumen.balance) || 0);
            const vAp = Math.max(0, Number(dataResumen.apartados) || 0);
            const vInv = Math.max(0, Number(dataResumen.inversiones) || 0);
            const totalAct = vBal + vAp + vInv;
            if (totalAct > 0) {
                const pBal = ((vBal / totalAct) * 100).toFixed(1);
                const pAp = ((vAp / totalAct) * 100).toFixed(1);
                const pInv = ((vInv / totalAct) * 100).toFixed(1);
                const barBal = document.getElementById('alloc-bar-balance');
                const barAp = document.getElementById('alloc-bar-apartados');
                const barInv = document.getElementById('alloc-bar-inversiones');
                if (barBal) { barBal.style.width = `${pBal}%`; barBal.title = `Efectivo: ${pBal}% (${fmt(vBal)})`; }
                if (barAp) { barAp.style.width = `${pAp}%`; barAp.title = `Metas/Apartados: ${pAp}% (${fmt(vAp)})`; }
                if (barInv) { barInv.style.width = `${pInv}%`; barInv.title = `Inversiones: ${pInv}% (${fmt(vInv)})`; }
            }
        }

        if (document.getElementById('lbl-apartados-total-acum')) {
            document.getElementById('lbl-apartados-total-acum').textContent = `${fmt(dataResumen.apartados)}`;
        }

        if (document.getElementById('lbl-balance')) {
            document.getElementById('lbl-balance').textContent = `${fmt(dataResumen.balance)}`;
            document.getElementById('lbl-ingresos').textContent = `${fmt(dataResumen.ingresos)}`;
            document.getElementById('lbl-gastos').textContent = `${fmt(dataResumen.gastos)}`;
        }

        // 2. Resumen Mensual Histórico
        const resMensual = await apiFetch('/api/resumen-mensual');
        const dataMensual = await resMensual.json();
        
        const contenedorMensual = document.getElementById('lista-resumen-mensual');
        if (contenedorMensual) {
            contenedorMensual.innerHTML = '';
            if (dataMensual.length === 0) {
                contenedorMensual.innerHTML = '<p style="text-align: center; color: var(--text-muted);">Sin registros mensuales aún.</p>';
            } else {
                dataMensual.forEach(m => {
                    const div = document.createElement('div');
                    div.className = 'monthly-card';
                    div.innerHTML = `
                        <div><strong>${m.mes}</strong></div>
                        <div class="monthly-info">
                            <span style="color: var(--success-color);">+${fmt(m.ingresos)}</span>
                            <span style="color: var(--danger-color);">-${fmt(m.gastos)}</span>
                        </div>
                    `;
                    contenedorMensual.appendChild(div);
                });
            }
        }

        actualizarGrafica(dataMensual.slice().reverse());

        // 3. Tabla Cronológica de Movimientos
        const resTrans = await apiFetch('/api/transacciones');
        const dataTrans = await resTrans.json();
        
        const tbody = document.getElementById('tabla-movimientos');
        if (tbody) {
            tbody.innerHTML = '';
            if (dataTrans.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No hay movimientos.</td></tr>';
            } else {
                dataTrans.forEach(t => {
                    estado.cache.transacciones[t.id] = t;
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td>${escapeHTML(t.fecha)}</td>
                        <td>${escapeHTML(t.descripcion || '-')}</td>
                        <td class="${t.tipo === 'gasto' ? 'text-gasto' : 'text-ingreso'}">${escapeHTML(t.tipo.toUpperCase())}</td>
                        <td>${fmt(t.monto)}</td>
                        <td class="col-acciones">
                            <button type="button" class="btn-accion btn-editar" onclick="abrirModalEditarTransaccionPorId(${t.id})" title="Editar movimiento"><svg class="action-svg-icon" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg></button>
                            <button type="button" class="btn-accion btn-eliminar" onclick="eliminarTransaccion(${t.id})" title="Eliminar movimiento"><svg class="action-svg-icon" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
                        </td>
                    `;
                    tbody.appendChild(tr);
                });
            }
        }

        // 4. Sobres de Ahorro y Portafolio de Inversiones
        await cargarApartados();
        await cargarInversiones();

    } catch (error) {
        console.error("Error al actualizar datos:", error);
    }
}


window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        cerrarModalEditarInversion();
        cerrarModalEditarTransaccion();
        cerrarModalCrearUsuario();
        cerrarModalEditarUsuario();
        cerrarModalCrearApartado();
        cerrarModalRecuperarPassword();
        cerrarModalLegal();
    }
});


// Cierre al hacer clic afuera de los menús emergentes
document.addEventListener('click', (e) => {
    const menu = document.getElementById('user-dropdown-menu');
    const trigger = document.getElementById('btn-user-menu-trigger');
    if (menu && menu.style.display !== 'none') {
        if (!menu.contains(e.target) && (!trigger || !trigger.contains(e.target))) {
            cerrarUserDropdown();
        }
    }
});


// Cierre al presionar la tecla Escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        cerrarUserDropdown();
        cerrarSidebarMobile();
    }
});


// Navegación en el historial del navegador (Atrás / Adelante)
window.addEventListener('popstate', () => {
    const token = localStorage.getItem('jwt_token');
    if (token && estado.usuarioActual) {
        establecerSesionActiva(estado.usuarioActual, token);
    } else {
        mostrarVistaLogin();
    }
});


// =============================================================================
// 14. ARRANQUE DE LA APLICACIÓN
// =============================================================================
document.addEventListener('sesion-expirada', (e) => cerrarSesionLimpia(e.detail));

inicializarTabs();

inicializarEstadoSidebar();

inicializarBuscadorTickers();

verificarSesionInicial();

document.addEventListener('recargar', cargarDatos);
