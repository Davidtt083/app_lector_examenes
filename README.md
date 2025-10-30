# Sistema de login con Flask y SQLite

Proyecto minimalista que implementa registro, login y logout usando Flask, Flask-Login y SQLite.

Requisitos
- Python 3.8+

Instalación y ejecución (PowerShell en Windows)

1) Crear y activar un entorno virtual:

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

2) Instalar dependencias:

```powershell
pip install -r requirements.txt
```

3) Ejecutar la aplicación:

```powershell
python run.py
```

La aplicación crea automáticamente la base de datos SQLite `site.db` en el directorio del proyecto la primera vez que la ejecutas.

Rutas principales
- / -> página principal (index)
- /register -> formulario de registro (validación: email válido, contraseña mínima 6 caracteres, confirmación)
- /login -> formulario de ingreso
- /dashboard -> ruta protegida para usuarios autenticados

Notas
- Cambia `SECRET_KEY` en producción. Puedes usar una variable de entorno `FLASK_SECRET`.
- Este proyecto es educativo; para producción añade medidas adicionales (HTTPS, bloqueo de intentos, validación más estricta, etc.).
