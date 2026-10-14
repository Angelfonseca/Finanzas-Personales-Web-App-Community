/**
 * static/app.js - Controlador Principal del Frontend (SPA Multi-Tenant)
 * 
 * Este módulo gestiona:
 * 1. Autenticación JWT y Guardias de Ruta (Login, Logout y Validación de Sesión).
 * 2. Cliente HTTP Interceptor (apiFetch) con inyección automática de Bearer Token y captura 401/403.
 * 3. Purga Limpia de Estado al Cerrar Sesión (destrucción de Chart.js, memoria y DOM).
 * 4. Navegación por pestañas (Dashboard, Movimientos, Metas, Inversiones y Panel de Administración).
 * 5. Panel de Administración: KPIs de tenants, tabla de usuarios con tiempo relativo y modal de alta.
 * 6. Visualizaciones reactivas con Chart.js y autocompletado en tiempo real con Yahoo Finance.
 */

// =============================================================================
// 1. ESTADO GLOBAL DE LA APLICACIÓN
// =============================================================================

let usuarioActual = null;          // Objeto con metadata del usuario en sesión
let miGrafica = null;              // Instancia Chart.js de barras (Ingresos vs Gastos)
let graficaDona = null;            // Instancia Chart.js de dona (Asset Allocation)
let monedaGlobal = localStorage.getItem('moneda_global') || 'MXN';
let tasasCambio = { USD: 1.0, MXN: 18.40, EUR: 0.89 };
let debounceTimerBuscar = null;

// =============================================================================
// 2. CLIENTE HTTP INTERCEPTOR (apiFetch)
// =============================================================================

/**
 * Cliente HTTP centralizado que intercepta todas las peticiones hacia la API:
 * 1. Inyecta la cabecera 'Authorization: Bearer <token>' automáticamente.
 * 2. Si el servidor responde 401 Unauthorized o 403 Forbidden, purga la sesión
 *    y redirige de inmediato a la pantalla de login.
 */
async function apiFetch(url, options = {}) {
    const token = localStorage.getItem('jwt_token');
    const headers = options.headers ? { ...options.headers } : {};

    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(url, { ...options, headers });

    // Si el token expiró o la cuenta fue suspendida en master_db
    if (response.status === 401 || response.status === 403) {
        if (!url.includes('/auth/login')) {
            cerrarSesionLimpia("Tu sesión ha expirado o tu cuenta ha sido suspendida.");
            throw new Error("No autorizado");
        }
    }

    return response;
}

// =============================================================================
// 3. AUTENTICACIÓN, LOGIN Y PURGA DE SESIÓN
// =============================================================================

/**
 * Verifica si existe una sesión activa válida al cargar la aplicación.
 */
async function verificarSesionInicial() {
    const token = localStorage.getItem('jwt_token');
    const vistaLogin = document.getElementById('vista-login');
    const vistaApp = document.getElementById('vista-app');

    if (!token) {
        mostrarVistaLogin();
        return;
    }

    try {
        const res = await apiFetch('/auth/me');
        if (res.ok) {
            const data = await res.json();
            establecerSesionActiva(data.user, token);
        } else {
            cerrarSesionLimpia();
        }
    } catch (e) {
        cerrarSesionLimpia();
    }
}

/**
 * Muestra la vista de login y oculta la aplicación financiera.
 */
function mostrarVistaLogin(errorMsg = '') {
    const vistaLogin = document.getElementById('vista-login');
    const vistaApp = document.getElementById('vista-app');
    const loginError = document.getElementById('login-error');

    if (vistaLogin) vistaLogin.style.display = 'flex';
    if (vistaApp) vistaApp.style.display = 'none';

    if (loginError) {
        if (errorMsg) {
            loginError.textContent = errorMsg;
            loginError.style.display = 'block';
        } else {
            loginError.style.display = 'none';
        }
    }
}

/**
 * Configura la UI para el usuario autenticado y carga sus datos.
 */
function establecerSesionActiva(user, token) {
    usuarioActual = user;
    localStorage.setItem('jwt_token', token);
    localStorage.setItem('user_info', JSON.stringify(user));

    // Ocultar login y mostrar aplicación
    const vistaLogin = document.getElementById('vista-login');
    const vistaApp = document.getElementById('vista-app');
    if (vistaLogin) vistaLogin.style.display = 'none';
    if (vistaApp) vistaApp.style.display = 'block';

    // Actualizar badges de usuario en el header
    const lblUser = document.getElementById('lbl-username');
    const lblRole = document.getElementById('lbl-user-role');
    if (lblUser) lblUser.textContent = user.username;
    if (lblRole) {
        lblRole.textContent = user.role;
        lblRole.className = `badge-role ${user.role === 'admin' ? 'badge-role-admin' : 'badge-role-user'}`;
    }

    // Pestaña de administración: visible estrictamente para rol admin
    const btnTabAdmin = document.getElementById('btn-tab-admin');
    if (btnTabAdmin) {
        btnTabAdmin.style.display = (user.role === 'admin') ? 'inline-block' : 'none';
    }

    // Cargar datos financieros del tenant
    cargarTiposCambio();
    cargarDatos();

    // Si es administrador, precargar datos de gestión
    if (user.role === 'admin') {
        cargarDatosAdmin();
    }
}

