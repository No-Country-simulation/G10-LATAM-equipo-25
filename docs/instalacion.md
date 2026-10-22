# Instalación paso a paso y cambio de credenciales

Esta guía sirve para instalar CommunityLab desde cero en una computadora y para cambiar las credenciales (claves de Gemini y Cohere, y datos de Oracle Cloud). Está escrita para que la pueda seguir cualquier integrante del equipo, programe o no.

El proyecto tiene **dos partes** que viven en dos ramas del mismo repositorio:

| Parte | Qué hace | Rama | Dirección al encenderla |
|---|---|---|---|
| **Motor** (backend) | Analiza los mensajes, busca la FAQ oficial, redacta los borradores con Gemini y los guarda | `feature/backend-ia-orchestration` | `http://localhost:8000` |
| **Panel** de curaduría | La pantalla donde el equipo revisa, edita y aprueba lo que preparó el motor | `feature/ui-curaduria` | `http://localhost:8501` |

> **Primero hay que encender el motor y después el panel.** El panel no piensa por sí mismo: le pide todo al motor.

---

## 1. Lo que necesitas antes de empezar

- **Python 3.13** o superior. Para revisarlo, abre una terminal y escribe `python --version`.
- **Git**, para descargar el repositorio.
- **Opcional:** una clave de Gemini, si quieres que la redacción la haga la IA. **Sin clave también funciona**: el motor usa reglas locales (lo llamamos *modo local*) y sirve para probar todo el recorrido.

> En Windows se usa **PowerShell**. Donde la guía muestra dos versiones de un comando, usa la de tu sistema.

---

## 2. Descargar el proyecto

Se descarga el repositorio dos veces, una por cada rama, en dos carpetas:

```bash
git clone -b feature/backend-ia-orchestration https://github.com/No-Country-simulation/G10-LATAM-equipo-25.git communitylab-motor
git clone -b feature/ui-curaduria https://github.com/No-Country-simulation/G10-LATAM-equipo-25.git communitylab-panel
```

Quedan dos carpetas: `communitylab-motor` y `communitylab-panel`.

---

## 3. Instalar y encender el motor

Abre una terminal **en la carpeta `communitylab-motor`** y sigue los pasos en orden.

**3.1 Crear un entorno aislado** (una "caja" con las librerías del proyecto, para no mezclarlas con otras):

```bash
python -m venv .venv
```

**3.2 Activarlo:**

- Windows (PowerShell): `.venv\Scripts\activate`
- macOS / Linux: `source .venv/bin/activate`

Si se activó bien, la línea de la terminal empieza con `(.venv)`.

> Si PowerShell dice que *la ejecución de scripts está deshabilitada*, ejecuta una sola vez `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` y vuelve a intentarlo.

**3.3 Instalar las librerías:**

```bash
pip install -r communitylab_backend/requirements.txt
```

**3.4 Crear el archivo de configuración `.env`**, que es una copia de la plantilla:

- Windows: `copy .env.example .env`
- macOS / Linux: `cp .env.example .env`

Sin cambiar nada, el motor ya funciona en modo local.

**3.5 Encender el motor:**

```bash
uvicorn communitylab_backend.main:app --reload
```

**3.6 Comprobar que funciona.** Abre `http://localhost:8000/docs` en el navegador: es la documentación interactiva, donde se puede probar cada función. Deja esta terminal abierta mientras uses el proyecto.

---

## 4. Instalar y encender el panel

Abre **otra** terminal en la carpeta `communitylab-panel\communitylab_ui` (la subcarpeta `communitylab_ui`) y repite los mismos pasos:

```bash
python -m venv .venv
```

Actívalo igual que en el paso 3.2 y luego:

```bash
pip install -r requirements.txt
```

- Windows: `copy .env.example .env`
- macOS / Linux: `cp .env.example .env`

```bash
streamlit run ui/app.py
```

El panel se abre en `http://localhost:8501`. Si arriba aparece el aviso **"Modo local"**, el panel ya está conectado al motor.

