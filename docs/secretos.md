# Manejo de secretos: claves de Gemini y Cohere

Este documento explica dónde viven las claves del proyecto y cómo protegerlas, tanto en una computadora (modo local) como en producción en OCI. Está escrito para que lo entienda cualquier persona del equipo, programe o no.

## En pocas palabras

- Una **clave de API** (Gemini, Cohere) funciona como una contraseña: quien la tenga puede gastar la cuota del equipo a su nombre. Si se publica, hay que darla por perdida.
- **En una computadora**, las claves van en el archivo `.env`, que nunca se sube al repositorio.
- **En producción (OCI Compute)**, las claves no se guardan en el servidor: se guardan cifradas en **OCI Vault** y el backend las pide al arrancar, identificándose como el servidor (*instance principal*), sin ninguna contraseña escrita en disco.
- El cambio entre un modo y otro es **una sola variable**: `SECRET_PROVIDER=environment` (por defecto) o `SECRET_PROVIDER=oci`. Ningún otro archivo del código cambia.

| | Modo local | Producción en OCI |
|---|---|---|
| Variable | `SECRET_PROVIDER=environment` | `SECRET_PROVIDER=oci` |
| Dónde está la clave | Archivo `.env` en tu computadora | Secreto cifrado en OCI Vault |
| Cómo se identifica el backend | No hace falta | *Instance principal*: la identidad del propio servidor |
| Quién puede leerla | Quien use tu computadora | Solo los servidores del grupo dinámico autorizado |
| Cambiar la clave | Editar el `.env` y reiniciar | Nueva versión del secreto y reiniciar |

## 1. Modo local (cada persona en su computadora)

### Reglas

1. **El `.env` nunca se sube.** Ya está en `.gitignore`. Lo que sí se sube es `.env.example`, que tiene los nombres de las variables pero ningún valor.
2. **Nunca escribas una clave en el código**, en un notebook, en un ejemplo, en un issue, en un mensaje del chat del equipo ni en una captura de pantalla. El código solo pide la clave por su nombre (`GEMINI_API_KEY`).
3. **Una clave por persona.** Cada integrante crea su propia clave de Gemini (en Google AI Studio) y de Cohere. Así, si una se filtra, se revoca solo esa y nadie más queda sin trabajar; y se sabe de dónde salió el problema. La clave de producción es otra distinta y solo vive en OCI Vault.
4. **Restringe tu clave de Gemini en Google Cloud.** Las claves de AI Studio pertenecen a un proyecto de Google Cloud. En la consola de Google Cloud, en *APIs y servicios → Credenciales*, abre la clave y:
   - en **Restricciones de API**, permite solo la **Generative Language API**;
   - si la clave es para un servidor con IP fija, en **Restricciones de aplicaciones** limita por **dirección IP**.

   Así, aunque alguien la consiga, no podrá usarla para otros servicios de Google ni desde otro lugar.

### Cómo se configura

```bash
# Windows:  copy .env.example .env
cp .env.example .env
```

Después, en el `.env`:

```
SECRET_PROVIDER=environment
GEMINI_API_KEY=<tu clave personal>
COHERE_API_KEY=<tu clave personal>
```

Antes de subir cambios, comprueba que el `.env` no esté en el repositorio (este comando no debe mostrar nada):

```bash
git ls-files .env
```

### Si una clave se publicó por error

Borrar el archivo o el commit **no alcanza**: el historial de git, las copias y los buscadores ya pueden tenerla.

1. **Revócala de inmediato** (Google AI Studio o el panel de Cohere) y crea una nueva.
2. Pon la nueva en tu `.env` (o, si era la de producción, crea una nueva versión del secreto en OCI Vault, ver la sección 3).
3. Avisa al equipo para revisar si hubo consumo extraño.

## 2. Producción en OCI (OCI Compute + OCI Vault)

### Las piezas

