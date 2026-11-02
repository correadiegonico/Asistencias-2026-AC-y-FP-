import streamlit as st
import os
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import re

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="Gestor de Vouchers - Micros",
    page_icon="🚌",
    layout="wide"
)

# --- CONEXIÓN A GOOGLE DRIVE API ---
def get_drive_service():
    scopes = ['https://www.googleapis.com/auth/drive']
    if "gcp_service_account" in st.secrets:
        creds = service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"], scopes=scopes
        )
    else:
        st.error("No se encontraron las credenciales 'gcp_service_account' en st.secrets.")
        st.stop()
    return build('drive', 'v3', credentials=creds)

FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "1y91snFY_N25xoOaYlm6Fq-PWSjTzf7Gy")

# --- FUNCIONES DE GOOGLE DRIVE ---
def listar_archivos_drive():
    try:
        service = get_drive_service()
        query = f"'{FOLDER_ID}' in parents and trashed = false" if FOLDER_ID else "trashed = false"
        results = service.files().list(
            q=query,
            pageSize=1000,
            fields="nextPageToken, files(id, name, createdTime, mimeType)"
        ).execute()
        return results.get('files', [])
    except Exception as e:
        st.error(f"Error al consultar Google Drive: {e}")
        return []

def descargar_archivo_drive(file_id):
    try:
        service = get_drive_service()
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.seek(0)
        return fh.read()
    except Exception as e:
        st.error(f"Error al descargar desde Drive: {e}")
        return None

# --- INTERFAZ / LAYOUT DE STREAMLIT ---
st.title("🚌 Consulta y Descarga de Vouchers de Pasajeros")

# --- PANEL IZQUIERDO (SIDEBAR) ---
with st.sidebar:
    st.header("🔍 Filtros de Búsqueda")
    tipo_filtro = st.radio("Buscar por:", ["Número de Micro", "Fecha de Salida", "Ver Todos"])
    
    filtro_micro = ""
    filtro_fecha = None
    
    if tipo_filtro == "Número de Micro":
        filtro_micro = st.text_input("Ingresar N° de Coche / Micro:", placeholder="Ej: 16")
    elif tipo_filtro == "Fecha de Salida":
        filtro_fecha = st.date_input("Seleccionar Fecha:")

# --- ÁREA PRINCIPAL ---
st.subheader("📄 Vouchers Disponibles en Drive")

archivos_drive = listar_archivos_drive()

archivos_filtrados = []
for file in archivos_drive:
    nombre = file['name']
    if tipo_filtro == "Número de Micro" and filtro_micro.strip():
        num_buscado = filtro_micro.strip()
        # Patrón para asegurar que el número esté aislado por espacios o límites
        patron = rf'(?<!\d){re.escape(num_buscado)}(?!\d)'
        if re.search(patron, nombre):
            archivos_filtrados.append(file)
    elif tipo_filtro == "Fecha de Salida" and filtro_fecha:
        fecha_str = filtro_fecha.strftime("%Y-%m-%d")
        if nombre.startswith(fecha_str):
            archivos_filtrados.append(file)
    elif tipo_filtro == "Ver Todos":
        archivos_filtrados.append(file)

if not archivos_filtrados:
    st.info("No se encontraron vouchers con los criterios seleccionados.")
else:
    st.write(f"Se encontraron **{len(archivos_filtrados)}** archivo(s):")
    
    col_enc1, col_enc2 = st.columns([4, 2])
    col_enc1.write("**Nombre del Archivo**")
    col_enc2.write("**Acciones**")
    st.markdown("---")

    for f in archivos_filtrados:
        c1, c2 = st.columns([4, 2])
        c1.text(f["name"])
        
        pdf_bytes = descargar_archivo_drive(f["id"])
        if pdf_bytes:
            c2.download_button(
                label="📥 Descargar PDF",
                data=pdf_bytes,
                file_name=f["name"],
                mime="application/pdf",
                key=f"dl_{f['id']}"
            )
