# 💰 Finanzas Personales Web App (SaaS Multi-Tenant)

Una plataforma web moderna, ligera, minimalista y autohospedada para llevar el control integral de finanzas personales, metas de ahorro y portafolios de inversión con **arquitectura Multi-Tenant (base de datos aislada por usuario)** y autenticación mediante **JSON Web Tokens (JWT)**.

Diseñada desde cero para ser rápida, privada y correr de forma ultra eficiente en servidores locales o dispositivos como una Raspberry Pi mediante Docker.

---

## 🚀 Tecnologías Utilizadas

* **Backend:** [FastAPI](https://fastapi.tiangolo.com/) (Python 3.11) con inyección dinámica de dependencias.
* **Seguridad & Auth:** [PyJWT](https://pyjwt.readthedocs.io/) (Firma de tokens HS256) y [bcrypt](https://pypi.org/project/bcrypt/) (Hashing seguro con salt automático).
* **Base de Datos Dual (Multi-Tenant):** [SQLite](https://www.sqlite.org/) con modo WAL (`PRAGMA journal_mode=WAL;`):
  * **Master DB:** `data/master.db` (Control de usuarios, roles, estado y métricas de acceso).
  * **Tenant DBs:** `data/tenants/user_{id}.db` (Bases de datos independientes y 100% aisladas para cada usuario).
* **Frontend:** HTML5, CSS3 Moderno (Variables CSS & Modo Oscuro), JavaScript (Vanilla ES6+ SPA) y cliente interceptor `apiFetch`.
* **Visualización de Datos:** [Chart.js](https://www.chartjs.org/) (Gráficas de barras mensuales y dona de asignación de activos).
* **Servidor ASGI:** [Uvicorn](https://www.uvicorn.org/) (Con live-reload activo).
* **Despliegue & Contenedor:** Docker y Docker Compose.

---

## ✨ Características y Módulos

### 1. 🛡️ Arquitectura Multi-Tenant Dinámica (DB por Usuario)
* **Aislamiento Total de Datos (Zero-Leakage):** Cada usuario posee su propio archivo SQLite físico (`data/tenants/user_{id}.db`). No existe riesgo de filtración de datos cruzados entre usuarios.
* **Sin Duplicación de Código:** Una sola instancia de FastAPI y un solo Frontend SPA. El backend resuelve dinámicamente en cada petición la conexión correspondiente al tenant extrayendo el `db_name` del JWT verificado.
* **Aprovisionamiento Automático:** Al dar de alta un usuario desde el panel de administración, el sistema crea e inicializa automáticamente su base de datos individual con todas las tablas e índices.

### 2. 🔐 Autenticación JWT y Guardias de Sesión
* **Inicio de Sesión Seguro:** Endpoint `POST /auth/login` con validación de contraseña mediante bcrypt y verificación de cuenta activa (`is_active == 1`).
* **Auditoría de Actividad:** Cada inicio de sesión exitoso actualiza en `master.db` la fecha/hora de `last_login` e incrementa el contador `login_count`.
* **Interceptor Automático (`apiFetch`):** Todas las peticiones del Frontend adjuntan la cabecera `Authorization: Bearer <token>`. Si el token expira o el usuario es suspendido, el sistema redirige automáticamente al login.
* **Purga Limpia de Sesión (Logout):** Al cerrar sesión o cambiar de cuenta, el cliente destruye las instancias de Chart.js, purga la memoria y limpia el DOM para garantizar que ningún dato quede visible en caché para el siguiente usuario.

### 3. 👥 Panel de Administración de Usuarios (Solo Admin)
* Pestaña exclusiva `🛡️ Admin` visible únicamente para cuentas con rol `admin`.
* **Tarjetas KPI Globales:**
  * 👥 Total de usuarios registrados.
  * 🟢 Usuarios activos hoy y en los últimos 7 días.
  * 🔴 Usuarios suspendidos o inactivos.
  * 💾 Almacenamiento total acumulado en disco por todas las bases de datos tenant.
* **Tabla de Gestión de Usuarios:**
  * Usuario, Rol, Estado (Activo / Suspendido).
  * Fecha de creación y **Último Acceso en tiempo relativo** (*"Hace 10 min"*, *"Hace 2 horas"*, *"Nunca"*).
  * Total de inicios de sesión y peso de su base de datos individual en KB/MB.
* **Controles Administrativos:**
  * Modal para **Crear Nuevos Usuarios** (con rol `user` o `admin`).
  * Botón para **Suspender / Reactivar** acceso de usuarios en tiempo real.
  * Botón para **Eliminar usuario** con borrado físico de su base de datos.
  * Protección contra auto-bloqueo y auto-eliminación de la cuenta del administrador en sesión.

### 4. 📊 Dashboard Central & Patrimonio Neto (Net Worth)
* **Métrica Consolidada:** Cálculo en tiempo real de tu Patrimonio Neto Total integrando los 3 pilares financieros:
  * 💵 **Balance Disponible** (Efectivo en caja).
  * 🐖 **Apartados y Metas** (Ahorro guardado en sobres).
  * 📈 **Portafolio de Inversión** (Valor de mercado actual de acciones y ETFs).
* **Métricas de Flujo:** Ingresos totales, gastos acumulados y rendimiento global de inversiones.
* **Gráfica Mensual:** Comparativa visual de ingresos vs gastos mes a mes con Chart.js.

### 5. 💳 Movimientos y 🎯 Metas de Ahorro
* Registro rápido de ingresos y gastos con modales de edición in situ.
* Sobres libres de ahorro y metas con barra de progreso porcentual.
* Transferencias protegidas contra depósitos que excedan el balance disponible.

### 6. 📈 Inversiones & Asset Allocation en Tiempo Real
* **Autocompletado Predictivo:** Búsqueda en vivo de tickers en Yahoo Finance (símbolo, nombre, bolsa).
* **Soporte Multidivisa Inteligente:** Tratamiento diferenciado de activos en `USD` y `MXN` con tipos de cambio oficiales.
* **Gráfica de Dona:** Visualización del peso porcentual de cada activo sobre el portafolio total.
* **Sincronización con 1 Clic:** Actualización en lote de cotizaciones y rendimientos de mercado.

### 7. 📑 Exportación a Excel y Respaldos Aislados
* **Excel con Gráfica Nativa de Pastel:** Descarga el reporte contable del tenant activo con Asset Allocation en formato `.xlsx`.
* **Copia de Seguridad por Usuario:** Botón directo para descargar el archivo `.db` propio del usuario en sesión.

---

## 📂 Estructura del Proyecto

```text
finanzas-app/
├── main.py              # API REST en FastAPI, inyección Depends(get_tenant_db) y endpoints
├── master_db.py         # Base de datos maestra (users, auditoría, estadísticas admin y códigos OTP)
├── security.py          # Criptografía bcrypt, tokens JWT y dependencias verify_token/verify_admin
├── email_service.py     # Servicio de envío de correos transaccionales (API o SMTP)
├── database.py          # Gestor de esquemas tenant, conexiones dinámicas y aprovisionamiento
├── export_service.py    # Servicio generador de reportes Excel (.xlsx) con gráficas nativas
├── requirements.txt     # Dependencias (fastapi, uvicorn, pydantic, openpyxl, bcrypt, pyjwt)
├── Dockerfile           # Imagen Docker basada en python:3.11-slim
├── docker-compose.yml   # Configuración de Docker Compose con volumen montado y puerto 8001
├── .env.example         # Plantilla de variables de entorno para JWT y claves de correo
├── README.md            # Documentación completa del proyecto
├── LICENSE              # Licencia GNU General Public License v3.0 (GPLv3)
├── data/                # Almacenamiento local (ignorado en git)
│   ├── master.db        # Base maestra de usuarios y auditoría
│   └── tenants/         # Directorio de bases de datos individuales (user_1.db, user_2.db...)
└── static/
    ├── index.html       # Interfaz SPA con login, pestañas financieras y panel admin
    ├── style.css        # Estilos modernos, diseño responsivo móvil/desktop y modo oscuro
    └── app.js           # Cliente interceptor apiFetch, purga limpia de estado y Chart.js
```

---

## 🛠️ Instalación y Despliegue con Docker

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/Ricardo-Gomez-4-113/Finanzas-Personales-Web-App-Community.git
   cd Finanzas-Personales-Web-App-Community
   ```

2. **Configurar variables de entorno (Opcional):**
   ```bash
   cp .env.example .env
   ```

3. **Construir e iniciar los contenedores:**
   ```bash
   docker compose up -d --build
   ```

4. **Abrir en el navegador:**
   Ingresa a `http://localhost:8001`.

### 🔑 Credenciales Iniciales por Defecto

Al arrancar por primera vez, el sistema crea automáticamente el usuario Administrador y migra los datos preexistentes:

* **Usuario:** `admin`
* **Contraseña:** `admin123`
* **Rol:** `admin`

> [!TIP]
> Una vez dentro, puedes ingresar a la pestaña `🛡️ Admin` para crear nuevos usuarios o dar de alta cuentas adicionales con su respectivo correo electrónico.

## 📧 Configuración del Servicio de Correo (Opcional)

La versión comunitaria incluye soporte para el envío de códigos de recuperación de contraseña de 6 dígitos. Puedes conectar tu propio servicio de correo mediante API o servidor SMTP configurando el archivo `.env`:

1. **Copia la plantilla de configuración:**
   ```bash
   cp .env.example .env
   ```

2. **Define las credenciales de tu proveedor:**
   * **Opción A: Vía API de Correo**
     ```env
     RESEND_API_KEY=tu_api_key_aqui
     RESEND_FROM=Finora MX <notificaciones@tu-dominio.com>
     ```
   * **Opción B: Vía Servidor SMTP**
     ```env
     SMTP_HOST=smtp.tu-servidor.com
     SMTP_PORT=587
     SMTP_USER=tu_usuario@tu-dominio.com
     SMTP_PASSWORD=tu_contrasena_o_token
     SMTP_FROM=Finora MX <tu_usuario@tu-dominio.com>
     ```

> [!NOTE]
> Si no configuras un proveedor de correo, la aplicación opera de forma autónoma en modo local. Las contraseñas pueden ser administradas directamente desde el panel de administración.

---

## 🌐 Resumen de Endpoints de la API

### Autenticación, Perfil y Recuperación
| Método | Endpoint | Seguridad | Descripción |
| :--- | :--- | :--- | :--- |
| `POST` | `/auth/login` | Público | Autenticación con credenciales, registro de auditoría y emisión de JWT |
| `GET` | `/auth/me` | `verify_token` | Retorna los datos del usuario en sesión activa |
| `PATCH` | `/auth/profile` | `verify_token` | Permite al usuario activo modificar su nombre de usuario o contraseña |
| `POST` | `/auth/recuperar-password/solicitar` | Público | Genera y envía código de 6 dígitos por email si está configurado |
| `POST` | `/auth/recuperar-password/confirmar` | Público | Valida código de 6 dígitos no expirado y actualiza la contraseña |

### Administración (Exclusivo Admin)
| Método | Endpoint | Seguridad | Descripción |
| :--- | :--- | :--- | :--- |
| `GET` | `/admin/stats` | `verify_admin` | KPIs globales: total usuarios, activos hoy/7d, inactivos y peso en disco |
| `GET` | `/admin/users` | `verify_admin` | Lista todos los usuarios con fecha relativa de acceso y tamaño de BD |
| `POST` | `/admin/users` | `verify_admin` | Crea usuario y aprovisiona automáticamente su base de datos individual |
| `PATCH` | `/admin/users/{id}` | `verify_admin` | Modifica nombre de usuario, contraseña o rol (renueva JWT si es la propia cuenta) |
| `PATCH` | `/admin/users/{id}/status` | `verify_admin` | Activa o suspende el acceso de un usuario (protege al admin actual) |
| `DELETE` | `/admin/users/{id}` | `verify_admin` | Elimina usuario y purga su BD tenant (**protegido**: no se puede borrar administradores) |

### Endpoints Financieros Multi-Tenant (Aislados por Usuario)
| Método | Endpoint | Seguridad | Descripción |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/resumen` | `verify_token` | Resumen patrimonial del tenant en la divisa base |
| `GET` | `/api/resumen-mensual` | `verify_token` | Agrupación de ingresos y gastos mensuales |
| `GET` | `/api/transacciones` | `verify_token` | Listado histórico de movimientos de caja |
| `POST` | `/api/transacciones` | `verify_token` | Registrar movimiento en la BD del tenant |
| `PUT` | `/api/transacciones/{id}` | `verify_token` | Editar movimiento existente |
| `DELETE` | `/api/transacciones/{id}` | `verify_token` | Eliminar movimiento |
| `GET` | `/api/apartados` | `verify_token` | Listar sobres y metas de ahorro |
| `POST` | `/api/apartados` | `verify_token` | Crear apartado o meta |
| `POST` | `/api/apartados/{id}/movimiento` | `verify_token` | Depositar o retirar fondos de un apartado |
| `DELETE` | `/api/apartados/{id}` | `verify_token` | Eliminar apartado (valida saldo en cero) |
| `GET` | `/api/inversiones` | `verify_token` | Portafolio con valuación y Asset Allocation |
| `POST` | `/api/inversiones` | `verify_token` | Dar de alta posición bursátil |
| `PUT` | `/api/inversiones/{id}` | `verify_token` | Modificar títulos o precio promedio |
| `DELETE` | `/api/inversiones/{id}` | `verify_token` | Eliminar posición bursátil |
| `POST` | `/api/inversiones/sincronizar` | `verify_token` | Sincronizar cotizaciones en vivo en lote |
| `GET` | `/api/inversiones/cotizar/{ticker}` | `verify_token` | Consultar precio de mercado en tiempo real |
| `GET` | `/api/inversiones/buscar` | `verify_token` | Autocompletado de tickers de Yahoo Finance |
| `GET` | `/api/tipo-cambio` | `verify_token` | Tipos de cambio vigentes con caché |
| `GET` | `/api/exportar-excel` | `verify_token` | Descarga de reporte Excel del tenant |
| `GET` | `/api/backup` | `verify_token` | Descarga de la base de datos SQLite del tenant |

---

## 📜 Licencia y Términos de Uso

Este proyecto se distribuye bajo la licencia **GNU General Public License v3.0 (GNU GPLv3)**. Consulta el archivo [`LICENSE`](./LICENSE) para el texto legal completo.

* **Libertad de Uso y Estudio:** Puedes descargar, auditar, instalar y utilizar esta plataforma de forma totalmente libre y gratuita para tu uso personal, familiar o interno.
* **Libertad de Modificación y Contribución:** Eres libre de modificar el código fuente, corregir errores o añadir nuevas funcionalidades, siempre y cuando cualquier redistribución o trabajo derivado se mantenga bajo los mismos términos libres y de código abierto de la licencia GPLv3.
* **Protección contra Apropiación y Reventa Comercial (Copyleft):** No se autoriza empaquetar, cerrar el código fuente ni comercializar este software como un producto privativo o de reventa cerrada. El código y sus derivados deben permanecer siempre abiertos y accesibles para toda la comunidad.

