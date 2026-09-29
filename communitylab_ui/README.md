# CommunityLab — UI y Secretos (Sprint 1)

Panel de curaduría y gestión de secretos del proyecto CommunityLab.
Hackathon ONE G10 · Enfoque: Motor de FAQ dinámico y contenido educativo.

---

## Qué hay aquí y qué NO hay

**Sí hay:**
- Un panel de Streamlit funcionando, con las cuatro vistas del MVP.
- El contrato de datos: la estructura exacta que el backend deberá producir.
- Un módulo de secretos con la ruta `.env` (hoy) → OCI Vault (Sprint 2).

**No hay todavía:**
- Motor de análisis. El panel lee un archivo de ejemplo escrito a mano.
- Conexión real a OCI Object Storage.
- Backend FastAPI.

Esto es deliberado. La interfaz se puede construir y demostrar **antes** de
que el motor exista, y al hacerlo primero queda fijada la estructura de datos
que el resto del equipo debe producir.

---

## Cómo ejecutarlo

```bash
git clone <url-del-repo>
cd communitylab

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env             # Windows: copy .env.example .env

streamlit run ui/app.py
```

Se abre en `http://localhost:8501`.

No hace falta llenar el `.env` para ver el panel. La pestaña **Configuración**
te dirá qué secretos faltan.

---

## Estructura

```
communitylab/
├── data/
│   └── resultados_ejemplo.json   ← CONTRATO DE DATOS (mock)
├── ui/
│   └── app.py                    ← Panel de Streamlit
├── core/
│   └── secretos.py               ← Gestión de secretos
├── .env.example                  ← Plantilla (SÍ se sube)
├── .gitignore                    ← Excluye .env (NUNCA se sube)
└── requirements.txt
```

---

## El contrato de datos

`data/resultados_ejemplo.json` es la pieza más importante de esta entrega.
Define qué debe devolver el backend. Sus bloques:

| Bloque | Qué contiene | Lo pide el documento |
|---|---|---|
| `resumen_comunidad` | Totales, sentimiento, temas | Sí |
| `activos_distribucion_generados` | Los contenidos generados | Sí |
| `almacenamiento_oci` | Bucket, ruta, estado | Sí |
| `dudas_recurrentes_detectadas` | Grupos de preguntas equivalentes | Añadido (núcleo del enfoque FAQ) |
| `interacciones_muestra` | Mensajes con su análisis y decisión | Añadido (trazabilidad para la demo) |

**Regla del equipo:** si el backend necesita cambiar el nombre de un campo,
se cambia primero aquí y se avisa. Es el único punto de sincronización entre
los dos frentes de trabajo.

---

## Conectar el backend (Sprint 2)

Se toca **una sola función**, en `ui/app.py`:

```python
def cargar_resultados() -> dict:
    with open(ARCHIVO_MOCK, "r", encoding="utf-8") as f:
        return json.load(f)
```

pasa a ser:

```python
def cargar_resultados() -> dict:
    import requests
    return requests.post("http://localhost:8000/procesar", json=lote).json()
```

Nada más del panel cambia.

---

## Secretos

### Hoy: archivo `.env`

Todo el equipo usa la misma función y no le importa de dónde sale el valor:

```python
from core.secretos import obtener_secreto

clave = obtener_secreto("GEMINI_API_KEY")
```

Verificar el entorno propio:

```bash
python core/secretos.py
```

### Sprint 2: OCI Vault

La migración consiste en implementar `_leer_de_vault()` en `core/secretos.py`
y cambiar una variable de entorno:

```
FUENTE_SECRETOS=vault
```

Ningún otro archivo del proyecto cambia.

**Sobre el costo:** OCI Vault entra en Always Free (hasta 20 versiones de
claves maestras y 150 secretos). Hay que usar el **Virtual Vault**, que es el
tipo por defecto, con **clave de software**. El Private Vault y las claves HSM
dedicadas sí tienen costo. Verificar los límites vigentes de Always Free antes
de crear nada.

### Reglas innegociables

1. `.env` **nunca** se sube. Ya está en `.gitignore`.
2. `.env.example` sí se sube, con nombres de variables y sin valores.
3. Si alguien sube una clave por error, hay que **rotarla**. Borrarla del
   repositorio no la borra del historial de Git.

---

## Estado frente al checklist de evaluación

| Requisito | Estado |
|---|---|
| Ingesta funcional | Pendiente (backend) |
| Análisis con LLM | Pendiente (backend) |
| ≥ 2 formatos de activo | Estructura definida y visible en el panel |
| Orquestación | Pendiente (backend) |
| OCI Object Storage | Pendiente — **máxima prioridad del equipo** |
| 3 ejemplos demostrados | 5 activos de ejemplo ya visibles |
| Repo documentado | En curso |

---

## Próximos pasos de este frente

1. Revisar el contrato de datos con el equipo de backend y congelarlo.
2. Sustituir `cargar_resultados()` por la llamada real cuando exista el endpoint.
3. Implementar `_leer_de_vault()` una vez el MVP funcione completo.
