import json
from datetime import datetime, time, date, timedelta 
import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file # Añadido send_file
from werkzeug.security import generate_password_hash, check_password_hash
import openpyxl # Para Excel - Recuerda: pip install openpyxl
from io import BytesIO # Para Excel
import logging # Para un logging más flexible
import copy
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
import pytz

def formatear_info_actualizacion(fecha_dt_utc, usuario_str):
    """
    Formatea la fecha y el usuario, convirtiendo la hora de UTC a la de Bogotá.
    Esta versión es robusta y maneja correctamente las zonas horarias.
    """
    try:
        if not fecha_dt_utc or not usuario_str:
            return "Información no disponible."

        # Define la zona horaria de Bogotá
        bogota_zone = pytz.timezone('America/Bogota')

        # Comprobación de seguridad: Si la fecha no tiene zona horaria (es "naive"),
        # le asignamos UTC. Si ya la tiene, no hacemos nada.
        if fecha_dt_utc.tzinfo is None:
            fecha_dt_utc = pytz.utc.localize(fecha_dt_utc)

        # Ahora que estamos seguros de que es una fecha en UTC, la convertimos a la zona de Bogotá
        dt_obj_bogota = fecha_dt_utc.astimezone(bogota_zone)

        # Formateamos el texto final para mostrarlo
        meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        nombre_mes = meses[dt_obj_bogota.month - 1]
        
        fecha_formateada = dt_obj_bogota.strftime(f"%d de {nombre_mes} de %Y")
        hora_formateada = dt_obj_bogota.strftime("%I:%M %p")

        mensaje = f"Última actualización guardada por {usuario_str} el {fecha_formateada} a las {hora_formateada}"
        return mensaje

    except Exception as e:
        print(f"Error al formatear fecha: {e}")
        return "Fecha de registro con error de formato."

app = Flask(__name__)
app.secret_key = 'clave_secreta_para_produccion_cambiar'


app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///local_test.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app) # <--- ESTA LÍNEA ES LA QUE CREA LA VARIABLE 'db'

class RegistroPlanta(db.Model):
    __tablename__ = 'registros_planta'

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    usuario = db.Column(db.String(100), nullable=False)
    
    tk = db.Column(db.String(50))
    producto = db.Column(db.String(100))
    max_cap = db.Column(db.Float)
    bls_60 = db.Column(db.Float)
    api = db.Column(db.Float)
    bsw = db.Column(db.Float)
    s = db.Column(db.Float)

    def __repr__(self):
        return f'<RegistroPlanta ID: {self.id}, TK: {self.tk}>'
    
class RegistroBarcazaOrion(db.Model):
    __tablename__ = 'registros_barcaza_orion' # Nombre de la nueva tabla

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    usuario = db.Column(db.String(100), nullable=False)
    
    # Columnas específicas de la planilla Orion
    tk = db.Column(db.String(50))
    producto = db.Column(db.String(100))
    max_cap = db.Column(db.Float)
    bls_60 = db.Column(db.Float)
    api = db.Column(db.Float)
    bsw = db.Column(db.Float)
    s = db.Column(db.Float)
    grupo = db.Column(db.String(50)) # Columna especial para Orion

    def __repr__(self):
        return f'<RegistroBarcazaOrion ID: {self.id}, TK: {self.tk}>'
class RegistroBarcazaBita(db.Model):
    __tablename__ = 'registros_barcaza_bita' # Nombre de la nueva tabla

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    usuario = db.Column(db.String(100), nullable=False)
    
    # Columnas de la planilla BITA
    tk = db.Column(db.String(50))
    producto = db.Column(db.String(100))
    max_cap = db.Column(db.Float)
    bls_60 = db.Column(db.Float)
    api = db.Column(db.Float)
    bsw = db.Column(db.Float)
    s = db.Column(db.Float)

    def __repr__(self):
        return f'<RegistroBarcazaBita ID: {self.id}, TK: {self.tk}>'

class RegistroTransito(db.Model):
    __tablename__ = 'registros_transito'

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    usuario = db.Column(db.String(100), nullable=False)
    
    # Columna para saber si es 'general' (EDSM) o 'refineria'
    tipo_transito = db.Column(db.String(50), nullable=False)

    # El resto de las columnas de tu planilla
    origen = db.Column(db.String(100))
    fecha = db.Column(db.String(50)) # Guardamos la fecha del cargue como texto
    guia = db.Column(db.String(100))
    producto = db.Column(db.String(100))
    placa = db.Column(db.String(50))
    api = db.Column(db.Float)
    bsw = db.Column(db.Float)
    nsv = db.Column(db.Float)
    observaciones = db.Column(db.Text)

    def __repr__(self):
        return f'<RegistroTransito ID: {self.id}, Guia: {self.guia}>'
    

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

@app.context_processor
def inject_current_year():
    return {'current_year': datetime.now().year}