/**
 * Maneja el envío del formulario de login.
 */
async function iniciarSesion(e) {
    e.preventDefault();
    const usernameInput = document.getElementById('login-username');
    const passwordInput = document.getElementById('login-password');
    const loginError = document.getElementById('login-error');
    const btnSubmit = document.getElementById('btn-login-submit');

    const username = usernameInput.value.trim();
    const password = passwordInput.value;

    if (!username || !password) return;

    btnSubmit.disabled = true;
    btnSubmit.textContent = '⏳ Verificando credenciales...';
    if (loginError) loginError.style.display = 'none';

    try {
        const res = await fetch('/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });

        const data = await res.json();

        if (res.ok && data.access_token) {
            usernameInput.value = '';
            passwordInput.value = '';
            establecerSesionActiva(data.user, data.access_token);
        } else {
            loginError.textContent = data.detail || 'Usuario o contraseña incorrectos.';
            loginError.style.display = 'block';
        }
    } catch (err) {
        loginError.textContent = 'Error de conexión con el servidor.';
        loginError.style.display = 'block';
    } finally {
        btnSubmit.disabled = false;
        btnSubmit.textContent = 'Ingresar a la Plataforma';
    }
}

/**
 * Cierre de sesión voluntario por parte del usuario.
 */
function logoutUsuario() {
    if (confirm("¿Deseas cerrar tu sesión actual?")) {
        cerrarSesionLimpia();
    }
}

/**
 * Purga completa de sesión y aislamiento total de memoria:
 * 1. Elimina tokens de localStorage.
 * 2. Destruye instancias activas de Chart.js.
 * 3. Vacía variables de memoria y tablas del DOM.
 * 4. Muestra la pantalla de login para evitar contaminación visual entre cuentas.
 */
function cerrarSesionLimpia(errorMsg = '') {
    // 1. Eliminar persistencia local
    localStorage.removeItem('jwt_token');
    localStorage.removeItem('user_info');
    usuarioActual = null;

    // 2. Destruir instancias de Chart.js
    if (miGrafica) {
        miGrafica.destroy();
        miGrafica = null;
    }
    if (graficaDona) {
        graficaDona.destroy();
        graficaDona = null;
    }

    // 3. Limpiar elementos del DOM
    const tMov = document.getElementById('tabla-movimientos');
    if (tMov) tMov.innerHTML = '';

    const tInv = document.getElementById('tabla-inversiones');
    if (tInv) tInv.innerHTML = '';

    const tApt = document.getElementById('contenedor-apartados');
    if (tApt) tApt.innerHTML = '';

    const lMes = document.getElementById('lista-resumen-mensual');
    if (lMes) lMes.innerHTML = '';

    const tAdm = document.getElementById('tabla-usuarios-admin');
    if (tAdm) tAdm.innerHTML = '';

    // Restablecer etiquetas numéricas a cero
    document.querySelectorAll('[id^="lbl-dash-"], [id^="lbl-inv-"], #lbl-balance, #lbl-ingresos, #lbl-gastos, #lbl-apartados-total-acum').forEach(el => {
        el.textContent = '$0.00';
    });

    // Ocultar botón de admin y restablecer pestaña por defecto
    const btnTabAdmin = document.getElementById('btn-tab-admin');
    if (btnTabAdmin) btnTabAdmin.style.display = 'none';
    cambiarPestana('tab-dashboard');

    // 4. Mostrar pantalla de login
    mostrarVistaLogin(errorMsg);
}

// =============================================================================
// 4. GESTIÓN DEL TEMA VISUAL (MODO OSCURO / CLARO)
// =============================================================================

const btnModo = document.getElementById('btn-modo');
const temaGuardado = localStorage.getItem('theme');
if (temaGuardado === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
    if (btnModo) btnModo.textContent = '☀️ Modo Claro';
}

if (btnModo) {
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
        if (miGrafica) actualizarColoresGrafica();
        if (graficaDona) actualizarColoresDona();
    });
}

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
// 5. CARGA DE DATOS FINANCIEROS DEL TENANT ACTIVO
// =============================================================================

