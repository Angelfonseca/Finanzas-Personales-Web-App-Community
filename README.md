# Finanzas-Personales-Web-App
# 💰 Finanzas Personales Web App

Una aplicación web ligera, minimalista y autohospedada para llevar el control detallado de tus finanzas personales. Diseñada desde cero para ser rápida, privada y correr de forma eficiente en servidores locales o dispositivos como una Raspberry Pi.

---

## 🚀 Tecnologías Utilizadas

* **Backend:** [FastAPI](https://fastapi.tiangolo.com/) (Python)
* **Base de Datos:** [SQLite](https://www.sqlite.org/)
* **Frontend:** HTML5, CSS3 Moderno, JavaScript (Vanilla)
* **Servidor ASGI:** [Uvicorn](https://www.uvicorn.org/)

---

## 📂 Estructura del Proyecto

```text
finanzas-app/
├── main.py            # Servidor FastAPI y Endpoints REST (CRUD)
├── database.py        # Configuración inicial y esquema de SQLite
├── finanzas-app.db    # Archivo local de la base de datos (generado automáticamente)
├── requirements.txt   # Dependencias de Python
└── static/
    ├── index.html     # Interfaz visual de usuario (Dashboard)
    ├── style.css      # Estilos limpios, modernos y responsivos
    └── app.js         # Lógica de cliente y peticiones asíncronas (Fetch API)
