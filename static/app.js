/**
 * static/app.js - Controlador Principal del Frontend (SPA)
 * 
 * Este archivo gestiona la lógica del cliente para la aplicación de finanzas:
 * - Navegación fluida por pestañas (Dashboard, Movimientos, Metas, Inversiones).
 * - Renderizado reactivo de gráficas con Chart.js (Barras mensuales y Dona de Asset Allocation).
 * - Sincronización y persistencia de moneda base (MXN / USD) y tema visual (Claro / Oscuro).
 * - Formularios interactivos, modales de edición y autocompletado en tiempo real con Yahoo Finance.
 * - Exportación de reportes a Excel y descargas de copias de seguridad.
 */

// =============================================================================
// 1. UTILIDADES Y FECHA LOCAL
// =============================================================================

/**
 * Retorna la fecha local del dispositivo en formato ISO 'YYYY-MM-DD'.
 * Evita desfaces causados por toISOString() que utiliza tiempo universal UTC.
 */
function obtenerFechaLocalISO() {
    const d = new Date();
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

// Inicializar el campo de fecha con el día de hoy
document.getElementById('fecha').value = obtenerFechaLocalISO();

// Referencias a elementos recurrentes del DOM
const form = document.getElementById('transaccion-form');
const mensajeDiv = document.getElementById('mensaje');
const btnModo = document.getElementById('btn-modo');

// Instancias globales de Chart.js para permitir su actualización sin parpadeos
let miGrafica = null;      // Gráfica de barras (Ingresos vs Gastos)
let graficaDona = null;    // Gráfica de dona (Asignación de Activos / Asset Allocation)

// =============================================================================
// 2. GESTIÓN DEL TEMA VISUAL (MODO OSCURO / CLARO)
// =============================================================================

// Recuperar preferencia de tema guardada en localStorage
const temaGuardado = localStorage.getItem('theme');
if (temaGuardado === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
    btnModo.textContent = '☀️ Modo Claro';
}

// Alternar entre modo oscuro y modo claro al hacer clic en el botón
btnModo.addEventListener('click', () => {
    const esOscuro = document.documentElement.getAttribute('data-theme') === 'dark';
    if (esOscuro) {
        document.documentElement.removeAttribute('data-theme');
        localStorage.setItem('theme', 'light');
        btnModo.textContent = '🌙 Modo Oscuro';
    } else {
        document.documentElement.setAttribute('data-theme', 'dark');
        localStorage.setItem('theme', 'dark');
        btnModo.textContent = '☀️ Modo Claro';
    }
    // Sincronizar colores de las gráficas al nuevo contraste
    if (miGrafica) {
        actualizarColoresGrafica();
    }
    if (graficaDona) {
        actualizarColoresDona();
    }
});

/**
 * Actualiza los colores de texto y cuadrículas de la gráfica de barras para
 * garantizar legibilidad según el tema activo.
 */
function actualizarColoresGrafica() {
    if (!miGrafica) return;
    const esOscuro = document.documentElement.getAttribute('data-theme') === 'dark';
    const textColor = esOscuro ? '#e0e0e0' : '#333333';
    const gridColor = esOscuro ? '#333333' : '#eee';

    miGrafica.options.scales.x.ticks.color = textColor;
    miGrafica.options.scales.y.ticks.color = textColor;
    miGrafica.options.scales.x.grid.color = gridColor;
    miGrafica.options.scales.y.grid.color = gridColor;
    miGrafica.options.plugins.legend.labels.color = textColor;
    miGrafica.update();
}

/**
 * Actualiza los colores de texto y bordes de la gráfica de dona (Asset Allocation).
 */
function actualizarColoresDona() {
    if (!graficaDona) return;
    const esOscuro = document.documentElement.getAttribute('data-theme') === 'dark';
    const textColor = esOscuro ? '#e0e0e0' : '#333333';
    graficaDona.options.plugins.legend.labels.color = textColor;
    if (graficaDona.data && graficaDona.data.datasets && graficaDona.data.datasets[0]) {
        graficaDona.data.datasets[0].borderColor = esOscuro ? '#1e1e1e' : '#ffffff';
    }
    graficaDona.update();
}

// =============================================================================
// 3. CARGA GENERAL DE DATOS (DASHBOARD, MOVIMIENTOS Y RESÚMENES)
// =============================================================================

/**
 * Orquestador principal de recarga de datos:
 * 1. Consulta el resumen financiero consolidado en la divisa base actual.
 * 2. Consulta y renderiza el resumen mensual histórico y la gráfica de barras.
 * 3. Actualiza la tabla cronológica de movimientos.
 * 4. Refresca los sobres de ahorro y metas.
 * 5. Refresca el portafolio bursátil de inversiones.
 */
async function cargarDatos() {
    try {
        // -------------------------------------------------------------
        // 1. Resumen General Consolidado
        // -------------------------------------------------------------
        const resResumen = await fetch(`/api/resumen?moneda_base=${encodeURIComponent(monedaGlobal)}`);
        const dataResumen = await resResumen.json();
        
        // Formateador de moneda auxiliar
        const fmtMoneda = (val) => val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

        // Actualizar etiquetas de la Tarjeta Hero del Dashboard
        if (document.getElementById('lbl-dash-patrimonio')) {
            document.getElementById('lbl-dash-patrimonio').textContent = `$${fmtMoneda(dataResumen.patrimonio_neto)} ${monedaGlobal}`;
            document.getElementById('lbl-dash-balance').textContent = `$${fmtMoneda(dataResumen.balance)}`;
            document.getElementById('lbl-dash-apartados').textContent = `$${fmtMoneda(dataResumen.apartados)}`;
            document.getElementById('lbl-dash-inversiones').textContent = `$${fmtMoneda(dataResumen.inversiones)} ${monedaGlobal}`;
            document.getElementById('lbl-dash-ingresos').textContent = `$${fmtMoneda(dataResumen.ingresos)}`;
            document.getElementById('lbl-dash-gastos').textContent = `$${fmtMoneda(dataResumen.gastos)}`;
        }

        // Pestaña de Apartados (píldora con el total acumulado en reserva)
        if (document.getElementById('lbl-apartados-total-acum')) {
            document.getElementById('lbl-apartados-total-acum').textContent = `$${fmtMoneda(dataResumen.apartados)}`;
        }

        // Pestaña de Movimientos (tarjetas de balance de caja)
        if (document.getElementById('lbl-balance')) {
            document.getElementById('lbl-balance').textContent = `$${dataResumen.balance.toFixed(2)}`;
            document.getElementById('lbl-ingresos').textContent = `$${dataResumen.ingresos.toFixed(2)}`;
            document.getElementById('lbl-gastos').textContent = `$${dataResumen.gastos.toFixed(2)}`;
        }

        // -------------------------------------------------------------
        // 2. Resumen Mensual (Tarjetas y Gráfica)
        // -------------------------------------------------------------
        const resMensual = await fetch('/api/resumen-mensual');
        const dataMensual = await resMensual.json();
        
        const contenedorMensual = document.getElementById('lista-resumen-mensual');
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
                        <span style="color: #2ecc71;">+${m.ingresos.toFixed(2)}</span>
                        <span style="color: #e74c3c;">-${m.gastos.toFixed(2)}</span>
                    </div>
                `;
                contenedorMensual.appendChild(div);
            });
        }

        // Invertir copia del array para mostrar la gráfica en orden cronológico (de más antiguo a más nuevo)
        actualizarGrafica(dataMensual.slice().reverse());

        // -------------------------------------------------------------
        // 3. Tabla Cronológica de Movimientos
        // -------------------------------------------------------------
        const resTrans = await fetch('/api/transacciones');
        const dataTrans = await resTrans.json();
        
        const tbody = document.getElementById('tabla-movimientos');
        tbody.innerHTML = '';

        if (dataTrans.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No hay movimientos.</td></tr>';
        } else {
            dataTrans.forEach(t => {
                const tr = document.createElement('tr');
                // Escape seguro de caracteres especiales para evitar inyecciones en el atributo onclick
                const descSegura = (t.descripcion || '')
                    .replace(/\\/g, '\\\\')
                    .replace(/'/g, "\\'")
                    .replace(/"/g, '&quot;')
                    .replace(/\n/g, '\\n')
                    .replace(/\r/g, '\\r');

                tr.innerHTML = `
                    <td>${t.fecha}</td>
                    <td>${t.descripcion || '-'}</td>
                    <td class="${t.tipo === 'gasto' ? 'text-gasto' : 'text-ingreso'}">${t.tipo.toUpperCase()}</td>
                    <td>$${t.monto.toFixed(2)}</td>
                    <td class="col-acciones">
                        <button type="button" class="btn-accion btn-editar" onclick="abrirModalEditarTransaccion(${t.id}, '${t.fecha}', ${t.monto}, '${t.tipo}', '${descSegura}')" title="Editar movimiento">✏️</button>
                        <button type="button" class="btn-accion btn-eliminar" onclick="eliminarTransaccion(${t.id})" title="Eliminar movimiento">✕</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        }

        // -------------------------------------------------------------
        // 4. Cargar Sobres y Portafolio de Inversiones
        // -------------------------------------------------------------
        await cargarApartados();
        await cargarInversiones();

    } catch (error) {
        console.error("Error al actualizar datos:", error);
    }
}