function obtenerFechaLocalISO() {
    const d = new Date();
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

const inputFecha = document.getElementById('fecha');
if (inputFecha) inputFecha.value = obtenerFechaLocalISO();

async function cargarDatos() {
    try {
        const fmtMoneda = (val) => Number(val || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

        // 1. Resumen Consolidado del Tenant
        const resResumen = await apiFetch(`/api/resumen?moneda_base=${encodeURIComponent(monedaGlobal)}`);
        const dataResumen = await resResumen.json();
        
        if (document.getElementById('lbl-dash-patrimonio')) {
            document.getElementById('lbl-dash-patrimonio').textContent = `$${fmtMoneda(dataResumen.patrimonio_neto)} ${monedaGlobal}`;
            document.getElementById('lbl-dash-balance').textContent = `$${fmtMoneda(dataResumen.balance)}`;
            document.getElementById('lbl-dash-apartados').textContent = `$${fmtMoneda(dataResumen.apartados)}`;
            document.getElementById('lbl-dash-inversiones').textContent = `$${fmtMoneda(dataResumen.inversiones)} ${monedaGlobal}`;
            document.getElementById('lbl-dash-ingresos').textContent = `$${fmtMoneda(dataResumen.ingresos)}`;
            document.getElementById('lbl-dash-gastos').textContent = `$${fmtMoneda(dataResumen.gastos)}`;
        }

        if (document.getElementById('lbl-apartados-total-acum')) {
            document.getElementById('lbl-apartados-total-acum').textContent = `$${fmtMoneda(dataResumen.apartados)}`;
        }

        if (document.getElementById('lbl-balance')) {
            document.getElementById('lbl-balance').textContent = `$${Number(dataResumen.balance).toFixed(2)}`;
            document.getElementById('lbl-ingresos').textContent = `$${Number(dataResumen.ingresos).toFixed(2)}`;
            document.getElementById('lbl-gastos').textContent = `$${Number(dataResumen.gastos).toFixed(2)}`;
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
                            <span style="color: #2ecc71;">+${Number(m.ingresos).toFixed(2)}</span>
                            <span style="color: #e74c3c;">-${Number(m.gastos).toFixed(2)}</span>
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
                    const tr = document.createElement('tr');
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
                        <td>$${Number(t.monto).toFixed(2)}</td>
                        <td class="col-acciones">
                            <button type="button" class="btn-accion btn-editar" onclick="abrirModalEditarTransaccion(${t.id}, '${t.fecha}', ${t.monto}, '${t.tipo}', '${descSegura}')" title="Editar movimiento">✏️</button>
                            <button type="button" class="btn-accion btn-eliminar" onclick="eliminarTransaccion(${t.id})" title="Eliminar movimiento">✕</button>
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

function actualizarGrafica(dataMensual) {
    const canvas = document.getElementById('graficaFinanzas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
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
                    x: { ticks: { color: textColor }, grid: { color: gridColor } },
                    y: { beginAtZero: true, ticks: { color: textColor }, grid: { color: gridColor } }
                },
                plugins: {
                    legend: { labels: { color: textColor } }
                }
            }
        });
    }
}

// Listener de registro de transacciones
const formTrans = document.getElementById('transaccion-form');
if (formTrans) {
    formTrans.addEventListener('submit', async (e) => {
        e.preventDefault();
        const mensajeDiv = document.getElementById('mensaje');

        const datos = {
            fecha: document.getElementById('fecha').value,
            monto: parseFloat(document.getElementById('monto').value),
            tipo: document.getElementById('tipo').value,
            descripcion: document.getElementById('descripcion').value,
            categoria_id: 1
        };

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
                cargarDatos();
            } else {
                if (mensajeDiv) {
                    mensajeDiv.style.color = '#e74c3c';
                    mensajeDiv.textContent = 'Error al guardar.';
                }
            }
        } catch (error) {
            if (mensajeDiv) {
                mensajeDiv.style.color = '#e74c3c';
                mensajeDiv.textContent = 'Error de conexión.';
            }
        }
    });
}

async function eliminarTransaccion(id) {
    if (!confirm("¿Eliminar este movimiento?")) return;
    try {
        const response = await apiFetch(`/api/transacciones/${id}`, { method: 'DELETE' });
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
// 6. APARTADOS Y METAS DE AHORRO
// =============================================================================

function toggleMetaInput() {
    const tipo = document.getElementById('tipo-apartado').value;
    const metaGroup = document.getElementById('group-meta-monto');
    if (metaGroup) metaGroup.style.display = tipo === 'meta' ? 'block' : 'none';
}

async function cargarApartados() {
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
                <h3 style="margin: 0 20px 8px 0;">${item.nombre} <small style="font-weight: normal; font-size: 0.8rem;">(${item.tipo})</small></h3>
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

const formApartado = document.getElementById('form-apartado');
if (formApartado) {
    formApartado.addEventListener('submit', async (e) => {
        e.preventDefault();
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
            const res = await apiFetch('/api/apartados', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ nombre, tipo, meta_monto })
            });

            if (res.ok) {
                cerrarModalCrearApartado();
                await cargarDatos();
            } else {
                const error = await res.json();
                alert(error.detail || 'Error al crear apartado');
            }
        } catch (err) {
            alert("Error al conectar con el servidor.");
        }
    });
}

