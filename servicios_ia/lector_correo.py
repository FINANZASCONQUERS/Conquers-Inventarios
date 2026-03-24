import imaplib
import email
from email.header import decode_header
import os

# Configuración del correo (¡Excelente que ya tengamos las credenciales!)
IMAP_SERVER = "outlook.office365.com"
EMAIL_ACCOUNT = "ops@conquerstrading.com"
EMAIL_PASSWORD = "Conquers2024."
CARPETA_OBJETIVO = "Transito" # Basado en la captura de pantalla

def conectar_correo():
    """
    Se conecta al servidor de Office 365 (Outlook) y selecciona la carpeta de tránsito.
    """
    try:
        # Conexión segura al servidor IMAP de Outlook
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
        print("✅ Conectado exitosamente al correo de Outlook.")
        
        # Seleccionamos la carpeta
        # NOTA: A veces Outlook llama a las carpetas con comillas, ej: '"Transito"'
        status, mensajes = mail.select(CARPETA_OBJETIVO)
        if status != 'OK':
            print(f"⚠️ No se encontró la carpeta: {CARPETA_OBJETIVO}. Intentando buscarla...")
            # Si falla, listamos las carpetas para ver cuál es el nombre real interno
            for i in mail.list()[1]:
                print(i.decode())
            return None
            
        print(f"📂 Carpeta '{CARPETA_OBJETIVO}' seleccionada. Mensajes totales: {mensajes[0].decode()}")
        return mail
        
    except Exception as e:
        print(f"❌ Error al conectar con el correo: {e}")
        return None

def descargar_adjuntos_recientes(mail, top_n=5):
    """
    Busca los últimos 'top_n' correos en la carpeta seleccionada 
    y descarga sus archivos Excel (.xls, .xlsx, .ods).
    """
    if not mail:
        return []
        
    archivos_descargados = []
    
    # Buscar todos los correos
    status, messages = mail.search(None, "ALL")
    if status != 'OK':
        return []
        
    # Obtener los IDs de los mensajes y tomar los últimos 'top_n'
    lista_ids = messages[0].split()
    ultimos_ids = lista_ids[-top_n:]
    
    # Crear carpeta temporal para guardar los excels descargados
    carpeta_temp = os.path.join(os.path.dirname(__file__), 'temp_archivos')
    os.makedirs(carpeta_temp, exist_ok=True)
    
    for email_id in reversed(ultimos_ids):
        # Obtener el correo por ID
        status, data = mail.fetch(email_id, "(RFC822)")
        
        for response_part in data:
            if isinstance(response_part, tuple):
                mensaje = email.message_from_bytes(response_part[1])
                
                # Decodificar el asunto para saber de qué correo estamos hablando
                asunto, encoding = decode_header(mensaje["Subject"])[0]
                if isinstance(asunto, bytes):
                    try:
                        asunto = asunto.decode(encoding or "utf-8")
                    except:
                        asunto = str(asunto)
                
                print(f"Tratando correo: {asunto}")
                
                # Buscar archivos adjuntos en el correo
                if mensaje.is_multipart():
                    for part in mensaje.walk():
                        if part.get_content_maintype() == 'multipart':
                            continue
                        if part.get('Content-Disposition') is None:
                            continue
                            
                        nombre_archivo = part.get_filename()
                        if nombre_archivo:
                            # Decodificar nombre del archivo si viene con caracteres raros
                            nombre_archivo, encoding = decode_header(nombre_archivo)[0]
                            if isinstance(nombre_archivo, bytes):
                                nombre_archivo = nombre_archivo.decode(encoding or "utf-8")
                            
                            # Solo queremos descargar Excel u ODS
                            if nombre_archivo.lower().endswith(('.xlsx', '.xls', '.ods')):
                                filepath = os.path.join(carpeta_temp, nombre_archivo)
                                # Guardar el archivo
                                with open(filepath, "wb") as f:
                                    f.write(part.get_payload(decode=True))
                                archivos_descargados.append(filepath)
                                print(f"  📥 Descargado: {nombre_archivo}")
                                
    return archivos_descargados

def cerrar_conexion(mail):
    if mail:
        mail.close()
        mail.logout()
        print("🔌 Conexión al correo cerrada.")

if __name__ == "__main__":
    # Prueba rápida: ¿Logramos conectarnos?
    conexion = conectar_correo()
    if conexion:
        cerrar_conexion(conexion)
