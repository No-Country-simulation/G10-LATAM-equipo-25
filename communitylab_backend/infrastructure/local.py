"""Adaptadores locales de la capa de infraestructura.

Sanitizan el texto, simulan el análisis y guardan borradores en una carpeta.
Ninguno llama a APIs: permiten ejecutar y demostrar el flujo completo sin
claves. La búsqueda de FAQs local vive en ``faq_database.py``.
"""

import json
import os
import re
import unicodedata
from dataclasses import replace
from pathlib import Path

from communitylab_backend.domain.errors import AssetGenerationError, InvalidInteractionError, StorageError
from communitylab_backend.domain.models import Analysis, ContentBrief, DraftAsset, Evidence, InteractionSignal, SanitizedInteraction
from communitylab_backend.infrastructure.pii import sanitize as existing_sanitize


def _plain(text: str | None) -> str:
    """Pasa ``text`` a minúsculas y sin tildes para comparar palabras clave."""
    decomposed = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _words(csv: str) -> tuple[str, ...]:
    """Convierte una lista separada por comas en palabras normalizadas."""
    return tuple(_plain(word.strip()) for word in csv.split(",") if word.strip())


def _mentions(text: str, words: tuple[str, ...]) -> bool:
    """Indica si ``text`` (ya normalizado) contiene alguna de ``words``.

    Las palabras deben empezar donde empieza una palabra del texto, para que
    "como" no coincida dentro de "economía". Los signos (como ``?``) se buscan
    en cualquier posición. No tiene efectos secundarios.
    """
    return any(re.search(rf"(?<![a-z0-9]){re.escape(word)}", text) if word[:1].isalnum() else word in text for word in words)


class InteractionRules:
    """Clasifica una interacción con reglas locales, sin llamar a ningún modelo.

    Pertenece a infraestructura. Calcula para cada mensaje su sentimiento, su
    categoría (``logro``, ``duda``, ``apoyo`` o ``comentario``), si la persona
    necesita apoyo y una relevancia de 0 a 1. La usa ``MockLLMProvider`` y,
    como respaldo, ``GeminiLLMAdapter`` cuando Gemini omite algún mensaje.
    """

    POSITIVE = ("gracias", "agradec", "logre", "consegui", "excelente", "felic", "feliz", "seleccionad", "contratad", "orgullo", "genial", "muy bien", "encanta", "success")
    NEGATIVE = ("error", "problema", "fallo", "falla", "no puedo", "no funciona", "frustr", "atorad", "help")
    # El sentimiento del LOTE en modo local conserva sus listas originales (MockLLMProvider.POSITIVE / NEGATIVE).
    FRUSTRATION = ("frustr", "no puedo", "no funciona", "no me funciona", "atorad", "atascad", "me cuesta", "no entiendo", "no me quedo claro", "bloquead", "estancad", "desmotiv", "sigo sin")
    BASE_RELEVANCE = {"logro": 0.85, "duda": 0.7, "apoyo": 0.65, "comentario": 0.4}

    def __init__(self, success_keywords: str = "conseguí trabajo,quedé seleccionad,me contrataron,logré,certifiqué,gradué,success,got a job", faq_keywords: str = "cómo,como,how,ayuda,error,problema,help,?", success_types: str = "testimonial,testimonio,logro", faq_types: str = "question,pregunta,pregunta_tecnica,duda"):
        """Configura palabras clave y tipos declarados de logro y de duda.

        Recibe listas separadas por comas; los valores por defecto son los de
        ``Settings``. No lee archivos ni servicios.
        """
        self.success_keywords = _words(success_keywords)
        self.faq_keywords = _words(faq_keywords)
        self.success_types = _words(success_types)
        self.faq_types = _words(faq_types)

    def is_success(self, item: SanitizedInteraction) -> bool:
        """Indica si ``item`` cuenta un logro, por su tipo declarado o por sus palabras."""
        return _plain(item.type) in self.success_types or _mentions(_plain(item.text_sanitized), self.success_keywords)

    def is_question(self, item: SanitizedInteraction) -> bool:
        """Indica si ``item`` parece una duda, por su tipo, sus palabras o un signo de pregunta."""
        return _plain(item.type) in self.faq_types or _mentions(_plain(item.text_sanitized), self.faq_keywords)

    def signal(self, item: SanitizedInteraction) -> InteractionSignal:
        """Calcula la ``InteractionSignal`` de una interacción sanitizada.

        La categoría sigue la prioridad logro > duda > apoyo > comentario.
        La relevancia parte de un valor por categoría y se ajusta por el largo
        del texto (los mensajes muy cortos aportan menos contexto). Una duda,
        un pedido de apoyo o un mensaje negativo marcan ``needs_support``.
        """
        text = f" {_plain(item.text_sanitized)} "
        positive = _mentions(text, self.POSITIVE)
        negative = _mentions(text, self.NEGATIVE) or _mentions(text, self.FRUSTRATION)
        sentiment = "mixed" if positive and negative else "positive" if positive else "negative" if negative else "neutral"
        category = "logro" if self.is_success(item) else "duda" if self.is_question(item) else "apoyo" if _mentions(text, self.FRUSTRATION) else "comentario"
        relevance = self.BASE_RELEVANCE[category] + 0.15 * min(len(item.text_sanitized), 400) / 400 - 0.05
        needs_support = category in {"duda", "apoyo"} or sentiment == "negative"
        return InteractionSignal(item.id, sentiment, category, round(min(max(relevance, 0.0), 1.0), 2), needs_support)


