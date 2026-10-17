/**
 * static/js/main.js - Punto de entrada: compone los módulos, escucha eventos globales y arranca la app.
 */

import { cerrarModalCrearUsuario, cerrarModalEditarUsuario } from './admin.js';
import { cargarApartados, cerrarModalCrearApartado } from './apartados.js';
import { cerrarModalRecuperarPassword, cerrarSesionLimpia, establecerSesionActiva, mostrarVistaLogin, verificarSesionInicial } from './auth.js';
import { apiFetch, escapeHTML, estado, fmt } from './core.js';
import { actualizarGrafica } from './dashboard.js';
import { cargarInversiones, cerrarModalEditarInversion, inicializarBuscadorTickers } from './inversiones.js';
import { cargarRecurrentes } from './recurrentes.js';
import { cargarCategorias, cerrarModalEditarTransaccion, renderTablaMovimientos } from './movimientos.js';
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

        // 3. Movimientos: lista en caché, tabla con filtros y categorías
        const resTrans = await apiFetch('/api/transacciones');
        const dataTrans = await resTrans.json();
        estado.cache.transacciones = {};
        dataTrans.forEach(t => { estado.cache.transacciones[t.id] = t; });
        estado.cache.listaTransacciones = dataTrans;
        renderTablaMovimientos();
        await cargarCategorias();
        await cargarRecurrentes();

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