function abrirModalCrearApartado() {
    const modal = document.getElementById('modal-crear-apartado');
    if (modal) {
        modal.style.display = 'flex';
        setTimeout(() => {
            const input = document.getElementById('nombre-apartado');
            if (input) input.focus();
        }, 50);
    }
}

function cerrarModalCrearApartado() {
    const modal = document.getElementById('modal-crear-apartado');
    if (modal) modal.style.display = 'none';
    const form = document.getElementById('form-apartado');
    if (form) form.reset();
    toggleMetaInput();
}

async function realizarMovimiento(id, accion) {
    const input = document.getElementById(`monto-acc-${id}`);
    const monto = parseFloat(input.value);

    if (isNaN(monto) || monto <= 0) {
        alert('Ingresa un monto válido.');
        return;
    }

    const res = await apiFetch(`/api/apartados/${id}/movimiento`, {
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
        const res = await apiFetch(`/api/apartados/${id}`, { method: 'DELETE' });
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
// 7. INVERSIONES & ASSET ALLOCATION
// =============================================================================

async function cargarTiposCambio() {
    try {
        const res = await apiFetch('/api/tipo-cambio');
        if (res.ok) {
            const data = await res.json();
            tasasCambio = data.tasas || tasasCambio;
            actualizarIndicadorTasa();
        }
    } catch (e) {
        console.warn("No se pudo obtener tipo de cambio:", e);
    }
}

function actualizarIndicadorTasa() {
    const selectGlobal = document.getElementById('select-moneda-global');
    if (selectGlobal) selectGlobal.value = monedaGlobal;

    const badgeGlobal = document.getElementById('badge-tasa-global');
    if (badgeGlobal) badgeGlobal.textContent = `1 USD ≈ $${Number(tasasCambio.MXN || 18.40).toFixed(2)} MXN`;

    const badgeInv = document.getElementById('badge-tasa-inversiones');
    if (badgeInv) badgeInv.textContent = `1 USD ≈ $${Number(tasasCambio.MXN || 18.40).toFixed(2)} MXN`;

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
        const res = await apiFetch(`/api/inversiones?moneda_base=${encodeURIComponent(monedaGlobal)}`);
        if (!res.ok) return;
        const data = await res.json();
        const { resumen, posiciones, tasa_usd_mxn } = data;

        if (tasa_usd_mxn) {
            tasasCambio.MXN = tasa_usd_mxn;
            actualizarIndicadorTasa();
        }

        const fmtMoneda = (val) => Number(val || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

        // Tarjetas de Resumen
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

        // Tabla de Inversiones
        const tbody = document.getElementById('tabla-inversiones');
        if (tbody) {
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
                        ? `<br><small style="color: var(--text-muted); font-size: 0.75rem;">($${Number(pos.valor_actual_orig).toFixed(2)} ${pos.moneda})</small>`
                        : '';

                    tr.innerHTML = `
                        <td><strong>${pos.ticker}</strong></td>
                        <td><span class="badge-peso" style="${badgeMonedaColor}">${pos.moneda}</span></td>
                        <td>${pos.cantidad}</td>
                        <td>$${Number(pos.precio_promedio).toFixed(2)} <small style="color: var(--text-muted);">${pos.moneda}</small></td>
                        <td>$${Number(pos.precio_actual).toFixed(2)} <small style="color: var(--text-muted);">${pos.moneda}</small></td>
                        <td><strong>$${fmtMoneda(pos.valor_actual)}</strong> ${subOrig}</td>
                        <td class="${clasePnl}">${signoPosMonto}$${fmtMoneda(Math.abs(pos.pnl))} (${signoPos}${pos.pnl_porcentaje.toFixed(2)}%)</td>
                        <td><span class="badge-peso">${pos.peso_porcentaje.toFixed(1)}%</span></td>
                        <td class="col-acciones">
                            <button type="button" class="btn-accion btn-editar" onclick="abrirModalEditarInversion(${pos.id}, '${pos.ticker}', ${pos.cantidad}, ${pos.precio_promedio}, '${pos.moneda}')" title="Editar posición">✏️</button>
                            <button type="button" class="btn-accion btn-eliminar" onclick="eliminarInversion(${pos.id})" title="Eliminar posición">✕</button>
                        </td>
                    `;
                    tbody.appendChild(tr);
                });
            }
        }

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
                        labels: { color: textColor, boxWidth: 12, font: { size: 11 } }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const valor = context.raw || 0;
                                const pct = total > 0 ? ((valor / total) * 100).toFixed(1) : 0;
                                const valorFmt = Number(valor).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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
// 8. BUSCADOR Y AUTOCOMPLETADO DE TICKERS
// =============================================================================

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
                const res = await apiFetch(`/api/inversiones/buscar?q=${encodeURIComponent(val)}`);
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
        const res = await apiFetch(`/api/inversiones/cotizar/${ticker}`);
        if (res.ok) {
            const data = await res.json();
            inputActual.value = data.precio;
            
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

const formInversion = document.getElementById('form-inversion');
if (formInversion) {
    formInversion.addEventListener('submit', async (e) => {
        e.preventDefault();
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
            const res = await apiFetch('/api/inversiones', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ticker, cantidad, precio_promedio, precio_actual, moneda })
            });

            if (res.ok) {
                formInversion.reset();
                await cargarInversiones();
                await cargarDatos();
            } else {
                const err = await res.json();
                alert(err.detail || "Error al registrar la inversión.");
            }
        } catch (err) {
            alert("Error de red al guardar la inversión.");
        }
    });
}

