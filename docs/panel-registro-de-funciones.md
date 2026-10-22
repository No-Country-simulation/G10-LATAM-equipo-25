# Registro de funciones del panel: para qué sirve cada una y por qué cambió

Este documento lista **cada función del panel que se agregó, cambió o quitó** respecto de la versión original de la rama `feature/ui-curaduria` (Sprint 1). Para cada una dice para qué sirve y por qué se tocó, en palabras simples.

- La historia completa de cada cambio, con su verificación, está en [integracion-con-backend.md](integracion-con-backend.md). Aquí "cambio 11" significa "ver el cambio 11 de ese documento".
- Dentro del código, cada función tiene su propia explicación (docstring).
- Las funciones que **no aparecen aquí** quedaron igual que en la versión original.

---

## 1. Cómo está organizado el panel

El panel está dividido para que **un cambio en el motor solo obligue a tocar un archivo**:

```
   Motor (backend)  ◀── HTTP ──  core/backend.py      (único que llama al motor)
                                       │
                                       ▼
                                 core/adaptador.py    (único que conoce los nombres de los datos del motor
                                       │               y los traduce a español)
                                       ▼
                         ui/app.py · ui/mui_blocks.py · ui/previas.py   (solo dibujan)
```

| Regla del equipo | ¿Se cumple? |
|---|---|
| Solo `core/backend.py` hace llamadas al motor | Sí |
| Si cambia un campo del motor, solo se toca `core/adaptador.py` | Sí. Desde el cambio 18, las vistas ya no leen ningún nombre del motor directamente |
| Las claves no aparecen en pantalla | Sí. La vista Configuración solo dice "Configurado" o "Falta" |
| Los datos personales no se muestran | Sí. El panel muestra el texto que el motor ya limpió (cambio 13) |
| Todo documentado en español | Sí. Cada módulo y función tiene su explicación |

---

## 2. `core/` (conexión y traducción)

### `core/backend.py` (nuevo, cambios 1, 14 a 17)

Único archivo que habla con el motor. Si el motor no responde, todas las funciones devuelven un mensaje claro ("Revisa que el backend esté encendido").

| Función | Para qué sirve |
|---|---|
| `url_backend` | Dirección del motor (de `BACKEND_URL`) |
| `_llamar` | Hace la llamada y traduce cualquier falla a un mensaje claro (`BackendNoDisponible`) |
| `estado` | Pregunta qué modelo, búsqueda y almacenamiento usa el motor |
| `procesar_lote` | Envía un lote de mensajes al motor |
| `guardar_curaduria` | Guarda lo que el equipo aprobó o rechazó |
| `resumen_base`, `faqs_base`, `resenas_base`, `buscar_faq` | Consultan la base de conocimiento (cambio 14) |
| `importar_faqs` | Agrega FAQs nuevas a la base (cambios 15 y 17) |
| `dudas_frecuentes` | Pide el ranking de dudas frecuentes (cambio 16) |

### `core/adaptador.py` (nuevo, cambios 2, 8, 13 a 18)

Traduce lo que responde el motor (en inglés) a lo que dibujan las vistas (en español).

| Función | Para qué sirve | Cambio |
|---|---|---|
| `armar_vista` | Junta todos los lotes de la sesión en una sola estructura para las vistas: resumen, mensajes, rutas, borradores y almacenamiento | 2, 8 y 16 |
| `_analisis_por_mensaje` | Une el análisis del motor con cada mensaje del lote | 8 |
| `rutas_de`, `resumen_respuesta` | Qué rutas activó el lote y la frase de "lote procesado" | 8 |
| `_es_pregunta`, `_faq_de` | Detectar dudas y separar pregunta y respuesta de una FAQ citada | 2 |
| `numero_activos`, `ubicacion`, `resumen_guardado`, `estado_motor`, `decision_backend`, `activo_para_guardar` | Traducen los datos que antes las vistas leían directo del motor: cuántos borradores hay, dónde se guardó, qué modelo usa y cómo se envía la curaduría | 18 |
| `vista_base`, `citas_en_sesion`, `resultados_busqueda`, `tabla_resenas`, `lote_desde_resenas` | Base de conocimiento: resumen, FAQs más citadas, buscador y reseñas reales convertidas en un lote | 14 |
| `resultado_importacion` (y `fila`) | Resultado de agregar FAQs: qué se agrega, qué ya existía y qué filas tienen errores | 15 |
| `ranking_dudas` (y `respaldo`) | Ranking de dudas frecuentes, con un texto que dice si cada tema tiene FAQ oficial | 16 |
| `motor_faq`, `_clave_tema` | Une, tema por tema, las dudas de la comunidad con el tutorial, el tip y la documentación | 17 |
| `briefing_de` | El resultado del lote con la estructura exacta del ejemplo del briefing | 17 |

### `core/ingesta.py` (nuevo, cambios 3 y 15)

| Función | Para qué sirve |
|---|---|
| `leer_archivo`, `lote_desde_dict`, `_limpiar` | Leer un lote propio (JSON o CSV) en español o en inglés |
| `lotes_ejemplo`, `leer_ejemplo` | Los lotes de ejemplo para la demo |
| `leer_respuesta_guardada` | Cargar una respuesta ya procesada (plan B si no hay motor) |
| `leer_faqs` | Leer un CSV o JSON con FAQs nuevas (cambio 15) |

### `core/secretos.py` (original, cambios 10 y 20)