def _answer_from(evidence: Evidence) -> tuple[str, str]:
    """Separa la pregunta y la respuesta de una cita de FAQ.

    Las citas de FAQ tienen el formato ``Pregunta: ...`` y ``Respuesta: ...``.
    Si la cita no sigue ese formato, retorna su texto completo como respuesta.
    """
    question, _, answer = evidence.snippet.partition("\nRespuesta:")
    if not answer:
        return "", evidence.snippet.strip()
    return question.replace("Pregunta:", "", 1).strip(), answer.strip()


class ExistingSanitizerAdapter:
    """Adapta las reglas de datos personales al puerto de sanitización.

    Pertenece a infraestructura. Usa ``infrastructure.pii``; no conserva el
    texto original ni llama a proveedores externos.
    """

    def sanitize(self, interaction_id: str, text: str, channel: str | None, kind: str | None) -> SanitizedInteraction:
        """Recibe ID, texto, canal y tipo; devuelve la interacción segura.

        Sustituye correos, teléfonos, enlaces, IPs y menciones por etiquetas.
        Produce ``InvalidInteractionError`` si ``text`` está vacío.
        """
        if not text.strip():
            raise InvalidInteractionError("El texto de la interacción no puede estar vacío")
        safe, _ = existing_sanitize(text.strip(), {key: True for key in ("email", "phone", "url", "ip", "user")})
        return SanitizedInteraction(interaction_id, safe, channel, kind)