async function eliminarInversion(id) {
    if (!confirm("¿Deseas eliminar esta posición de tu portafolio?")) return;
    try {
        const res = await apiFetch(`/api/inversiones/${id}`, { method: 'DELETE' });
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

async function sincronizarPrecios() {
    const btn = document.getElementById('btn-sync-precios');
    const originalText = btn.textContent;
    btn.textContent = '⏳ Sincronizando...';
    btn.disabled = true;

    try {
        const res = await apiFetch('/api/inversiones/sincronizar', { method: 'POST' });
        if (res.ok) {
            const data = await res.json();
            await cargarInversiones();
            await cargarDatos();
            alert(data.mensaje);
        } else {
            alert("Error al sincronizar cotizaciones.");
        }
    } catch (err) {
        alert("Error de conexión al sincronizar.");
    } finally {
        btn.textContent = originalText;
        btn.disabled = false;
    }
}

// =============================================================================
// 9. PANEL DE ADMINISTRACIÓN DE USUARIOS (SOLO ADMIN)
// =============================================================================

/**
 * Convierte una fecha/hora (string) a formato relativo legible en español ("hace X tiempo").
 */
function formatoTiempoRelativo(fechaStr) {
    if (!fechaStr) return '<span style="color: var(--text-muted);">Nunca</span>';
    
    // Normalizar formato fecha si viene de SQLite (ej. YYYY-MM-DD HH:MM:SS)
    const fecha = new Date(fechaStr.replace(' ', 'T'));
    const ahora = new Date();
    const diffSegundos = Math.floor((ahora - fecha) / 1000);

    if (isNaN(diffSegundos) || diffSegundos < 0) {
        return fechaStr;
    }
    if (diffSegundos < 60) {
        return 'Hace unos instantes';
    }
    const diffMinutos = Math.floor(diffSegundos / 60);
    if (diffMinutos < 60) {
        return `Hace ${diffMinutos} min`;
    }
    const diffHoras = Math.floor(diffMinutos / 60);
    if (diffHoras < 24) {
        return `Hace ${diffHoras} ${diffHoras === 1 ? 'hora' : 'horas'}`;
    }
    const diffDias = Math.floor(diffHoras / 24);
    if (diffDias < 30) {
        return `Hace ${diffDias} ${diffDias === 1 ? 'día' : 'días'}`;
    }
    return fechaStr.split(' ')[0];
}

/**
 * Carga las métricas globales y la lista de usuarios del panel de administración.
 */
async function cargarDatosAdmin() {
    if (!usuarioActual || usuarioActual.role !== 'admin') return;

    try {
        // 1. Cargar KPIs
        const resStats = await apiFetch('/admin/stats');
        if (resStats.ok) {
            const stats = await resStats.json();
            document.getElementById('lbl-kpi-total-users').textContent = stats.total_users;
            document.getElementById('lbl-kpi-active-today').textContent = stats.active_users_today;
            document.getElementById('lbl-kpi-active-7d').textContent = stats.active_users_7d;
            document.getElementById('lbl-kpi-inactive').textContent = stats.inactive_users;
            document.getElementById('lbl-kpi-disk-total').textContent = stats.total_disk_formatted;
        }

        // 2. Cargar Directorio de Usuarios
        const resUsers = await apiFetch('/admin/users');
        if (resUsers.ok) {
            const usuarios = await resUsers.json();
            const tbody = document.getElementById('tabla-usuarios-admin');
            tbody.innerHTML = '';

            if (usuarios.length === 0) {
                tbody.innerHTML = '<tr><td colspan="9" style="text-align: center; color: var(--text-muted);">Sin usuarios registrados.</td></tr>';
            } else {
                usuarios.forEach(u => {
                    const tr = document.createElement('tr');
                    const esMismoAdmin = (usuarioActual && usuarioActual.id === u.id);
                    
                    const badgeRol = `<span class="badge-role ${u.role === 'admin' ? 'badge-role-admin' : 'badge-role-user'}">${u.role}</span>`;
                    const badgeEstado = u.is_active 
                        ? `<span class="badge-status badge-status-active">Activo</span>`
                        : `<span class="badge-status badge-status-inactive">Inactivo</span>`;

                    const fechaCreacion = (u.created_at || '').split(' ')[0] || '-';
                    const ultimoAccesoRelativo = formatoTiempoRelativo(u.last_login);
                    const detalleTitle = u.last_login ? `title="Fecha exacta: ${u.last_login}"` : '';

                    const esAdminPrincipal = (u.id === 1 || (u.username && u.username.toLowerCase() === 'admin'));
                    
                    let accionesHtml = `
                        <button type="button" class="btn-edit-user" onclick="abrirModalEditarUsuario(${u.id}, '${u.username}', '${u.role}')" title="Editar nombre de usuario y contraseña">✏️ Editar</button>
                    `;

                    if (!esMismoAdmin) {
                        const textoToggle = u.is_active ? 'Suspender' : 'Activar';
                        const nuevoEstado = !u.is_active;
                        accionesHtml += `
                            <button type="button" class="btn-status-toggle" onclick="cambiarEstadoUsuario(${u.id}, ${nuevoEstado})">${textoToggle}</button>
                        `;
                    }

                    if (esAdminPrincipal || esMismoAdmin) {
                        accionesHtml += `
                            <button type="button" class="btn-delete-user btn-disabled" disabled title="No se puede eliminar la cuenta principal de administración">🚫 Eliminar</button>
                        `;
                    } else {
                        accionesHtml += `
                            <button type="button" class="btn-delete-user" onclick="eliminarUsuarioTenant(${u.id}, '${u.username}')" title="Eliminar usuario y su base de datos">🗑️ Eliminar</button>
                        `;
                    }

                    tr.innerHTML = `
                        <td>${u.id}</td>
                        <td><strong>${u.username}</strong></td>
                        <td>${badgeRol}</td>
                        <td>${badgeEstado}</td>
                        <td>${fechaCreacion}</td>
                        <td ${detalleTitle}>${ultimoAccesoRelativo}</td>
                        <td>${u.login_count}</td>
                        <td>${u.db_size_formatted || '0 KB'}</td>
                        <td class="col-acciones">${accionesHtml}</td>
                    `;
                    tbody.appendChild(tr);
                });
            }
        }
    } catch (error) {
        console.error("Error al cargar datos administrativos:", error);
    }
}

/**
 * Activa o suspende el acceso de un usuario tenant.
 */
async function cambiarEstadoUsuario(userId, nuevoEstado) {
    try {
        const res = await apiFetch(`/admin/users/${userId}/status`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: nuevoEstado })
        });

        if (res.ok) {
            cargarDatosAdmin();
        } else {
            const err = await res.json();
            alert(err.detail || "Error al modificar el estado del usuario.");
        }
    } catch (e) {
        alert("Error de red al actualizar estado.");
    }
}