/**
 * Renderiza o actualiza la gráfica de barras de Ingresos vs Gastos con Chart.js.
 */
function actualizarGrafica(dataMensual) {
    const ctx = document.getElementById('graficaFinanzas').getContext('2d');
    const esOscuro = document.documentElement.getAttribute('data-theme') === 'dark';
    const textColor = esOscuro ? '#e0e0e0' : '#333333';
    const gridColor = esOscuro ? '#333333' : '#eee';
    
    const meses = dataMensual.map(m => m.mes);
    const ingresos = dataMensual.map(m => m.ingresos);
    const gastos = dataMensual.map(m => m.gastos);

    if (miGrafica) {
        // Actualizar datos existentes
        miGrafica.data.labels = meses;
        miGrafica.data.datasets[0].data = ingresos;
        miGrafica.data.datasets[1].data = gastos;
        miGrafica.update();
    } else {
        // Crear nueva instancia de Chart.js
        miGrafica = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: meses,
                datasets: [
                    {
                        label: 'Ingresos',
                        data: ingresos,
                        backgroundColor: 'rgba(46, 204, 113, 0.7)',
                        borderColor: '#2ecc71',
                        borderWidth: 1
                    },
                    {
                        label: 'Gastos',
                        data: gastos,
                        backgroundColor: 'rgba(231, 76, 60, 0.7)',
                        borderColor: '#e74c3c',
                        borderWidth: 1
                    }
                ]
            },
            options: {
                responsive: true,
                scales: {
                    x: {
                        ticks: { color: textColor },
                        grid: { color: gridColor }
                    },
                    y: {
                        beginAtZero: true,
                        ticks: { color: textColor },
                        grid: { color: gridColor }
                    }
                },
                plugins: {
                    legend: {
                        labels: { color: textColor }
                    }
                }
            }
        });
    }
}