class MockLLMProvider:
    """Simula el puerto LLM con reglas locales y resultados reproducibles.

    Pertenece a infraestructura. Permite demostrar el flujo sin credenciales.
    Sus señales salen de palabras clave y sus borradores sólo reutilizan el
    texto de la comunidad y las respuestas de la FAQ oficial: no redacta como
    un modelo real. Con ``LLM_PROVIDER=gemini`` el mismo flujo usa Gemini.
    """

    name = "mock"
    POSITIVE = ("gracias", "agradec", "logre", "consegui", "excelente", "felic", "seleccionad", "contratad", "orgullo", "genial", "success")
    NEGATIVE = ("error", "problema", "fallo", "falla", "no puedo", "no funciona", "frustr", "atorad", "help")
    TOPICS = {
        "Empleo y logros": ("trabajo", "empleo", "puesto", "contrat", "seleccionad", "job"),
        "Certificación": ("certificacion", "certifique", "examen", "exam"),
        "Machine learning": ("machine learning", "aprendizaje", "modelo", "sobreajuste", "overfitting", "dropout", "regulariz", "red neuronal", "neural", "dataset", "clustering", "clasificacion", "regresion", "supervisado"),
        "IA generativa y LangGraph": ("langgraph", "langchain", "llm", "prompt", "gemini", " ia "),
        "Datos y Python": ("python", "pandas", "datos", "faltantes", "nulos", "missing", "preprocesamiento", "sql", "notebook"),
        "Oracle Cloud (OCI)": ("oci", "oracle", "bucket"),
        "Comunidad": ("comunidad", "community", "grupo", "evento"),
        "Plataformas y calidad del curso": ("watson", "skills network", "platform", "plataforma", "peer", "rating", "quiz", "trainer", "videos"),
    }

    def __init__(self, success_keywords: str = "conseguí trabajo,logré,certifiqué,got a job", faq_keywords: str = "cómo,como,error,problema,help,?", success_types: str = "testimonial", faq_types: str = "question"):
        """Configura palabras de éxito, de FAQ y tipos declarados de cada ruta.

        Recibe listas separadas por comas. No lee servicios ni archivos;
        estas reglas sólo determinan señales para la demo local.
        """
        self.rules = InteractionRules(success_keywords, faq_keywords, success_types, faq_types)

    def _is_question(self, item: SanitizedInteraction) -> bool:
        """Indica si ``item`` parece una duda, por su tipo o por sus palabras."""
        return self.rules.is_question(item)

    def _topics(self, interactions: list[SanitizedInteraction]) -> list[str]:
        """Retorna hasta 5 temas de ``interactions`` según ``TOPICS``, o ``["General"]``."""
        text = f" {' '.join(_plain(item.text_sanitized) for item in interactions)} "
        return ([name for name, words in self.TOPICS.items() if any(word in text for word in words)] or ["General"])[:5]

    def analyze(self, interactions: list[SanitizedInteraction], known_topics: list[str] | None = None) -> Analysis:
        """Deriva sentimiento, temas y señales del lote sanitizado.

        ``interactions`` debe contener texto seguro. Retorna ``Analysis``
        determinista con una ``InteractionSignal`` por mensaje, calculada con
        ``InteractionRules``; el tema de cada mensaje sale de ``TOPICS``.
        ``known_topics`` no se usa: los nombres de ``TOPICS`` ya son estables
        entre lotes. No realiza inferencia real ni llamadas externas.
        """
        text = f" {' '.join(_plain(item.text_sanitized) for item in interactions)} "
        positive = any(word in text for word in self.POSITIVE)
        negative = any(word in text for word in self.NEGATIVE)
        sentiment = "mixed" if positive and negative else "positive" if positive else "negative" if negative else "neutral"
        signals = [replace(self.rules.signal(item), topic=self._topics([item])[0]) for item in interactions]
        story = any(signal.category == "logro" for signal in signals)
        questions = [signal for signal in signals if signal.category == "duda"]
        support = [signal for signal in signals if signal.needs_support]
        insights = []
        if story:
            insights.append("Posible historia de éxito para validar con la persona")
        if questions:
            insights.append(f"{len(questions)} duda(s) que pueden convertirse en FAQ")
        if support:
            insights.append(f"{len(support)} persona(s) podrían necesitar apoyo o mentoría")
        return Analysis(sentiment, self._topics(interactions), insights or ["Actividad general de la comunidad"], story, bool(questions), signals)

    def generate_assets(self, briefs: list[ContentBrief], analysis: Analysis) -> list[DraftAsset]:
        """Redacta los activos de todos los ``briefs`` con las reglas locales.

        Los encargos de la rama ``faq`` (uno por tema) producen el tutorial
        rápido, el tip de la semana y el tema de documentación con
        ``_educational``. Los demás se arman como en ``generate``, con sus
        propias interacciones y temas. Un activo se identifica por tipo y
        tema. Retorna ``DraftAsset`` en estado ``draft``; produce
        ``AssetGenerationError`` si un encargo no trae interacciones.
        """
        found: dict[tuple[str, str | None], DraftAsset] = {}
        for brief in briefs:
            if not brief.interactions:
                raise AssetGenerationError("Un encargo de contenido llegó sin interacciones")
            if brief.flow == "faq":
                assets = self._educational(brief)
            else:
                assets = self.generate(brief.flow, replace(analysis, topics=self._topics(brief.interactions)), brief.interactions, brief.evidence)
            for asset in assets:
                if asset.kind in brief.kinds and (asset.kind, asset.topic) not in found:
                    found[(asset.kind, asset.topic)] = asset
        return list(found.values())

    def _educational(self, brief: ContentBrief) -> list[DraftAsset]:
        """Arma el tutorial rápido, el tip de la semana y el tema de documentación de un tema.

        Si hay FAQ oficial, el tutorial convierte su respuesta en pasos y el
        tip toma su primera idea. Si no la hay, deja un esqueleto para que un
        mentor lo complete y lo dice claramente. En modo local la respuesta
        oficial queda en inglés, como está en la base; Gemini la redacta en
        español.
        """
        topic = brief.topic or "General"
        questions = brief.interactions
        first = questions[0].text_sanitized[:220]
        ids = [item.record_id for item in brief.evidence[:1]]
        if brief.evidence:
            official, answer = _answer_from(brief.evidence[0])
            ideas = [part.strip() for part in re.split(r"(?<=[.!?])\s+", answer) if part.strip()][:4] or [answer]
            steps = "\n".join(f"{number}. {idea}" for number, idea in enumerate(ideas, 1))
            tutorial = f"Duda de la comunidad: «{first}»\n\nPaso a paso (según la FAQ oficial «{official}»):\n{steps}\n\nPara practicar: aplica estos pasos en tu proyecto y comparte el resultado en el canal."
            tip = f"Tip de la semana · {topic}: {ideas[0]}"
            source = f"FAQ oficial {ids[0]} («{official}»)"
        else:
            tutorial = (f"Duda de la comunidad: «{first}»\n\nTodavía no hay una FAQ oficial sobre este tema. Esqueleto para que un mentor lo complete:\n"
                        "1. Explicar la idea principal en una frase.\n2. Mostrar un ejemplo mínimo.\n3. Señalar el error más común.\n4. Enlazar el material del curso.")
            tip = f"Tip de la semana · {topic}: si te trabas con este tema, compártelo en el canal; {len(questions)} persona(s) preguntaron lo mismo."
            source = "sin FAQ oficial: hay que crear contenido nuevo"
        examples = "\n".join(f"   • {item.text_sanitized[:140]}" for item in questions[:3])
        doc = (f"Por qué hace falta: {len(questions)} duda(s) de la comunidad sobre «{topic}».\nRespaldo: {source}.\n\nSecciones propuestas:\n"
               f"1. Qué es y cuándo aparece.\n2. Paso a paso con un ejemplo.\n3. Errores frecuentes.\n4. Preguntas reales de la comunidad:\n{examples}")
        return [
            DraftAsset("quick_tutorial", f"Tutorial rápido: {topic}"[:150], tutorial, evidence_ids=ids, topic=topic),
            DraftAsset("weekly_tip", f"Tip de la semana: {topic}"[:150], tip[:280], evidence_ids=ids, topic=topic),
            DraftAsset("doc_topic", f"Tema de documentación: {topic}"[:150], doc, evidence_ids=ids, topic=topic),
        ]

    def generate(self, flow: str, analysis: Analysis, interactions: list[SanitizedInteraction], evidence: list[Evidence]) -> list[DraftAsset]:
        """Crea los dos borradores de la ruta seleccionada.

        Recibe ``flow``, señales, interacciones sanitizadas y citas. En la ruta
        FAQ usa la respuesta de la FAQ oficial mejor puntuada; si no hay
        citas, deja la respuesta pendiente de revisión humana. Retorna
        ``DraftAsset`` en estado ``draft``; no guarda ni publica contenido.
        """
        references = [item.record_id for item in evidence]
        topic = ", ".join(analysis.topics)
        if flow == "faq":
            return self._faq(analysis, interactions, evidence, topic)
        if flow == "success_story":
            story = next((item for item in interactions if _plain(item.type) in self.rules.success_types), interactions[0])
            excerpt = story.text_sanitized[:400]
            return [
                DraftAsset("success_story", "Historia de éxito de la comunidad", f"Borrador para validar con la persona antes de publicar:\n\n\"{excerpt}\"\n\nTemas: {topic}.", evidence_ids=references),
                DraftAsset("linkedin_post", "De la comunidad al mercado", f"¡Nada nos da más orgullo que ver a nuestra comunidad avanzar! 🚀\n\n\"{excerpt[:280]}\"\n\nHistorias como esta muestran que construir proyectos reales impulsa la carrera tech. 👏\n\n#ComunidadTech #InteligenciaArtificial #OracleCloud", evidence_ids=references),
            ]
        excerpt = interactions[0].text_sanitized[:240]
        return [
            DraftAsset("linkedin_post", "Novedades de la comunidad", f"Esta semana la comunidad conversó sobre {topic}.\n\n\"{excerpt}\"\n\n#ComunidadTech #Aprendizaje", evidence_ids=references),
            DraftAsset("newsletter_highlight", "Resumen de la comunidad", f"Lo más comentado: {topic}. {len(interactions)} interacciones analizadas. Destacado: \"{excerpt}\"", evidence_ids=references),
        ]

    def _faq(self, analysis: Analysis, interactions: list[SanitizedInteraction], evidence: list[Evidence], topic: str) -> list[DraftAsset]:
        """Arma el contenido de FAQ y el destacado de newsletter de la ruta FAQ.

        Sólo cita la evidencia recibida: la respuesta sale de la FAQ oficial
        de ``motor_educativo.db``, que está en inglés. Gemini la redacta en
        español cuando está activo.
        """
        questions = [item for item in interactions if self._is_question(item)] or interactions[:1]
        asked = "\n".join(f"• {item.text_sanitized[:300]}" for item in questions)
        if evidence:
            best = evidence[0]
            official_question, answer = _answer_from(best)
            body = f"Dudas de la comunidad:\n{asked}\n\nRespuesta sugerida (FAQ oficial: \"{official_question}\"):\n{answer}"
            related = [_answer_from(item)[0] for item in evidence[1:3] if _answer_from(item)[0]]
            if related:
                body += "\n\nFAQs relacionadas: " + "; ".join(related)
            title = f"FAQ: {official_question}" if official_question else "Pregunta frecuente de la semana"
            ids = [item.record_id for item in evidence[:3]]
        else:
            body = f"Dudas de la comunidad:\n{asked}\n\nRespuesta pendiente de revisión humana con evidencia."
            title, ids = f"Duda de la semana: {topic}", []
        newsletter = f"Tip de la semana sobre {topic}: {len(questions)} persona(s) preguntaron por este tema. " + ("Preparamos una respuesta basada en la FAQ oficial del curso." if evidence else "El equipo de mentores preparará la respuesta.")
        return [DraftAsset("faq_content", title[:150], body, evidence_ids=ids), DraftAsset("newsletter_highlight", "Dudas de la semana", newsletter, evidence_ids=ids)]