/**
 * Elimina un usuario tenant y borra su archivo de base de datos físico.
 */
async function eliminarUsuarioTenant(userId, username) {
    const confirmacion = confirm(`¿Estás seguro de eliminar al usuario '${username}'?\n\nADVERTENCIA: Se borrará permanentemente su base de datos y todos sus movimientos financieros.`);
    if (!confirmacion) return;

    try {
        const res = await apiFetch(`/admin/users/${userId}`, {
            method: 'DELETE'
        });

        if (res.ok) {
            cargarDatosAdmin();
        } else {
            const err = await res.json();
            alert(err.detail || "No se pudo eliminar el usuario.");
        }
    } catch (e) {
        alert("Error de red al eliminar usuario.");
    }
}

function abrirModalCrearUsuario() {
    const modal = document.getElementById('modal-crear-usuario');
    if (modal) {
        modal.style.display = 'flex';
        setTimeout(() => {
            const input = document.getElementById('nuevo-user-username');
            if (input) input.focus();
        }, 50);
    }
}

function cerrarModalCrearUsuario() {
    const modal = document.getElementById('modal-crear-usuario');
    if (modal) modal.style.display = 'none';
    const form = document.getElementById('form-crear-usuario');
    if (form) form.reset();
}

async function guardarNuevoUsuario(e) {
    e.preventDefault();
    const username = document.getElementById('nuevo-user-username').value.trim();
    const password = document.getElementById('nuevo-user-password').value;
    const role = document.getElementById('nuevo-user-role').value;

    if (!username || !password) return;

    try {
        const res = await apiFetch('/admin/users', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password, role })
        });

        if (res.ok) {
            cerrarModalCrearUsuario();
            await cargarDatosAdmin();
            alert(`Usuario '${username}' y su base de datos individual han sido creados con éxito.`);
        } else {
            const err = await res.json();
            alert(err.detail || "Error al crear usuario.");
        }
    } catch (error) {
        alert("Error de conexión al crear usuario.");
    }
}