// =============================================================================
// 4. TRANSACCIONES: REGISTRO Y ELIMINACIÓN
// =============================================================================

// Listener para el formulario de registrar nueva transacción
form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const datos = {
        fecha: document.getElementById('fecha').value,
        monto: parseFloat(document.getElementById('monto').value),
        tipo: document.getElementById('tipo').value,
        descripcion: document.getElementById('descripcion').value,
        categoria_id: 1
    };

    try {
        const response = await fetch('/api/transacciones', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(datos)
        });

        if (response.ok) {
            mensajeDiv.style.color = '#2ecc71';
            mensajeDiv.textContent = '¡Movimiento guardado!';
            form.reset();
            document.getElementById('fecha').value = obtenerFechaLocalISO();
            cargarDatos();
        } else {
            mensajeDiv.style.color = '#e74c3c';
            mensajeDiv.textContent = 'Error al guardar.';
        }
    } catch (error) {
        mensajeDiv.style.color = '#e74c3c';
        mensajeDiv.textContent = 'Error de conexión.';
    }
});

/**
 * Solicita confirmación y elimina un movimiento de caja existente.
 */
async function eliminarTransaccion(id) {
    if (!confirm("¿Eliminar este movimiento?")) return;

    try {
        const response = await fetch(`/api/transacciones/${id}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            cargarDatos();
        } else {
            alert("No se pudo eliminar.");
        }
    } catch (error) {
        console.error("Error al eliminar:", error);
    }
}

// =============================================================================
// 5. APARTADOS Y METAS DE AHORRO
// =============================================================================

/**
 * Muestra u oculta el campo de monto objetivo según si el apartado seleccionado es 'meta' o 'libre'.
 */
function toggleMetaInput() {
    const tipo = document.getElementById('tipo-apartado').value;
    const metaGroup = document.getElementById('group-meta-monto');
    metaGroup.style.display = tipo === 'meta' ? 'block' : 'none';
}

/**
 * Consulta y renderiza las tarjetas de sobres de ahorro con barra de progreso.
 */
async function cargarApartados() {
    try {
        const res = await fetch('/api/apartados');
        const apartados = await res.json();
        
        const contenedor = document.getElementById('contenedor-apartados');
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
                const porcentaje = Math.min(item.porcentaje, 100);
                contenidoMeta = `
                    <p style="margin: 5px 0;"><small>Meta: $${item.meta_monto.toFixed(2)} (${item.porcentaje}%)</small></p>
                    <div class="progress-bar-bg">
                        <div class="progress-bar-fill" style="width: ${porcentaje}%;"></div>
                    </div>
                `;
            }

            card.innerHTML = `
                <button type="button" class="btn-eliminar-apartado" onclick="eliminarApartado(${item.id})" title="Eliminar">×</button>
                <h3 style="margin: 0 20px 8px 0;">${item.nombre} <small style="font-weight: normal; font-size: 0.8rem;">(${item.tipo})</small></h3>
                <p style="margin: 5px 0;"><strong>Saldo:</strong> $${item.monto_actual.toFixed(2)}</p>
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

// Listener para el formulario de creación de nuevo apartado
const formApartado = document.getElementById('form-apartado');
if (formApartado) {
    formApartado.addEventListener('submit', async (e) => {
        e.preventDefault();
        e.stopPropagation();

        const nombreInput = document.getElementById('nombre-apartado');
        const tipoInput = document.getElementById('tipo-apartado');
        const metaInput = document.getElementById('meta-monto');

        const nombre = nombreInput.value.trim();
        const tipo = tipoInput.value;
        const meta_monto = tipo === 'meta' ? parseFloat(metaInput.value) : null;

        if (!nombre) {
            alert("Ingresa un nombre para el apartado.");
            return;
        }

        try {
            const res = await fetch('/api/apartados', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ nombre, tipo, meta_monto })
            });

            if (res.ok) {
                formApartado.reset();
                toggleMetaInput();
                await cargarDatos();
            } else {
                const error = await res.json();
                alert(error.detail || 'Error al crear apartado');
            }
        } catch (err) {
            console.error("Error de red:", err);
            alert("Error al conectar con el servidor.");
        }
    });
}

