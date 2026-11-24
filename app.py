import io
import re
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="Gestor de Vouchers - Micros",
    page_icon="🚌",
    layout="wide"
)

# --- CONEXIÓN A GOOGLE DRIVE API ---
def get_drive_service():
    scopes = ["https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" not in st.secrets:
        st.error("No se encontraron las credenciales 'gcp_service_account' en st.secrets.")
        st.stop()

    sa_info = dict(st.secrets["gcp_service_account"])
    if "private_key" in sa_info and isinstance(sa_info["private_key"], str):
        raw = sa_info["private_key"].replace("\\n", "\n").strip()
        match = re.search(
            r"-----BEGIN PRIVATE KEY-----(.*?)-----END PRIVATE KEY-----",
            raw,
            flags=re.DOTALL,
        )
        if match:
            cuerpo_limpio = re.sub(r"\s+", "", match.group(1))
            bloques = "\n".join(
                cuerpo_limpio[i : i + 64] for i in range(0, len(cuerpo_limpio), 64)
            )
            sa_info["private_key"] = (
                f"-----BEGIN PRIVATE KEY-----\n{bloques}\n-----END PRIVATE KEY-----\n"
            )

    creds = service_account.Credentials.from_service_account_info(
        sa_info, scopes=scopes
    )
    return build("drive", "v3", credentials=creds)

FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "1y91snFY_N25xoOaYlm6Fq-PWSjTzf7Gy")

# --- FUNCIONES DE GOOGLE DRIVE CON CACHÉ ---
@st.cache_data(ttl=300)
def listar_archivos_drive(folder_id):
    service = get_drive_service()
    query = (
        f"'{folder_id}' in parents and trashed = false"
        if folder_id
        else "trashed = false"
    )
    results = service.files().list(
        q=query,
        pageSize=1000,
        fields="nextPageToken, files(id, name, createdTime, mimeType)"
    ).execute()
    return results.get("files", [])

@st.cache_data(ttl=600)
def descargar_archivo_drive(file_id):
    service = get_drive_service()
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    return fh.read()

def solo_digitos(texto):
    return re.sub(r"\D", "", texto or "")

# --- INTERFAZ EN PÁGINA PRINCIPAL ---
st.title("🚌 Consulta y Descarga de Vouchers de Pasajeros")

col_input, col_btn = st.columns([3.2, 1])

with col_input:
    valor_busqueda = st.text_input(
        "Buscar por número de coche:",
        placeholder="Ej: 16"
    )

with col_btn:
    st.write("")
    st.write("")
    if st.button("🔄 Actualizar lista"):
        st.cache_data.clear()
        st.rerun()

st.divider()
st.subheader("📄 Resultados")

try:
    archivos_drive = listar_archivos_drive(FOLDER_ID)
except Exception as e:
    st.error(f"Error al consultar Google Drive: {e}")
    st.stop()

archivos_filtrados = []
termino = (valor_busqueda or "").strip()

if not termino:
    st.info("Ingresá un número de coche para buscar vouchers.")
else:
    num_buscado = solo_digitos(termino)
    if num_buscado:
        patron = rf"(?<!\d){re.escape(num_buscado)}(?!\d)"
        for file in archivos_drive:
            nombre = file.get("name", "")
            if re.search(patron, nombre):
                archivos_filtrados.append(file)

if termino and not archivos_filtrados:
    st.warning("No se encontraron vouchers para ese número de coche.")
elif archivos_filtrados:
    st.write(f"Se encontraron **{len(archivos_filtrados)}** archivo(s):")

    for f in archivos_filtrados:
        c1, c2 = st.columns([4, 1.5])
        c1.write(f"**{f['name']}**")

        pdf_bytes = descargar_archivo_drive(f["id"])
        if pdf_bytes:
            c2.download_button(
                label="📥 Descargar PDF",
                data=pdf_bytes,
                file_name=f["name"],
                mime="application/pdf",
                key=f"dl_{f['id']}"
            )
