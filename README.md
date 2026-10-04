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

## Desarrollo local

El backend usa SQLite por defecto. Crea `Hospifer-Backend/.env`:

```env
SECRET_KEY=una-clave-local-larga-y-aleatoria
ENVIRONMENT=development
DATABASE_URL=sqlite+aiosqlite:///./app.db
CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
```

Para PostgreSQL puedes cambiar únicamente la URL, usando el driver async de Psycopg:

```env
DATABASE_URL=postgresql+psycopg://usuario:clave@localhost:5432/hospifer
```

Instala las dependencias y ejecuta las migraciones antes de iniciar la API:

```powershell
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
alembic upgrade head
python run.py
```

En desarrollo se crea el usuario inicial `admin` con contraseña `admin`; el token indica que debe cambiarla inmediatamente. En producción configura `ENVIRONMENT=production`, un `SECRET_KEY` de al menos 32 bytes y `INITIAL_ADMIN_PASSWORD` con al menos 12 bytes antes de migrar/iniciar.

Las migraciones deben ejecutarse con `alembic upgrade head`; la aplicación no crea ni altera tablas al arrancar. Para autogenerar cambios de esquema usa `alembic revision --autogenerate -m "descripcion"` y revisa el archivo antes de aplicarlo.

El inicio de sesión es `POST /auth/login` con JSON `{ "username": "admin", "password": "admin" }`. Usa `POST /auth/change-password` autenticado y consulta `/auth/me` para el perfil, roles y permisos efectivos. El backend ofrece pacientes/antecedentes, profesionales/especialidades, citas, consultas/prescripciones, catálogo, facturación, seguridad RBAC, auditoría y PDF clínicos. Los routers clínicos validan permisos en backend; ocultar módulos en Vue nunca sustituye esta comprobación.

Pruebas locales: `python -m unittest discover -s tests`. Comprobación de migraciones: `alembic check`.