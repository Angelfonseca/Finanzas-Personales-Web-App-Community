document.getElementById('fecha').valueAsDate = new Date();

const form = document.getElementById('transaccion-form');
const mensajeDiv = document.getElementById('mensaje');
const btnModo = document.getElementById('btn-modo');
let miGrafica = null;
let graficaDona = null;

// --- GESTIÓN DE MODO OSCURO ---
const temaGuardado = localStorage.getItem('theme');
if (temaGuardado === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
    btnModo.textContent = '☀️ Modo Claro';
}

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
    if (miGrafica) {
        actualizarColoresGrafica();
    }
    if (graficaDona) {
        actualizarColoresDona();
    }
});

function actualizarColoresGrafica() {
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

function actualizarColoresDona() {
    if (!graficaDona) return;
    const esOscuro = document.documentElement.getAttribute('data-theme') === 'dark';
    const textColor = esOscuro ? '#e0e0e0' : '#333333';
    graficaDona.options.plugins.legend.labels.color = textColor;
    graficaDona.update();
}

// --- CARGA GENERAL DE DATOS ---
async function cargarDatos() {
    try {
        // 1. Resumen general unificado en moneda base
        const resResumen = await fetch(`/api/resumen?moneda_base=${encodeURIComponent(monedaGlobal)}`);
        const dataResumen = await resResumen.json();
        
        // Etiquetas del Dashboard General
        if (document.getElementById('lbl-dash-patrimonio')) {
            document.getElementById('lbl-dash-patrimonio').textContent = `$${dataResumen.patrimonio_neto.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${monedaGlobal}`;
            document.getElementById('lbl-dash-balance').textContent = `$${dataResumen.balance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
            document.getElementById('lbl-dash-apartados').textContent = `$${dataResumen.apartados.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
            document.getElementById('lbl-dash-inversiones').textContent = `$${dataResumen.inversiones.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${monedaGlobal}`;
            document.getElementById('lbl-dash-ingresos').textContent = `$${dataResumen.ingresos.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
            document.getElementById('lbl-dash-gastos').textContent = `$${dataResumen.gastos.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
        }

        // Pestaña de Apartados (píldora superior)
        if (document.getElementById('lbl-apartados-total-acum')) {
            document.getElementById('lbl-apartados-total-acum').textContent = `$${dataResumen.apartados.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
        }

        // Pestaña de Movimientos
        if (document.getElementById('lbl-balance')) {
            document.getElementById('lbl-balance').textContent = `$${dataResumen.balance.toFixed(2)}`;
            document.getElementById('lbl-ingresos').textContent = `$${dataResumen.ingresos.toFixed(2)}`;
            document.getElementById('lbl-gastos').textContent = `$${dataResumen.gastos.toFixed(2)}`;
        }

        // 2. Resumen mensual
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

        actualizarGrafica(dataMensual.slice().reverse());

        // 3. Tabla de transacciones
        const resTrans = await fetch('/api/transacciones');
        const dataTrans = await resTrans.json();
        
        const tbody = document.getElementById('tabla-movimientos');
        tbody.innerHTML = '';

        if (dataTrans.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No hay movimientos.</td></tr>';
        } else {
            dataTrans.forEach(t => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${t.fecha}</td>
                    <td>${t.descripcion || '-'}</td>
                    <td class="${t.tipo === 'gasto' ? 'text-gasto' : 'text-ingreso'}">${t.tipo.toUpperCase()}</td>
                    <td>$${t.monto.toFixed(2)}</td>
                    <td><button class="btn-eliminar" onclick="eliminarTransaccion(${t.id})">X</button></td>
                `;
                tbody.appendChild(tr);
            });
        }

        // 4. Cargar apartados y metas
        await cargarApartados();

        // 5. Cargar módulo de inversiones (Fase 7)
        await cargarInversiones();

    } catch (error) {
        console.error("Error al actualizar datos:", error);
    }
}

function actualizarGrafica(dataMensual) {
    const ctx = document.getElementById('graficaFinanzas').getContext('2d');
    const esOscuro = document.documentElement.getAttribute('data-theme') === 'dark';
    const textColor = esOscuro ? '#e0e0e0' : '#333333';
    const gridColor = esOscuro ? '#333333' : '#eee';
    
    const meses = dataMensual.map(m => m.mes);
    const ingresos = dataMensual.map(m => m.ingresos);
    const gastos = dataMensual.map(m => m.gastos);

    if (miGrafica) {
        miGrafica.data.labels = meses;
        miGrafica.data.datasets[0].data = ingresos;
        miGrafica.data.datasets[1].data = gastos;
        miGrafica.update();
    } else {
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

// --- TRANSACCIONES ---
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
            document.getElementById('fecha').valueAsDate = new Date();
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

// --- APARTADOS Y METAS ---
function toggleMetaInput() {
    const tipo = document.getElementById('tipo-apartado').value;
    const metaGroup = document.getElementById('group-meta-monto');
    metaGroup.style.display = tipo === 'meta' ? 'block' : 'none';
}

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
                await cargarApartados();
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
async function eliminarApartado(id) {
    if (!confirm("¿Seguro que deseas eliminar este apartado? Se perderá el registro de este sobre.")) return;

    try {
        const res = await fetch(`/api/apartados/${id}`, {
            method: 'DELETE'
        });

        if (res.ok) {
            cargarApartados();
        } else {
            alert("No se pudo eliminar el apartado.");
        }
    } catch (error) {
        console.error("Error al eliminar:", error);
    }
}

// Asegúrate de agregarla a los exports globales al final de app.js:
window.eliminarApartado = eliminarApartado;

// ==========================================
// --- MÓDULO DE INVERSIONES & ASSET ALLOCATION (FASE 7) ---
// ==========================================

// --- ESTADO DE MONEDA GLOBAL Y TIPOS DE CAMBIO ---
let monedaGlobal = localStorage.getItem('moneda_global') || 'MXN';
let tasasCambio = { USD: 1.0, MXN: 18.40, EUR: 0.89 };

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

    // Actualizar todas las etiquetas de moneda base en la interfaz
    document.querySelectorAll('.lbl-moneda-base').forEach(el => {
        el.textContent = monedaGlobal;
    });
}

function cambiarMonedaGlobal(nuevaMoneda) {
    monedaGlobal = nuevaMoneda;
    localStorage.setItem('moneda_global', nuevaMoneda);
    actualizarIndicadorTasa();
    cargarDatos();
}

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

        // 1. Actualizar Tarjetas de Resumen
        document.getElementById('lbl-inv-invertido').textContent = `$${resumen.total_invertido.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${monedaGlobal}`;
        document.getElementById('lbl-inv-valor').textContent = `$${resumen.total_valor_actual.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${monedaGlobal}`;
        
        const lblPnl = document.getElementById('lbl-inv-pnl');
        const signo = resumen.total_pnl >= 0 ? '+' : '';
        const signoMonto = resumen.total_pnl < 0 ? '-' : (resumen.total_pnl > 0 ? '+' : '');

        if (lblPnl) {
            lblPnl.innerHTML = `${signoMonto}$${Math.abs(resumen.total_pnl).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${monedaGlobal} <span id="lbl-inv-pnl-pct" class="pnl-badge">(${signo}${resumen.total_pnl_porcentaje.toFixed(2)}%)</span>`;
            lblPnl.className = resumen.total_pnl > 0 ? 'pnl-positivo' : (resumen.total_pnl < 0 ? 'pnl-negativo' : 'pnl-neutro');
        }

        const lblDashPnl = document.getElementById('lbl-dash-pnl');
        if (lblDashPnl) {
            lblDashPnl.innerHTML = `${signoMonto}$${Math.abs(resumen.total_pnl).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${monedaGlobal} <small style="font-size: 0.85rem;">(${signo}${resumen.total_pnl_porcentaje.toFixed(2)}%)</small>`;
            lblDashPnl.className = resumen.total_pnl > 0 ? 'pnl-positivo' : (resumen.total_pnl < 0 ? 'pnl-negativo' : 'pnl-neutro');
        }

        // 2. Actualizar Tabla de Posiciones
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
                    <td><strong>$${pos.valor_actual.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong> ${subOrig}</td>
                    <td class="${clasePnl}">${signoPosMonto}$${Math.abs(pos.pnl).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} (${signoPos}${pos.pnl_porcentaje.toFixed(2)}%)</td>
                    <td><span class="badge-peso">${pos.peso_porcentaje.toFixed(1)}%</span></td>
                    <td>
                        <button type="button" class="btn-eliminar" onclick="eliminarInversion(${pos.id})" title="Eliminar posición">X</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        }

        // 3. Actualizar Gráfica de Dona
        actualizarGraficaDona(posiciones);

    } catch (error) {
        console.error("Error al cargar inversiones:", error);
    }
}

