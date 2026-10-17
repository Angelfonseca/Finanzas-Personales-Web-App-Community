/**
 * static/js/dashboard.js - Gráfica mensual del dashboard.
 */

import { estado } from './core.js';


export function actualizarGrafica(dataMensual) {
    const canvas = document.getElementById('graficaFinanzas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const esOscuro = document.documentElement.getAttribute('data-theme') === 'dark';
    const textColor = esOscuro ? '#f0f0f0' : '#0d172a';
    const gridColor = esOscuro ? 'rgba(255, 255, 255, 0.12)' : 'rgba(13, 23, 42, 0.08)';
    
    const meses = dataMensual.map(m => m.mes);
    const ingresos = dataMensual.map(m => m.ingresos);
    const gastos = dataMensual.map(m => m.gastos);

    if (estado.graficas.barras) {
        estado.graficas.barras.data.labels = meses;
        estado.graficas.barras.data.datasets[0].data = ingresos;
        estado.graficas.barras.data.datasets[1].data = gastos;
        if (estado.graficas.barras.options && estado.graficas.barras.options.scales) {
            if (estado.graficas.barras.options.scales.x) {
                estado.graficas.barras.options.scales.x.ticks.color = textColor;
                estado.graficas.barras.options.scales.x.grid.color = gridColor;
            }
            if (estado.graficas.barras.options.scales.y) {
                estado.graficas.barras.options.scales.y.ticks.color = textColor;
                estado.graficas.barras.options.scales.y.grid.color = gridColor;
            }
        }
        if (estado.graficas.barras.options && estado.graficas.barras.options.plugins && estado.graficas.barras.options.plugins.legend) {
            estado.graficas.barras.options.plugins.legend.labels.color = textColor;
        }
        estado.graficas.barras.update();
    } else {
        estado.graficas.barras = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: meses,
                datasets: [
                    {
                        label: 'Ingresos',
                        data: ingresos,
                        backgroundColor: 'rgba(16, 185, 129, 0.75)',
                        borderColor: '#10b981',
                        borderWidth: 1,
                        borderRadius: 6
                    },
                    {
                        label: 'Gastos',
                        data: gastos,
                        backgroundColor: 'rgba(244, 63, 94, 0.75)',
                        borderColor: '#f43f5e',
                        borderWidth: 1,
                        borderRadius: 6
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
