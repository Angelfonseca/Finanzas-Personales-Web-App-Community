document.getElementById('fecha').valueAsDate = new Date();

const form = document.getElementById('transaccion-form');
const mensajeDiv = document.getElementById('mensaje');
const btnModo = document.getElementById('btn-modo');
let miGrafica = null;

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
    // Actualizar colores de la gráfica al cambiar el tema
    if (miGrafica) {
        actualizarColoresGrafica();
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
// -----------------------------

async function cargarDatos() {
    try {
        const resResumen = await fetch('/api/resumen');
        const dataResumen = await resResumen.json();
        
        document.getElementById('lbl-balance').textContent = `$${dataResumen.balance.toFixed(2)}`;
        document.getElementById('lbl-ingresos').textContent = `$${dataResumen.ingresos.toFixed(2)}`;
        document.getElementById('lbl-gastos').textContent = `$${dataResumen.gastos.toFixed(2)}`;

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

cargarDatos();