/**
 * Realiza una transferencia (depósito o retiro) entre el balance disponible y un apartado.
 */
async function realizarMovimiento(id, accion) {
    const input = document.getElementById(`monto-acc-${id}`);
    const monto = parseFloat(input.value);

    if (isNaN(monto) || monto <= 0) {
        alert('Ingresa un monto válido.');
        return;
    }

    const res = await fetch(`/api/apartados/${id}/movimiento`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ monto, accion })
    });

    if (res.ok) {
        cargarDatos();
    } else {
        const error = await res.json();
        alert(error.detail || 'Error en la operación');
    }
}

/**
 * Elimina un sobre de ahorro previa validación de fondos en el servidor.
 */
async function eliminarApartado(id) {
    if (!confirm("¿Seguro que deseas eliminar este apartado? Se perderá el registro de este sobre.")) return;

    try {
        const res = await fetch(`/api/apartados/${id}`, {
            method: 'DELETE'
        });

        if (res.ok) {
            await cargarDatos();
        } else {
            const error = await res.json();
            alert(error.detail || "No se pudo eliminar el apartado.");
        }
    } catch (error) {
        console.error("Error al eliminar:", error);
    }
}

// =============================================================================
// 6. MÓDULO DE INVERSIONES & ASSET ALLOCATION
// =============================================================================

// Estado global de divisa base y tasas de conversión cambiaria
let monedaGlobal = localStorage.getItem('moneda_global') || 'MXN';
let tasasCambio = { USD: 1.0, MXN: 18.40, EUR: 0.89 };

/**
 * Consulta las tasas de cambio activas del servidor para refrescar insignias y badges.
 */
async function cargarTiposCambio() {
    try {
        const res = await fetch('/api/tipo-cambio');
        if (res.ok) {
            const data = await res.json();
            tasasCambio = data.tasas || tasasCambio;
            actualizarIndicadorTasa();
        }
    } catch (e) {
        console.warn("No se pudo obtener tipo de cambio en vivo:", e);
    }
}

/**
 * Actualiza los badges de tipo de cambio y los indicadores de divisa en toda la UI.
 */
function actualizarIndicadorTasa() {
    const selectGlobal = document.getElementById('select-moneda-global');
    if (selectGlobal) selectGlobal.value = monedaGlobal;

    const badgeGlobal = document.getElementById('badge-tasa-global');
    if (badgeGlobal) {
        badgeGlobal.textContent = `1 USD ≈ $${(tasasCambio.MXN || 18.40).toFixed(2)} MXN`;
    }

    const badgeInv = document.getElementById('badge-tasa-inversiones');
    if (badgeInv) {
        badgeInv.textContent = `1 USD ≈ $${(tasasCambio.MXN || 18.40).toFixed(2)} MXN`;
    }

    // Actualizar todas las etiquetas visuales de moneda base en la interfaz
    document.querySelectorAll('.lbl-moneda-base').forEach(el => {
        el.textContent = monedaGlobal;
    });
}

/**
 * Cambia la divisa base de la aplicación (MXN o USD), la persiste y recarga datos.
 */
function cambiarMonedaGlobal(nuevaMoneda) {
    monedaGlobal = nuevaMoneda;
    localStorage.setItem('moneda_global', nuevaMoneda);
    actualizarIndicadorTasa();
    cargarDatos();
}

/**
 * Carga las posiciones bursátiles, tarjetas de resumen, tabla y gráfica de dona.
 */