/**
 * Abre el modal de edición de usuario desde el panel de administración.
 */
function abrirModalEditarUsuario(id, username, role) {
    const modal = document.getElementById('modal-editar-usuario');
    if (!modal) return;

    document.getElementById('lbl-edit-user-title').textContent = username;
    document.getElementById('edit-user-id').value = id;
    document.getElementById('edit-user-username').value = username;
    document.getElementById('edit-user-password').value = '';
    
    const roleSelect = document.getElementById('edit-user-role');
    const roleGroup = document.getElementById('group-edit-user-role');
    
    if (roleSelect) {
        roleSelect.value = role || 'user';
        // Si es el admin actual editándose a sí mismo, bloquear el cambio de rol para evitar perder privilegios
        if (usuarioActual && usuarioActual.id === id && role === 'admin') {
            roleSelect.disabled = true;
        } else {
            roleSelect.disabled = false;
        }
    }
    if (roleGroup) {
        roleGroup.style.display = (usuarioActual && usuarioActual.role === 'admin') ? 'block' : 'none';
    }

    modal.style.display = 'flex';
    setTimeout(() => {
        const input = document.getElementById('edit-user-username');
        if (input) input.focus();
    }, 50);
}

/**
 * Abre el modal de edición para que el usuario activo edite su propio perfil.
 */
function abrirModalEditarMiPerfil() {
    if (!usuarioActual) return;
    abrirModalEditarUsuario(usuarioActual.id, usuarioActual.username, usuarioActual.role);
}

/**
 * Cierra el modal de edición de usuario.
 */
function cerrarModalEditarUsuario() {
    const modal = document.getElementById('modal-editar-usuario');
    if (modal) modal.style.display = 'none';
    const form = document.getElementById('form-editar-usuario');
    if (form) form.reset();
}

/**
 * Envía la actualización de nombre de usuario y/o contraseña al backend.
 */
async function guardarEdicionUsuario(e) {
    e.preventDefault();
    const userId = document.getElementById('edit-user-id').value;
    const username = document.getElementById('edit-user-username').value.trim();
    const password = document.getElementById('edit-user-password').value;
    const roleSelect = document.getElementById('edit-user-role');
    const role = roleSelect ? roleSelect.value : undefined;

    if (!username) {
        alert("El nombre de usuario no puede estar vacío.");
        return;
    }

    const payload = { username };
    if (password && password.trim().length > 0) {
        if (password.length < 4) {
            alert("La nueva contraseña debe tener al menos 4 caracteres.");
            return;
        }
        payload.password = password;
    }

    if (roleSelect && !roleSelect.disabled && role) {
        payload.role = role;
    }

    try {
        const endpoint = (usuarioActual && usuarioActual.role === 'admin') 
            ? `/admin/users/${userId}` 
            : `/auth/profile`;

        const res = await apiFetch(endpoint, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            const data = await res.json();
            cerrarModalEditarUsuario();
            
            // Si el usuario editado es el usuario en sesión activa, actualizar token y UI
            if (usuarioActual && usuarioActual.id === parseInt(userId, 10)) {
                if (data.new_token) {
                    localStorage.setItem('jwt_token', data.new_token);
                }
                if (data.user) {
                    usuarioActual = data.user;
                    localStorage.setItem('user_info', JSON.stringify(data.user));
                    const lblUser = document.getElementById('lbl-username');
                    const lblRole = document.getElementById('lbl-user-role');
                    if (lblUser) lblUser.textContent = data.user.username;
                    if (lblRole) {
                        lblRole.textContent = data.user.role;
                        lblRole.className = `badge-role ${data.user.role === 'admin' ? 'badge-role-admin' : 'badge-role-user'}`;
                    }
                }
            }
            
            if (usuarioActual && usuarioActual.role === 'admin') {
                await cargarDatosAdmin();
            }
            alert(data.mensaje || "Usuario actualizado exitosamente.");
        } else {
            const err = await res.json();
            alert(err.detail || "Error al actualizar el usuario.");
        }
    } catch (error) {
        alert("Error de conexión al guardar cambios.");
    }
}

