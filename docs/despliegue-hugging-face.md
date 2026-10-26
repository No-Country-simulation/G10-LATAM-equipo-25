# Despliegue en Hugging Face Spaces (con OCI Object Storage y OCI Vault)

Esta guía publica CommunityLab en internet usando **Hugging Face Spaces**, que es gratis. Los servicios de Oracle siguen siendo el corazón del proyecto, como pidieron los organizadores:

- **OCI Object Storage** guarda los paquetes de cada lote, la curaduría aprobada y **la memoria del motor**: el historial de dudas y la base de FAQs.
- **OCI Vault** guarda las claves de Gemini y Cohere, y la contraseña del panel.

El servidor de Hugging Face solo ejecuta el programa. Si se reinicia, no se pierde nada, porque todo lo importante vive en OCI.

```
Equipo y jueces ──HTTPS──▶ Hugging Face Space (Docker, gratis)
                             ├─ Panel Streamlit   ← lo único visible, con contraseña
                             └─ Motor FastAPI     ← solo por dentro (127.0.0.1)
                                    │
                                    ├─▶ OCI Vault           claves de Gemini y Cohere
                                    ├─▶ OCI Object Storage  paquetes + memoria del motor
                                    └─▶ Gemini              análisis y redacción
```

> **Regla de oro:** ninguna clave, llave `.pem` u OCID va en un archivo. Todo va en *Settings → Variables and secrets* del Space, y lo que es clave, como **Secret** (nunca como Variable).

---

## 1. Lo que necesitas