class MockRetriever:
    """Recuperador vacío para probar el flujo sin ninguna fuente de FAQs.

    Implementa ``RetrieverPort`` en infraestructura; no fabrica evidencia.
    """

    def retrieve(self, query: str, limit: int = 5) -> list[Evidence]:
        """Recibe consulta segura y límite; devuelve una lista vacía.

        No tiene efectos secundarios ni dependencias externas.
        """
        return []


class LocalObjectStorageAdapter:
    """Guarda paquetes JSON sanitizados en un directorio local.

    Implementa ``ObjectStoragePort`` en infraestructura. Escribe mediante
    un archivo temporal para evitar paquetes incompletos; no publica assets.
    """

    provider = "local"

    def __init__(self, directory: Path):
        """Recibe el directorio ``directory`` destinado a borradores locales.

        La creación del directorio se difiere hasta ``save``.
        """
        self.directory = Path(directory)

    def save(self, request_id: str, package: dict) -> str:
        """Guarda ``package`` con el nombre ``request_id`` y retorna la ruta.

        Crea el directorio y reemplaza atómicamente el destino. Puede
        producir ``StorageError`` ante un fallo del sistema de archivos.
        """
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            destination = self.directory / f"{request_id}.json"
            temporary = self.directory / f"{request_id}.tmp"
            temporary.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, destination)
            return destination.as_posix()
        except OSError as exc:
            raise StorageError("No se pudo guardar el paquete local de borradores") from exc


class EnvironmentSecretProvider:
    """Implementa el puerto de secretos mediante variables de entorno.

    Pertenece a infraestructura. Lee bajo demanda; no guarda ni registra
    el valor y permite reemplazo posterior por OCI Vault.
    """

    def get(self, name: str) -> str | None:
        """Busca ``name`` en el entorno y devuelve el valor o ``None``.

        No tiene efectos secundarios y no imprime el secreto.
        """
        return os.environ.get(name)