- **Vault:** la "caja fuerte" de OCI donde se guardan secretos.
- **Clave maestra:** la llave con la que el Vault cifra los secretos. Se crea una vez dentro del Vault.
- **Secreto:** cada clave de API guardada en el Vault, con un nombre. El backend busca estos nombres:

  | Clave | Nombre del secreto (por defecto) | Variable para cambiar el nombre |
  |---|---|---|
  | `GEMINI_API_KEY` | `communitylab-gemini-api-key` | `OCI_SECRET_GEMINI` |
  | `COHERE_API_KEY` | `communitylab-cohere-api-key` | `OCI_SECRET_COHERE` |

  Son los mismos nombres del catálogo del panel (`communitylab_ui/core/secretos.py`), así que backend y panel comparten los secretos.
- **Grupo dinámico:** un grupo cuyos miembros no son personas sino **servidores** (instancias de OCI Compute) que cumplen una regla.
- **Política:** la regla escrita que dice qué puede hacer ese grupo. Aquí: solo **leer** secretos.
- **Instance principal:** la forma en que el servidor demuestra quién es ante OCI. No requiere `~/.oci/config` ni claves `.pem` en el servidor.

**Sobre el costo:** usar el **Vault virtual** (el tipo por defecto) con una clave maestra **protegida por software**. El Private Vault y las claves HSM dedicadas tienen costo. Revisar los límites vigentes de Always Free antes de crear nada.

### Paso a paso (consola de OCI)

1. **Crear el Vault.** *Identidad y seguridad → Vault → Crear Vault*, en el compartimento del proyecto. Tipo por defecto (virtual).
2. **Crear la clave maestra.** Dentro del Vault, *Claves de cifrado maestras → Crear clave*. Modo de protección: **Software**; algoritmo AES.
3. **Crear los secretos.** Dentro del Vault, *Secretos → Crear secreto*:
   - Nombre: `communitylab-gemini-api-key` (y otro `communitylab-cohere-api-key`).
   - Clave de cifrado: la clave maestra del paso 2.
   - Tipo de plantilla: **texto sin formato** (*plain-text*); pega la clave **de producción**. La consola la guarda codificada en base64; el backend la decodifica.

   Es preferible hacerlo desde la consola y no por línea de comandos, para que la clave no quede en el historial de la terminal.
4. **Copiar el OCID del Vault** (en los detalles del Vault, empieza con `ocid1.vault.`). Va en `OCI_VAULT_ID`. No es una clave, pero tampoco hace falta publicarlo.
5. **Crear el grupo dinámico.** *Identidad → Grupos dinámicos → Crear*. Regla recomendada (solo esa instancia):

   ```
   ALL {instance.id = '<OCID de la instancia del backend>'}
   ```

   O, si habrá varias instancias, todas las del compartimento:

   ```
   ALL {instance.compartment.id = '<OCID del compartimento>'}
   ```
6. **Crear la política.** *Identidad → Políticas → Crear*, en el compartimento del Vault:

   ```
   allow dynamic-group <grupo> to read secret-family in compartment <compartimento>
   ```

   Solo permite **leer**: el servidor no puede crear, cambiar ni borrar secretos. En cuentas con *dominios de identidad*, el grupo se escribe con su dominio, por ejemplo `'Default'/'<grupo>'`. (Si además se usa Object Storage desde el servidor, ese permiso se agrega aparte: ver [object-storage-oci.md](object-storage-oci.md).)
7. **Configurar el backend en el servidor.** El `.env` del servidor **no lleva claves**, solo la configuración:

   ```
   SECRET_PROVIDER=oci
   OCI_VAULT_ID=ocid1.vault.oc1...
   OCI_AUTH=instance_principal
   OCI_REGION=<región del Vault, por ejemplo sa-saopaulo-1>
   LLM_PROVIDER=gemini
   # GEMINI_API_KEY y COHERE_API_KEY se dejan vacías: con SECRET_PROVIDER=oci no se usan
   ```

   El SDK `oci` ya está en `communitylab_backend/requirements.txt`.