- Una cuenta de [Hugging Face](https://huggingface.co/join) (gratis).
- Acceso a la consola de OCI de la cuenta del equipo, para crear el bucket, la llave de API y el Vault.
- Una clave de Gemini (y, si se usa la búsqueda inteligente, una de Cohere).
- El repositorio en GitHub con todo en `main` (motor y panel). El Space descarga el código de ahí.

---

## 2. Preparar OCI (una sola vez)

### 2.1 Bucket

En la consola de OCI: *Storage → Buckets → Create Bucket*.

- Nombre: por ejemplo `communitylab-activos`. Anótalo junto con el **namespace**, que aparece en los detalles del bucket.
- Opcional pero recomendado: activa **Object Versioning**. Así cada versión anterior de la memoria del motor queda guardada como copia de seguridad.

### 2.2 Llave de API (para que el Space se identifique ante OCI)

1. *Perfil (arriba a la derecha) → My profile → API keys → Add API key → Generate API key pair*.
2. **Descarga la llave privada** (`.pem`). Es lo único que no se puede volver a descargar.
3. Pulsa **Add**. OCI muestra un texto con `user`, `fingerprint`, `tenancy` y `region`: **cópialo**, lo vas a necesitar en el paso 5.

> Lo ideal es crear un **usuario de OCI solo para el Space**, con permisos mínimos. Si se filtra su llave, se borra sin afectar a nadie más.

### 2.3 Permisos

Si el usuario no es administrador, su grupo necesita estas dos políticas (*Identity → Policies*):

```
Allow group <grupo-del-space> to manage objects in compartment <compartimento> where target.bucket.name = '<nombre-del-bucket>'
Allow group <grupo-del-space> to read secret-family in compartment <compartimento>
```

### 2.4 Vault y secretos

*Identity & Security → Vault → Create Vault*. Usa el tipo por defecto (**Virtual Vault**, gratis) y una **clave de cifrado de software**. Después crea estos secretos, con los nombres **exactamente** así:

| Nombre del secreto | Valor |
|---|---|
| `communitylab-gemini-api-key` | Tu clave de Gemini |
| `communitylab-cohere-api-key` | Tu clave de Cohere (solo si usan la búsqueda inteligente) |
| `communitylab-panel-password` | La contraseña para entrar al panel publicado |

Anota el **OCID del Vault** (empieza con `ocid1.vault.`).

Más detalle sobre Vault y cómo cambiar una clave sin tocar el código: [secretos.md](secretos.md).

---

## 3. Subir la memoria inicial al bucket (opcional, recomendado)

El Space arranca con la base de FAQs del repositorio y un ranking vacío. Para que arranque con el ranking que ya tienen (las dudas de los ejemplos procesados), súbelo **una vez** desde la computadora donde corre el motor.

1. En el `.env` del motor pon los datos del bucket y tu configuración de OCI:

   ```
   OCI_NAMESPACE=tu_namespace
   OCI_BUCKET=communitylab-activos
   OCI_REGION=tu_region
   ```

2. Sube la memoria:

   ```bash
   python -m communitylab_backend.tools.sync_state subir
   ```

Debe mostrar dos líneas `[OK]`: `estado/historial_dudas.db` y `estado/motor_educativo.db`.

> Ojo: `subir` **reemplaza** la memoria que haya en el bucket. Hazlo antes de publicar, no después. Para traer a tu computadora lo que aprendió el Space, usa `bajar`.

---

## 4. Crear el Space

1. En Hugging Face: [New Space](https://huggingface.co/new-space).
2. **Space SDK:** `Docker` → *Blank*.
3. **Hardware:** `CPU basic` (gratis).
4. **Visibilidad:** *Public* si los jueces deben entrar sin cuenta (el panel igual pide contraseña), o *Private* si solo entra el equipo.
5. En la pestaña **Files**, sube dos archivos:
   - `Dockerfile`: el de `despliegue/huggingface/Dockerfile` de este repositorio, tal cual.
   - `README.md`: reemplaza el que crea Hugging Face por este texto (la parte entre `---` es la configuración del Space):

     ```
     ---
     title: CommunityLab
     emoji: 📋
     colorFrom: blue
     colorTo: indigo
     sdk: docker
     app_port: 7860
     pinned: false
     ---

     CommunityLab: motor de FAQ dinámico y panel de curaduría (Hackathon ONE G10, equipo 25).
     ```

El código **no** se sube al Space: el `Dockerfile` lo descarga de GitHub al construir.

---

## 5. Configurar secretos y variables

En el Space: *Settings → Variables and secrets*.

### Secrets (privados, nunca se muestran)

| Nombre | Valor | De dónde sale |
|---|---|---|
| `OCI_PRIVATE_KEY` | El contenido completo del `.pem`, desde `-----BEGIN` hasta `-----END` | Paso 2.2 |
| `OCI_USER_OCID` | El valor `user=` | Texto del paso 2.2 |
| `OCI_FINGERPRINT` | El valor `fingerprint=` | Texto del paso 2.2 |
| `OCI_TENANCY_OCID` | El valor `tenancy=` | Texto del paso 2.2 |
| `OCI_VAULT_ID` | El OCID del Vault | Paso 2.4 |

> Si al pegar la llave se pierden los saltos de línea, usa `OCI_PRIVATE_KEY_B64` en lugar de `OCI_PRIVATE_KEY`, con la llave en base64. En PowerShell: `[Convert]::ToBase64String([IO.File]::ReadAllBytes("ruta\a\llave.pem"))`.

### Variables (no son secretas)

| Nombre | Valor |
|---|---|
| `OCI_REGION` | La región del bucket y del Vault, por ejemplo `mx-queretaro-1` |
| `OCI_NAMESPACE` | El namespace del bucket |
| `OCI_BUCKET` | El nombre del bucket |

### Si el Vault está en otra cuenta de OCI que el bucket

Los secretos de arriba son los de la cuenta del **bucket**. Para la cuenta del **Vault** se agregan estos; con ellos el arranque arma un segundo perfil (`[VAULT]`) y el motor y el panel leen las claves con él:

| Tipo | Nombre | Valor |
|---|---|---|
| Secret | `OCI_VAULT_PRIVATE_KEY` (o `OCI_VAULT_PRIVATE_KEY_B64`) | La llave privada de la cuenta del Vault |
| Secret | `OCI_VAULT_USER_OCID` | `user=` de la cuenta del Vault |
| Secret | `OCI_VAULT_FINGERPRINT` | `fingerprint=` de esa llave |
| Secret | `OCI_VAULT_TENANCY_OCID` | `tenancy=` de la cuenta del Vault |
| Variable | `OCI_VAULT_REGION` | La región del Vault, por ejemplo `mx-queretaro-1` |

En ese caso `OCI_REGION` es la región del bucket.

El resto ya viene configurado en el `Dockerfile`: Gemini (`gemini-3.1-flash-lite`), paquetes, memoria y claves en OCI. Si quieres cambiar algo, crea una Variable con el mismo nombre y tiene prioridad; por ejemplo, `LLM_PROVIDER=mock` para probar sin gastar cuota de Gemini.

---

## 6. Construir y comprobar

Al guardar los secretos, el Space se construye solo (pestaña **Logs**, unos 5 minutos la primera vez). Cuando termina, los registros deben mostrar:

```
[arranque] Configuracion de OCI lista
[arranque] Motor listo
```

Después:

1. Abre la pestaña **App**: aparece la pantalla de contraseña. Entra con la que guardaste en el Vault.
2. **Configuración** debe decir `OCI OBJECT STORAGE` y `memoria : OCI (historial y FAQs respaldados en el bucket)`.
3. **Procesar lote → 01 briefing semana04 → Procesar este lote.** Cuando termine, en la consola de OCI el bucket tiene `activos/<id>.json` y `estado/historial_dudas.db` actualizado.
4. **Motor de FAQ** muestra los temas. Reinicia el Space (*Settings → Restart*) y comprueba que el ranking sigue ahí: eso confirma que la memoria vive en OCI.

---

## 7. Actualizar el Space

- **Cuando haya commits nuevos en GitHub:** *Settings → Factory rebuild*. El `Dockerfile` detecta los commits nuevos y descarga el código otra vez.
- **Para probar una rama antes de unirla a `main`:** en el `Dockerfile` del Space cambia `RAMA_MOTOR` o `RAMA_PANEL` por el nombre de esa rama.
- **Para cambiar una clave:** crea una versión nueva del secreto en OCI Vault y reinicia el Space. No hace falta tocar nada más.

---

## 8. Problemas comunes

| Lo que ves | Qué significa | Qué hacer |
|---|---|---|
| Los registros dicen `Falta el secreto OCI_...` | Falta un secreto del paso 5 | Créalo con el nombre exacto y reinicia |
| `no hay OCI_PRIVATE_KEY; OCI no va a funcionar` | No se cargó la llave | Revisa `OCI_PRIVATE_KEY` (o usa `OCI_PRIVATE_KEY_B64`) |
| El panel muestra errores **503** y los registros `state_restore_failed` | El motor no pudo bajar su memoria de OCI. **Por seguridad no trabaja con una memoria vacía** | Revisa las credenciales, `OCI_NAMESPACE`, `OCI_BUCKET`, `OCI_REGION` y el permiso `manage objects`. Al corregirlo, se recupera solo |
| `OCI rechazó las credenciales` | Llave, fingerprint u OCIDs no coinciden | Vuelve a copiar el texto del paso 2.2 |
| `OCI Vault no tiene el secreto ...` | El nombre del secreto no coincide | Debe ser exactamente `communitylab-gemini-api-key` (y los demás del paso 2.4) |
| El panel no pide contraseña | No encontró `communitylab-panel-password` | Créalo en el Vault, o agrega un Secret `PANEL_PASSWORD` en el Space |
| Gemini responde 429 | Se acabó la cuota del día (unas 20 consultas; cada lote usa 2) | Esperar al día siguiente, o la Variable `LLM_PROVIDER=mock` |
| La página tarda en abrir | El Space gratuito se duerme tras 48 horas sin visitas | Abrirlo unos minutos antes de la demo |

---

## 9. Cómo funciona por dentro (para quien programa)

- `despliegue/huggingface/Dockerfile`:
  - usa Python 3.13;
  - clona las dos ramas de GitHub e instala las librerías del motor y del panel juntas (93 paquetes, sin conflictos);
  - deja la configuración por defecto del despliegue.
- `despliegue/huggingface/arrancar.sh` hace cuatro cosas:
  1. arma `~/.oci/config` con los secretos (sin imprimirlos);
  2. enciende el motor en `127.0.0.1:8000`;
  3. espera a que responda y enciende el panel en `0.0.0.0:7860`;
  4. si uno de los dos se cae, termina el contenedor para que Hugging Face lo reinicie.
- **Memoria en OCI** (`STATE_PROVIDER=oci`, módulo `infrastructure/oci_state.py`):
  - al encender, el motor baja `estado/historial_dudas.db` y `estado/motor_educativo.db` del bucket;
  - después de cada cambio los vuelve a subir;
  - si no puede bajarlos, responde 503 en vez de trabajar con una memoria vacía que después pisaría la buena.
- **Claves:** el motor lee la de Gemini del Vault (`SECRET_PROVIDER=oci`). El panel lee su contraseña del Vault y, si no está, del Secret `PANEL_PASSWORD` (`FUENTE_SECRETOS=auto`).
- **`enableXsrfProtection=false`** en Streamlit: sin esto, subir archivos falla detrás del proxy de Hugging Face. El panel queda protegido por la contraseña.
- **Concurrencia:** pensado para un solo contenedor con un solo proceso del motor, que es lo que da el Space. Con varias copias del motor a la vez, la última en subir la memoria ganaría.
