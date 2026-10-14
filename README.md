# 💰 Finanzas Personales Web App

Una aplicación web moderna, ligera, minimalista y autohospedada para llevar el control integral de tus finanzas personales y patrimonio neto. Diseñada desde cero para ser rápida, privada y correr de forma ultra eficiente en servidores locales o dispositivos como una Raspberry Pi mediante Docker.

---

## 🚀 Tecnologías Utilizadas

* **Backend:** [FastAPI](https://fastapi.tiangolo.com/) (Python 3.11)
* **Base de Datos:** [SQLite](https://www.sqlite.org/) (Conexión nativa con cálculos derivativos)
* **Frontend:** HTML5, CSS3 Moderno (Variables CSS & Modo Oscuro), JavaScript (Vanilla ES6+)
* **Visualización de Datos:** [Chart.js](https://www.chartjs.org/) (Gráficas de barras y dona de asignación de activos)
* **Servidor ASGI:** [Uvicorn](https://www.uvicorn.org/) (Con live-reload activo)
* **Despliegue & Contenedor:** Docker y Docker Compose

---

## ✨ Características y Módulos

### 1. 📊 Dashboard Central & Patrimonio Neto (Net Worth)
* **Métrica Consolidada:** Cálculo en tiempo real de tu Patrimonio Neto Total integrando los 3 pilares financieros:
  * 💵 **Balance Disponible** (Efectivo en mano).
  * 🐖 **Apartados y Metas** (Ahorro guardado en sobres).
  * 📈 **Portafolio de Inversión** (Valor de mercado actual de acciones y ETFs).
* **Métricas de Flujo:** Ingresos totales, gastos acumulados y rendimiento global de inversiones.
* **Gráfica de Comportamiento Mensual:** Comparativa visual de ingresos vs gastos mes a mes.

### 2. 💳 Movimientos (Flujo de Caja)
* Registro rápido de transacciones de ingreso y gasto con fecha, monto y descripción.
* Historial completo y ordenado con eliminación de movimientos.
* Desglose agrupado por mes.

### 3. 🎯 Apartados y Metas de Ahorro
* Creación de sobres de ahorro:
  * **Sobre Libre:** Fondos de ahorro sin límite específico.
  * **Meta de Ahorro:** Objetivos financieros fijos con seguimiento mediante barras de progreso porcentual.
* Movimientos de **depósito (+)** y **retiro (-)** que validan el balance disponible y generan registros automáticos de trazabilidad.

### 4. 📈 Módulo de Inversiones & Asset Allocation
* **Seguimiento de Portafolio:** Registro de posiciones en ETFs y acciones (Ticker, cantidad de títulos, precio promedio de compra y divisa).
* **Búsqueda Predictiva y Autocompletado de Tickers:** Al escribir en el campo de ticker, se despliega un listado en vivo de sugerencias de Yahoo Finance con símbolo, nombre completo, tipo de instrumento y bolsa de cotización.
* **Soporte Multidivisa Inteligente:**
  * Cada activo se almacena en su moneda nativa (`USD` para acciones/ETFs estadounidenses como VOO o QQQ; `MXN` para acciones mexicanas o ETFs del SIC como WALMEX.MX o VUAAN.MX).
  * **Sin conversiones innecesarias:** Si una acción ya está en Pesos Mexicanos (MXN) y tu moneda base es MXN, se contabiliza de forma directa sin multiplicarse. Si está en Dólares (USD), se convierte dinámicamente con el tipo de cambio oficial del día.
  * Permite sumar con precisión matemática el portafolio de inversión junto al balance en efectivo y metas de ahorro para obtener el **Patrimonio Neto real**.
* **Cálculos Derivativos en Caliente:** Cálculo automático de capital invertido, valor de mercado actual, PnL por posición ($ y %) y PnL global del portafolio.
* **Asset Allocation (% Peso):** Cálculo dinámico del porcentaje de peso de cada activo sobre el total del portafolio, representado visualmente con una **Gráfica de Dona (Doughnut)** interactiva de Chart.js.
* **Automatización y Cotizaciones en Vivo:** Consulta y sincronización automática de precios de mercado y divisas mediante Yahoo Finance API sin dependencias pesadas de terceros. Botón de sincronización masiva con un solo clic.

### 5. 📑 Experiencia de Usuario, Moneda Global & Responsividad
* **Selector de Moneda Base Global:** Conmutador en la barra superior (MXN / USD) que recalcula al instante todas las vistas del sistema (Dashboard general, balance, metas e inversiones) y muestra la tasa de cambio vigente (`1 USD ≈ $18.50 MXN`).
* **Diseño 100% Responsivo:** Adaptado meticulosamente para teléfonos inteligentes, tablets y pantallas de escritorio:
  * Grillas adaptables con auto-ajuste de tarjetas (`minmax(140px, 1fr)`).
  * Barra de navegación con scroll horizontal táctil suave para pantallas angostas.
  * Tablas con scroll horizontal contenedor para evitar desbordes en móviles.
  * Inputs optimizados con tamaño táctil de 16px para prevenir zoom involuntario en iOS/Android.
* **Navegación por Pestañas (Tabs):** Organización modular tipo SPA que separa el Dashboard, Movimientos, Apartados e Inversiones sin saturar la pantalla.
* **Memoria de Estado:** Recuerda la pestaña activa y la divisa seleccionada mediante `localStorage` para preservar tu sesión tras recargar la página.
* **Modo Oscuro / Claro:** Alternancia fluida de tema con adaptación automática de colores en gráficos y tarjetas.

### 6. 📊 Exportación Profesional a Excel con Gráficas Nativas (.xlsx)
* **Reporte Financiero Integral en 3 Hojas:**
  * **Resumen General:** Indicadores patrimoniales clave (Patrimonio neto, balance libre, apartados, valuación de inversiones, PnL global y flujos) y tabla de seguimiento de metas.
  * **Movimientos:** Historial cronológico con formatos contables, colores de ingresos/gastos y balance total disponible.
  * **Inversiones & Asset Allocation:** Detalle de posiciones con cotizaciones sincronizadas en vivo al momento de la exportación, rendimientos y porcentajes de asignación.
* **Gráfica de Pastel Nativa Incrustada (`PieChart`):** Generada mediante `openpyxl`, con visualización automática de porcentajes de peso de cada activo dentro de la misma hoja de cálculo de Excel.
* **Descarga Adaptable:** Genera el reporte en Pesos Mexicanos (MXN) o Dólares (USD) según la divisa base activa en la interfaz.

### 7. 💾 Copia de Seguridad y Respaldo
* **Respaldo con 1 Clic:** Botón directo en la barra superior para descargar el archivo de base de datos SQLite (`finanzas.db`) con marca de tiempo, garantizando la seguridad y portabilidad de tus datos sin configuraciones complejas.

---

## 📂 Estructura del Proyecto

```text
finanzas-app/
├── main.py              # API REST en FastAPI, cálculos derivativos, tipos de cambio y endpoints
├── export_service.py    # Servicio generador de reportes Excel (.xlsx) y gráficas nativas con openpyxl
├── database.py          # Esquema SQLite (categorías, transacciones, apartados, inversiones)
├── finanzas.db          # Base de datos SQLite local
├── Dockerfile           # Imagen Docker basada en python:3.11-slim
├── docker-compose.yml   # Configuración de Docker Compose con volumen montado y puerto 8001
├── requirements.txt     # Dependencias del backend (fastapi, uvicorn, pydantic, openpyxl)
├── README.md            # Documentación completa del proyecto
└── static/
    ├── index.html       # Interfaz visual de usuario con selector global y pestañas
    ├── style.css        # Estilos modernos, diseño responsivo móvil/desktop y modo oscuro
    └── app.js           # Lógica del cliente, autocompletado, gráficos Chart.js y fetch API
```

---

## 🛠️ Instalación y Despliegue con Docker

> [!IMPORTANT]
> Se recomienda utilizar la bandera `--build` al iniciar por primera vez o tras actualizar dependencias (`requirements.txt`) para asegurar que Docker compile la imagen con todos los paquetes necesarios.

1. **Clonar el repositorio:**
   ```bash
   git clone <URL_DEL_REPOSITORIO>
   cd finanzas-app
   ```

2. **Construir e iniciar los contenedores:**
   ```bash
   docker compose up -d --build
   ```
   *¿Por qué `--build`?* La opción `--build` compila la imagen Docker local a partir del `Dockerfile` e instala todas las librerías necesarias de `requirements.txt` (FastAPI, Uvicorn, Pydantic, openpyxl). En arranques posteriores donde no hayan cambiado dependencias, puedes usar simplemente `docker compose up -d`.

3. **Abrir en el navegador:**
   Ingresa a `http://localhost:8001` (o a la dirección IP de tu servidor local / Raspberry Pi en la red).

### Comandos Útiles de Docker

* **Ver los logs en tiempo real:**
  ```bash
  docker compose logs -f
  ```
* **Detener la aplicación:**
  ```bash
  docker compose down
  ```
* **Reconstruir desde cero (sin caché de capas):**
  ```bash
  docker compose build --no-cache && docker compose up -d
  ```

---

## 🌐 Endpoints Principales de la API

| Método | Endpoint | Descripción |
| :--- | :--- | :--- |
| `GET` | `/api/resumen?moneda_base=MXN` | Resumen general, balance, apartados, inversiones y patrimonio neto en la moneda base |
| `GET` | `/api/tipo-cambio` | Tipos de cambio en tiempo real (USD y MXN) con caché en memoria de 5 min |
| `GET` | `/api/resumen-mensual` | Agrupación de ingresos y gastos por mes para gráficos |
| `GET` | `/api/transacciones` | Lista histórica de transacciones |
| `POST` | `/api/transacciones` | Registrar una nueva transacción con validación de montos positivos y fechas |
| `PUT` | `/api/transacciones/{id}` | Actualizar cualquier campo de una transacción existente (fecha, monto, tipo, descripción) |
| `DELETE` | `/api/transacciones/{id}` | Eliminar una transacción existente |
| `GET` | `/api/apartados` | Lista de sobres y metas con sus porcentajes de avance |
| `POST` | `/api/apartados` | Crear un nuevo apartado o meta |
| `POST` | `/api/apartados/{id}/movimiento` | Depositar o retirar fondos de un apartado (con registro de fecha local) |
| `DELETE` | `/api/apartados/{id}` | Eliminar un apartado (protegido contra eliminación si tiene saldo disponible) |
| `GET` | `/api/inversiones?moneda_base=MXN` | Resumen consolidado del portafolio y posiciones con Asset Allocation y conversión |
| `GET` | `/api/inversiones/buscar?q={query}` | Búsqueda predictiva y autocompletado en vivo de tickers de bolsa |
| `GET` | `/api/inversiones/cotizar/{ticker}` | Consultar cotización y moneda nativa de un ticker en tiempo real |
| `POST` | `/api/inversiones` | Registrar una nueva posición de inversión (`ticker, cantidad, precio_promedio, precio_actual, moneda`) |
| `PUT` | `/api/inversiones/{id}` | Actualizar cantidad de títulos, precio promedio o cotización de una posición |
| `DELETE` | `/api/inversiones/{id}` | Eliminar una posición del portafolio |
| `POST` | `/api/inversiones/sincronizar` | Actualizar automáticamente las cotizaciones de mercado y divisas en lote |
| `GET` | `/api/exportar-excel?moneda_base=MXN` | Generar y descargar el reporte financiero completo en Excel (.xlsx) con Asset Allocation |
| `GET` | `/api/backup` | Descargar una copia de seguridad directa del archivo de base de datos SQLite `finanzas.db` |
