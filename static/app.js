document.getElementById('fecha').valueAsDate = new Date();

const form = document.getElementById('transaccion-form');
const mensajeDiv = document.getElementById('mensaje');
let miGrafica = null; // Variable para controlar la instancia de Chart.js

async function cargarDatos() {
    try {
        // 1. Cargar Resumen General
        const resResumen = await fetch('/api/resumen');
        const dataResumen = await resResumen.json();
        
        document.getElementById('lbl-balance').textContent = `$${dataResumen.balance.toFixed(2)}`;
        document.getElementById('lbl-ingresos').textContent = `$${dataResumen.ingresos.toFixed(2)}`;
        document.getElementById('lbl-gastos').textContent = `$${dataResumen.gastos.toFixed(2)}`;

        // 2. Cargar Resumen Mensual y actualizar Gráfica
        const resMensual = await fetch('/api/resumen-mensual');
        const dataMensual = await resMensual.json();
        
        const contenedorMensual = document.getElementById('lista-resumen-mensual');
        contenedorMensual.innerHTML = '';

        if (dataMensual.length === 0) {
            contenedorMensual.innerHTML = '<p style="text-align: center; color: #7f8c8d;">Sin registros mensuales aún.</p>';
        } else {
            dataMensual.forEach(m => {
                const balanceMes = m.ingresos - m.gastos;
                const div = document.createElement('div');
                div.className = 'monthly-card';
                div.innerHTML = `
                    <div><strong>${m.mes}</strong></div>
                    <div class="monthly-info">
                        <span style="color: #27ae60;">+${m.ingresos.toFixed(2)}</span>
                        <span style="color: #c0392b;">-${m.gastos.toFixed(2)}</span>
                    </div>
                `;
                contenedorMensual.appendChild(div);
            });
        }

        // Renderizar o actualizar Chart.js (Datos ordenados cronológicamente para la gráfica)
        actualizarGrafica(dataMensual.slice().reverse());

        // 3. Cargar Tabla de Transacciones
        const resTrans = await fetch('/api/transacciones');
        const dataTrans = await resTrans.json();
        
        const tbody = document.getElementById('tabla-movimientos');
        tbody.innerHTML = '';

        if (dataTrans.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #7f8c8d;">No hay movimientos.</td></tr>';
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
                        backgroundColor: 'rgba(39, 174, 96, 0.7)',
                        borderColor: '#27ae60',
                        borderWidth: 1
                    },
                    {
                        label: 'Gastos',
                        data: gastos,
                        backgroundColor: 'rgba(192, 57, 43, 0.7)',
                        borderColor: '#c0392b',
                        borderWidth: 1
                    }
                ]
            },
            options: {
                responsive: true,
                scales: {
                    y: { beginAtZero: true }
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
            mensajeDiv.style.color = 'green';
            mensajeDiv.textContent = '¡Movimiento guardado!';
            form.reset();
            document.getElementById('fecha').valueAsDate = new Date();
            cargarDatos();
        } else {
            mensajeDiv.style.color = 'red';
            mensajeDiv.textContent = 'Error al guardar.';
        }
    } catch (error) {
        mensajeDiv.style.color = 'red';
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