function actualizarGraficaDona(posiciones) {
    const canvas = document.getElementById('graficaDonaAllocation');
    if (!canvas) return;

    const esOscuro = document.documentElement.getAttribute('data-theme') === 'dark';
    const textColor = esOscuro ? '#e0e0e0' : '#333333';

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
                cutout: '65%',
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
                                return ` ${context.label}: $${valor.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${monedaGlobal} (${pct}%)`;
                            }
                        }
                    }
                }
            }
        });
    }
}

// --- BUSCADOR Y AUTOCOMPLETADO DE TICKERS ---
let debounceTimerBuscar = null;

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

        debounceTimerBuscar = setTimeout(async () => {
            try {
                const res = await fetch(`/api/inversiones/buscar?q=${encodeURIComponent(val)}`);
                if (!res.ok) return;
                const sugerencias = await res.json();
                renderizarSugerenciasTickers(sugerencias, dropdown, input);
            } catch (err) {
                console.error("Error al buscar tickers:", err);
            }
        }, 220);
    });

    // Cerrar sugerencias al hacer clic fuera del componente
    document.addEventListener('click', (e) => {
        if (!input.contains(e.target) && !dropdown.contains(e.target)) {
            dropdown.style.display = 'none';
        }
    });
}

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
            // Consultar precio automáticamente en tiempo real
            buscarCotizacionTicker();
        });

        dropdown.appendChild(div);
    });

    dropdown.style.display = 'block';
}

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

            console.log(`Cotización obtenida para ${data.ticker}: $${data.precio} ${data.moneda || 'USD'}`);
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
                await cargarDatos(); // Sincronizar patrimonio neto general
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