# Decorador para verificar login (mejorado para AJAX)
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'email' not in session:
            # Si la petición espera JSON (como fetch), devuelve un error JSON y un código 401
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or \
               (request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json'):
                return jsonify(success=False, message="Sesión expirada o no autenticado. Por favor, inicie sesión de nuevo.", error_code="SESSION_EXPIRED"), 401
            
            flash('Por favor inicie sesión para acceder a esta página.', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@app.before_request
def log_request():
    print(f"➞️  {request.method} {request.path}")

USUARIOS = {
    # Carlos (Admin): Tiene acceso a todo.
    "oci@conquerstrading.com": {
        "password": generate_password_hash("Conquers2025"),
        "nombre": "Carlos Barón",
        "rol": "admin",
        "area": [] # El admin no necesita áreas específicas, su rol le da acceso a todo.
    },
    # Juan Diego (Editor): Solo acceso a Barcaza Orion.
    "qualitycontrol@conquerstrading.com": {
        "password": generate_password_hash("Conquers2025"),
        "nombre": "Juan Diego Cuadros",
        "rol": "editor",
        "area": ["barcaza_orion"] 
    },
    # Ricardo (Editor): Solo acceso a Barcaza BITA.
    "quality.manager@conquerstrading.com": {
        "password": generate_password_hash("Conquers2025"),
        "nombre": "Ricardo Congo",
        "rol": "editor",
        "area": ["barcaza_bita"]
    },
    # Omar (Viewer): Rol limitado para ver reportes.
    "omar.morales@conquerstrading.com": {
    "password": generate_password_hash("Conquers2025"),
    "nombre": "Omar Morales",
    "rol": "viewer",
    "area": ["reportes", "planilla_precios"]
},

    "david.restrepo@conquerstrading.com": {
        "password": generate_password_hash("Conquers2025"),
        "nombre": "David Restrepo",
        "rol": "viewer",
        "area": ["reportes", "planilla_precios"] 
    },
    
    # Ignacio (Editor): Solo acceso a Planta.
    "production@conquerstrading.com": {
        "password": generate_password_hash("Conquers2025"),
        "nombre": "Ignacio Quimbayo",
        "rol": "editor",
        "area": ["planta"] # Corregido: ya no tiene acceso a tránsito.
    },
    # Juliana (Editor): Tiene acceso a Tránsito y a Generar Guía.
    "ops@conquerstrading.com": {
        "password": generate_password_hash("Conquers2025"),
        "nombre": "Juliana Torres",
        "rol": "editor",
        "area": ["transito", "guia_transporte"]
    },
    # Samantha (Editor): Tiene acceso solo a Generar Guía.
    "logistic@conquerstrading.com": {
        "password": generate_password_hash("Conquers2025"),
        "nombre": "Samantha Roa",
        "rol": "editor",
        "area": ["guia_transporte"]
    }
}

    
PLANILLA_PLANTA = [
    {"TK": "TK-109", "PRODUCTO": "CRUDO RF.", "MAX_CAP": 22000, "BLS_60": "", "API": "", "BSW": "", "S": ""},
    {"TK": "TK-110", "PRODUCTO": "FO4",       "MAX_CAP": 22000, "BLS_60": "", "API": "", "BSW": "", "S": ""},
    {"TK": "TK-01",  "PRODUCTO": "DILUYENTE", "MAX_CAP": 450,   "BLS_60": "", "API": "", "BSW": "", "S": ""},
    {"TK": "TK-02",  "PRODUCTO": "DILUYENTE", "MAX_CAP": 450,   "BLS_60": "", "API": "", "BSW": "", "S": ""},
    {"TK": "TK-102", "PRODUCTO": "FO6",       "MAX_CAP": 4100,  "BLS_60": "", "API": "", "BSW": "", "S": ""}
]
PLANILLA_BARCAZA_ORION = [
    # Sección MANZANILLO (MGO)
    {"TK": "1", "PRODUCTO": "MGO", "MAX_CAP": 709, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "MANZANILLO"},
    {"TK": "2", "PRODUCTO": "MGO", "MAX_CAP": 806, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "MANZANILLO"},
    {"TK": "3", "PRODUCTO": "MGO", "MAX_CAP": 694, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "MANZANILLO"},
    
    # Tanque Principal (TK-101)
    {"TK": "TK-101", "PRODUCTO": "VLSFO", "MAX_CAP":4660.52, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "PRINCIPAL"},
    
    # BARCAZA CR (VLSFO)
    {"TK": "1P", "PRODUCTO": "VLSFO", "MAX_CAP": 742.68, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "CR"},
    {"TK": "1S", "PRODUCTO": "VLSFO", "MAX_CAP": 739.58, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "CR"},
    {"TK": "2P", "PRODUCTO": "VLSFO", "MAX_CAP": 886.56, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "CR"},
    {"TK": "2S", "PRODUCTO": "VLSFO", "MAX_CAP": 890.24, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "CR"},
    {"TK": "3P", "PRODUCTO": "VLSFO", "MAX_CAP": 877.95, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "CR"},
    {"TK": "3S", "PRODUCTO": "VLSFO", "MAX_CAP": 888.44, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "CR"},
    {"TK": "4P", "PRODUCTO": "VLSFO", "MAX_CAP": 892.57, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "CR"},
    {"TK": "4S", "PRODUCTO": "VLSFO", "MAX_CAP": 887.54, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "CR"},
    {"TK": "5P", "PRODUCTO": "VLSFO", "MAX_CAP": 737.09, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "CR"},
    {"TK": "5S", "PRODUCTO": "VLSFO", "MAX_CAP": 739.45, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "CR"},
    
    # BARCAZA MARGOTH (VLSFO)
    {"TK": "1P", "PRODUCTO": "VLSFO", "MAX_CAP": 582.09, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "MARGOTH"},
    {"TK": "1S", "PRODUCTO": "VLSFO", "MAX_CAP": 582.09, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "MARGOTH"},
    {"TK": "2P", "PRODUCTO": "VLSFO", "MAX_CAP": 572.66, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "MARGOTH"},
    {"TK": "2S", "PRODUCTO": "VLSFO", "MAX_CAP": 572.66, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "MARGOTH"},
    {"TK": "3P", "PRODUCTO": "VLSFO", "MAX_CAP": 572.68, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "MARGOTH"},
    {"TK": "3S", "PRODUCTO": "VLSFO", "MAX_CAP": 572.68, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "MARGOTH"},
    {"TK": "4P", "PRODUCTO": "VLSFO", "MAX_CAP": 575.10, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "MARGOTH"},
    {"TK": "4S", "PRODUCTO": "VLSFO", "MAX_CAP": 575.10, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "MARGOTH"},
    {"TK": "5P", "PRODUCTO": "VLSFO", "MAX_CAP": 571.72, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "MARGOTH"},
    {"TK": "5S", "PRODUCTO": "VLSFO", "MAX_CAP": 571.72, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "MARGOTH"},
    
    # BARCAZA ODISEA (VLSFO)
    {"TK": "1P", "PRODUCTO": "VLSFO", "MAX_CAP": 2533.98, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "ODISEA"},
    {"TK": "1S", "PRODUCTO": "VLSFO", "MAX_CAP": 2544.17, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "ODISEA"},
    {"TK": "2P", "PRODUCTO": "VLSFO", "MAX_CAP": 3277.10, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "ODISEA"},
    {"TK": "2S", "PRODUCTO": "VLSFO", "MAX_CAP": 3282.97, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "ODISEA"},
    {"TK": "3P", "PRODUCTO": "VLSFO", "MAX_CAP": 3302.94, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "ODISEA"},
    {"TK": "3S", "PRODUCTO": "VLSFO", "MAX_CAP": 3287.42, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "ODISEA"},
    {"TK": "4P", "PRODUCTO": "VLSFO", "MAX_CAP": 3282.96, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "ODISEA"},
    {"TK": "4S", "PRODUCTO": "VLSFO", "MAX_CAP": 3291.98, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "ODISEA"},
    {"TK": "5P", "PRODUCTO": "VLSFO", "MAX_CAP": 2930.16, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "ODISEA"},
]

PLANILLA_BARCAZA_BITA = [
    # Barcaza Marinse
    {"TK": "MARI TK-1C", "PRODUCTO": "VLSFO", "MAX_CAP": 1506.56, "BLS_60": "", "API": "", "BSW": "", "S": ""},
    {"TK": "MARI TK-2C", "PRODUCTO": "VLSFO", "MAX_CAP": 1541.10, "BLS_60": "", "API": "", "BSW": "", "S": ""},
    {"TK": "MARI TK-3C", "PRODUCTO": "VLSFO", "MAX_CAP": 1438.96, "BLS_60": "", "API": "", "BSW": "", "S": ""},
    {"TK": "MARI TK-4C", "PRODUCTO": "VLSFO", "MAX_CAP": 1433.75, "BLS_60": "", "API": "", "BSW": "", "S": ""},
    {"TK": "MARI TK-5C", "PRODUCTO": "VLSFO", "MAX_CAP": 1641.97, "BLS_60": "", "API": "", "BSW": "", "S": ""},
    {"TK": "MARI TK-6C", "PRODUCTO": "VLSFO", "MAX_CAP": 1617.23, "BLS_60": "", "API": "", "BSW": "", "S": ""},
    # Barcaza Oidech
    {"TK": "OID TK-1C", "PRODUCTO": "VLSFO", "MAX_CAP": 4535.54, "BLS_60": "", "API": "", "BSW": "", "S": ""},
    {"TK": "OID TK-2C", "PRODUCTO": "VLSFO", "MAX_CAP": 5808.34, "BLS_60": "", "API": "", "BSW": "", "S": ""},
    {"TK": "OID TK-3C", "PRODUCTO": "VLSFO", "MAX_CAP": 4928.29, "BLS_60": "", "API": "", "BSW": "", "S": ""}
]
PLANILLA_TRANSITO_GENERAL = [
    {"ORIGEN": "", "FECHA": "", "GUIA": "", "PRODUCTO": "", "PLACA": "", "API": "", "BSW": "",  "NSV": "", "OBSERVACIONES":""}
    for _ in range(10)  # O el número de filas que desees por defecto
]

PLANILLA_TRANSITO_REFINERIA = [
    {"ORIGEN": "", "FECHA": "", "GUIA": "", "PRODUCTO": "", "PLACA": "", "API": "", "BSW": "",  "NSV": "", "OBSERVACIONES":""}
    for _ in range(10)  # O el número de filas que desees por defecto
]

# REEMPLAZA TU LISTA ACTUAL CON ESTA
DEPARTAMENTOS_Y_CAPITALES = [
    {"departamento": "Amazonas", "capital": "Leticia", "lat": -4.2152, "lng": -69.9406},
    {"departamento": "Antioquia", "capital": "Medellín", "lat": 6.2442, "lng": -75.5812},
    {"departamento": "Arauca", "capital": "Arauca", "lat": 7.084, "lng": -70.759},
    {"departamento": "Atlántico", "capital": "Barranquilla", "lat": 10.9639, "lng": -74.7964},
    {"departamento": "Bolívar", "capital": "Cartagena", "lat": 10.3910, "lng": -75.4794},
    {"departamento": "Boyacá", "capital": "Tunja", "lat": 5.534, "lng": -73.367},
    {"departamento": "Caldas", "capital": "Manizales", "lat": 5.068, "lng": -75.517},
    {"departamento": "Caquetá", "capital": "Florencia", "lat": 1.614, "lng": -75.606},
    {"departamento": "Casanare", "capital": "Yopal", "lat": 5.337, "lng": -72.390},
    {"departamento": "Cauca", "capital": "Popayán", "lat": 2.445, "lng": -76.614},
    {"departamento": "Cesar", "capital": "Valledupar", "lat": 10.463, "lng": -73.253},
    {"departamento": "Chocó", "capital": "Quibdó", "lat": 5.694, "lng": -76.661},
    {"departamento": "Córdoba", "capital": "Montería", "lat": 8.747, "lng": -75.881},
    {"departamento": "Cundinamarca", "capital": "Bogotá", "lat": 4.711, "lng": -74.072},
    {"departamento": "Guainía", "capital": "Inírida", "lat": 3.865, "lng": -67.923},
    {"departamento": "Guaviare", "capital": "San José del Guaviare", "lat": 2.572, "lng": -72.645},
    {"departamento": "Huila", "capital": "Neiva", "lat": 2.927, "lng": -75.281},
    {"departamento": "La Guajira", "capital": "Riohacha", "lat": 11.544, "lng": -72.907},
    {"departamento": "Magdalena", "capital": "Santa Marta", "lat": 11.240, "lng": -74.199},
    {"departamento": "Meta", "capital": "Villavicencio", "lat": 4.142, "lng": -73.626},
    {"departamento": "Nariño", "capital": "Pasto", "lat": 1.213, "lng": -77.281},
    {"departamento": "Norte de Santander", "capital": "Cúcuta", "lat": 7.893, "lng": -72.507},
    {"departamento": "Putumayo", "capital": "Mocoa", "lat": 1.154, "lng": -76.646},
    {"departamento": "Quindío", "capital": "Armenia", "lat": 4.533, "lng": -75.681},
    {"departamento": "Risaralda", "capital": "Pereira", "lat": 4.813, "lng": -75.696},
    {"departamento": "San Andrés y Providencia", "capital": "San Andrés", "lat": 12.584, "lng": -81.700},
    {"departamento": "Santander", "capital": "Bucaramanga", "lat": 7.119, "lng": -73.122},
    {"departamento": "Sucre", "capital": "Sincelejo", "lat": 9.295, "lng": -75.397},
    {"departamento": "Tolima", "capital": "Ibagué", "lat": 4.438, "lng": -75.232},
    {"departamento": "Valle del Cauca", "capital": "Cali", "lat": 3.451, "lng": -76.532},
    {"departamento": "Vaupés", "capital": "Mitú", "lat": 1.257, "lng": -70.234},
    {"departamento": "Vichada", "capital": "Puerto Carreño", "lat": 6.189, "lng": -67.485}
]
PLANILLA_PRECIOS = [
    {
        "DEPARTAMENTO": d["departamento"], "CAPITAL": d["capital"],
        "LAT": d["lat"], "LNG": d["lng"], # <-- AÑADIMOS LAS COORDENADAS AQUÍ
        "DISTANCIA_KM": "", "COSTO_FLETE": "", "PRECIO_VENTA": ""
    } for d in DEPARTAMENTOS_Y_CAPITALES
]

def cargar_productos():
    ruta = "productos.json"
    try:
        if os.path.exists(ruta):
            with open(ruta, encoding='utf-8') as f:
                data = json.load(f)
                # Validar estructura
                if not all(isinstance(v, list) for v in data.values()):
                    raise ValueError("Estructura inválida en productos.json")
                return data
    except Exception as e:
        print(f"Error cargando productos: {e}")
    return {"REFINERIA": [], "EDSM": []}  # Estructura por defecto

def guardar_registro_generico(datos_a_guardar, tipo_area):
    """
    Función genérica para guardar los datos de cualquier planilla en un archivo JSON.
    
    Args:
        datos_a_guardar (list): La lista de diccionarios (la planilla) con los datos actualizados.
        tipo_area (str): Un prefijo para el nombre del archivo (ej: 'planta', 'barcaza_orion').
    """
    try:
        # 1. Crear el timestamp para el nombre del archivo
        fecha = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        
        # 2. Definir la carpeta y el nombre del archivo
        carpeta = "registros"
        os.makedirs(carpeta, exist_ok=True) # Crea la carpeta si no existe
        nombre_archivo = f"{tipo_area}_{fecha}.json"
        ruta_completa = os.path.join(carpeta, nombre_archivo)
        
        # 3. Preparar el diccionario de datos que se guardará
        data_para_json = {
            "fecha": fecha,
            "area": tipo_area,
            "usuario": session.get("nombre", "No identificado"),
            "datos": datos_a_guardar
        }
        
        # 4. Escribir el archivo JSON
        with open(ruta_completa, 'w', encoding='utf-8') as f:
            json.dump(data_para_json, f, ensure_ascii=False, indent=4)
            
        # 5. Devolver una respuesta de éxito en formato JSON
        return jsonify(success=True, message=f"Registro de '{tipo_area}' guardado exitosamente.")

    except Exception as e:
        # En caso de cualquier error, registrarlo y devolver un error en formato JSON
        print(f"ERROR en guardar_registro_generico para '{tipo_area}': {e}")
        return jsonify(success=False, message=f"Error interno del servidor al guardar el registro: {str(e)}"), 500

def cargar_transito_config():
    ruta_config = "transito_config.json"
    default_config = {
        "REFINERIA": {
            "nombre_display": "Tránsito Crudo Refinería",
            "campos": {}
        },
        "EDSM": {
            "nombre_display": "Tránsito Crudo EDSM",
            "campos": {}
        }
    }
    
    try:
        if os.path.exists(ruta_config):
            with open(ruta_config, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # Validación de estructura básica
                if not all(k in config for k in ['REFINERIA', 'EDSM']):
                    raise ValueError("Estructura inválida")
                return config
    except Exception as e:
        print(f"Error cargando configuración: {e}")
    
    # Si hay error, devolver configuración por defecto
    return default_config

def login_required(f):
    # ... tu decorador de login (déjalo como está) ...
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # ...
     return decorated_function


def permiso_requerido(area_requerida):
    """
    Decorador que verifica si un usuario tiene permiso para un área específica.
    El rol 'admin' siempre tiene acceso.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 1. El admin siempre tiene acceso
            if session.get('rol') == 'admin':
                return f(*args, **kwargs)
            
            # 2. Revisa si el área requerida está en la lista de áreas del usuario
            areas_del_usuario = session.get('area', [])
            if area_requerida in areas_del_usuario:
                return f(*args, **kwargs)
            
            # 3. Si no cumple ninguna condición, denegar acceso
            flash("No tienes los permisos necesarios para acceder a esta página.", "danger")
            return redirect(url_for('home'))
        return decorated_function
    return decorator
def calcular_estadisticas(lista_tanques):
    """
    Calcula totales y promedios PONDERADOS para una lista de tanques.
    El promedio de API, BSW y S se pondera por el volumen (BLS_60) de cada tanque.
    """
    if not lista_tanques:
        return {
            'total_cap': 0, 'total_bls': 0, 'total_porc': 0,
            'prom_api': 0, 'prom_bsw': 0, 'prom_s': 0
        }

    # --- Totales simples (Suma) ---
    total_cap = sum(float(t.get('MAX_CAP') or 0) for t in lista_tanques)
    total_bls = sum(float(t.get('BLS_60') or 0) for t in lista_tanques)
    total_porc = (total_bls / total_cap * 100) if total_cap > 0 else 0

    # --- INICIO DEL CÁLCULO DE PROMEDIO PONDERADO ---
    
    suma_ponderada_api = 0
    suma_ponderada_bsw = 0
    suma_ponderada_s = 0

    # Solo calculamos si hay volumen total para evitar división por cero
    if total_bls > 0:
        for t in lista_tanques:
            bls = float(t.get('BLS_60') or 0)
            
            # El "peso" de cada tanque es su volumen dividido por el volumen total
            peso = bls / total_bls
            
            # Multiplicamos el valor de cada propiedad por su peso y lo sumamos
            suma_ponderada_api += (float(t.get('API') or 0) * peso)
            suma_ponderada_bsw += (float(t.get('BSW') or 0) * peso)
            suma_ponderada_s += (float(t.get('S') or 0) * peso)

    return {
        'total_cap': total_cap,
        'total_bls': total_bls,
        'total_porc': total_porc,
        'prom_api': suma_ponderada_api, # Ahora estos son los promedios ponderados
        'prom_bsw': suma_ponderada_bsw,
        'prom_s': suma_ponderada_s
    }

@login_required
@permiso_requerido('transito')
@app.route('/transito')
def transito():
    # Iniciamos la consulta base
    query = db.session.query(RegistroTransito)

    # Leemos todos los posibles filtros desde la URL
    filtros = {
        'fecha': request.args.get('fecha_cargue'),
        'guia': request.args.get('guia'),
        'origen': request.args.get('origen'),
        'producto': request.args.get('producto'),
        'placa': request.args.get('placa')
    }

    # Aplicamos los filtros a la consulta solo si tienen un valor
    if filtros['fecha']:
        query = query.filter(RegistroTransito.fecha == filtros['fecha'])
    if filtros['guia']:
        query = query.filter(RegistroTransito.guia.ilike(f"%{filtros['guia']}%"))
    if filtros['origen']:
        query = query.filter(RegistroTransito.origen == filtros['origen'])
    if filtros['producto']:
        query = query.filter(RegistroTransito.producto == filtros['producto'])
    if filtros['placa']:
        query = query.filter(RegistroTransito.placa.ilike(f"%{filtros['placa']}%"))

    # Ejecutamos la consulta final
    todos_los_registros = query.order_by(RegistroTransito.timestamp.desc()).all()

    # Separamos los resultados y los convertimos a diccionario
    datos_general = [{ "id": r.id, "ORIGEN": r.origen, "FECHA": r.fecha, "GUIA": r.guia, "PRODUCTO": r.producto, "PLACA": r.placa, "API": r.api or '', "BSW": r.bsw or '', "NSV": r.nsv or '', "OBSERVACIONES": r.observaciones or '' } for r in todos_los_registros if r.tipo_transito == 'general']
    datos_refineria = [{ "id": r.id, "ORIGEN": r.origen, "FECHA": r.fecha, "GUIA": r.guia, "PRODUCTO": r.producto, "PLACA": r.placa, "API": r.api or '', "BSW": r.bsw or '', "NSV": r.nsv or '', "OBSERVACIONES": r.observaciones or '' } for r in todos_los_registros if r.tipo_transito == 'refineria']

    return render_template("transito.html",
                           nombre=session.get("nombre"),
                           datos_general=datos_general,
                           datos_refineria=datos_refineria,
                           tipo_inicial="general",
                           transito_config=cargar_transito_config(),
                           # Pasamos los filtros de vuelta para que se muestren en los campos
                           filtros=filtros)
@login_required
@app.route('/api/add-origen', methods=['POST'])
def agregar_origen():
    data = request.get_json()
    origen_nombre = data.get('origen_nombre', '').strip().upper()
    tipo_planilla = data.get('tipo_planilla', 'EDSM')  # 'EDSM' o 'REFINERIA'

    if not origen_nombre or tipo_planilla not in ['EDSM', 'REFINERIA']:
        return jsonify(success=False, message="Datos incompletos o inválidos"), 400

    try:
        # Cargar configuración actual
        config = cargar_transito_config()
        
        # Verificar si el origen ya existe
        if origen_nombre in config[tipo_planilla]['campos']:
            return jsonify(success=False, message="Este origen ya existe"), 409

        # Agregar el nuevo origen
        config[tipo_planilla]['campos'][origen_nombre] = {
            "productos": [],
            "auto_select_product": ""
        }

        # Guardar la configuración actualizada
        with open('transito_config.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)

        return jsonify(success=True, message="Origen agregado exitosamente")

    except Exception as e:
        print(f"Error al agregar origen: {e}")
        return jsonify(success=False, message="Error interno del servidor"), 500
    
@login_required
@app.route('/api/add-producto', methods=['POST'])
def agregar_producto_transito():
    data = request.get_json()
    origen_nombre = data.get('origen_nombre', '').strip().upper()
    producto_nombre = data.get('producto_nombre', '').strip()
    tipo_planilla = data.get('tipo_planilla', 'EDSM')  # 'EDSM' o 'REFINERIA'

    if not origen_nombre or not producto_nombre or tipo_planilla not in ['EDSM', 'REFINERIA']:
        return jsonify(success=False, message="Datos incompletos o inválidos"), 400

    try:
        # Cargar configuración actual
        config = cargar_transito_config()
        
        # Verificar si el origen existe
        if origen_nombre not in config[tipo_planilla]['campos']:
            return jsonify(success=False, message="El origen especificado no existe"), 404

        # Verificar si el producto ya existe
        if producto_nombre in config[tipo_planilla]['campos'][origen_nombre]['productos']:
            return jsonify(success=False, message="Este producto ya existe para este origen"), 409

        # Agregar el nuevo producto
        config[tipo_planilla]['campos'][origen_nombre]['productos'].append(producto_nombre)

        # Guardar la configuración actualizada
        with open('transito_config.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)

        return jsonify(success=True, message="Producto agregado exitosamente")

    except Exception as e:
        print(f"Error al agregar producto: {e}")
        return jsonify(success=False, message="Error interno del servidor"), 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'email' in session:
        return redirect(url_for('home'))

    next_page = request.args.get('next')
    if request.method == 'POST':
        email = request.form['email'].lower()
        password = request.form['password']
        user = USUARIOS.get(email)

        if user and check_password_hash(user['password'], password):
            session['email'] = email
            session['area'] = user['area']
            session['nombre'] = user['nombre']
            session['rol'] = user['rol']
            flash(f"Bienvenido {user['nombre']}", 'success')
            return redirect(next_page or url_for('home'))

        flash('Email o contraseña incorrectos', 'danger')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Sesión cerrada', 'info')
    return redirect(url_for('login'))

@login_required
@permiso_requerido('planta')
@app.route('/planta')
def planta():
    # 1. Obtiene la fecha del filtro de la URL. Si no se envía ninguna, usa la fecha de hoy.
    fecha_str = request.args.get('fecha')

    try:
        # Intenta convertir el texto de la fecha a un objeto de fecha real
        fecha_seleccionada = date.fromisoformat(fecha_str) if fecha_str else date.today()
    except (ValueError, TypeError):
        # Si el formato es incorrecto, usa la fecha de hoy como valor por defecto seguro
        fecha_seleccionada = date.today()
    
    # Creamos un timestamp del final del día seleccionado para incluir todos los registros de ese día
    timestamp_limite = datetime.combine(fecha_seleccionada, time.max)

    # 2. Consulta para obtener el estado MÁS RECIENTE de CADA tanque EN O ANTES de la fecha seleccionada
    subquery = db.session.query(
        RegistroPlanta.tk,
        func.max(RegistroPlanta.timestamp).label('max_timestamp')
    ).filter(RegistroPlanta.timestamp <= timestamp_limite
             ) .group_by(RegistroPlanta.tk
                         ).subquery()

    registros_recientes = db.session.query(RegistroPlanta).join(
        subquery,
        (RegistroPlanta.tk == subquery.c.tk) & (RegistroPlanta.timestamp == subquery.c.max_timestamp)
    ).all()
    
    # 3. La lógica para preparar y mostrar los datos es la misma de antes
    datos_para_plantilla = []
    if registros_recientes:
        for registro in registros_recientes:
            datos_para_plantilla.append({
                "TK": registro.tk, "PRODUCTO": registro.producto, "MAX_CAP": registro.max_cap,
                "BLS_60": registro.bls_60 or "", "API": registro.api or "", 
                "BSW": registro.bsw or "", "S": registro.s or ""
            })
    else:
        # Si no hay registros para esa fecha, mostramos la planilla por defecto
        datos_para_plantilla = PLANILLA_PLANTA

    # 4. Enviamos los datos y la fecha seleccionada de vuelta al HTML
    return render_template("planta.html", 
                           planilla=datos_para_plantilla, 
                           nombre=session.get("nombre", "Usuario"),
                           # Esto es para que el campo de fecha muestre el día que estás viendo
                           fecha_seleccionada=fecha_seleccionada.isoformat())

@login_required
@app.route('/reporte_planta')
def reporte_planta():
    # 1. Lee la fecha del filtro de la URL (o usa la de hoy si no hay ninguna)
    fecha_str = request.args.get('fecha')
    try:
        fecha_seleccionada = date.fromisoformat(fecha_str) if fecha_str else date.today()
    except (ValueError, TypeError):
        fecha_seleccionada = date.today()
    
    timestamp_limite = datetime.combine(fecha_seleccionada, time.max)

    # 2. Ejecuta la consulta a la base de datos para obtener el estado de ese día
    subquery = (db.session.query(
        func.max(RegistroPlanta.id).label('max_id')
    ).filter(
        RegistroPlanta.timestamp <= timestamp_limite
    ).group_by(RegistroPlanta.tk).subquery())

    registros_recientes = (db.session.query(RegistroPlanta)
        .filter(RegistroPlanta.id.in_(subquery))
        .all())
    
    # 3. Prepara los datos y la información de actualización para la plantilla
    datos_planta_js = []
    fecha_actualizacion_info = "No hay registros para la fecha seleccionada."

    if registros_recientes:
        for registro in registros_recientes:
            datos_planta_js.append({
                "TK": registro.tk,
                "PRODUCTO": registro.producto,
                "MAX_CAP": registro.max_cap,
                "BLS_60": registro.bls_60,
                "API": registro.api,
                "BSW": registro.bsw,
                "S": registro.s
            })
        
        # Para el mensaje "Última actualización", buscamos el registro más reciente de la selección
        ultimo_registro = max(registros_recientes, key=lambda r: r.timestamp)
        fecha_formato_para_funcion = ultimo_registro.timestamp.strftime("%Y_%m_%d_%H_%M_%S")
        fecha_actualizacion_info = formatear_info_actualizacion(
            fecha_formato_para_funcion, 
            ultimo_registro.usuario
        )

    # 4. Renderiza la plantilla del reporte con los datos y fechas correctos
    return render_template("reporte_planta.html", 
                           datos_planta_para_js=datos_planta_js,
                           fecha_actualizacion_info=fecha_actualizacion_info,
                           fecha_seleccionada=fecha_seleccionada.isoformat(),
                           today_iso=date.today().isoformat())

@login_required
@permiso_requerido('transito')
@app.route('/guardar-config-transito', methods=['POST'])
def guardar_config_transito():
    try:
        nueva_config = request.get_json()
        # Validación básica de la estructura recibida
        if not isinstance(nueva_config, dict) or 'REFINERIA' not in nueva_config or 'EDSM' not in nueva_config:
            return jsonify(success=False, message="Formato de configuración inválido."), 400

        with open('transito_config.json', 'w', encoding='utf-8') as f:
            json.dump(nueva_config, f, ensure_ascii=False, indent=4)

        return jsonify(success=True, message="Configuración guardada exitosamente.")
    except Exception as e:
        print(f"Error al guardar transito_config.json: {e}")
        return jsonify(success=False, message=f"Error interno del servidor: {str(e)}"), 500

@login_required
@permiso_requerido('transito')
@app.route('/guardar-registro-transito-<tipo_transito>', methods=['POST'])
def guardar_transito(tipo_transito):
    datos_recibidos = request.get_json()
    if not isinstance(datos_recibidos, list):
        return jsonify(success=False, message="Formato de datos incorrecto."), 400

    try:
        # Itera sobre cada fila enviada desde el frontend
        for datos_fila in datos_recibidos:
            # Solo procesamos filas que tengan datos, especialmente una guía.
            guia = datos_fila.get('GUIA')
            if not guia:
                continue

            registro_id = datos_fila.get('id')

            # Si la fila tiene un ID, significa que es un registro existente.
            if registro_id:
                registro = db.session.query(RegistroTransito).get(registro_id)
                if registro:
                    # ACTUALIZAMOS el registro existente
                    registro.usuario = session.get("nombre", "No identificado")
                    registro.origen = datos_fila.get('ORIGEN')
                    registro.fecha = datos_fila.get('FECHA')
                    registro.producto = datos_fila.get('PRODUCTO')
                    registro.placa = datos_fila.get('PLACA')
                    registro.api = float(str(datos_fila.get('API')).replace(',', '.')) if datos_fila.get('API') else None
                    registro.bsw = float(str(datos_fila.get('BSW')).replace(',', '.')) if datos_fila.get('BSW') else None
                    registro.nsv = float(str(datos_fila.get('NSV')).replace(',', '.')) if datos_fila.get('NSV') else None
                    registro.observaciones = datos_fila.get('OBSERVACIONES')
                    registro.timestamp = datetime.utcnow()
            else:
                # Si la fila NO tiene ID, es un registro nuevo y lo CREAMOS.
                nuevo_registro = RegistroTransito(
                    usuario=session.get("nombre", "No identificado"),
                    tipo_transito=tipo_transito,
                    guia=guia,
                    origen=datos_fila.get('ORIGEN'),
                    fecha=datos_fila.get('FECHA'),
                    producto=datos_fila.get('PRODUCTO'),
                    placa=datos_fila.get('PLACA'),
                    api=float(str(datos_fila.get('API')).replace(',', '.')) if datos_fila.get('API') else None,
                    bsw=float(str(datos_fila.get('BSW')).replace(',', '.')) if datos_fila.get('BSW') else None,
                    nsv=float(str(datos_fila.get('NSV')).replace(',', '.')) if datos_fila.get('NSV') else None,
                    observaciones=datos_fila.get('OBSERVACIONES')
                )
                db.session.add(nuevo_registro)

        # Confirmamos todos los cambios (updates y nuevos) en la base de datos.
        db.session.commit()

        # Después de guardar, consultamos el historial COMPLETO para devolverlo al frontend.
        registros_actualizados = db.session.query(RegistroTransito).filter_by(tipo_transito=tipo_transito).order_by(RegistroTransito.timestamp.desc()).all()
        
        datos_para_frontend = [
            {"id": r.id, "ORIGEN": r.origen, "FECHA": r.fecha, "GUIA": r.guia, "PRODUCTO": r.producto, "PLACA": r.placa, "API": r.api or '', "BSW": r.bsw or '', "NSV": r.nsv or '', "OBSERVACIONES": r.observaciones or ''}
            for r in registros_actualizados
        ]
        
        return jsonify(success=True, message="Historial guardado exitosamente.", datos=datos_para_frontend)

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error al guardar tránsito: {e}")
        return jsonify(success=False, message=f"Error interno: {str(e)}"), 500
    
@login_required
@permiso_requerido('transito')
@app.route('/eliminar-registro-transito/<int:registro_id>', methods=['DELETE'])
def eliminar_registro_transito(registro_id):
    try:
        registro_a_eliminar = db.session.query(RegistroTransito).get(registro_id)
        if registro_a_eliminar:
            db.session.delete(registro_a_eliminar)
            db.session.commit()
            return jsonify(success=True, message="Registro eliminado exitosamente.")
        else:
            return jsonify(success=False, message="Registro no encontrado."), 404
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, message=f"Error interno: {str(e)}"), 500

    
@login_required
@app.route('/agregar-producto', methods=['POST'])
def agregar_producto():
    data = request.get_json()
    nuevo_producto = data.get("producto")
    grupo = data.get("grupo")  # "REFINERIA" o "EDSM"

    if not nuevo_producto or grupo not in ["REFINERIA", "EDSM"]:
        return jsonify(success=False, message="Datos incompletos")

    ruta = "productos.json"
    try:
        with open(ruta, encoding="utf-8") as f:
            productos = json.load(f)

        if nuevo_producto not in productos[grupo]:
            productos[grupo].append(nuevo_producto)
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump(productos, f, ensure_ascii=False, indent=2)

        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, message=str(e))
    
@login_required       
@app.route('/historial_registros') 
def historial_registros():        
    registros = []
    carpeta = "registros"
    os.makedirs(carpeta, exist_ok=True)

    for archivo in sorted(os.listdir(carpeta), reverse=True):
        if archivo.endswith(".json"):
            ruta = os.path.join(carpeta, archivo)
            try:
                with open(ruta, encoding='utf-8') as f:
                    registro = json.load(f)
                    if session.get("email") in ["omar.morales@conquerstrading.com", "oci@conquerstrading.com"]:
                        registros.append(registro)
                    else:
                        if registro.get("usuario") == session.get("nombre"):
                            registros.append(registro)
            except Exception as e:
                print(f"Error al cargar {archivo}: {e}")
    # Asegúrate que el nombre del template sigue siendo el correcto si quieres reutilizarlo
    return render_template("reporte_general.html", registros=registros, nombre=session.get("nombre"))

@login_required
@permiso_requerido('transito')
@app.route('/reporte_transito')
def reporte_transito():
    app.logger.info("Accediendo a /reporte_transito desde la base de datos")
    datos_consolidados = {}
    datos_conteo_camiones = {}
    # --- CORRECCIÓN 1: INICIALIZAR EL DICCIONARIO AQUÍ ---
    observaciones_camiones = {} 
    
    fecha_actualizacion_info = "No se encontraron registros de tránsito."
    
    try:
        todos_los_registros = db.session.query(RegistroTransito).order_by(RegistroTransito.timestamp.desc()).all()

        if not todos_los_registros:
            return render_template("reporte_transito.html", 
                                   datos_consolidados=datos_consolidados, 
                                   datos_conteo_camiones=datos_conteo_camiones,
                                   # --- CORRECCIÓN 2: PASAR LA VARIABLE AQUÍ TAMBIÉN ---
                                   observaciones_camiones=observaciones_camiones,
                                   nombre=session.get("nombre"), 
                                   fecha_actualizacion_info=fecha_actualizacion_info)

        ultimo_registro = max(todos_los_registros, key=lambda r: r.timestamp)
        fecha_formato = ultimo_registro.timestamp.strftime("%Y_%m_%d_%H_%M_%S")
        fecha_actualizacion_info = formatear_info_actualizacion(fecha_formato, ultimo_registro.usuario)

        for reg in todos_los_registros:
            origen = (reg.origen or "").strip()
            producto = (reg.producto or "").strip()
            
            if not origen or not producto:
                continue
            
            tipo_destino_reporte = "Refinería" if reg.tipo_transito == "refineria" else "EDSM"
            nsv = float(reg.nsv or 0.0)

            datos_consolidados.setdefault(tipo_destino_reporte, {}).setdefault(origen, {}).setdefault(producto, 0.0)
            datos_consolidados[tipo_destino_reporte][origen][producto] += nsv
            
            datos_conteo_camiones.setdefault(tipo_destino_reporte, {}).setdefault(origen, {}).setdefault(producto, 0)
            datos_conteo_camiones[tipo_destino_reporte][origen][producto] += 1
            
            if reg.observaciones and reg.observaciones.strip():
                observacion_texto = reg.observaciones.strip()
                placa = reg.placa or "SIN PLACA"
                texto_completo = f"{placa}: {observacion_texto}"
                
                lista_de_observaciones = observaciones_camiones.setdefault(tipo_destino_reporte, {}).setdefault(origen, {}).setdefault(producto, [])
                lista_de_observaciones.append(texto_completo)
            
    except Exception as e:
        app.logger.error(f"Error crítico al generar reporte de tránsito desde BD: {e}")
        flash(f"Ocurrió un error al generar el reporte: {e}", "danger")
        fecha_actualizacion_info = "Error al cargar los datos."

    return render_template("reporte_transito.html",
                           datos_consolidados=datos_consolidados,
                           datos_conteo_camiones=datos_conteo_camiones,
                           # --- CORRECCIÓN 3: PASAR LA VARIABLE EN EL RETURN FINAL ---
                           observaciones_camiones=observaciones_camiones,
                           nombre=session.get("nombre"),
                           fecha_actualizacion_info=fecha_actualizacion_info)

@login_required
@permiso_requerido('barcaza_orion')
@app.route('/barcaza_orion')
def barcaza_orion():
    print("\n--- INICIANDO RUTA /barcaza_orion ---")
    
    fecha_str = request.args.get('fecha')
    try:
        fecha_seleccionada = date.fromisoformat(fecha_str) if fecha_str else date.today()
    except (ValueError, TypeError):
        fecha_seleccionada = date.today()
    
    print(f"DEBUG: Filtrando por fecha: {fecha_seleccionada}")
    timestamp_limite = datetime.combine(fecha_seleccionada, time.max)

    subquery = (db.session.query(
        func.max(RegistroBarcazaOrion.id).label('max_id')
    ).filter(RegistroBarcazaOrion.timestamp <= timestamp_limite).group_by(RegistroBarcazaOrion.tk).subquery())

    registros_recientes = (db.session.query(RegistroBarcazaOrion)
        .filter(RegistroBarcazaOrion.id.in_(subquery)).all())
    
    print(f"DEBUG: La consulta a la BD encontró {len(registros_recientes)} registros.")
    
    datos_para_plantilla = []
    if registros_recientes:
        for registro in registros_recientes:
            datos_para_plantilla.append({
                "TK": registro.tk, "PRODUCTO": registro.producto, "MAX_CAP": registro.max_cap,
                "BLS_60": registro.bls_60 or "", "API": registro.api or "", 
                "BSW": registro.bsw or "", "S": registro.s or "", "grupo": registro.grupo or ""
            })
    else:
        print("DEBUG: No se encontraron registros, se usará la planilla por defecto.")
        datos_para_plantilla = PLANILLA_BARCAZA_ORION

    tanques_principales = [tk for tk in datos_para_plantilla if tk.get('grupo') == 'PRINCIPAL']
    tanques_man = [tk for tk in datos_para_plantilla if tk.get('grupo') == 'MANZANILLO']
    tanques_cr = [tk for tk in datos_para_plantilla if tk.get('grupo') == 'CR']
    tanques_margoth = [tk for tk in datos_para_plantilla if tk.get('grupo') == 'MARGOTH']
    tanques_odisea = [tk for tk in datos_para_plantilla if tk.get('grupo') == 'ODISEA']

    return render_template("barcaza_orion.html",
                           titulo="Planilla Barcaza Orion",
                           tanques_principales=tanques_principales,
                           tanques_man=tanques_man,
                           tanques_cr=tanques_cr,
                           tanques_margoth=tanques_margoth,
                           tanques_odisea=tanques_odisea,
                           nombre=session.get("nombre"),
                           fecha_seleccionada=fecha_seleccionada.isoformat())

@login_required
@permiso_requerido('barcaza_bita')
@app.route('/barcaza_bita')
def barcaza_bita():
    # 1. Lógica del filtro de fecha
    fecha_str = request.args.get('fecha')
    try:
        fecha_seleccionada_obj = date.fromisoformat(fecha_str) if fecha_str else date.today()
    except (ValueError, TypeError):
        fecha_seleccionada_obj = date.today()

    # --- CÓDIGO CLAVE PARA FORMATEAR LA FECHA ---
    meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    nombre_mes = meses[fecha_seleccionada_obj.month - 1]
    fecha_display = fecha_seleccionada_obj.strftime(f"%d de {nombre_mes} de %Y")
    # --- FIN DEL CÓDIGO CLAVE ---
    

    timestamp_limite = datetime.combine(fecha_seleccionada_obj, time.max)

    # 2. Consulta a la base de datos para BITA
    subquery = (db.session.query(func.max(RegistroBarcazaBita.id).label('max_id'))
        .filter(RegistroBarcazaBita.timestamp <= timestamp_limite).group_by(RegistroBarcazaBita.tk).subquery())

    registros_recientes = (db.session.query(RegistroBarcazaBita)
        .filter(RegistroBarcazaBita.id.in_(subquery)).all())

    # 3. Preparar los datos
    datos_para_plantilla = []
    if registros_recientes:
        for r in registros_recientes:
            datos_para_plantilla.append({
                "TK": r.tk, "PRODUCTO": r.producto, "MAX_CAP": r.max_cap,
                "BLS_60": r.bls_60 or "", "API": r.api or "", "BSW": r.bsw or "", "S": r.s or ""
            })
    else:
        datos_para_plantilla = PLANILLA_BARCAZA_BITA

    # 4. Lógica para separar en grupos
    grupos = {
        "BARCAZA MARINSE": [tk for tk in datos_para_plantilla if tk.get('TK', '').startswith('MARI')],
        "BARCAZA OIDECH": [tk for tk in datos_para_plantilla if tk.get('TK', '').startswith('OID')]
    }

    # 5. Renderizar la plantilla, pasando todas las variables necesarias
    return render_template("barcaza_bita.html",
                           titulo="Planilla Barcaza BITA",
                           grupos=grupos,
                           nombre=session.get('nombre', 'Desconocido'),
                           fecha_seleccionada=fecha_seleccionada_obj.isoformat(),
                           today_iso=date.today().isoformat(),
                           fecha_display=fecha_display) 

@login_required
@permiso_requerido('guia_transporte') 
@app.route('/guia_transporte')
def guia_transporte():
    # El if de permisos ya no es necesario aquí.
    return render_template("guia_transporte.html", nombre=session.get("nombre"))

@login_required
@app.route('/reporte_barcaza')
def reporte_barcaza():
    # 1. Lógica del filtro de fecha (idéntica a la que ya usamos)
    fecha_str = request.args.get('fecha')
    try:
        fecha_seleccionada = date.fromisoformat(fecha_str) if fecha_str else date.today()
    except (ValueError, TypeError):
        fecha_seleccionada = date.today()
    
    timestamp_limite = datetime.combine(fecha_seleccionada, time.max)

    # 2. Consulta a la base de datos para obtener el estado de ese día para la Barcaza Orion
    subquery = (db.session.query(
        func.max(RegistroBarcazaOrion.id).label('max_id')
    ).filter(
        RegistroBarcazaOrion.timestamp <= timestamp_limite
    ).group_by(RegistroBarcazaOrion.tk).subquery())

    registros_recientes = (db.session.query(RegistroBarcazaOrion)
        .filter(RegistroBarcazaOrion.id.in_(subquery))
        .all())
    
    # 3. Preparar los datos para la plantilla
    todos_los_tanques_lista = []
    if registros_recientes:
        for registro in registros_recientes:
            todos_los_tanques_lista.append({
                "TK": registro.tk, "PRODUCTO": registro.producto, "MAX_CAP": registro.max_cap,
                "BLS_60": registro.bls_60, "API": registro.api, 
                "BSW": registro.bsw, "S": registro.s, "grupo": registro.grupo
            })

    # 4. Calcular el total consolidado a partir de los datos filtrados
    total_consolidado = calcular_estadisticas(todos_los_tanques_lista)
    
    # 5. Agrupar los tanques en el diccionario que la plantilla espera
    datos_para_template = {}
    nombres_display = {
        "PRINCIPAL": "Tanque Principal (TK-101)", "MANZANILLO": "Barcaza Manzanillo (MGO)",
        "CR": "Barcaza CR", "MARGOTH": "Barcaza Margoth", "ODISEA": "Barcaza Odisea"
    }
    if todos_los_tanques_lista:
        for tanque in todos_los_tanques_lista:
            grupo_key = tanque.get("grupo")
            if grupo_key in nombres_display:
                nombre_barcaza = nombres_display[grupo_key]
                if nombre_barcaza not in datos_para_template:
                    datos_para_template[nombre_barcaza] = {"tanques": [], "totales": {}}
                datos_para_template[nombre_barcaza]["tanques"].append(tanque)
        
        # Calcular las estadísticas para cada grupo
        for nombre, data in datos_para_template.items():
            data["totales"] = calcular_estadisticas(data["tanques"])

    # 6. Formatear el mensaje de "Última actualización"
    fecha_actualizacion_info = "No hay registros para la fecha seleccionada."
    if registros_recientes:
        ultimo_registro = max(registros_recientes, key=lambda r: r.timestamp)
        fecha_formato_para_funcion = ultimo_registro.timestamp.strftime("%Y_%m_%d_%H_%M_%S")
        fecha_actualizacion_info = formatear_info_actualizacion(
            fecha_formato_para_funcion, 
            ultimo_registro.usuario
        )
    
    # 7. Renderizar la plantilla con todos los datos necesarios
    return render_template("reporte_barcaza_orion.html",
                           titulo="Reporte Interactivo - Barcaza Orion", # Título corregido
                           datos_para_template=datos_para_template,
                           total_consolidado=total_consolidado,
                           todos_los_tanques_json=json.dumps(todos_los_tanques_lista),
                           fecha_actualizacion_info=fecha_actualizacion_info,
                           fecha_seleccionada=fecha_seleccionada.isoformat(),
                           today_iso=date.today().isoformat())

@login_required
@app.route('/reporte_barcaza_bita')
def reporte_barcaza_bita():
    # La lógica de consulta es idéntica a la de la planilla
    fecha_str = request.args.get('fecha')
    try:
        fecha_seleccionada = date.fromisoformat(fecha_str) if fecha_str else date.today()
    except (ValueError, TypeError):
        fecha_seleccionada = date.today()

    timestamp_limite = datetime.combine(fecha_seleccionada, time.max)
    subquery = (db.session.query(func.max(RegistroBarcazaBita.id).label('max_id'))
        .filter(RegistroBarcazaBita.timestamp <= timestamp_limite).group_by(RegistroBarcazaBita.tk).subquery())
    registros_recientes = (db.session.query(RegistroBarcazaBita)
        .filter(RegistroBarcazaBita.id.in_(subquery)).all())

    # Preparar los datos y estadísticas para el reporte
    datos_reporte = []
    if registros_recientes:
        for r in registros_recientes:
            datos_reporte.append({
                "TK": r.tk, "PRODUCTO": r.producto, "MAX_CAP": r.max_cap,
                "BLS_60": r.bls_60, "API": r.api, "BSW": r.bsw, "S": r.s
            })

    total_consolidado = calcular_estadisticas(datos_reporte)
    tanques_marinse = [tk for tk in datos_reporte if tk.get('TK','').startswith('MARI')]
    tanques_oidech = [tk for tk in datos_reporte if tk.get('TK','').startswith('OID')]
    stats_marinse = calcular_estadisticas(tanques_marinse)
    stats_oidech = calcular_estadisticas(tanques_oidech)

    fecha_actualizacion_info = "No hay registros para la fecha seleccionada."
    if registros_recientes:
        ultimo_registro = max(registros_recientes, key=lambda r: r.timestamp)
        fecha_fmt = ultimo_registro.timestamp.strftime("%Y_%m_%d_%H_%M_%S")
        fecha_actualizacion_info = formatear_info_actualizacion(fecha_fmt, ultimo_registro.usuario)

    return render_template("reporte_barcaza_bita.html",
                           titulo="Reporte Interactivo - Barcaza BITA",
                           fecha_actualizacion_info=fecha_actualizacion_info,
                           nombre=session.get('nombre', 'Desconocido'),
                           total_consolidado=total_consolidado,
                           todos_los_tanques_json=json.dumps(datos_reporte),
                           tanques_marinse=tanques_marinse,
                           stats_marinse=stats_marinse,
                           tanques_oidech=tanques_oidech,
                           stats_oidech=stats_oidech,
                           fecha_seleccionada=fecha_seleccionada.isoformat(),
                           today_iso=date.today().isoformat())

@login_required
@permiso_requerido('barcaza_bita')
@app.route('/guardar-registro-bita', methods=['POST'])
def guardar_registro_bita():
    lista_tanques = request.get_json()
    if not lista_tanques or not isinstance(lista_tanques, list):
        return jsonify(success=False, message="No se recibieron datos o el formato es incorrecto."), 400

    try:
        for datos_tanque in lista_tanques:
            if not datos_tanque.get('TK'):
                continue
            
            nuevo_registro = RegistroBarcazaBita(
                usuario=session.get("nombre", "No identificado"),
                tk=datos_tanque.get('TK'),
                producto=datos_tanque.get('PRODUCTO'),
                max_cap=float(datos_tanque.get('MAX_CAP')) if datos_tanque.get('MAX_CAP') else None,
                bls_60=float(datos_tanque.get('BLS_60')) if datos_tanque.get('BLS_60') else None,
                api=float(datos_tanque.get('API')) if datos_tanque.get('API') else None,
                bsw=float(datos_tanque.get('BSW')) if datos_tanque.get('BSW') else None,
                s=float(datos_tanque.get('S')) if datos_tanque.get('S') else None
            )
            db.session.add(nuevo_registro)

        db.session.commit()
        return jsonify(success=True, message="Registro de Barcaza BITA guardado en la base de datos.")

    except Exception as e:
        db.session.rollback()
        print(f"Error al guardar Barcaza BITA en la base de datos: {e}")
        return jsonify(success=False, message=f"Error interno del servidor: {str(e)}"), 500

@login_required
@permiso_requerido('barcaza_orion')
@app.route('/guardar_registro_barcaza', methods=['POST'])
def guardar_registro_barcaza():
    # 1. Recibimos la lista de tanques desde la planilla
    lista_tanques = request.get_json()
    if not lista_tanques or not isinstance(lista_tanques, list):
        return jsonify(success=False, message="No se recibieron datos o el formato es incorrecto."), 400

    try:
        # 2. Recorremos cada tanque que se recibió
        for datos_tanque in lista_tanques:
            # Ignoramos filas vacías
            if not datos_tanque.get('TK'):
                continue
            
            # 3. Creamos una instancia del modelo de base de datos RegistroBarcazaOrion
            nuevo_registro = RegistroBarcazaOrion(
                usuario=session.get("nombre", "No identificado"),
                tk=datos_tanque.get('TK'),
                producto=datos_tanque.get('PRODUCTO'),
                grupo=datos_tanque.get('grupo'),
                max_cap=float(datos_tanque.get('MAX_CAP')) if datos_tanque.get('MAX_CAP') else None,
                bls_60=float(datos_tanque.get('BLS_60')) if datos_tanque.get('BLS_60') else None,
                api=float(datos_tanque.get('API')) if datos_tanque.get('API') else None,
                bsw=float(datos_tanque.get('BSW')) if datos_tanque.get('BSW') else None,
                s=float(datos_tanque.get('S')) if datos_tanque.get('S') else None
            )
            # 4. Añadimos la nueva "fila" a la sesión de la base de datos
            db.session.add(nuevo_registro)

        # 5. Guardamos todos los cambios de forma permanente
        db.session.commit()
        
        return jsonify(success=True, message="Registro de Barcaza Orion guardado en la BASE DE DATOS.")

    except Exception as e:
        # Si algo sale mal, deshacemos los cambios para mantener la integridad de los datos
        db.session.rollback()
        print(f"Error al guardar Barcaza Orion en la base de datos: {e}")
        return jsonify(success=False, message=f"Error al guardar en la base de datos: {str(e)}"), 500
    
@login_required
@app.route('/dashboard_reportes')
def dashboard_reportes():
    # El permiso de acceso no necesita cambios
    user_areas = session.get('area', [])
    if session.get('rol') != 'admin' and len(user_areas) == 1 and user_areas[0] == 'guia_transporte':
        return redirect(url_for('home_logistica'))

    # --- Resumen para PLANTA ---
    planta_summary = {'datos': [], 'info_completa': 'Sin Registros'}
    try:
        registros_planta = db.session.query(RegistroPlanta).all()
        # Filtramos para asegurarnos de que solo usamos registros con fecha
        registros_validos = [r for r in registros_planta if r.timestamp]
        if registros_validos:
            ultimo_registro = max(registros_validos, key=lambda r: r.timestamp)
            planta_summary['datos'] = registros_validos
            planta_summary['info_completa'] = formatear_info_actualizacion(
                ultimo_registro.timestamp, ultimo_registro.usuario
            )
    except Exception as e:
        print(f"Error al cargar resumen de Planta: {e}")

    # --- Resumen para BARCAZA ORION ---
    orion_summary = {'datos': [], 'info_completa': 'Sin Registros'}
    try:
        registros_orion = db.session.query(RegistroBarcazaOrion).all()
        registros_validos = [r for r in registros_orion if r.timestamp]
        if registros_validos:
            ultimo_registro = max(registros_validos, key=lambda r: r.timestamp)
            orion_summary['datos'] = registros_validos
            orion_summary['info_completa'] = formatear_info_actualizacion(
                ultimo_registro.timestamp, ultimo_registro.usuario
            )
    except Exception as e:
        print(f"Error al cargar resumen de Orion: {e}")

    # --- Resumen para BARCAZA BITA ---
    bita_summary = {'datos': [], 'info_completa': 'Sin Registros'}
    try:
        registros_bita = db.session.query(RegistroBarcazaBita).all()
        registros_validos = [r for r in registros_bita if r.timestamp]
        if registros_validos:
            ultimo_registro = max(registros_validos, key=lambda r: r.timestamp)
            bita_summary['datos'] = registros_validos
            bita_summary['info_completa'] = formatear_info_actualizacion(
                ultimo_registro.timestamp, ultimo_registro.usuario
            )
    except Exception as e:
        print(f"Error al cargar resumen de BITA: {e}")

    # --- Resumen para TRÁNSITO ---
    transito_summary = {'datos': [], 'refineria_count': 0, 'edms_count': 0, 'otros_count': 0, 'info_completa': 'Sin Registros'}
    try:
        registros_transito = db.session.query(RegistroTransito).all()
        registros_validos = [r for r in registros_transito if r.timestamp]
        if registros_validos:
            ultimo_registro = max(registros_validos, key=lambda r: r.timestamp)
            transito_summary['datos'] = registros_validos
            transito_summary['info_completa'] = formatear_info_actualizacion(
                ultimo_registro.timestamp, ultimo_registro.usuario
            )
            transito_summary['refineria_count'] = sum(1 for r in registros_validos if r.tipo_transito == 'refineria')
            transito_summary['edms_count'] = sum(1 for r in registros_validos if r.tipo_transito == 'general')
            
    except Exception as e:
        print(f"Error al cargar resumen de Tránsito: {e}")

    # --- Renderizar la plantilla ---
    return render_template("dashboard_reportes.html",
                           nombre=session.get("nombre"),
                           planta_summary=planta_summary,
                           orion_summary=orion_summary,
                           bita_summary=bita_summary,
                           transito_summary=transito_summary)

@login_required                        
@app.route('/guardar-datos-planta', methods=['POST'])
def guardar_datos_planta():
    if not request.is_json:
        return jsonify(success=False, message="Formato no válido"), 400

    data = request.get_json()
    tk = data.get("tk")
    field = data.get("field")
    value = data.get("value")

    if not all([tk, field]):
        return jsonify(success=False, message="Datos incompletos"), 400

    for fila in PLANILLA_PLANTA:
        if fila["TK"] == tk and field in fila:
            fila[field] = value
            return jsonify(success=True)

    return jsonify(success=False, message="Tanque o campo no encontrado"), 404

@login_required
@permiso_requerido('planta')
@app.route('/guardar-registro-planta', methods=['POST'])
def guardar_registro_planta():
    # 1. Recibimos la lista de tanques desde la planilla (esto no cambia)
    lista_tanques = request.get_json()
    if not isinstance(lista_tanques, list):
        return jsonify(success=False, message="Formato de datos incorrecto."), 400

    try:
        # 2. Recorremos cada tanque que se recibió
        for datos_tanque in lista_tanques:
            # Si una fila está vacía (sin TK), la ignoramos para no guardar basura
            if not datos_tanque.get('TK'):
                continue

            # 3. Creamos una fila nueva para nuestra tabla 'RegistroPlanta'
            nuevo_registro = RegistroPlanta(
               # timestamp=(datetime.utcnow() - timedelta(days=1)),# 
                usuario=session.get("nombre", "No identificado"),
                tk=datos_tanque.get('TK'),
                producto=datos_tanque.get('PRODUCTO'),
                # Convertimos a float, si está vacío o da error, guardamos None (NULO en la base de datos)
                max_cap=float(datos_tanque.get('MAX_CAP')) if datos_tanque.get('MAX_CAP') else None,
                bls_60=float(datos_tanque.get('BLS_60')) if datos_tanque.get('BLS_60') else None,
                api=float(datos_tanque.get('API')) if datos_tanque.get('API') else None,
                bsw=float(datos_tanque.get('BSW')) if datos_tanque.get('BSW') else None,
                s=float(datos_tanque.get('S')) if datos_tanque.get('S') else None
            )
            
            # 4. Añadimos el nuevo registro a la 'sesión' (una zona de preparación)
            db.session.add(nuevo_registro)

        # 5. Guardamos TODO en la base de datos de forma permanente
        db.session.commit()
        
        return jsonify(success=True, message="Registro guardado en la BASE DE DATOS exitosamente.")

    except Exception as e:
        # 6. Si algo sale mal, revertimos los cambios para no dejar datos corruptos
        db.session.rollback()
        print(f"Error al guardar en la base de datos para planta: {e}")
        return jsonify(success=False, message=f"Error interno del servidor al guardar en la base de datos: {str(e)}"), 500


@app.route('/')
def home():
    """Redirige al usuario a su página de inicio correcta después de iniciar sesión."""
    if 'email' not in session:
        return redirect(url_for('login'))

    # Si el rol es 'admin', siempre va al dashboard completo.
    if session.get('rol') == 'admin':
        return redirect(url_for('dashboard_reportes'))
    
    # Si el usuario es de logística (y no es admin), va a su página de inicio especial.
    # Comprobamos si 'guia_transporte' es su ÚNICO permiso para evitar confusiones.
    user_areas = session.get('area', [])
    if len(user_areas) == 1 and user_areas[0] == 'guia_transporte':
        return redirect(url_for('home_logistica'))

    # Todos los demás usuarios van al dashboard general.
    return redirect(url_for('dashboard_reportes'))

@login_required
@permiso_requerido('guia_transporte')
@app.route('/inicio-logistica')
def home_logistica():
    """Página de inicio simplificada para el área de logística."""
    return render_template('home_logistica.html')

@app.route('/test')
def test():
    return "✅ El servidor Flask está funcionando"
@app.route('/debug/productos')

def debug_productos():
    productos = cargar_productos()
    return jsonify({
        "productos": productos,
        "exists": os.path.exists("productos.json"),
        "file_content": open("productos.json").read() if os.path.exists("productos.json") else None
    })

def cargar_clientes():
    """Función auxiliar para cargar clientes desde Clientes.json de forma segura."""
    try:
        # Buscamos el archivo en la carpeta 'static'
        ruta_clientes = os.path.join(BASE_DIR, 'static', 'Clientes.json')
        with open(ruta_clientes, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Si el archivo no existe o está vacío/corrupto, devuelve una lista vacía.
        return []

def guardar_clientes(clientes):
    """Función auxiliar para guardar la lista de clientes en Clientes.json."""
    # Buscamos el archivo en la carpeta 'static'
    ruta_clientes = os.path.join(BASE_DIR, 'static', 'Clientes.json')
    with open(ruta_clientes, 'w', encoding='utf-8') as f:
        json.dump(clientes, f, ensure_ascii=False, indent=4)

@login_required
@app.route('/gestionar_clientes')
def gestionar_clientes():    
    clientes_actuales = cargar_clientes()
    return render_template('gestionar_clientes.html', clientes=clientes_actuales)

@login_required
@app.route('/guardar_cliente', methods=['POST'])
def guardar_cliente():

    nombre = request.form.get('nombre_cliente')
    direccion = request.form.get('direccion_cliente')
    ciudad = request.form.get('ciudad_cliente')

    if not nombre or not direccion or not ciudad:
        flash("Todos los campos son obligatorios.", "danger")
        return redirect(url_for('gestionar_clientes'))

    clientes = cargar_clientes()
    
    # Opcional: Verificar si el cliente ya existe para no duplicarlo
    if any(c['NOMBRE_CLIENTE'].lower() == nombre.lower() for c in clientes):
        flash(f"El cliente '{nombre}' ya existe en la base de datos.", "warning")
        return redirect(url_for('gestionar_clientes'))

    nuevo_cliente = {
        "NOMBRE_CLIENTE": nombre.upper(),
        "DIRECCION": direccion.upper(),
        "CIUDAD_DEPARTAMENTO": ciudad.upper()
    }
    clientes.append(nuevo_cliente)
    
    # Ordenar la lista alfabéticamente por nombre de cliente
    clientes.sort(key=lambda x: x['NOMBRE_CLIENTE'])

    guardar_clientes(clientes)

    flash(f"Cliente '{nombre}' agregado exitosamente.", "success")
    return redirect(url_for('gestionar_clientes'))

@login_required
@app.route('/agregar_cliente_ajax', methods=['POST'])
def agregar_cliente_ajax():

    data = request.get_json()
    nombre = data.get('nombre')
    direccion = data.get('direccion')
    ciudad = data.get('ciudad')

    if not nombre or not direccion or not ciudad:
        return jsonify(success=False, message="Todos los campos son obligatorios."), 400

    clientes = cargar_clientes()

    if any(c.get('NOMBRE_CLIENTE', '').lower() == nombre.lower() for c in clientes):
        return jsonify(success=False, message=f"El cliente '{nombre}' ya existe."), 409 # 409 Conflict

    nuevo_cliente = {
        "NOMBRE_CLIENTE": nombre.upper(),
        "DIRECCION": direccion.upper(),
        "CIUDAD_DEPARTAMENTO": ciudad.upper()
    }
    clientes.append(nuevo_cliente)
    clientes.sort(key=lambda x: x['NOMBRE_CLIENTE'])
    guardar_clientes(clientes)
    return jsonify(success=True, message="Cliente agregado exitosamente.", nuevo_cliente=nuevo_cliente)

@login_required
@permiso_requerido('planilla_precios')
@app.route('/planilla_precios')
def planilla_precios():
    # La lógica para cargar los datos se mantiene igual
    datos_guardados = []
    try:
        carpeta = "registros"
        archivos_precios = sorted([a for a in os.listdir(carpeta) if a.startswith("precios_") and a.endswith(".json")], reverse=True)
        if archivos_precios:
            ruta_reciente = os.path.join(carpeta, archivos_precios[0])
            with open(ruta_reciente, 'r', encoding='utf-8') as f:
                contenido = json.load(f)
            datos_guardados = contenido.get("datos", [])
    except Exception as e:
        print(f"Error cargando planilla de precios: {e}")
        pass

    fuente_de_datos = datos_guardados if datos_guardados else PLANILLA_PRECIOS

    # ¡Ya no necesitamos la clave de Google!
    # Simplemente renderizamos la plantilla con los datos de la planilla.
    return render_template('planilla_precios.html',
                           planilla=fuente_de_datos,
                           nombre=session.get("nombre"))

def cargar_conductores():
    """Función auxiliar para cargar conductores desde Conductores.json de forma segura."""
    try:
        ruta_conductores = os.path.join(BASE_DIR, 'static', 'Conductores.json')
        with open(ruta_conductores, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def guardar_conductores(conductores):
    """Función auxiliar para guardar la lista de conductores en Conductores.json."""
    try:
        ruta_conductores = os.path.join(BASE_DIR, 'static', 'Conductores.json')
        with open(ruta_conductores, 'w', encoding='utf-8') as f:
            json.dump(conductores, f, ensure_ascii=False, indent=4)
        return True # Devuelve True si todo salió bien
    except (IOError, PermissionError) as e:
        # Captura errores de escritura o de permisos
        print(f"ERROR AL GUARDAR: No se pudo escribir en el archivo Conductores.json. Causa: {e}")
        return False # Devuelve False si hubo un error

def cargar_empresas():
    """Función auxiliar para cargar empresas desde EmpresasTransportadoras.json."""
    try:
        ruta_empresas = os.path.join(BASE_DIR, 'static', 'EmpresasTransportadoras.json')
        if not os.path.exists(ruta_empresas):
            return [] # Si el archivo no existe, devuelve una lista vacía
        with open(ruta_empresas, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def guardar_empresas(empresas):
    """Función auxiliar para guardar la lista de empresas en EmpresasTransportadoras.json."""
    ruta_empresas = os.path.join(BASE_DIR, 'static', 'EmpresasTransportadoras.json')
    with open(ruta_empresas, 'w', encoding='utf-8') as f:
        json.dump(empresas, f, ensure_ascii=False, indent=4)        

@login_required
@app.route('/agregar_conductor_ajax', methods=['POST'])
def agregar_conductor_ajax():
        
    data = request.get_json()
    nombre = str(data.get('nombre', ''))
    cedula = str(data.get('cedula', ''))
    placa = str(data.get('placa', ''))

    if not nombre or not cedula or not placa:
        return jsonify(success=False, message="Todos los campos son obligatorios."), 400

    conductores = cargar_conductores()

    # Verificación de duplicados (versión segura)
    if any(c.get('CEDULA', '').lower() == cedula.lower() for c in conductores):
        return jsonify(success=False, message=f"Un conductor con la cédula '{cedula}' ya existe."), 409

    nuevo_conductor = {
        "CONDUCTOR": nombre.upper(),
        "CEDULA": cedula.upper(),
        "PLACA": placa.upper()
    }
    conductores.append(nuevo_conductor)
    
    # Ordenar la lista (versión segura)
    conductores.sort(key=lambda x: x.get('CONDUCTOR', ''))
    
    # Guardar los datos y comprobar el resultado
    guardado_exitoso = guardar_conductores(conductores)

    if guardado_exitoso:
        return jsonify(success=True, message="Conductor agregado exitosamente.", nuevo_conductor=nuevo_conductor)
    else:
        return jsonify(success=False, message="Error del servidor: No se pudo escribir en el archivo de conductores."), 500

@login_required
@app.route('/agregar_empresa_ajax', methods=['POST'])
def agregar_empresa_ajax():
    data = request.get_json()
    nombre = data.get('nombre')

    if not nombre:
        return jsonify(success=False, message="El nombre es obligatorio."), 400

    empresas = cargar_empresas()

    if any(e['NOMBRE_EMPRESA'].lower() == nombre.lower() for e in empresas):
        return jsonify(success=False, message=f"La empresa '{nombre}' ya existe."), 409

    nueva_empresa = { "NOMBRE_EMPRESA": nombre.upper() }
    empresas.append(nueva_empresa)
    empresas.sort(key=lambda x: x['NOMBRE_EMPRESA'])
    guardar_empresas(empresas)

    return jsonify(success=True, message="Empresa agregada exitosamente.", nueva_empresa=nueva_empresa)


@app.cli.command("init-db")
def init_db_command():
    """Crea las tablas nuevas de la base de datos."""
    db.create_all()
    print("Base de datos inicializada y tablas creadas.")


with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
