import io
import re
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from pypdf import PdfReader

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

@st.cache_data(ttl=600)
def extraer_texto_pdf(file_id):
    pdf_bytes = descargar_archivo_drive(file_id)
    if not pdf_bytes:
        return ""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        paginas = [page.extract_text() or "" for page in reader.pages]
        # Normaliza espacios múltiples para facilitar coincidencias
        return re.sub(r"\s+", " ", " ".join(paginas))
    except Exception:
        return ""

def solo_digitos(texto):
    return re.sub(r"\D", "", texto or "")

# --- INTERFAZ EN PÁGINA PRINCIPAL ---
st.title("🚌 Consulta y Descarga de Vouchers de Pasajeros")

col_modo, col_input = st.columns([1.4, 2.6])

with col_modo:
    modo_busqueda = st.radio(
        "Buscar por:",
        ["Número de coche", "DNI pax"],
        horizontal=True
    )

with col_input:
    if modo_busqueda == "Número de coche":
        valor_busqueda = st.text_input(
            "Ingresar N° de coche:",
            placeholder="Ej: 16"
        )
    else:
        valor_busqueda = st.text_input(
            "Ingresar DNI del pasajero:",
            placeholder="Ej: 35123456 o 35.123.456"
        )

if st.button("🔄 Actualizar lista de Drive"):
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

if modo_busqueda == "Número de coche":
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

elif modo_busqueda == "DNI pax":
    dni_limpio = solo_digitos(termino)
    if len(dni_limpio) < 6:
        st.info("Ingresá al menos 6 dígitos del DNI para buscar dentro de los PDFs.")
    else:
        patron_dni = rf"(?<!\d){re.escape(dni_limpio)}(?!\d)"
        with st.spinner("Buscando el DNI dentro de los PDFs..."):
            for file in archivos_drive:
                nombre = file.get("name", "")
                if not nombre.lower().endswith(".pdf") and file.get("mimeType") != "application/pdf":
                    continue
                texto_pdf = extraer_texto_pdf(file["id"])
                # Quita puntos/espacios entre dígitos del texto para detectar 35.123.456 o 35123456
                texto_sin_puntos = re.sub(r"(?<=\d)[.\s-]+(?=\d)", "", texto_pdf)
                if re.search(patron_dni, texto_sin_puntos):
                    archivos_filtrados.append(file)

if termino and not archivos_filtrados and (
    modo_busqueda == "Número de coche" or len(solo_digitos(termino)) >= 6
):
    st.warning("No se encontraron vouchers con ese criterio.")
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
