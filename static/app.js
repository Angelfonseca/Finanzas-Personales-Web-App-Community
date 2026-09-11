document.getElementById('fecha').valueAsDate = new Date();

const form = document.getElementById('transaccion-form');
const mensajeDiv = document.getElementById('mensaje');

async function cargarDatos() {
    try {
        // 1. Cargar Resumen General
        const resResumen = await fetch('/api/resumen');
        const dataResumen = await resResumen.json();
        
        document.getElementById('lbl-balance').textContent = `$${dataResumen.balance.toFixed(2)}`;
        document.getElementById('lbl-ingresos').textContent = `$${dataResumen.ingresos.toFixed(2)}`;
        document.getElementById('lbl-gastos').textContent = `$${dataResumen.gastos.toFixed(2)}`;

        // 2. Cargar Resumen Mensual
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
                    <div><strong>Mes: ${m.mes}</strong></div>
                    <div class="monthly-info">
                        <span style="color: #27ae60;">+ $${m.ingresos.toFixed(2)}</span>
                        <span style="color: #c0392b;">- $${m.gastos.toFixed(2)}</span>
                        <span style="color: #2980b9;">Neto: $${balanceMes.toFixed(2)}</span>
                    </div>
                `;
                contenedorMensual.appendChild(div);
            });
        }

        // 3. Cargar Tabla de Transacciones (Todas con opción de eliminar)
        const resTrans = await fetch('/api/transacciones');
        const dataTrans = await resTrans.json();
        
        const tbody = document.getElementById('tabla-movimientos');
        tbody.innerHTML = '';

        if (dataTrans.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #7f8c8d;">No hay movimientos registrados.</td></tr>';
        } else {
            dataTrans.forEach(t => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${t.fecha}</td>
                    <td>${t.descripcion || '-'}</td>
                    <td class="${t.tipo === 'gasto' ? 'text-gasto' : 'text-ingreso'}">${t.tipo.toUpperCase()}</td>
                    <td>$${t.monto.toFixed(2)}</td>
                    <td><button class="btn-eliminar" onclick="eliminarTransaccion(${t.id})">Eliminar</button></td>
                `;
                tbody.appendChild(tr);
            });
        }

    } catch (error) {
        console.error("Error al actualizar datos:", error);
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
            mensajeDiv.textContent = '¡Movimiento guardado con éxito!';
            form.reset();
            document.getElementById('fecha').valueAsDate = new Date();
            cargarDatos();
        } else {
            mensajeDiv.style.color = 'red';
            mensajeDiv.textContent = 'Error al guardar el movimiento.';
        }
    } catch (error) {
        mensajeDiv.style.color = 'red';
        mensajeDiv.textContent = 'Error de conexión con el servidor.';
    }
});

async function eliminarTransaccion(id) {
    if (!confirm("¿Estás seguro de eliminar este movimiento?")) return;

    try {
        const response = await fetch(`/api/transacciones/${id}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            cargarDatos();
        } else {
            alert("No se pudo eliminar la transacción.");
        }
    } catch (error) {
        console.error("Error al eliminar:", error);
    }
}

// Cargar datos al abrir la página
cargarDatos();
