#!/usr/bin/env bash
# ---------------------------------------------------------------
# Arranca CommunityLab dentro del contenedor de Hugging Face Spaces.
#
# 1. Arma el archivo de configuracion de OCI con los secretos del Space.
# 2. Enciende el motor (FastAPI) SOLO hacia adentro: 127.0.0.1:8000.
# 3. Enciende el panel (Streamlit) hacia afuera: puerto 7860.
# 4. Si cualquiera de los dos se cae, se cae el contenedor y
#    Hugging Face lo reinicia.
# Nunca imprime el valor de un secreto.
# ---------------------------------------------------------------
set -euo pipefail

# --- 1. Credenciales de OCI (Settings -> Secrets del Space) ---
if [ -n "${OCI_PRIVATE_KEY:-}${OCI_PRIVATE_KEY_B64:-}" ]; then
    mkdir -p "$HOME/.oci"
    chmod 700 "$HOME/.oci"
    umask 077
    if [ -n "${OCI_PRIVATE_KEY_B64:-}" ]; then
        printf '%s' "$OCI_PRIVATE_KEY_B64" | base64 -d > "$HOME/.oci/oci_api_key.pem"
    else
        printf '%s\n' "$OCI_PRIVATE_KEY" > "$HOME/.oci/oci_api_key.pem"
    fi
    cat > "$HOME/.oci/config" <<EOF
[DEFAULT]
user=${OCI_USER_OCID:?Falta el secreto OCI_USER_OCID}
fingerprint=${OCI_FINGERPRINT:?Falta el secreto OCI_FINGERPRINT}
tenancy=${OCI_TENANCY_OCID:?Falta el secreto OCI_TENANCY_OCID}
region=${OCI_REGION:?Falta la variable OCI_REGION}
key_file=$HOME/.oci/oci_api_key.pem
EOF
    # Vault en otra cuenta de OCI (opcional): segundo perfil con sus propios secretos
    if [ -n "${OCI_VAULT_PRIVATE_KEY:-}${OCI_VAULT_PRIVATE_KEY_B64:-}" ]; then
        if [ -n "${OCI_VAULT_PRIVATE_KEY_B64:-}" ]; then
            printf '%s' "$OCI_VAULT_PRIVATE_KEY_B64" | base64 -d > "$HOME/.oci/oci_vault_key.pem"
        else
            printf '%s\n' "$OCI_VAULT_PRIVATE_KEY" > "$HOME/.oci/oci_vault_key.pem"
        fi
        cat >> "$HOME/.oci/config" <<EOF

[VAULT]
user=${OCI_VAULT_USER_OCID:?Falta el secreto OCI_VAULT_USER_OCID}
fingerprint=${OCI_VAULT_FINGERPRINT:?Falta el secreto OCI_VAULT_FINGERPRINT}
tenancy=${OCI_VAULT_TENANCY_OCID:?Falta el secreto OCI_VAULT_TENANCY_OCID}
region=${OCI_VAULT_REGION:?Falta la variable OCI_VAULT_REGION}
key_file=$HOME/.oci/oci_vault_key.pem
EOF
        export OCI_VAULT_CONFIG_PROFILE=VAULT
        echo "[arranque] Perfil VAULT de OCI listo"
    fi
    umask 022
    echo "[arranque] Configuracion de OCI lista"
else
    echo "[arranque] AVISO: no hay OCI_PRIVATE_KEY; OCI no va a funcionar"
fi

# --- 2. Motor, solo hacia adentro ---
cd "$HOME/app/motor"
python -m uvicorn communitylab_backend.main:app --host 127.0.0.1 --port 8000 &

# Espera hasta 90 segundos a que el motor responda (al arrancar baja su memoria de OCI)
for _ in $(seq 90); do
    if python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)" 2>/dev/null; then
        echo "[arranque] Motor listo"
        break
    fi
    sleep 1
done

# --- 3. Panel, hacia afuera ---
# enableXsrfProtection=false: sin esto, subir archivos falla detras del proxy de
# Hugging Face. El panel queda protegido con PANEL_PASSWORD.
cd "$HOME/app/panel/communitylab_ui"
python -m streamlit run ui/app.py \
    --server.port 7860 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --server.enableXsrfProtection false \
    --browser.gatherUsageStats false &

# --- 4. Si uno de los dos termina, se termina todo ---
wait -n
echo "[arranque] Un proceso termino; se reinicia el contenedor"
exit 1
