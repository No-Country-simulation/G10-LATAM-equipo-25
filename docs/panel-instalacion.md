# Instalación del panel paso a paso

Esta guía instala el **panel de curaduría**: la pantalla donde el equipo revisa, edita y aprueba lo que prepara el motor.

> **La guía completa del proyecto** (motor + panel, cambio de credenciales y problemas comunes) está en la rama del motor, `feature/backend-ia-orchestration`, en `docs/instalacion.md`. Conviene seguir esa. Este documento repite solo la parte del panel.

**El panel necesita el motor encendido.** Sin motor, abre igual y muestra el aviso "Backend sin conexión"; desde *Procesar lote → Respuesta guardada* se pueden cargar resultados ya procesados para mirarlos.

---

## 1. Requisitos

- **Python 3.13** o superior (`python --version` para revisarlo).
- **Git**.
- El **motor** instalado y encendido en `http://localhost:8000`.

## 2. Descargar

```bash
git clone -b feature/ui-curaduria https://github.com/No-Country-simulation/G10-LATAM-equipo-25.git communitylab-panel
```

## 3. Instalar

Abre una terminal en `communitylab-panel\communitylab_ui` (la subcarpeta `communitylab_ui`).

**3.1 Crear un entorno aislado** (una "caja" con las librerías del panel):

```bash
python -m venv .venv
```

**3.2 Activarlo:**

- Windows (PowerShell): `.venv\Scripts\activate`
- macOS / Linux: `source .venv/bin/activate`

**3.3 Instalar las librerías:**

```bash
pip install -r requirements.txt
```

**3.4 Crear el archivo de configuración:**

- Windows: `copy .env.example .env`
- macOS / Linux: `cp .env.example .env`

## 4. Encender

```bash
streamlit run ui/app.py
```

Se abre en `http://localhost:8501`. Si arriba aparece el aviso **"Modo local"** (o ningún aviso, si el motor usa Gemini), el panel está conectado.

## 5. Cambiar la configuración

El `.env` del panel **no lleva claves de IA**: el que habla con Gemini y Cohere es el motor, y sus claves van en el `.env` del motor. En el panel solo se cambia:

| Variable | Para qué | Cuándo cambiarla |
|---|---|---|
| `BACKEND_URL` | Dirección del motor | Si el motor no está en `http://localhost:8000` (por ejemplo, en un servidor) |
| `FUENTE_SECRETOS` | De dónde lee el panel sus datos: `auto` (la plantilla; usa el Vault si está configurado y, si no, este archivo), `env` (solo este archivo) o `vault` (solo OCI Vault) | Normalmente no se toca |
| `OCI_VAULT_ID`, `OCI_AUTH` | Datos del Vault (también se acepta `OCI_VAULT_OCID`) | Solo si se usa OCI Vault |

Después de cambiar algo, apaga el panel (Ctrl + C) y vuelve a encenderlo.

La vista **Configuración** muestra qué datos están configurados, **sin mostrar nunca los valores**. El `.env` **nunca** se sube a GitHub (ya está bloqueado en `.gitignore`).

## 6. Problemas comunes

| Lo que ves | Qué hacer |
|---|---|
| "Backend sin conexión" | Enciende el motor o revisa `BACKEND_URL` |
| `ModuleNotFoundError` | Activa `.venv` (paso 3.2) y repite `pip install -r requirements.txt` |
| La barra lateral desapareció | Pulsa la flecha `>` arriba a la izquierda para volver a abrirla |
| Se perdió lo revisado al recargar | En *Procesar lote* aparece **Recuperar sesión** |

Qué hace cada función del panel y por qué cambió: [panel-registro-de-funciones.md](panel-registro-de-funciones.md).