async function cargarInversiones() {
    try {
        const res = await fetch(`/api/inversiones?moneda_base=${encodeURIComponent(monedaGlobal)}`);
        if (!res.ok) return;
        const data = await res.json();
        const { resumen, posiciones, tasa_usd_mxn } = data;

        if (tasa_usd_mxn) {
            tasasCambio.MXN = tasa_usd_mxn;
            actualizarIndicadorTasa();
        }

        const fmtMoneda = (val) => val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

        // 1. Tarjetas de Resumen de Inversiones
        document.getElementById('lbl-inv-invertido').textContent = `$${fmtMoneda(resumen.total_invertido)} ${monedaGlobal}`;
        document.getElementById('lbl-inv-valor').textContent = `$${fmtMoneda(resumen.total_valor_actual)} ${monedaGlobal}`;
        
        const lblPnl = document.getElementById('lbl-inv-pnl');
        const signo = resumen.total_pnl >= 0 ? '+' : '';
        const signoMonto = resumen.total_pnl < 0 ? '-' : (resumen.total_pnl > 0 ? '+' : '');

        if (lblPnl) {
            lblPnl.innerHTML = `${signoMonto}$${fmtMoneda(Math.abs(resumen.total_pnl))} ${monedaGlobal} <span id="lbl-inv-pnl-pct" class="pnl-badge">(${signo}${resumen.total_pnl_porcentaje.toFixed(2)}%)</span>`;
            lblPnl.className = resumen.total_pnl > 0 ? 'pnl-positivo' : (resumen.total_pnl < 0 ? 'pnl-negativo' : 'pnl-neutro');
        }

        const lblDashPnl = document.getElementById('lbl-dash-pnl');
        if (lblDashPnl) {
            lblDashPnl.innerHTML = `${signoMonto}$${fmtMoneda(Math.abs(resumen.total_pnl))} ${monedaGlobal} <small style="font-size: 0.85rem;">(${signo}${resumen.total_pnl_porcentaje.toFixed(2)}%)</small>`;
            lblDashPnl.className = resumen.total_pnl > 0 ? 'pnl-positivo' : (resumen.total_pnl < 0 ? 'pnl-negativo' : 'pnl-neutro');
        }

        // 2. Tabla de Posiciones Bursátiles
        const tbody = document.getElementById('tabla-inversiones');
        tbody.innerHTML = '';

        if (posiciones.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" style="text-align: center; color: var(--text-muted);">Sin posiciones registradas. ¡Añade tu primer ETF o acción!</td></tr>';
        } else {
            posiciones.forEach(pos => {
                const tr = document.createElement('tr');
                const signoPos = pos.pnl >= 0 ? '+' : '';
                const clasePnl = pos.pnl > 0 ? 'pnl-positivo' : (pos.pnl < 0 ? 'pnl-negativo' : 'pnl-neutro');
                const signoPosMonto = pos.pnl < 0 ? '-' : (pos.pnl > 0 ? '+' : '');

                const badgeMonedaColor = pos.moneda === 'USD' 
                    ? 'background: rgba(46, 204, 113, 0.15); color: #27ae60;' 
                    : 'background: rgba(52, 152, 219, 0.15); color: #2980b9;';

                const subOrig = (pos.moneda !== monedaGlobal)
                    ? `<br><small style="color: var(--text-muted); font-size: 0.75rem;">($${pos.valor_actual_orig.toFixed(2)} ${pos.moneda})</small>`
                    : '';

                tr.innerHTML = `
                    <td><strong>${pos.ticker}</strong></td>
                    <td><span class="badge-peso" style="${badgeMonedaColor}">${pos.moneda}</span></td>
                    <td>${pos.cantidad}</td>
                    <td>$${pos.precio_promedio.toFixed(2)} <small style="color: var(--text-muted);">${pos.moneda}</small></td>
                    <td>$${pos.precio_actual.toFixed(2)} <small style="color: var(--text-muted);">${pos.moneda}</small></td>
                    <td><strong>$${fmtMoneda(pos.valor_actual)}</strong> ${subOrig}</td>
                    <td class="${clasePnl}">${signoPosMonto}$${fmtMoneda(Math.abs(pos.pnl))} (${signoPos}${pos.pnl_porcentaje.toFixed(2)}%)</td>
                    <td><span class="badge-peso">${pos.peso_porcentaje.toFixed(1)}%</span></td>
                    <td class="col-acciones">
                        <button type="button" class="btn-accion btn-editar" onclick="abrirModalEditarInversion(${pos.id}, '${pos.ticker}', ${pos.cantidad}, ${pos.precio_promedio}, '${pos.moneda}')" title="Editar unidades y precio de compra">✏️</button>
                        <button type="button" class="btn-accion btn-eliminar" onclick="eliminarInversion(${pos.id})" title="Eliminar posición">✕</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        }

        // 3. Gráfica de Dona de Asignación de Activos (Asset Allocation)
        actualizarGraficaDona(posiciones);

    } catch (error) {
        console.error("Error al cargar inversiones:", error);
    }
}

/**
 * Renderiza o actualiza la gráfica de dona con los pesos porcentuales de cada ticker.
 */
function actualizarGraficaDona(posiciones) {
    const canvas = document.getElementById('graficaDonaAllocation');
    if (!canvas) return;

    const esOscuro = document.documentElement.getAttribute('data-theme') === 'dark';
    const textColor = esOscuro ? '#e0e0e0' : '#333333';

    // Paleta de colores armoniosa para hasta 12 activos
    const paleta = [
        '#3498db', '#9b59b6', '#2ecc71', '#f39c12',
        '#e74c3c', '#1abc9c', '#34495e', '#e67e22',
        '#00cec9', '#fd79a8', '#6c5ce7', '#fab1a0'
    ];

    const labels = posiciones.map(p => p.ticker);
    const dataValores = posiciones.map(p => p.valor_actual);
    const colores = labels.map((_, i) => paleta[i % paleta.length]);

    if (graficaDona) {
        graficaDona.data.labels = labels;
        graficaDona.data.datasets[0].data = dataValores;
        graficaDona.data.datasets[0].backgroundColor = colores;
        graficaDona.data.datasets[0].borderColor = esOscuro ? '#1e1e1e' : '#ffffff';
        graficaDona.options.plugins.legend.labels.color = textColor;
        graficaDona.update();
    } else {
        graficaDona = new Chart(canvas.getContext('2d'), {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: dataValores,
                    backgroundColor: colores,
                    borderWidth: 2,
                    borderColor: esOscuro ? '#1e1e1e' : '#ffffff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '65%', // Dona estilizada con hueco interior elegante
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: textColor,
                            boxWidth: 12,
                            font: { size: 11 }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const valor = context.raw || 0;
                                const pct = total > 0 ? ((valor / total) * 100).toFixed(1) : 0;
                                const valorFmt = valor.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                                return ` ${context.label}: $${valorFmt} ${monedaGlobal} (${pct}%)`;
                            }
                        }
                    }
                }
            }
        });
    }
}

// =============================================================================
// 7. BUSCADOR Y AUTOCOMPLETADO DE TICKERS (YAHOO FINANCE)
// =============================================================================

let debounceTimerBuscar = null;

/**
 * Inicializa el autocompletado en el input de búsqueda de tickers con debounce de 220ms.
 */
function inicializarBuscadorTickers() {
    const input = document.getElementById('inv-ticker');
    const dropdown = document.getElementById('ticker-sugerencias');
    if (!input || !dropdown) return;

    input.addEventListener('input', (e) => {
        const val = e.target.value.trim();
        clearTimeout(debounceTimerBuscar);

        if (val.length < 1) {
            dropdown.style.display = 'none';
            dropdown.innerHTML = '';
            return;
        }

        // Debounce para evitar llamadas excesivas al escribir rápidamente
        debounceTimerBuscar = setTimeout(async () => {
            try {
                const res = await fetch(`/api/inversiones/buscar?q=${encodeURIComponent(val)}`);
                if (!res.ok) return;
                const sugerencias = await res.json();
                if (input.value.trim().toUpperCase() === val.toUpperCase()) {
                    renderizarSugerenciasTickers(sugerencias, dropdown, input);
                }
            } catch (err) {
                console.error("Error al buscar tickers:", err);
            }
        }, 220);
    });

    // Cerrar el dropdown de sugerencias al hacer clic fuera del componente
    document.addEventListener('click', (e) => {
        if (!input.contains(e.target) && !dropdown.contains(e.target)) {
            dropdown.style.display = 'none';
        }
    });
}

/**
 * Renderiza la lista flotante de sugerencias encontradas.
 */
function renderizarSugerenciasTickers(sugerencias, dropdown, input) {
    if (!sugerencias || sugerencias.length === 0) {
        dropdown.style.display = 'none';
        dropdown.innerHTML = '';
        return;
    }

    dropdown.innerHTML = '';
    sugerencias.forEach(item => {
        const div = document.createElement('div');
        div.className = 'sugerencia-item';
        div.innerHTML = `
            <div class="sugerencia-info">
                <span class="sugerencia-simbolo">${item.symbol}</span>
                <span class="sugerencia-nombre" title="${item.nombre}">${item.nombre}</span>
            </div>
            <span class="sugerencia-badge">${item.tipo}</span>
        `;

        div.addEventListener('click', () => {
            input.value = item.symbol;
            dropdown.style.display = 'none';
            dropdown.innerHTML = '';
            // Consultar precio y moneda automáticamente en tiempo real
            buscarCotizacionTicker();
        });

        dropdown.appendChild(div);
    });

    dropdown.style.display = 'block';
}

/**
 * Consulta la cotización en vivo del ticker escrito y rellena los campos automáticamente.
 */
async function buscarCotizacionTicker() {
    const inputTicker = document.getElementById('inv-ticker');
    const ticker = inputTicker.value.trim().toUpperCase();
    if (!ticker) {
        alert("Por favor ingresa un ticker (ej. VOO, QQQ).");
        return;
    }

    const inputActual = document.getElementById('inv-precio-actual');
    const btn = document.querySelector('.btn-search-ticker');
    const textoOriginal = btn.textContent;
    btn.textContent = '⏳ Buscando...';
    btn.disabled = true;

    try {
        const res = await fetch(`/api/inversiones/cotizar/${ticker}`);
        if (res.ok) {
            const data = await res.json();
            inputActual.value = data.precio;
            
            // Auto-seleccionar la moneda detectada del activo (USD o MXN)
            const selectMoneda = document.getElementById('inv-moneda');
            if (selectMoneda && data.moneda) {
                selectMoneda.value = data.moneda;
            }
        } else {
            const error = await res.json();
            alert(error.detail || "No se encontró cotización en vivo. Puedes ingresarla manualmente.");
        }
    } catch (err) {
        alert("Error de conexión al consultar cotización.");
    } finally {
        btn.textContent = textoOriginal;
        btn.disabled = false;
    }
}

// Listener para registrar una nueva posición en el portafolio
const formInversion = document.getElementById('form-inversion');
if (formInversion) {
    formInversion.addEventListener('submit', async (e) => {
        e.preventDefault();
        e.stopPropagation();

        const ticker = document.getElementById('inv-ticker').value.trim().toUpperCase();
        const cantidad = parseFloat(document.getElementById('inv-cantidad').value);
        const precio_promedio = parseFloat(document.getElementById('inv-precio-promedio').value);
        const actualVal = document.getElementById('inv-precio-actual').value;
        const precio_actual = actualVal ? parseFloat(actualVal) : null;
        const moneda = document.getElementById('inv-moneda')?.value || 'USD';

        if (!ticker || isNaN(cantidad) || isNaN(precio_promedio)) {
            alert("Completa los campos obligatorios.");
            return;
        }

        try {
            const res = await fetch('/api/inversiones', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ticker, cantidad, precio_promedio, precio_actual, moneda })
            });

            if (res.ok) {
                formInversion.reset();
                await cargarInversiones();
                await cargarDatos(); // Sincronizar patrimonio neto general del Dashboard
            } else {
                const err = await res.json();
                alert(err.detail || "Error al registrar la inversión.");
            }
        } catch (err) {
            console.error("Error al registrar inversión:", err);
            alert("Error de red al guardar la inversión.");
        }
    });
}

/**
 * Elimina una posición bursátil de la cartera previa confirmación.
 */
async function eliminarInversion(id) {
    if (!confirm("¿Deseas eliminar esta posición de tu portafolio?")) return;
    try {
        const res = await fetch(`/api/inversiones/${id}`, { method: 'DELETE' });
        if (res.ok) {
            await cargarInversiones();
            await cargarDatos();
        } else {
            alert("No se pudo eliminar la inversión.");
        }
    } catch (err) {
        console.error("Error al eliminar inversión:", err);
    }
}

/**
 * Dispara la sincronización masiva de precios en tiempo real para todas las acciones en cartera.
 */
async function sincronizarPrecios() {
    const btn = document.getElementById('btn-sync-precios');
    const originalText = btn.textContent;
    btn.textContent = '⏳ Sincronizando...';
    btn.disabled = true;

    try {
        const res = await fetch('/api/inversiones/sincronizar', { method: 'POST' });
        if (res.ok) {
            const data = await res.json();
            await cargarInversiones();
            await cargarDatos();
            alert(data.mensaje);
        } else {
            alert("Error al sincronizar cotizaciones.");
        }
    } catch (err) {
        console.error("Error al sincronizar:", err);
        alert("Error de conexión al sincronizar.");
    } finally {
        btn.textContent = originalText;
        btn.disabled = false;
    }
}

// =============================================================================
// 8. SISTEMA DE PESTAÑAS (TABS)
// =============================================================================

/**
 * Configura los botones de pestañas y recupera la última vista activa desde localStorage.
 */
function inicializarTabs() {
    const tabBtns = document.querySelectorAll('.tab-btn');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.getAttribute('data-tab');
            cambiarPestana(targetTab);
        });
    });

    // Cargar pestaña guardada o la inicial por defecto (Dashboard)
    const pestanaGuardada = localStorage.getItem('active_tab') || 'tab-dashboard';
    cambiarPestana(pestanaGuardada);
}

/**
 * Alterna la visibilidad entre secciones y redimensiona las gráficas de Chart.js
 * para evitar deformaciones cuando sus contenedores pasan de display:none a display:block.
 */
function cambiarPestana(tabId) {
    const targetContent = document.getElementById(tabId);
    if (!targetContent) return;

    // Actualizar estados visuales de los botones
    document.querySelectorAll('.tab-btn').forEach(b => {
        b.classList.toggle('active', b.getAttribute('data-tab') === tabId);
    });

    // Alternar paneles de contenido
    document.querySelectorAll('.tab-content').forEach(c => {
        c.classList.toggle('active', c.id === tabId);
    });

    localStorage.setItem('active_tab', tabId);

    // Ajustar tamaño de gráficas de Chart.js cuando su contenedor se vuelve visible
    setTimeout(() => {
        if (miGrafica) miGrafica.resize();
        if (graficaDona) graficaDona.resize();
    }, 60);
}

// =============================================================================
// 9. MODALES DE EDICIÓN: INVERSIONES Y MOVIMIENTOS
// =============================================================================

/**
 * Abre el modal para editar unidades y costo promedio de un activo bursátil.
 */
function abrirModalEditarInversion(id, ticker, cantidad, precio_promedio, moneda) {
    const inputId = document.getElementById('modal-edit-id');
    const lblTicker = document.getElementById('modal-edit-ticker');
    const inputCant = document.getElementById('modal-edit-cantidad');
    const inputProm = document.getElementById('modal-edit-precio-promedio');
    const lblMoneda = document.getElementById('modal-edit-moneda');

    if (inputId) inputId.value = id;
    if (lblTicker) lblTicker.textContent = ticker;
    if (inputCant) inputCant.value = cantidad;
    if (inputProm) inputProm.value = precio_promedio;
    if (lblMoneda) lblMoneda.textContent = moneda || 'USD';

    const modal = document.getElementById('modal-editar-inversion');
    if (modal) {
        modal.style.display = 'flex';
        setTimeout(() => {
            if (inputCant) {
                inputCant.focus();
                inputCant.select();
            }
        }, 50);
    }
}

/**
 * Cierra el modal de edición de inversión.
 */
function cerrarModalEditarInversion() {
    const modal = document.getElementById('modal-editar-inversion');
    if (modal) {
        modal.style.display = 'none';
    }
}

/**
 * Guarda los cambios realizados en una posición bursátil.
 */
async function guardarEdicionInversion(e) {
    if (e) {
        e.preventDefault();
        e.stopPropagation();
    }

    const id = document.getElementById('modal-edit-id').value;
    const cantidad = parseFloat(document.getElementById('modal-edit-cantidad').value);
    const precio_promedio = parseFloat(document.getElementById('modal-edit-precio-promedio').value);

    if (isNaN(cantidad) || cantidad <= 0 || isNaN(precio_promedio) || precio_promedio <= 0) {
        alert("Por favor ingresa valores numéricos válidos mayores a cero.");
        return;
    }

    try {
        const res = await fetch(`/api/inversiones/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cantidad, precio_promedio })
        });

        if (res.ok) {
            cerrarModalEditarInversion();
            await cargarInversiones();
            await cargarDatos();
        } else {
            const err = await res.json();
            alert(err.detail || "Error al actualizar la posición.");
        }
    } catch (err) {
        console.error("Error al actualizar posición:", err);
        alert("Error de red al intentar guardar los cambios.");
    }
}