// =============================================================================
// 10. SISTEMA DE PESTAÑAS (TABS)
// =============================================================================

function inicializarTabs() {
    const tabBtns = document.querySelectorAll('.tab-btn');
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.getAttribute('data-tab');
            cambiarPestana(targetTab);
        });
    });

    const pestanaGuardada = localStorage.getItem('active_tab') || 'tab-dashboard';
    cambiarPestana(pestanaGuardada);
}

function cambiarPestana(tabId) {
    const targetContent = document.getElementById(tabId);
    if (!targetContent) return;

    document.querySelectorAll('.tab-btn').forEach(b => {
        b.classList.toggle('active', b.getAttribute('data-tab') === tabId);
    });

    document.querySelectorAll('.tab-content').forEach(c => {
        c.classList.toggle('active', c.id === tabId);
    });

    localStorage.setItem('active_tab', tabId);

    // Si entra al panel de administración, recargar métricas frescas
    if (tabId === 'tab-admin') {
        cargarDatosAdmin();
    }

    setTimeout(() => {
        if (miGrafica) miGrafica.resize();
        if (graficaDona) graficaDona.resize();
    }, 60);
}

// =============================================================================
// 11. MODALES DE EDICIÓN: INVERSIONES Y MOVIMIENTOS
// =============================================================================

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

function cerrarModalEditarInversion() {
    const modal = document.getElementById('modal-editar-inversion');
    if (modal) modal.style.display = 'none';
}

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
        const res = await apiFetch(`/api/inversiones/${id}`, {
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
        alert("Error de red al intentar guardar los cambios.");
    }
}

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

function cerrarModalEditarTransaccion() {
    const modal = document.getElementById('modal-editar-transaccion');
    if (modal) modal.style.display = 'none';
}

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
        const res = await apiFetch(`/api/transacciones/${id}`, {
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
        alert("Error de red al intentar guardar los cambios.");
    }
}

window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        cerrarModalEditarInversion();
        cerrarModalEditarTransaccion();
        cerrarModalCrearUsuario();
        cerrarModalEditarUsuario();
        cerrarModalCrearApartado();
    }
});

// =============================================================================
// 12. EXPORTACIÓN A EXCEL
// =============================================================================

function exportarExcel() {
    const token = localStorage.getItem('jwt_token');
    const url = `/api/exportar-excel?moneda_base=${encodeURIComponent(monedaGlobal)}&token=${encodeURIComponent(token || '')}`;
    
    // Descarga directa autorizada
    apiFetch(`/api/exportar-excel?moneda_base=${encodeURIComponent(monedaGlobal)}`)
        .then(res => {
            if (!res.ok) throw new Error("Error en la exportación");
            return res.blob();
        })
        .then(blob => {
            const downloadUrl = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = downloadUrl;
            a.download = `reporte_financiero_${usuarioActual ? usuarioActual.username : 'tenant'}_${monedaGlobal}.xlsx`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(downloadUrl);
        })
        .catch(err => {
            alert("No se pudo generar la exportación a Excel.");
        });
}

// =============================================================================
// 13. EXPOSICIÓN GLOBAL DE FUNCIONES EN WINDOW
// =============================================================================
window.iniciarSesion = iniciarSesion;
window.logoutUsuario = logoutUsuario;
window.exportarExcel = exportarExcel;
window.toggleMetaInput = toggleMetaInput;
window.realizarMovimiento = realizarMovimiento;
window.eliminarApartado = eliminarApartado;
window.abrirModalCrearApartado = abrirModalCrearApartado;
window.cerrarModalCrearApartado = cerrarModalCrearApartado;
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
window.cambiarMonedaInversiones = cambiarMonedaGlobal;

// Funciones del Panel de Administración y Perfil
window.abrirModalCrearUsuario = abrirModalCrearUsuario;
window.cerrarModalCrearUsuario = cerrarModalCrearUsuario;
window.guardarNuevoUsuario = guardarNuevoUsuario;
window.abrirModalEditarUsuario = abrirModalEditarUsuario;
window.cerrarModalEditarUsuario = cerrarModalEditarUsuario;
window.abrirModalEditarMiPerfil = abrirModalEditarMiPerfil;
window.guardarEdicionUsuario = guardarEdicionUsuario;
window.cambiarEstadoUsuario = cambiarEstadoUsuario;
window.eliminarUsuarioTenant = eliminarUsuarioTenant;

// =============================================================================
// 14. ARRANQUE DE LA APLICACIÓN
// =============================================================================
inicializarTabs();
inicializarBuscadorTickers();
verificarSesionInicial();
