# Sistema de Gestión Clínica — Backend

Backend del **Sistema Integral de Gestión de una Clínica de Salud**, encargado de proporcionar la API, lógica de negocio, autenticación y acceso controlado a la información almacenada en PostgreSQL.

El backend constituye la capa de servicios entre la aplicación cliente y el sistema gestor de bases de datos, garantizando la validación, consistencia, seguridad y procesamiento transaccional de la información.


## ✨ Características

El backend proporciona los servicios necesarios para:

* 👤 Gestión de pacientes.
* 🩺 Gestión de profesionales y especialidades.
* 📅 Programación y administración de citas.
* 🏥 Registro de consultas médicas.
* 📋 Gestión de historias clínicas.
* 💊 Prescripción de medicamentos.
* 🔬 Gestión de procedimientos clínicos.
* 💰 Gestión de servicios y facturación.
* 🔐 Autenticación de usuarios.
* 👥 Control de acceso basado en roles (RBAC).
* 📝 Auditoría de operaciones sensibles.
* 📊 Generación de información para reportes.
* 🔄 Procesamiento transaccional mediante PostgreSQL.

## 🛠️ Tecnologías

* **Python**
* **FastAPI**
* **Uvicorn**
* **PostgreSQL**
* **SQL**
* **Pydantic**
* **JWT** para autenticación, si aplica.
* **pytest** para pruebas automatizadas.

La aplicación utiliza PostgreSQL como sistema gestor de bases de datos relacional.

## Setup

Archivo .env en root con el siguiente formato:

```
secret_key=...
```