| Función | Estado | Para qué sirve | Por qué cambió |
|---|---|---|---|
| `_leer_de_vault` | Cambiada | Lee un secreto de OCI Vault | En el Sprint 1 era un espacio vacío. Braulio (commit `50645d3`) y nosotros (cambio 10) lo implementamos en paralelo y se combinaron (cambio 20): queda nuestra versión, con mensajes por tipo de error y sin copiar identificadores de la cuenta |
| `_id_vault`, `_cliente_vault` | Nuevas | Obtienen la identificación del Vault (`OCI_VAULT_ID` u `OCI_VAULT_OCID`) y abren una sola conexión con OCI, con archivo de configuración o con la identidad del servidor | Necesarias para leer del Vault |
| `obtener_secreto`, `diagnostico` | Cambiadas | Devuelven un secreto (o el estado de todos) venga del `.env` o del Vault | Respetan la opción `auto` y usan `_fuente_activa` |
| `_fuente_activa` | Nueva (aporte de Braulio, commit `50645d3`) | Dice de dónde leer los secretos | Lee el `.env` antes de decidir; corrige que la primera consulta ignorara un `FUENTE_SECRETOS` escrito en el `.env` (cambio 20) |
| `CATALOGO_SECRETOS` | Cambiado | Lista de secretos del proyecto | Suma `BACKEND_URL` y, de Braulio, `COHERE_API_KEY` (cambios 10 y 20) |

---

## 3. `ui/` (pantallas)

### `ui/app.py` (original)

| Función | Estado | Para qué sirve | Cambio |
|---|---|---|---|
| `cargar_resultados` | **Quitada** | Leía un archivo de ejemplo fijo | La reemplaza la conexión real con el motor (cambio 2) |
| `init_estado`, `main`, `barra_lateral` | Cambiadas | Preparan la sesión, el menú y la sección elegida | Secciones nuevas y sesión recuperable (cambios 4, 14, 16 y 17) |
| `vista_procesar`, `procesar`, `agregar_corrida` | Nuevas | Enviar un lote al motor (ejemplo, archivo o texto pegado) y guardarlo en la sesión | 4 |
| `vista_resumen`, `vista_ingesta` | Cambiadas | Resumen de la comunidad y tabla de mensajes | Usan datos reales: rutas, relevancia y quién necesita apoyo (cambios 5, 9 y 12) |
| `vista_curaduria` | Cambiada | Bandeja de revisión: lista a la izquierda y el borrador abierto a la derecha | Rediseño como bandeja de trabajo (cambio 11) |
| `marcar`, `abrir`, `fila_bandeja`, `_md_seguro` | Cambiada / nuevas | Aprobar o rechazar y pasar al siguiente; moverse por la bandeja | 11 |
| `texto_actual`, `guardar_edicion`, `restaurar` | Nuevas | Editar un borrador sin perder los cambios y volver al original | 11 |
| `exportar_markdown`, `guardar_en_backend` | Nuevas | Descargar lo aprobado y guardar la curaduría en el motor | 11 y 18 |
| `vista_motor_faq`, `_tarjeta_tema`, `ir_a_curaduria` | Nuevas | La pantalla central del proyecto: cada duda frecuente convertida en tutorial, tip y documentación | 17 |
| `agregar_tutorial_a_base` | Nueva | Aprobar un tutorial y sumarlo a la base como FAQ oficial | 16 |
| `vista_semana`, `_bloque`, `_texto_html` | Nuevas | El resultado del lote con la estructura del briefing | 17 |
| `vista_base_conocimiento`, `agregar_faqs` | Nuevas | Ver la base y agregarle FAQs desde un archivo | 14 y 15 |
| `guardar_sesion`, `recuperar_sesion`, `oferta_recuperar`, `sin_datos` | Nuevas | No perder el trabajo si se recarga la página | 17 |
| `vista_config`, `banner` | Cambiada / nueva | Estado del motor y aviso de "modo local" o "sin conexión" | 5 y 18 |

### `ui/mui_blocks.py` (original, cambios 6, 9, 12 y 18)

| Función | Estado | Por qué cambió |
|---|---|---|
| `fila_metricas`, `barra_apilada_sentimiento`, `panel_temas`, `tabla_grupos`, `lista_mensajes` | Cambiadas | Muestran datos reales y se acomodan mejor en pantallas angostas (cambios 6, 9 y 12) |
| `cabecera_activo` | Cambiada | Íconos de los tipos nuevos y chip de tema (cambio 16) |
| `tarjeta_almacenamiento`, `tarjeta_origen` | Cambiadas | Muestran la configuración real del motor, ya traducida por el adaptador (cambios 5 y 18) |
| `tarjeta_secretos` | Cambiada | Dice qué secretos están configurados, nunca su valor (cambio 10) |
| `tabla_corridas`, `tabla_apoyo` | Nuevas | Qué rutas eligió el motor en cada lote y quién necesita apoyo (cambio 9) |

### `ui/previas.py` (nuevo, cambios 11 y 16)

Vistas previas de cada borrador con la forma de su canal, para que quien revisa vea cómo se publicaría.

| Función | Para qué sirve |
|---|---|
| `previa` | Elige la vista previa según el tipo de borrador |
| `_linkedin`, `_newsletter`, `_faq`, `_caso_exito` | Publicación de LinkedIn, sección de newsletter, entrada de FAQ e historia de éxito |
| `_tutorial`, `_tip`, `_documentacion` | Tutorial rápido, tip de la semana (como mensaje fijado de Discord) y propuesta de documentación (cambio 16) |
| `_respaldo` | Franja que dice si el contenido se apoya en una FAQ oficial |
| `fuente` | Los mensajes de la comunidad y las FAQs que originaron el borrador |
| `contador` | Avisa si el texto se pasa del largo recomendado del canal |
| `_texto`, `_hashtags` | Escapan el texto y resaltan los hashtags |

### `ui/theme.py` (original)

Solo contiene colores, la lista de secciones y estilos. Se agregaron las secciones nuevas y los estilos de la bandeja, las vistas previas y el Motor de FAQ (cambios 6, 11, 16 y 17).