async function eliminarInversion(id) {
    if (!confirm("¿Deseas eliminar esta posición de tu portafolio?")) return;
    try {
        const res = await fetch(`/api/inversiones/${id}`, { method: 'DELETE' });
        if (res.ok) {
            await cargarInversiones();
            await cargarDatos(); // Sincronizar patrimonio neto general
        } else {
            alert("No se pudo eliminar la inversión.");
        }
    } catch (err) {
        console.error("Error al eliminar inversión:", err);
    }
}

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
            await cargarDatos(); // Sincronizar patrimonio neto general
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

// ==========================================
// --- SISTEMA DE PESTAÑAS (TABS) ---
// ==========================================

function inicializarTabs() {
    const tabBtns = document.querySelectorAll('.tab-btn');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.getAttribute('data-tab');
            cambiarPestana(targetTab);
        });
    });

    // Cargar pestaña guardada o la inicial (Dashboard)
    const pestanaGuardada = localStorage.getItem('active_tab') || 'tab-dashboard';
    cambiarPestana(pestanaGuardada);
}

function cambiarPestana(tabId) {
    const targetContent = document.getElementById(tabId);
    if (!targetContent) return;

    // Actualizar botones
    document.querySelectorAll('.tab-btn').forEach(b => {
        b.classList.toggle('active', b.getAttribute('data-tab') === tabId);
    });

    // Actualizar contenidos
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

// EXPONER FUNCIONES PARA EL DOM
window.toggleMetaInput = toggleMetaInput;
window.realizarMovimiento = realizarMovimiento;
window.eliminarTransaccion = eliminarTransaccion;
window.buscarCotizacionTicker = buscarCotizacionTicker;
window.sincronizarPrecios = sincronizarPrecios;
window.eliminarInversion = eliminarInversion;
window.cambiarPestana = cambiarPestana;
window.cambiarMonedaGlobal = cambiarMonedaGlobal;
window.cambiarMonedaInversiones = cambiarMonedaGlobal; // compatibilidad

// ARRANQUE DE APLICACIÓN
inicializarTabs();
inicializarBuscadorTickers();
cargarTiposCambio();
cargarDatos();