8. **Comprobar.** Reinicia el backend y abre `GET /api/v1/status`: debe indicar `"secret_provider": "oci"` (nunca muestra valores). Procesa un lote con Gemini activo: si algo falla, la respuesta 503 explica qué revisar sin mostrar la clave.

### Mensajes de error y qué revisar

| Mensaje | Qué revisar |
|---|---|
| `Falta configurar OCI_VAULT_ID` | La variable `OCI_VAULT_ID` en el `.env` del servidor |
| `No se pudo iniciar la sesión con OCI para leer el Vault` | Que el backend corra en OCI Compute con `OCI_AUTH=instance_principal` (o que `~/.oci/config` sea válido con `OCI_AUTH=config`) |
| `OCI rechazó las credenciales o falta el permiso para leer el secreto ...` | Que la instancia cumpla la regla del grupo dinámico y que exista la política `read secret-family` en el compartimento correcto |
| `OCI Vault no tiene el secreto '...'` | El nombre del secreto y que esté en el Vault de `OCI_VAULT_ID` (variables `OCI_SECRET_GEMINI` / `OCI_SECRET_COHERE`) |
| `El secreto '...' de OCI Vault no tiene un texto válido` | Que el secreto se haya creado como texto sin formato |

### Probar desde una computadora (opcional)

Para verificar los secretos antes de tener el servidor, se puede usar el archivo de configuración de OCI de una persona con permiso de lectura:

```
SECRET_PROVIDER=oci
OCI_VAULT_ID=ocid1.vault.oc1...
OCI_AUTH=config
OCI_CONFIG_FILE=~/.oci/config
OCI_CONFIG_PROFILE=DEFAULT
```

## 3. Rotar (cambiar) una clave en producción

Conviene rotar las claves de vez en cuando y siempre que se sospeche una filtración.

1. Crea la **nueva clave** en Google AI Studio o en Cohere.
2. En OCI Vault, abre el secreto (por ejemplo `communitylab-gemini-api-key`) y elige **Crear versión del secreto** con el valor nuevo. La nueva versión pasa a ser la *actual*; el nombre del secreto no cambia, así que no hay que tocar ninguna variable.
3. **Reinicia el backend** (y el panel, si usa `FUENTE_SECRETOS=vault`). El backend pide cada secreto una sola vez y lo guarda en memoria: hasta reiniciar sigue usando la versión anterior.
4. Comprueba que funciona y **revoca la clave anterior** en Google o Cohere.

## 4. Cómo lo hace el código (para quien programa)

- El puerto `SecretProvider` (`domain/ports.py`) define `get(nombre)`. `OCIVaultSecretProvider` (`infrastructure/oci_vault.py`) lo implementa con `SecretsClient.get_secret_bundle_by_name(nombre_del_secreto, vault_id)` y decodifica el base64.
- `api/dependencies.py` llama a `get_api_key(settings, "GEMINI_API_KEY")` antes de construir Gemini o Cohere. Con `environment` devuelve el valor de `Settings`, exactamente como antes; con `oci` lo pide al Vault. El lector del Vault se crea una sola vez por proceso. Las herramientas `build_faq_index` y `search_faq` usan la misma función.
- Solo se pide una clave cuando el proveedor la necesita: con `LLM_PROVIDER=mock` y `RETRIEVAL_PROVIDER=faq_db` no se consulta el Vault.
- Los valores nunca se registran ni aparecen en errores ni en `repr`. Los errores de OCI se traducen a `ProviderUnavailableError` (HTTP 503) con mensajes que no copian el texto del SDK, porque puede traer identificadores de la cuenta.
- Pruebas: `tests/backend/test_oci_vault.py`, con un cliente falso (sin red ni cuenta de OCI).
