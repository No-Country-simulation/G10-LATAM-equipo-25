# ---------------------------------------------------------------
# CommunityLab en Hugging Face Spaces (Docker)
#
# Este archivo es el UNICO que se sube al Space, junto con su README.md
# (ver docs/despliegue-hugging-face.md). El codigo se descarga de GitHub
# al construir: el motor y el panel de las ramas indicadas abajo.
# Las claves NUNCA van aqui: van en Settings -> Secrets del Space.
# ---------------------------------------------------------------
FROM python:3.13-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face ejecuta el contenedor con el usuario 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1
WORKDIR /home/user/app

# Rama de GitHub que se despliega: main tiene el motor y el panel juntos.
# Para probar otra rama antes de unirla, cambiar RAMA_MOTOR o RAMA_PANEL.
ARG REPO=No-Country-simulation/G10-LATAM-equipo-25
ARG RAMA_MOTOR=main
ARG RAMA_PANEL=main

# Si hay commits nuevos en GitHub, estas dos lineas obligan a descargar de nuevo
ADD https://api.github.com/repos/${REPO}/git/refs/heads/${RAMA_MOTOR} /tmp/version-motor.json
ADD https://api.github.com/repos/${REPO}/git/refs/heads/${RAMA_PANEL} /tmp/version-panel.json

RUN git clone --depth 1 --branch "${RAMA_MOTOR}" "https://github.com/${REPO}.git" motor \
    && git clone --depth 1 --branch "${RAMA_PANEL}" "https://github.com/${REPO}.git" panel \
    && sed -i 's/\r$//' motor/despliegue/huggingface/arrancar.sh

RUN pip install --no-cache-dir --user \
        -r motor/communitylab_backend/requirements.txt \
        -r panel/communitylab_ui/requirements.txt

# Configuracion por defecto del despliegue (se puede cambiar en Settings -> Variables)
ENV LLM_PROVIDER=gemini \
    GEMINI_MODEL=gemini-3.1-flash-lite \
    PROVIDER_TIMEOUT_SECONDS=120 \
    RETRIEVAL_PROVIDER=faq_db \
    STORAGE_PROVIDER=oci \
    STATE_PROVIDER=oci \
    SECRET_PROVIDER=oci \
    OCI_AUTH=config \
    FUENTE_SECRETOS=auto \
    BACKEND_URL=http://127.0.0.1:8000

EXPOSE 7860
CMD ["bash", "/home/user/app/motor/despliegue/huggingface/arrancar.sh"]