---

## 5. Probar que todo funciona (5 minutos)

1. En el panel, entra a **Procesar lote**, elige el lote `01 briefing semana04` y pulsa **Procesar este lote**.
2. Abre **Motor de FAQ**: aparecen las dudas agrupadas por tema, cada una con su tutorial rápido, su tip de la semana y su propuesta de documentación.
3. Abre **Curaduría de activos**, aprueba un borrador y pulsa **Guardar curaduría en el backend**. Debe aparecer "1 aprobados… Guardado en…".
4. En **Configuración** se ve qué modelo usa el motor y dónde guarda los paquetes.

Si los cuatro pasos funcionan, la instalación está completa.

---

## 6. Cambiar las credenciales

Todas las credenciales del motor van en **un solo archivo**: el `.env` de la carpeta `communitylab-motor`. **Después de cambiar algo hay que apagar el motor (Ctrl + C) y volver a encenderlo** (paso 3.5).

> **Regla de oro:** el `.env` **nunca** se sube a GitHub (ya está bloqueado en `.gitignore`). No pegues claves en el chat del equipo, en capturas de pantalla ni en el código. Si una clave se publica por error, hay que borrarla y crear una nueva: ver [secretos.md](secretos.md#si-una-clave-se-publicó-por-error).

### 6.1 Activar Gemini (la IA que analiza y redacta)

1. Crea tu clave en [Google AI Studio](https://aistudio.google.com/apikey). Lo ideal es **una clave por persona**: si una se filtra, solo se borra esa.
2. En el `.env` del motor, cambia estas tres líneas:

   ```
   LLM_PROVIDER=gemini
   GEMINI_API_KEY=tu_clave_aqui
   GEMINI_MODEL=gemini-3.1-flash-lite
   ```

3. Reinicia el motor. En el panel, el aviso "Modo local" desaparece y en **Configuración** se ve `gemini`.

`gemini-3.1-flash-lite` es el modelo con el que se probaron todos los ejemplos. Cada lote usa **2 consultas** a Gemini; la cuota gratuita permite unas 20 por día, así que conviene probar con un lote a la vez.

**Para cambiar la clave** (porque venció, se filtró o es de otra persona): reemplaza el valor de `GEMINI_API_KEY` y reinicia el motor. Nada más.

**Para volver al modo local** (sin gastar cuota): `LLM_PROVIDER=mock`.

### 6.2 Activar la búsqueda inteligente con Cohere (opcional)

La búsqueda normal (`faq_db`) no necesita claves y es la recomendada para la demo. La de Cohere entiende dudas escritas sin palabras técnicas. Para activarla:

```
RETRIEVAL_PROVIDER=semantic
EMBEDDING_PROVIDER=cohere
RERANKER_PROVIDER=cohere
COHERE_API_KEY=tu_clave_de_cohere
```

Después hay que preparar su índice una vez (unas 2 consultas a Cohere):

```bash
python -m communitylab_backend.tools.build_faq_index
```

Detalle y comparación entre las dos búsquedas: [busqueda-semantica.md](busqueda-semantica.md).

### 6.3 Guardar los paquetes en Oracle Cloud (OCI Object Storage)

Por defecto los paquetes se guardan en la carpeta `salidas/paquetes/`. Para guardarlos en un bucket de Oracle:

1. Crea en tu computadora el archivo `~/.oci/config` con tu llave de API de OCI (en la consola de OCI: *Perfil → Claves de API → Agregar clave de API*; la consola muestra el texto que va en el archivo).
2. En el `.env` del motor:

   ```
   STORAGE_PROVIDER=oci
   OCI_NAMESPACE=el_namespace_de_tu_tenancy
   OCI_BUCKET=nombre_del_bucket
   OCI_REGION=sa-saopaulo-1
   ```

3. Prueba la conexión (sube un paquete pequeño de prueba):

   ```bash
   python -m communitylab_backend.tools.check_oci
   ```

La llave `.pem` y el archivo `config` **nunca** se suben al repositorio. Más detalle: [object-storage-oci.md](object-storage-oci.md).

### 6.4 Producción: claves guardadas en OCI Vault

En un servidor no conviene dejar claves en un archivo. Para eso el motor puede leerlas de **OCI Vault** (una caja fuerte de Oracle) cambiando una sola línea: `SECRET_PROVIDER=oci`. Los pasos para crear el Vault, darle permiso al servidor y **rotar una clave** (cambiarla sin tocar el código) están en [secretos.md](secretos.md).

### 6.5 Credenciales del panel

El `.env` del panel **no lleva claves de IA**: el que habla con Gemini y Cohere es el motor. Lo único que se cambia ahí es:

| Variable | Para qué | Cuándo cambiarla |
|---|---|---|
| `BACKEND_URL` | Dirección del motor | Si el motor no está en `http://localhost:8000` (por ejemplo, en un servidor) |
| `FUENTE_SECRETOS` | De dónde lee el panel sus datos: `auto` (la plantilla; usa OCI Vault si está configurado y, si no, este archivo), `env` o `vault` | Normalmente no se toca |

La vista **Configuración** del panel muestra qué datos están configurados, **sin mostrar nunca los valores**.

---

## 7. Comando rápido para Windows

Si ya instalaste todo una vez, se pueden encender las dos partes juntas con un script de PowerShell que abre dos ventanas. Guarda esto como `levantar.ps1` en la carpeta que contiene `communitylab-motor` y `communitylab-panel`:

```powershell
$raiz = $PSScriptRoot
Start-Process powershell -WorkingDirectory "$raiz\communitylab-motor" -ArgumentList "-NoExit", "-Command", ".\.venv\Scripts\python -m uvicorn communitylab_backend.main:app --reload --port 8000"
Start-Process powershell -WorkingDirectory "$raiz\communitylab-panel\communitylab_ui" -ArgumentList "-NoExit", "-Command", ".\.venv\Scripts\python -m streamlit run ui/app.py --server.port 8501"
```

Y ejecútalo, desde cualquier carpeta, con la ruta completa entre comillas:

```powershell
powershell -ExecutionPolicy Bypass -File "C:\ruta\a\levantar.ps1"
```

---

## 8. Problemas comunes

| Lo que ves | Qué significa | Qué hacer |
|---|---|---|
| El panel dice **"Backend sin conexión"** | El motor está apagado o en otra dirección | Enciende el motor (paso 3.5) o revisa `BACKEND_URL` en el `.env` del panel |
| `ModuleNotFoundError` al encender | Falta instalar librerías o el entorno no está activado | Activa `.venv` (paso 3.2) y repite `pip install` |
| Gemini responde **401** o `API key not valid` | La clave está mal copiada o fue borrada | Crea una clave nueva y reemplázala en `GEMINI_API_KEY` |
| Gemini responde **404** | El nombre del modelo no existe | Usa `GEMINI_MODEL=gemini-3.1-flash-lite` |
| Gemini responde **429** | Se acabó la cuota del día | Espera al día siguiente o vuelve a `LLM_PROVIDER=mock` |
| Gemini responde **503** o **504** | Gemini está saturado o tardó demasiado | Reintenta en un minuto; si se repite, sube `PROVIDER_TIMEOUT_SECONDS` a `120` |
| `Address already in use` | Ya hay algo encendido en ese puerto | Cierra la otra ventana o usa otro puerto (`--port 8001`) y actualiza `BACKEND_URL` |

---

## 9. Para quien programa: comprobar el código

Con el entorno del motor activado:

```bash
pip install -r communitylab_backend/requirements-dev.txt
python -m pytest tests/backend -q
python -m communitylab_backend.documentation_check
```

Las pruebas no usan internet ni gastan cuota: usan versiones falsas de Gemini, Cohere y OCI. Qué hace cada función y por qué cambió: [registro-de-funciones.md](registro-de-funciones.md). Las del panel están en `docs/panel-registro-de-funciones.md` de su rama.