/**
 * Abre el modal para editar una transacción existente de flujo de efectivo.
 */
function abrirModalEditarTransaccion(id, fecha, monto, tipo, descripcion) {
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

/**
 * Cierra el modal de edición de transacciones.
 */
function cerrarModalEditarTransaccion() {
    const modal = document.getElementById('modal-editar-transaccion');
    if (modal) {
        modal.style.display = 'none';
    }
}

/**
 * Envía la actualización de la transacción al backend.
 */
async function guardarEdicionTransaccion(e) {
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
        const res = await fetch(`/api/transacciones/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ fecha, tipo, monto, descripcion })
        });

        if (res.ok) {
            cerrarModalEditarTransaccion();
            await cargarDatos();
        } else {
            const err = await res.json();
            alert(err.detail || "Error al actualizar el movimiento.");
        }
    } catch (err) {
        console.error("Error al actualizar el movimiento:", err);
        alert("Error de red al intentar guardar los cambios.");
    }
}

// Accesibilidad: Cerrar cualquier modal activo al presionar la tecla Escape
window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        cerrarModalEditarInversion();
        cerrarModalEditarTransaccion();
    }
});

// =============================================================================
// 10. EXPORTACIÓN A EXCEL
// =============================================================================

/**
 * Dispara la descarga del libro contable en Excel (.xlsx) respetando la divisa base activa.
 */
function exportarExcel() {
    const url = `/api/exportar-excel?moneda_base=${encodeURIComponent(monedaGlobal)}`;
    window.location.href = url;
}

// =============================================================================
// 11. EXPOSICIÓN GLOBAL DE FUNCIONES AL OBJETO WINDOW
// Permite que los atributos onclick del HTML invoquen estas funciones de forma segura.
// =============================================================================
window.exportarExcel = exportarExcel;
window.toggleMetaInput = toggleMetaInput;
window.realizarMovimiento = realizarMovimiento;
window.eliminarApartado = eliminarApartado;
window.eliminarTransaccion = eliminarTransaccion;
window.abrirModalEditarTransaccion = abrirModalEditarTransaccion;
window.cerrarModalEditarTransaccion = cerrarModalEditarTransaccion;
window.guardarEdicionTransaccion = guardarEdicionTransaccion;
window.buscarCotizacionTicker = buscarCotizacionTicker;
window.sincronizarPrecios = sincronizarPrecios;
window.eliminarInversion = eliminarInversion;
window.abrirModalEditarInversion = abrirModalEditarInversion;
window.cerrarModalEditarInversion = cerrarModalEditarInversion;
window.guardarEdicionInversion = guardarEdicionInversion;
window.cambiarPestana = cambiarPestana;
window.cambiarMonedaGlobal = cambiarMonedaGlobal;
window.cambiarMonedaInversiones = cambiarMonedaGlobal; // Alias de retrocompatibilidad

// =============================================================================
// 12. ARRANQUE AUTOMÁTICO DE LA APLICACIÓN
// =============================================================================
inicializarTabs();
inicializarBuscadorTickers();
cargarTiposCambio();
cargarDatos();
