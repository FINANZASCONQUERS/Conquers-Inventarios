import json
from datetime import datetime, time, date, timedelta 
import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file # Añadido send_file
from werkzeug.security import generate_password_hash, check_password_hash
import openpyxl 
from io import BytesIO # Para Excel
import logging # Para un logging más flexible
import copy
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
import pytz
import pandas as pd
from flask import g
from flask import Response
from weasyprint import HTML, CSS
import math
from sqlalchemy import or_
from flask_migrate import Migrate 

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
migrate = Migrate(app, db)

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

class RegistroZisa(db.Model):
    __tablename__ = 'registros_zisa'
    id = db.Column(db.Integer, primary_key=True)
    
    empresa = db.Column(db.String(50), nullable=False, default='ZISA', index=True)
    
    # Columnas de la planilla
    mes = db.Column(db.String(50), nullable=False)
    carrotanque = db.Column(db.String(100))
    producto = db.Column(db.String(100))
    numero_sae = db.Column(db.String(50)) # Para la columna "N° S.A.E"
    acta = db.Column(db.String(50))
    bbl_netos = db.Column(db.Float)
    bbl_descargados = db.Column(db.Float)

    # Datos de auditoría
    usuario_carga = db.Column(db.String(100), nullable=False)
    fecha_carga = db.Column(db.DateTime, default=datetime.utcnow)

    estado = db.Column(db.String(50), default='Disponible', nullable=False)

    def __repr__(self):
        return f'<RegistroZisa id={self.id} carrotanque={self.carrotanque}>'  

class DefinicionCrudo(db.Model):
    __tablename__ = 'definiciones_crudo'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False, index=True)
    api = db.Column(db.Float)
    sulfur = db.Column(db.Float, nullable=True)      
    viscosity = db.Column(db.Float, nullable=True)    
    curva_json = db.Column(db.Text, nullable=False)

    def __repr__(self):
        return f'<DefinicionCrudo {self.nombre}>'
    

    
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
    "area": ["reportes", "planilla_precios", "simulador_rendimiento"]
},

    "david.restrepo@conquerstrading.com": {
        "password": generate_password_hash("Conquers2025"),
        "nombre": "David Restrepo",
        "rol": "viewer",
        "area": ["reportes", "planilla_precios", "simulador_rendimiento"] 
    },

    "finance@conquerstrading.com": {
        "password": generate_password_hash("Conquers2025"),
        "nombre": "Germna Galvis",
        "rol": "viewer",
        "area": ["reportes", "planilla_precios"] 
    },
    
    # Ignacio (Editor): Solo acceso a Planta y Rendimientos
    "production@conquerstrading.com": {
        "password": generate_password_hash("Conquers2025"),
        "nombre": "Ignacio Quimbayo",
        "rol": "editor",
        "area": ["planta", "simulador_rendimiento"] 
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
    },

    "comex@conquerstrading.com": {
        "password": generate_password_hash("Conquers2025"),     
        "nombre": "Daniela Cuadrado",
        "rol": "editor",
        "area": ["zisa_inventory"] 
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
                           filtros=filtros)

@login_required
@app.route('/marcar-descargado/<int:registro_id>', methods=['POST'])
def marcar_descargado(registro_id):
    try:
        registro = db.session.query(RegistroTransito).get(registro_id)
        if registro:
            registro.estado = 'Descargado'
            db.session.commit()
            return jsonify(success=True, message="Registro marcado como 'Descargado'.")
        return jsonify(success=False, message="Registro no encontrado."), 404
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, message=f"Error interno: {str(e)}"), 500

@login_required
@app.route('/marcar-en-transito/<int:registro_id>', methods=['POST'])
def marcar_en_transito(registro_id):
    try:
        registro = db.session.query(RegistroTransito).get(registro_id)
        if registro:
            registro.estado = 'En Tránsito'
            db.session.commit()
            return jsonify(success=True, message="Registro reactivado a 'En Tránsito'.")
        return jsonify(success=False, message="Registro no encontrado."), 404
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, message=f"Error interno: {str(e)}"), 500
    
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
    # 1. La lógica del filtro de fecha no cambia
    fecha_str = request.args.get('fecha')
    try:
        fecha_seleccionada = date.fromisoformat(fecha_str) if fecha_str else date.today()
    except (ValueError, TypeError):
        fecha_seleccionada = date.today()
    
    timestamp_limite = datetime.combine(fecha_seleccionada, time.max)

    # 2. La consulta a la base de datos no cambia
    subquery = (db.session.query(
        func.max(RegistroPlanta.id).label('max_id')
    ).filter(
        RegistroPlanta.timestamp <= timestamp_limite
    ).group_by(RegistroPlanta.tk).subquery())

    registros_recientes = (db.session.query(RegistroPlanta)
        .filter(RegistroPlanta.id.in_(subquery))
        .all())
    
    # 3. Preparamos los datos y la información
    datos_planta_js = []
    fecha_actualizacion_info = "No hay registros para la fecha seleccionada."

    if registros_recientes:
        # ========================================================
        #  INICIO: LÓGICA DE ORDENAMIENTO PERSONALIZADO
        # ========================================================
        
        # 1. Definimos el orden exacto que queremos.
        orden_deseado = ["TK-109", "TK-110", "TK-102", "TK-01", "TK-02"]
        
        # 2. Creamos un mapa para asignar un "peso" a cada TK.
        orden_map = {tk: i for i, tk in enumerate(orden_deseado)}
        
        # 3. Ordenamos la lista de registros usando nuestro mapa.
        #    Los tanques no especificados en la lista irán al final.
        registros_ordenados = sorted(
            registros_recientes, 
            key=lambda r: orden_map.get(r.tk, 99) # Usamos 99 para que los no encontrados vayan al final
        )
        
        # ========================================================
        #  FIN DE LA LÓGICA DE ORDENAMIENTO
        # ========================================================

        # Usamos la nueva lista YA ORDENADA para construir los datos para el HTML
        for registro in registros_ordenados:
            datos_planta_js.append({
                "TK": registro.tk,
                "PRODUCTO": registro.producto,
                "MAX_CAP": registro.max_cap,
                "BLS_60": registro.bls_60,
                "API": registro.api,
                "BSW": registro.bsw,
                "S": registro.s
            })
        
        # La lógica para la fecha de actualización no cambia
        ultimo_registro_general = max(registros_recientes, key=lambda r: r.timestamp)
        fecha_formato = ultimo_registro_general.timestamp.strftime("%Y_%m_%d_%H_%M_%S")
        fecha_actualizacion_info = formatear_info_actualizacion(
            fecha_formato, 
            ultimo_registro_general.usuario
        )

    # 4. Renderizamos la plantilla con los datos ya ordenados
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
@permiso_requerido('transito') # <--- LÍNEA CORREGIDA
@app.route('/subir_excel_transito', methods=['POST'])
def subir_excel_transito():
    """
    Procesa un archivo Excel subido para cargar datos en la planilla de tránsito.
    """
    if 'archivo_excel' not in request.files:
        return jsonify({'success': False, 'message': "No se encontró el archivo en la solicitud."}), 400

    archivo = request.files['archivo_excel']
    tipo_transito = request.form.get('tipo_transito', 'general')
    sobrescribir = request.form.get('sobrescribirDatos') == 'on'

    if archivo.filename == '':
        return jsonify({'success': False, 'message': "No se seleccionó ningún archivo."}), 400

    if not archivo.filename.endswith('.xlsx'):
        return jsonify({'success': False, 'message': "Formato no válido. Por favor, suba un archivo .xlsx"}), 400

    try:
        # Si se marca "Sobrescribir", se borran los registros de hoy para esa planilla.
        if sobrescribir:
            today_start = datetime.combine(date.today(), time.min)
            today_end = datetime.combine(date.today(), time.max)
            
            num_borrados = db.session.query(RegistroTransito).filter(
                RegistroTransito.tipo_transito == tipo_transito,
                RegistroTransito.timestamp >= today_start,
                RegistroTransito.timestamp <= today_end
            ).delete(synchronize_session=False)
            
            db.session.commit()
            print(f"Sobrescribiendo: Se eliminaron {num_borrados} registros de hoy para '{tipo_transito}'.")

        workbook = openpyxl.load_workbook(archivo)
        sheet = workbook.active
        
        nuevos_registros = []
        filas_con_error = 0
        
        for row_index in range(2, sheet.max_row + 1):
            row_data = [cell.value for cell in sheet[row_index]]
            
            if not any(row_data) or not row_data[1]:
                continue
            
            try:
                def safe_float(value):
                    if value is None: return None
                    return float(str(value).replace(',', '.'))

                fecha = row_data[0]
                if isinstance(fecha, datetime):
                    fecha = fecha.strftime('%Y-%m-%d')
                else:
                    fecha = str(fecha) if fecha else None

                nuevo_registro = RegistroTransito(
                    usuario=session.get("nombre", "Carga Excel"),
                    tipo_transito=tipo_transito,
                    fecha=fecha,
                    guia=str(row_data[1]),
                    origen=str(row_data[2]),
                    producto=str(row_data[3]),
                    placa=str(row_data[4]),
                    api=safe_float(row_data[5]),
                    bsw=safe_float(row_data[6]),
                    nsv=safe_float(row_data[7]),
                    observaciones=str(row_data[8]) if len(row_data) > 8 and row_data[8] else ""
                )
                nuevos_registros.append(nuevo_registro)
            except (ValueError, TypeError, IndexError) as e:
                filas_con_error += 1
                app.logger.warning(f"ADVERTENCIA: Saltando fila {row_index} del Excel por error de formato: {e}")
                continue

        if not nuevos_registros:
            return jsonify({'success': False, 'message': "No se encontraron registros válidos para cargar en el archivo."}), 400
        
        db.session.add_all(nuevos_registros)
        db.session.commit()
        
        message = f"Se han cargado y guardado {len(nuevos_registros)} registros exitosamente."
        if filas_con_error > 0:
            message += f" Se saltaron {filas_con_error} filas por errores de formato."

        return jsonify({'success': True, 'message': message})

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error crítico al procesar el archivo Excel: {e}")
        return jsonify({'success': False, 'message': f"Error interno del servidor: {str(e)}"}), 500

    
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
    ).filter(RegistroBarcazaOrion.timestamp <= timestamp_limite).group_by(RegistroBarcazaOrion.tk, RegistroBarcazaOrion.grupo).subquery())

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
@permiso_requerido("zisa_inventory") # Usamos el permiso que le asignamos a Daniela
@app.route('/inicio-siza')
def home_siza():
    """Página de inicio personalizada para el módulo de Inventario SIZA."""
    return render_template('home_siza.html')

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
    ).group_by(RegistroBarcazaOrion.tk, RegistroBarcazaOrion.grupo).subquery())

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
    if not isinstance(lista_tanques, list):
        return jsonify(success=False, message="Formato de datos incorrecto."), 400

    try:
        today_start = datetime.combine(date.today(), time.min)
        today_end = datetime.combine(date.today(), time.max)

        for datos_tanque in lista_tanques:
            tk = datos_tanque.get('TK')
            if not tk: continue

            registro_existente = db.session.query(RegistroBarcazaBita).filter(
                RegistroBarcazaBita.tk == tk,
                RegistroBarcazaBita.timestamp.between(today_start, today_end)
            ).first()

            if registro_existente:
                # ACTUALIZAR
                registro_existente.usuario = session.get("nombre", "No identificado")
                registro_existente.bls_60 = float(datos_tanque.get('BLS_60')) if datos_tanque.get('BLS_60') else None
                registro_existente.api = float(datos_tanque.get('API')) if datos_tanque.get('API') else None
                registro_existente.bsw = float(datos_tanque.get('BSW')) if datos_tanque.get('BSW') else None
                registro_existente.s = float(datos_tanque.get('S')) if datos_tanque.get('S') else None
                registro_existente.timestamp = datetime.utcnow()
            else:
                # CREAR
                nuevo_registro = RegistroBarcazaBita(
                    timestamp=datetime.utcnow(),
                    usuario=session.get("nombre", "No identificado"),
                    tk=tk,
                    producto=datos_tanque.get('PRODUCTO'),
                    max_cap=float(datos_tanque.get('MAX_CAP')) if datos_tanque.get('MAX_CAP') else None,
                    bls_60=float(datos_tanque.get('BLS_60')) if datos_tanque.get('BLS_60') else None,
                    api=float(datos_tanque.get('API')) if datos_tanque.get('API') else None,
                    bsw=float(datos_tanque.get('BSW')) if datos_tanque.get('BSW') else None,
                    s=float(datos_tanque.get('S')) if datos_tanque.get('S') else None
                )
                db.session.add(nuevo_registro)
        
        db.session.commit()
        return jsonify(success=True, message="Inventario de Barcaza BITA actualizado.")
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, message=f"Error interno: {str(e)}"), 500

@login_required
@permiso_requerido('barcaza_orion')
@app.route('/guardar_registro_barcaza', methods=['POST'])
def guardar_registro_barcaza():
    lista_tanques = request.get_json()
    if not isinstance(lista_tanques, list):
        return jsonify(success=False, message="Formato incorrecto."), 400
    
    try:
        today_start = datetime.combine(date.today(), time.min)
        today_end = datetime.combine(date.today(), time.max)

        for datos_tanque in lista_tanques:
            tk = datos_tanque.get('TK')
            grupo = datos_tanque.get('grupo')
            if not tk or not grupo: continue

            registro_existente = db.session.query(RegistroBarcazaOrion).filter(
                RegistroBarcazaOrion.tk == tk,
                RegistroBarcazaOrion.grupo == grupo,
                RegistroBarcazaOrion.timestamp.between(today_start, today_end)
            ).first()

            if registro_existente:
                # ACTUALIZAR
                registro_existente.usuario = session.get("nombre", "No identificado")
                registro_existente.bls_60 = float(datos_tanque.get('BLS_60')) if datos_tanque.get('BLS_60') else None
                registro_existente.api = float(datos_tanque.get('API')) if datos_tanque.get('API') else None
                registro_existente.bsw = float(datos_tanque.get('BSW')) if datos_tanque.get('BSW') else None
                registro_existente.s = float(datos_tanque.get('S')) if datos_tanque.get('S') else None
                registro_existente.timestamp = datetime.utcnow()
            else:
                # CREAR
                nuevo_registro = RegistroBarcazaOrion(
                    timestamp=datetime.utcnow(),
                    usuario=session.get("nombre", "No identificado"),
                    tk=tk,
                    grupo=grupo,
                    producto=datos_tanque.get('PRODUCTO'),
                    max_cap=float(datos_tanque.get('MAX_CAP')) if datos_tanque.get('MAX_CAP') else None,
                    bls_60=float(datos_tanque.get('BLS_60')) if datos_tanque.get('BLS_60') else None,
                    api=float(datos_tanque.get('API')) if datos_tanque.get('API') else None,
                    bsw=float(datos_tanque.get('BSW')) if datos_tanque.get('BSW') else None,
                    s=float(datos_tanque.get('S')) if datos_tanque.get('S') else None
                )
                db.session.add(nuevo_registro)
        
        db.session.commit()
        return jsonify(success=True, message="Inventario de Barcaza Orion actualizado.")
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, message=f"Error interno: {str(e)}"), 500
    
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
    lista_tanques = request.get_json()
    if not isinstance(lista_tanques, list):
        return jsonify(success=False, message="Formato de datos incorrecto."), 400

    try:
        today_start = datetime.combine(date.today(), time.min)
        today_end = datetime.combine(date.today(), time.max)

        for datos_tanque in lista_tanques:
            tk = datos_tanque.get('TK')
            if not tk: continue

            registro_existente = db.session.query(RegistroPlanta).filter(
                RegistroPlanta.tk == tk,
                RegistroPlanta.timestamp.between(today_start, today_end)
            ).first()

            if registro_existente:
                # Si existe, lo ACTUALIZAMOS
                registro_existente.usuario = session.get("nombre", "No identificado")
                registro_existente.bls_60 = float(datos_tanque.get('BLS_60')) if datos_tanque.get('BLS_60') else None
                registro_existente.api = float(datos_tanque.get('API')) if datos_tanque.get('API') else None
                registro_existente.bsw = float(datos_tanque.get('BSW')) if datos_tanque.get('BSW') else None
                registro_existente.s = float(datos_tanque.get('S')) if datos_tanque.get('S') else None
                registro_existente.timestamp = datetime.utcnow()
            else:
                # Si no existe para hoy, CREAMOS uno nuevo
                nuevo_registro = RegistroPlanta(
                    timestamp=datetime.utcnow(),
                    usuario=session.get("nombre", "No identificado"),
                    tk=tk,
                    producto=datos_tanque.get('PRODUCTO'),
                    max_cap=float(datos_tanque.get('MAX_CAP')) if datos_tanque.get('MAX_CAP') else None,
                    bls_60=float(datos_tanque.get('BLS_60')) if datos_tanque.get('BLS_60') else None,
                    api=float(datos_tanque.get('API')) if datos_tanque.get('API') else None,
                    bsw=float(datos_tanque.get('BSW')) if datos_tanque.get('BSW') else None,
                    s=float(datos_tanque.get('S')) if datos_tanque.get('S') else None
                )
                db.session.add(nuevo_registro)
        
        db.session.commit()
        return jsonify(success=True, message="Inventario de planta actualizado exitosamente.")
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, message=f"Error interno: {str(e)}"), 500
    
@login_required
@permiso_requerido('zisa_inventory')    
@app.route('/inventario-zisa')
def inventario_zisa():
    # 1. Definimos la variable global 'g.current_time' para que la plantilla la pueda usar
    # Usamos la zona horaria de Bogotá que ya tienes configurada en otras partes
    try:
        bogota_zone = pytz.timezone('America/Bogota')
        g.current_time = datetime.now(bogota_zone)
    except Exception:
        g.current_time = datetime.now() # Fallback por si acaso

    # 2. Consultamos todos los registros de la tabla
    todos_los_registros = RegistroZisa.query.order_by(RegistroZisa.fecha_carga.desc()).all()
    
    # 3. Los separamos por empresa para las tablas
    registros_zisa = [r for r in todos_los_registros if r.empresa == 'ZISA']
    registros_fbcol = [r for r in todos_los_registros if r.empresa == 'FBCOL']

    # 4. Calculamos los totales de inventario disponible para las tarjetas de resumen
    total_zisa = db.session.query(func.sum(RegistroZisa.bbl_descargados)).filter_by(estado='Disponible', empresa='ZISA').scalar() or 0.0
    total_fbcol = db.session.query(func.sum(RegistroZisa.bbl_descargados)).filter_by(estado='Disponible', empresa='FBCOL').scalar() or 0.0
    
    # 5. Enviamos TODAS las variables que la plantilla necesita
    return render_template('inventario_zisa.html', 
                           registros_zisa=registros_zisa,
                           registros_fbcol=registros_fbcol,
                           total_zisa=total_zisa,       # <-- Variable añadida
                           total_fbcol=total_fbcol,     # <-- Variable añadida
                           nombre=session.get("nombre"))
@login_required
@permiso_requerido('zisa_inventory')
@app.route('/cargar-inventario-zisa', methods=['POST'])
def cargar_inventario_zisa():
    if 'archivo_excel' not in request.files:
        flash('No se seleccionó ningún archivo.', 'warning')
        return redirect(url_for('inventario_zisa'))

    archivo = request.files['archivo_excel']
    
    if not archivo.filename.lower().endswith('.xlsx'):
        flash('Formato de archivo no válido. Por favor, suba un archivo .xlsx', 'danger')
        return redirect(url_for('inventario_zisa'))

    try:
        xls = pd.ExcelFile(archivo)
        hojas_a_procesar = {'CWT 2025': 'ZISA', 'FBCOL 2025': 'FBCOL'}
        resultados = {'nuevos': 0, 'duplicados': 0, 'errores': 0}
        resumen = []

        for hoja, empresa in hojas_a_procesar.items():
            if hoja not in xls.sheet_names:
                resumen.append(f"Hoja '{hoja}' no encontrada - Saltada")
                continue

            try:
                df = pd.read_excel(xls, sheet_name=hoja)
                df.columns = df.columns.str.strip().str.upper()
                
                # Validación de columnas
                columnas_requeridas = {'MES', 'CARROTANQUE', 'PRODUCTO', 'N S.A.E', 'ACTA', 'BBL NETOS', 'VEHICULOS DESCARGADOS'}
                if not columnas_requeridas.issubset(df.columns):
                    faltantes = columnas_requeridas - set(df.columns)
                    resumen.append(f"Error en '{hoja}': Faltan columnas: {', '.join(faltantes)}")
                    resultados['errores'] += 1
                    continue
                
                # Procesamiento del DataFrame
                df = df.dropna(subset=['ACTA', 'CARROTANQUE'])
                nuevos = 0
                duplicados = 0
                
                for _, fila in df.iterrows():
                    try:
                        existe = RegistroZisa.query.filter_by(
                            empresa=empresa,
                            acta=str(fila['ACTA']),
                            carrotanque=str(fila['CARROTANQUE'])
                        ).first()

                        if not existe:
                            registro = RegistroZisa(
                                empresa=empresa,
                                mes=fila['MES'],
                                carrotanque=str(fila['CARROTANQUE']),
                                producto=fila['PRODUCTO'],
                                numero_sae=fila['N S.A.E'],
                                acta=str(fila['ACTA']),
                                bbl_netos=float(fila['BBL NETOS']),
                                bbl_descargados=float(fila['VEHICULOS DESCARGADOS']),
                                usuario_carga=session.get('nombre', 'Desconocido'),
                                estado='Disponible'
                            )
                            db.session.add(registro)
                            nuevos += 1
                        else:
                            duplicados += 1
                    except Exception as e:
                        app.logger.error(f"Error procesando fila en {hoja}: {str(e)}")
                        resultados['errores'] += 1

                db.session.commit()
                resultados['nuevos'] += nuevos
                resultados['duplicados'] += duplicados
                resumen.append(f"{hoja}: {nuevos} nuevos, {duplicados} duplicados")
                
            except Exception as e:
                db.session.rollback()
                app.logger.error(f"Error procesando hoja {hoja}: {str(e)}")
                resumen.append(f"Error procesando {hoja}: {str(e)}")
                resultados['errores'] += 1

        # Resultado final
        if resultados['nuevos'] > 0:
            flash(f"Procesamiento completado: {resultados['nuevos']} nuevos registros", 'success')
        if resultados['duplicados'] > 0:
            flash(f"{resultados['duplicados']} registros duplicados omitidos", 'info')
        if resultados['errores'] > 0:
            flash(f"Se encontraron {resultados['errores']} errores durante el procesamiento", 'warning')
        
        for mensaje in resumen:
            flash(mensaje, 'info')

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error crítico al procesar archivo: {str(e)}")
        flash(f'Error al procesar el archivo: {str(e)}', 'danger')
    
    return redirect(url_for('inventario_zisa'))

@login_required
@permiso_requerido('zisa_inventory')
@app.route('/consumir-inventario', methods=['GET', 'POST'])
def consumir_inventario():
    if request.method == 'POST':
        try:
            # --- DIAGNÓSTICO: Imprimimos lo que recibimos del formulario ---
            print("="*30)
            print("INICIANDO PROCESO DE CONSUMO")
            cantidad_a_consumir = float(request.form.get('cantidad_a_gastar', 0))
            empresa = request.form.get('empresa')
            print(f"--> Solicitud para consumir {cantidad_a_consumir} BBL de la empresa: {empresa}")

            if cantidad_a_consumir <= 0 or not empresa:
                flash('La cantidad debe ser positiva y debes seleccionar una empresa.', 'warning')
                return redirect(url_for('consumir_inventario'))

            registros_disponibles = RegistroZisa.query.filter_by(
                empresa=empresa, estado='Disponible'
            ).order_by(RegistroZisa.fecha_carga.asc()).all()

            total_disponible_en_bd = sum(r.bbl_descargados for r in registros_disponibles if r.bbl_descargados)
            if total_disponible_en_bd < cantidad_a_consumir:
                flash(f'Inventario insuficiente en {empresa}. Disponible: {total_disponible_en_bd:.2f} BBL, Solicitado: {cantidad_a_consumir:.2f} BBL', 'danger')
                return redirect(url_for('consumir_inventario'))
            
            cantidad_restante = cantidad_a_consumir
            actas_consumidas = []
            
            for registro in registros_disponibles:
                if cantidad_restante <= 0:
                    break
                
                # --- MEJORA DE ROBUSTEZ: Manejo de valores nulos o cero ---
                bbl_del_registro = registro.bbl_descargados or 0.0
                
                # --- DIAGNÓSTICO: Imprimimos cada registro que se va a procesar ---
                print(f"Procesando registro ID={registro.id}, Acta={registro.acta}, BBL_Descargados={bbl_del_registro}")

                # --- MEJORA DE ROBUSTEZ: Si el registro no tiene barriles, lo saltamos ---
                if bbl_del_registro <= 0:
                    print(f"--> SALTADO: El registro ID={registro.id} tiene 0 o menos barriles.")
                    continue

                if bbl_del_registro <= cantidad_restante:
                    registro.estado = 'Gastado'
                    cantidad_restante -= bbl_del_registro
                    actas_consumidas.append(f"{registro.acta} ({registro.carrotanque})")
                    print(f"--> CONSUMIDO COMPLETO: ID={registro.id}. Quedan por consumir: {cantidad_restante}")
                else:
                    # Lógica de división (ya estaba bien, pero la rodeamos de diagnósticos)
                    print(f"--> DIVIDIENDO: ID={registro.id}. Se consumirán {cantidad_restante} de {bbl_del_registro}")
                    proporcion_a_dividir = cantidad_restante / bbl_del_registro
                    bbl_netos_originales = registro.bbl_netos or 0.0

                    nuevo_registro_disponible = RegistroZisa(
                        empresa=registro.empresa, mes=registro.mes, carrotanque=registro.carrotanque,
                        producto=registro.producto, numero_sae=registro.numero_sae, acta=registro.acta,
                        bbl_netos = bbl_netos_originales * (1 - proporcion_a_dividir),
                        bbl_descargados = bbl_del_registro - cantidad_restante,
                        usuario_carga=registro.usuario_carga, fecha_carga=registro.fecha_carga,
                        estado='Disponible'
                    )
                    db.session.add(nuevo_registro_disponible)
                    
                    registro.estado = 'Gastado'
                    registro.bbl_descargados = cantidad_restante
                    registro.bbl_netos = bbl_netos_originales * proporcion_a_dividir
                    
                    actas_consumidas.append(f"{registro.acta} (parcial)")
                    cantidad_restante = 0
                    print(f"--> DIVISIÓN COMPLETA. ID={registro.id} ahora está gastado. Se creó un nuevo registro para el sobrante.")

            db.session.commit()
            print("--> COMMIT REALIZADO CON ÉXITO")
            print("="*30)
            flash(f'Éxito: Se consumieron {cantidad_a_consumir:.2f} BBL de {empresa}. Actas utilizadas: {", ".join(actas_consumidas)}', 'success')
            
        except Exception as e:
            db.session.rollback()
            # --- DIAGNÓSTICO CRÍTICO ---
            print("\n" + "!"*50)
            print(f"ERROR CATASTRÓFICO AL CONSUMIR: {e}")
            import traceback
            traceback.print_exc() # Imprime el error detallado en la consola
            print("!"*50 + "\n")
            app.logger.error(f"Error al consumir inventario: {str(e)}")
            flash('Ocurrió un error grave al procesar la solicitud. Revisa la consola del servidor.', 'danger')
        
        return redirect(url_for('consumir_inventario'))
    
    else: # El método GET se mantiene igual
        total_zisa = db.session.query(func.sum(RegistroZisa.bbl_descargados)).filter_by(estado='Disponible', empresa='ZISA').scalar() or 0.0
        total_fbcol = db.session.query(func.sum(RegistroZisa.bbl_descargados)).filter_by(estado='Disponible', empresa='FBCOL').scalar() or 0.0
        total_consumido_zisa = db.session.query(func.sum(RegistroZisa.bbl_descargados)).filter_by(estado='Gastado', empresa='ZISA').scalar() or 0.0
        total_consumido_fbcol = db.session.query(func.sum(RegistroZisa.bbl_descargados)).filter_by(estado='Gastado', empresa='FBCOL').scalar() or 0.0
        ultimos_consumos = RegistroZisa.query.filter_by(estado='Gastado').order_by(RegistroZisa.fecha_carga.desc()).limit(10).all()

        return render_template('consumir_inventario.html',
                               total_inventario_zisa=total_zisa,
                               total_inventario_fbcol=total_fbcol,
                               total_consumido_zisa=total_consumido_zisa,
                               total_consumido_fbcol=total_consumido_fbcol,
                               ultimos_consumos=ultimos_consumos)

@login_required
@permiso_requerido('zisa_inventory')    
@app.route('/reporte-consumo')
def reporte_consumo():
    # 1. Obtener los filtros desde la URL (si es que existen)
    empresa_filtro = request.args.get('empresa', default='')
    fecha_inicio_str = request.args.get('fecha_inicio', default='')
    fecha_fin_str = request.args.get('fecha_fin', default='')

    # 2. Empezar la consulta base: solo registros 'Gastado'
    query = RegistroZisa.query.filter_by(estado='Gastado')

    # 3. Aplicar los filtros a la consulta
    if empresa_filtro in ['ZISA', 'FBCOL']:
        query = query.filter_by(empresa=empresa_filtro)
    
    # Filtro por fecha de inicio
    if fecha_inicio_str:
        try:
            fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d')
            query = query.filter(RegistroZisa.fecha_carga >= fecha_inicio)
        except ValueError:
            flash('Formato de fecha de inicio inválido. Use AAAA-MM-DD.', 'warning')
    
    # Filtro por fecha de fin
    if fecha_fin_str:
        try:
            # Se suma un día para que el rango sea inclusivo hasta el final del día seleccionado
            fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(RegistroZisa.fecha_carga < fecha_fin)
        except ValueError:
            flash('Formato de fecha de fin inválido. Use AAAA-MM-DD.', 'warning')

    # 4. Ejecutar la consulta final
    registros_consumidos = query.order_by(RegistroZisa.fecha_carga.desc()).all()

    # 5. Calcular la suma total de los BBL descargados de los registros filtrados
    total_consumido_filtrado = sum(r.bbl_descargados for r in registros_consumidos)

    # 6. Preparar los filtros para devolverlos a la plantilla (para que los campos del formulario recuerden su valor)
    filtros_activos = {
        'empresa': empresa_filtro,
        'fecha_inicio': fecha_inicio_str,
        'fecha_fin': fecha_fin_str
    }

    return render_template('reporte_consumo.html',
                           registros=registros_consumidos,
                           total_consumido=total_consumido_filtrado,
                           filtros=filtros_activos)

@login_required
@permiso_requerido('zisa_inventory')
@app.route('/exportar-inventario-zisa')
def exportar_inventario_zisa():
    """
    Exporta el inventario de ZISA/FBCOL a un archivo Excel con filtros.
    """
    # Obtener los filtros desde los argumentos de la URL
    empresa_filtro = request.args.get('empresa')
    estado_filtro = request.args.get('estado')
    
    query = RegistroZisa.query

    # Aplicar filtros a la consulta si fueron proporcionados
    if empresa_filtro and empresa_filtro in ['ZISA', 'FBCOL']:
        query = query.filter_by(empresa=empresa_filtro)
    
    if estado_filtro and estado_filtro in ['Disponible', 'Gastado']:
        query = query.filter_by(estado=estado_filtro)

    # Ejecutar la consulta
    registros = query.order_by(RegistroZisa.fecha_carga.desc()).all()

    if not registros:
        flash('No hay datos para exportar con los filtros seleccionados.', 'warning')
        return redirect(url_for('inventario_zisa'))

    # Preparar los datos para el DataFrame de Pandas
    datos_para_df = [{
        'Empresa': r.empresa,
        'Mes': r.mes,
        'Carrotanque': r.carrotanque,
        'Producto': r.producto,
        'Numero SAE': r.numero_sae,
        'Acta': r.acta,
        'BBL Netos': r.bbl_netos,
        'BBL Descargados/Gastados': r.bbl_descargados,
        'Estado': r.estado,
        'Usuario Carga': r.usuario_carga,
        'Fecha Carga': r.fecha_carga.strftime('%Y-%m-%d %H:%M:%S') if r.fecha_carga else ''
    } for r in registros]

    df = pd.DataFrame(datos_para_df)

    # Crear el archivo Excel en memoria
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Inventario_ZISA')
    output.seek(0)

    # Enviar el archivo al usuario para su descarga
    filename = f"reporte_inventario_zisa_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )

@login_required
@app.route('/exportar-excel/<string:nombre_reporte>')
def exportar_excel(nombre_reporte):
    """
    Exporta los datos del reporte especificado a un archivo Excel con filtros avanzados.
    """
    filtro_tipo = request.args.get('filtro_tipo')
    valor = request.args.get('valor')
    
    registros_db = []
    columnas = []
    filename = f"reporte_{nombre_reporte}_{valor or 'general'}.xlsx"

    # --- Lógica de filtrado para modelos con `timestamp` (Planta, Orion, Bita) ---
    if nombre_reporte in ['planta', 'barcaza_orion', 'barcaza_bita']:
        timestamp_limite = None
        if valor:
            try:
                if filtro_tipo == 'dia':
                    timestamp_limite = datetime.combine(date.fromisoformat(valor), time.max)
                elif filtro_tipo == 'mes':
                    ano, mes = map(int, valor.split('-'))
                    ultimo_dia = (date(ano, mes, 1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
                    timestamp_limite = datetime.combine(ultimo_dia, time.max)
                elif filtro_tipo == 'trimestre':
                    ano_str, q_str = valor.split('-Q')
                    ano, trimestre = int(ano_str), int(q_str)
                    mes_fin = trimestre * 3
                    ultimo_dia = (date(ano, mes_fin, 1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
                    timestamp_limite = datetime.combine(ultimo_dia, time.max)
                elif filtro_tipo == 'anual':
                    ano = int(valor)
                    ultimo_dia = date(ano, 12, 31)
                    timestamp_limite = datetime.combine(ultimo_dia, time.max)
            except (ValueError, TypeError):
                timestamp_limite = datetime.now() # Fallback seguro

        if nombre_reporte == 'planta':
            subquery_base = db.session.query(RegistroPlanta.tk, func.max(RegistroPlanta.timestamp).label('max_timestamp'))
            subquery = subquery_base.filter(RegistroPlanta.timestamp <= timestamp_limite).group_by(RegistroPlanta.tk).subquery() if timestamp_limite else subquery_base.group_by(RegistroPlanta.tk).subquery()
            registros_db = db.session.query(RegistroPlanta).join(subquery, (RegistroPlanta.tk == subquery.c.tk) & (RegistroPlanta.timestamp == subquery.c.max_timestamp)).all()
            columnas = ["tk", "producto", "max_cap", "bls_60", "api", "bsw", "s"]

        elif nombre_reporte == 'barcaza_orion':
            subquery_base = db.session.query(RegistroBarcazaOrion.tk, RegistroBarcazaOrion.grupo, func.max(RegistroBarcazaOrion.timestamp).label('max_timestamp'))
            subquery = subquery_base.filter(RegistroBarcazaOrion.timestamp <= timestamp_limite).group_by(RegistroBarcazaOrion.tk, RegistroBarcazaOrion.grupo).subquery() if timestamp_limite else subquery_base.group_by(RegistroBarcazaOrion.tk, RegistroBarcazaOrion.grupo).subquery()
            registros_db = db.session.query(RegistroBarcazaOrion).join(subquery, (RegistroBarcazaOrion.tk == subquery.c.tk) & (RegistroBarcazaOrion.grupo == subquery.c.grupo) & (RegistroBarcazaOrion.timestamp == subquery.c.max_timestamp)).all()
            columnas = ["grupo", "tk", "producto", "max_cap", "bls_60", "api", "bsw", "s"]

        elif nombre_reporte == 'barcaza_bita':
            subquery_base = db.session.query(RegistroBarcazaBita.tk, func.max(RegistroBarcazaBita.timestamp).label('max_timestamp'))
            subquery = subquery_base.filter(RegistroBarcazaBita.timestamp <= timestamp_limite).group_by(RegistroBarcazaBita.tk).subquery() if timestamp_limite else subquery_base.group_by(RegistroBarcazaBita.tk).subquery()
            registros_db = db.session.query(RegistroBarcazaBita).join(subquery, (RegistroBarcazaBita.tk == subquery.c.tk) & (RegistroBarcazaBita.timestamp == subquery.c.max_timestamp)).all()
            columnas = ["tk", "producto", "max_cap", "bls_60", "api", "bsw", "s"]

    # --- Lógica de filtrado para Tránsito (usa la columna `fecha` que es texto) ---
    elif nombre_reporte == 'transito':
        query = db.session.query(RegistroTransito)
        if valor:
            try:
                if filtro_tipo == 'dia':
                    query = query.filter(RegistroTransito.fecha == valor)
                elif filtro_tipo == 'mes':
                    query = query.filter(RegistroTransito.fecha.like(f"{valor}-%"))
                elif filtro_tipo == 'trimestre':
                    ano_str, q_str = valor.split('-Q')
                    ano, trimestre = int(ano_str), int(q_str)
                    meses_trimestre = {1: ["01", "02", "03"], 2: ["04", "05", "06"], 3: ["07", "08", "09"], 4: ["10", "11", "12"]}[trimestre]
                    condiciones = [RegistroTransito.fecha.like(f"{ano}-{m}-%") for m in meses_trimestre]
                    query = query.filter(or_(*condiciones))
                elif filtro_tipo == 'anual':
                    query = query.filter(RegistroTransito.fecha.like(f"{valor}-%"))
            except (ValueError, TypeError):
                pass # Si el valor es inválido, no se filtra
        
        registros_db = query.order_by(RegistroTransito.fecha.desc()).all()
        columnas = ["tipo_transito", "fecha", "guia", "origen", "producto", "placa", "nsv", "api", "bsw", "observaciones"]

    if not registros_db:
        flash("No hay datos para exportar con el filtro seleccionado.", "warning")
        return redirect(request.referrer or url_for('dashboard_reportes'))

    # Convertir los resultados a una lista de diccionarios
    registros = [r.__dict__ for r in registros_db]
    
    # Crear el DataFrame y el archivo Excel
    df = pd.DataFrame(registros)
    # Asegurarse de que solo las columnas deseadas estén en el DataFrame final
    df = df.reindex(columns=columnas)

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Reporte')
    output.seek(0)

    # Enviar el archivo para su descarga
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )

@login_required
@app.route('/descargar-reporte-planta-pdf')
def descargar_reporte_planta_pdf():
    # --- La lógica de filtros que ya tienes se mantiene igual ---
    filtro_tipo = request.args.get('filtro_tipo', 'dia')
    valor = request.args.get('valor')
    
    subquery_base = db.session.query(RegistroPlanta.tk, func.max(RegistroPlanta.timestamp).label('max_timestamp'))
    fecha_reporte_str = f"General (últimos datos registrados al {date.today().strftime('%d/%m/%Y')})"
    subquery_filtrada = subquery_base

    if valor:
        if filtro_tipo == 'dia':
            fecha_obj = date.fromisoformat(valor)
            fecha_reporte_str = f"del día {fecha_obj.strftime('%d de %B de %Y')}"
            subquery_filtrada = subquery_base.filter(RegistroPlanta.timestamp <= datetime.combine(fecha_obj, time.max))
        # ... (el resto de tu lógica para 'mes', 'trimestre', 'anual' va aquí)
        elif filtro_tipo == 'mes':
            ano, mes = map(int, valor.split('-'))
            fecha_obj = date(ano, mes, 1)
            fecha_reporte_str = f"del mes de {fecha_obj.strftime('%B de %Y')}"
            ultimo_dia = (fecha_obj + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            subquery_filtrada = subquery_base.filter(RegistroPlanta.timestamp <= datetime.combine(ultimo_dia, time.max))
        elif filtro_tipo == 'trimestre':
            ano_str, q_str = valor.split('-Q')
            ano = int(ano_str)
            trimestre = int(q_str)
            mes_fin = trimestre * 3
            ultimo_dia_trimestre = (date(ano, mes_fin, 1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            fecha_reporte_str = f"del Trimestre {trimestre} de {ano}"
            subquery_filtrada = subquery_base.filter(RegistroPlanta.timestamp <= datetime.combine(ultimo_dia_trimestre, time.max))
        elif filtro_tipo == 'anual':
            ano = int(valor)
            ultimo_dia_ano = date(ano, 12, 31)
            fecha_reporte_str = f"del Año {ano}"
            subquery_filtrada = subquery_base.filter(RegistroPlanta.timestamp <= datetime.combine(ultimo_dia_ano, time.max))


    subquery = subquery_filtrada.group_by(RegistroPlanta.tk).subquery()
    registros_db = db.session.query(RegistroPlanta).join(subquery, (RegistroPlanta.tk == subquery.c.tk) & (RegistroPlanta.timestamp == subquery.c.max_timestamp)).all()

    if not registros_db:
        flash("No hay datos para generar el PDF con el filtro seleccionado.", "warning")
        return redirect(url_for('reporte_planta'))

    # ======== INICIO DE LA SOLUCIÓN DEFINITIVA ========
    # Se crea una nueva lista de diccionarios, asegurando que los valores nulos se conviertan en 0.0
    registros_limpios = []
    for r in registros_db:
        registros_limpios.append({
            'tk': r.tk,
            'producto': r.producto,
            'max_cap': r.max_cap or 0.0,
            'bls_60': r.bls_60 or 0.0,
            'api': r.api or 0.0,
            'bsw': r.bsw or 0.0,
            's': r.s or 0.0
        })
    # ======== FIN DE LA SOLUCIÓN DEFINITIVA ========

    # Se pasa la lista de datos ya limpios a la plantilla
    html_para_pdf = render_template('reportes_pdf/planta_pdf.html',
                                    registros=registros_limpios,
                                    fecha_reporte=fecha_reporte_str)
    
    pdf = HTML(string=html_para_pdf).write_pdf()
    return Response(pdf,
                  mimetype='application/pdf',
                  headers={'Content-Disposition': 'attachment;filename=reporte_planta.pdf'})

@login_required
@app.route('/descargar-reporte-orion-pdf')
def descargar_reporte_orion_pdf():
    # --- La lógica de filtros se mantiene igual ---
    fecha_str = request.args.get('fecha', date.today().isoformat())
    try:
        fecha_seleccionada = date.fromisoformat(fecha_str)
    except (ValueError, TypeError):
        fecha_seleccionada = date.today()
    timestamp_limite = datetime.combine(fecha_seleccionada, time.max)

    # 1. Obtener los datos de la base de datos
    subquery = (db.session.query(
        func.max(RegistroBarcazaOrion.id).label('max_id')
    ).filter(
        RegistroBarcazaOrion.timestamp <= timestamp_limite
    ).group_by(RegistroBarcazaOrion.tk, RegistroBarcazaOrion.grupo).subquery())
    registros_recientes = (db.session.query(RegistroBarcazaOrion)
        .filter(RegistroBarcazaOrion.id.in_(subquery))
        .all())

    if not registros_recientes:
        flash("No hay datos de Barcaza Orion para generar el PDF en esa fecha.", "warning")
        return redirect(url_for('reporte_barcaza'))

    # ======== INICIO DE LA SOLUCIÓN DEFINITIVA ========
    # 2. LIMPIEZA DE DATOS: Convertir registros a diccionarios y reemplazar None por 0.0
    todos_los_tanques_lista = []
    for r in registros_recientes:
        todos_los_tanques_lista.append({
            "TK": r.tk,
            "PRODUCTO": r.producto,
            "MAX_CAP": r.max_cap or 0.0,
            "BLS_60": r.bls_60 or 0.0,
            "API": r.api or 0.0,
            "BSW": r.bsw or 0.0,
            "S": r.s or 0.0,
            "grupo": r.grupo
        })
    # ======== FIN DE LA SOLUCIÓN DEFINITIVA ========

    # 3. Agrupar datos y calcular estadísticas (usa la lista ya limpia)
    datos_agrupados = {}
    nombres_display = {
        "PRINCIPAL": "Tanque Principal (TK-101)", "MANZANILLO": "Barcaza Manzanillo (MGO)",
        "CR": "Barcaza CR", "MARGOTH": "Barcaza Margoth", "ODISEA": "Barcaza Odisea"
    }
    for tanque in todos_los_tanques_lista:
        grupo_key = tanque.get("grupo")
        if grupo_key in nombres_display:
            nombre_barcaza = nombres_display[grupo_key]
            if nombre_barcaza not in datos_agrupados:
                datos_agrupados[nombre_barcaza] = {"tanques": []}
            datos_agrupados[nombre_barcaza]["tanques"].append(tanque)
    
    for nombre, data in datos_agrupados.items():
        data["totales"] = calcular_estadisticas(data["tanques"])
    
    total_consolidado = calcular_estadisticas(todos_los_tanques_lista)

    # 4. Renderizar la plantilla HTML del PDF
    html_para_pdf = render_template('reportes_pdf/orion_pdf.html',
                                    datos_agrupados=datos_agrupados,
                                    total_consolidado=total_consolidado,
                                    fecha_reporte=fecha_seleccionada.strftime('%d de %B de %Y'))
    
    pdf = HTML(string=html_para_pdf).write_pdf()
    return Response(pdf,
                  mimetype='application/pdf',
                  headers={'Content-Disposition': 'attachment;filename=reporte_barcaza_orion.pdf'})

@login_required
@app.route('/descargar-reporte-bita-pdf')
def descargar_reporte_bita_pdf():
    # --- Lógica para manejar los filtros avanzados ---
    filtro_tipo = request.args.get('filtro_tipo')
    valor = request.args.get('valor')
    
    subquery_base = db.session.query(RegistroBarcazaBita.tk, func.max(RegistroBarcazaBita.timestamp).label('max_timestamp'))
    fecha_reporte_str = "General (últimos datos registrados)"
    timestamp_limite = None

    if valor:
        try:
            if filtro_tipo == 'dia':
                fecha_obj = date.fromisoformat(valor)
                fecha_reporte_str = f"del día {fecha_obj.strftime('%d de %B de %Y')}"
                timestamp_limite = datetime.combine(fecha_obj, time.max)
            elif filtro_tipo == 'mes':
                ano, mes = map(int, valor.split('-'))
                fecha_obj = date(ano, mes, 1)
                fecha_reporte_str = f"del mes de {fecha_obj.strftime('%B de %Y')}"
                ultimo_dia = (fecha_obj + timedelta(days=32)).replace(day=1) - timedelta(days=1)
                timestamp_limite = datetime.combine(ultimo_dia, time.max)
            elif filtro_tipo == 'trimestre':
                ano_str, q_str = valor.split('-Q')
                ano, trimestre = int(ano_str), int(q_str)
                fecha_reporte_str = f"del Trimestre {trimestre} de {ano}"
                mes_fin = trimestre * 3
                ultimo_dia = (date(ano, mes_fin, 1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
                timestamp_limite = datetime.combine(ultimo_dia, time.max)
            elif filtro_tipo == 'anual':
                ano = int(valor)
                fecha_reporte_str = f"del Año {ano}"
                ultimo_dia = date(ano, 12, 31)
                timestamp_limite = datetime.combine(ultimo_dia, time.max)
        except (ValueError, TypeError):
            pass # Si hay un error en el valor, no se aplica el filtro de tiempo

    # Aplicar el filtro de tiempo a la consulta
    subquery_filtrada = subquery_base.filter(RegistroBarcazaBita.timestamp <= timestamp_limite) if timestamp_limite else subquery_base
    subquery = subquery_filtrada.group_by(RegistroBarcazaBita.tk).subquery()
    registros_recientes = db.session.query(RegistroBarcazaBita).join(subquery, (RegistroBarcazaBita.tk == subquery.c.tk) & (RegistroBarcazaBita.timestamp == subquery.c.max_timestamp)).all()

    if not registros_recientes:
        flash("No hay datos de Barcaza BITA para generar el PDF con el filtro seleccionado.", "warning")
        return redirect(url_for('reporte_barcaza_bita'))

    # --- Limpieza de datos para prevenir el TypeError ---
    datos_reporte = [{
        "TK": r.tk, "PRODUCTO": r.producto,
        "MAX_CAP": r.max_cap or 0.0,
        "BLS_60": r.bls_60 or 0.0,
        "API": r.api or 0.0,
        "BSW": r.bsw or 0.0,
        "S": r.s or 0.0
    } for r in registros_recientes]
    
    # Preparar datos y estadísticas con los datos ya limpios
    total_consolidado = calcular_estadisticas(datos_reporte)
    tanques_marinse = [tk for tk in datos_reporte if tk.get('TK','').startswith('MARI')]
    tanques_oidech = [tk for tk in datos_reporte if tk.get('TK','').startswith('OID')]
    stats_marinse = calcular_estadisticas(tanques_marinse)
    stats_oidech = calcular_estadisticas(tanques_oidech)

    # Renderizar la plantilla del PDF
    html_para_pdf = render_template('reportes_pdf/bita_pdf.html',
                                    tanques_marinse=tanques_marinse,
                                    stats_marinse=stats_marinse,
                                    tanques_oidech=tanques_oidech,
                                    stats_oidech=stats_oidech,
                                    total_consolidado=total_consolidado,
                                    fecha_reporte=fecha_reporte_str)

    pdf = HTML(string=html_para_pdf).write_pdf()
    return Response(pdf, mimetype='application/pdf', headers={'Content-Disposition': 'attachment;filename=reporte_barcaza_bita.pdf'})

@login_required
@app.route('/descargar-reporte-transito-pdf')
def descargar_reporte_transito_pdf():
    # 1. Obtener todos los registros de tránsito (la misma lógica que en la página del reporte)
    todos_los_registros = db.session.query(RegistroTransito).order_by(RegistroTransito.timestamp.desc()).all()

    if not todos_los_registros:
        flash("No hay datos de Tránsito para generar el PDF.", "warning")
        return redirect(url_for('reporte_transito'))

    # 2. Consolidar los datos
    datos_consolidados = {}
    datos_conteo_camiones = {}
    observaciones_camiones = {}
    
    for reg in todos_los_registros:
        origen = (reg.origen or "Sin Origen").strip()
        producto = (reg.producto or "Sin Producto").strip()
        tipo_destino_reporte = "Refinería" if reg.tipo_transito == "refineria" else "EDSM"
        nsv = float(reg.nsv or 0.0)

        # Sumar NSV
        datos_consolidados.setdefault(tipo_destino_reporte, {}).setdefault(origen, {}).setdefault(producto, 0.0)
        datos_consolidados[tipo_destino_reporte][origen][producto] += nsv
        
        # Contar camiones
        datos_conteo_camiones.setdefault(tipo_destino_reporte, {}).setdefault(origen, {}).setdefault(producto, 0)
        datos_conteo_camiones[tipo_destino_reporte][origen][producto] += 1
        
        # Agrupar observaciones
        if reg.observaciones and reg.observaciones.strip():
            texto_completo = f"{(reg.placa or 'S/P')}: {reg.observaciones.strip()}"
            lista_obs = observaciones_camiones.setdefault(tipo_destino_reporte, {}).setdefault(origen, {}).setdefault(producto, [])
            lista_obs.append(texto_completo)

    # 3. Renderizar la plantilla HTML del PDF
    html_para_pdf = render_template('reportes_pdf/transito_pdf.html',
                                    datos_consolidados=datos_consolidados,
                                    datos_conteo_camiones=datos_conteo_camiones,
                                    observaciones_camiones=observaciones_camiones,
                                    fecha_reporte=date.today().strftime('%d de %B de %Y'))

    # 4. Generar y devolver el PDF
    pdf = HTML(string=html_para_pdf).write_pdf()
    return Response(pdf,
                  mimetype='application/pdf',
                  headers={'Content-Disposition': 'attachment;filename=reporte_transito.pdf'})

@login_required
@permiso_requerido('zisa_inventory')
@app.route('/descargar-reporte-pdf')
def descargar_reporte_pdf():
    # --- PASO 1: REPETIMOS LA MISMA LÓGICA DE FILTRADO DE LA PÁGINA DEL REPORTE ---
    empresa_filtro = request.args.get('empresa', default='')
    fecha_inicio_str = request.args.get('fecha_inicio', default='')
    fecha_fin_str = request.args.get('fecha_fin', default='')

    query = RegistroZisa.query.filter_by(estado='Gastado')

    if empresa_filtro in ['ZISA', 'FBCOL']:
        query = query.filter_by(empresa=empresa_filtro)
    
    # Aplicar filtros de fecha...
    # ... (la misma lógica de fechas que en tu ruta 'reporte_consumo') ...

    registros_consumidos = query.order_by(RegistroZisa.fecha_carga.desc()).all()
    total_consumido_filtrado = sum(r.bbl_descargados for r in registros_consumidos)

    # --- PASO 2: RENDERIZAMOS UNA PLANTILLA HTML ESPECIAL PARA EL PDF ---
    # No es la página web completa, solo el contenido del reporte.
    html_para_pdf = render_template('reporte_pdf_template.html',
                                    registros=registros_consumidos,
                                    total_consumido=total_consumido_filtrado,
                                    empresa=empresa_filtro or "Todas",
                                    fecha_inicio=fecha_inicio_str,
                                    fecha_fin=fecha_fin_str)
    
    # --- PASO 3: USAMOS WEASYPRINT PARA CONVERTIR EL HTML A PDF ---
    pdf = HTML(string=html_para_pdf).write_pdf()

    # --- PASO 4: DEVOLVEMOS EL PDF COMO UNA DESCARGA ---
    return Response(pdf,
                    mimetype='application/pdf',
                    headers={'Content-Disposition': 'attachment;filename=reporte_consumo.pdf'})

@login_required
@permiso_requerido('simulador_rendimiento')
@app.route('/simulador_rendimiento')
def simulador_rendimiento():
    """
    Renderiza la página del Simulador de Rendimiento de Crudo.
    """
    return render_template('simulador_rendimiento.html', nombre=session.get("nombre"))

@login_required
@app.route('/api/calcular_rendimiento', methods=['POST'])
def api_calcular_rendimiento():
    """
    Calcula rendimiento, API, azufre y viscosidad de productos.
    VERSIÓN FINAL Y CORREGIDA.
    """
    try:
        data = request.get_json()
        puntos_curva = data.get('distillationCurve')
        puntos_corte = data.get('cutPoints')
        azufre_crudo = data.get('sulfurCrude') or 0
        api_crudo = data.get('apiCrude') or 0
        viscosidad_crudo = data.get('viscosityCrude') or 0

        if not all([puntos_curva, puntos_corte, api_crudo]) or len(puntos_curva) < 2:
            return jsonify({"success": False, "message": "Datos incompletos."}), 400

        puntos_curva.sort(key=lambda p: p['tempC'])

        def interpolar_porcentaje(temp_objetivo):
            if not puntos_curva: return 0
            if temp_objetivo <= puntos_curva[0]['tempC']: return puntos_curva[0]['percent']
            if temp_objetivo >= puntos_curva[-1]['tempC']: return puntos_curva[-1]['percent']
            for i in range(len(puntos_curva) - 1):
                p1, p2 = puntos_curva[i], puntos_curva[i+1]
                if p1['tempC'] <= temp_objetivo <= p2['tempC']:
                    if p2['tempC'] == p1['tempC']: return p1['percent']
                    return p1['percent'] + (temp_objetivo - p1['tempC']) * (p2['percent'] - p1['percent']) / (p2['tempC'] - p1['tempC'])
            return 100

        # 1. Calcular Rendimientos
        porc_nafta = interpolar_porcentaje(puntos_corte.get('nafta', 0))
        porc_kero_acumulado = interpolar_porcentaje(puntos_corte.get('kero', 0))
        porc_fo4_acumulado = interpolar_porcentaje(puntos_corte.get('fo4', 0))
        rendimientos = {
            "NAFTA": max(0, porc_nafta),
            "KERO": max(0, porc_kero_acumulado - porc_nafta),
            "FO4": max(0, porc_fo4_acumulado - porc_kero_acumulado),
            "FO6": max(0, 100 - porc_fo4_acumulado)
        }
        
        ORDEN_PRODUCTOS = ["NAFTA", "KERO", "FO4", "FO6"]

        # 2. Calcular Azufre por Producto
        azufre_por_producto = {p: 0 for p in ORDEN_PRODUCTOS}
        if azufre_crudo > 0:
            FACTORES_AZUFRE = {'NAFTA': 0.05, 'KERO': 0.15, 'FO4': 1.0, 'FO6': 2.5}
            denominador_k_s = sum(rendimientos[p] * FACTORES_AZUFRE[p] for p in ORDEN_PRODUCTOS if p in rendimientos)
            if denominador_k_s > 0:
                k_s = (100 * azufre_crudo) / denominador_k_s
                for p in azufre_por_producto: azufre_por_producto[p] = round(k_s * FACTORES_AZUFRE.get(p, 0), 4)

        # 3. Calcular API por Producto
        api_por_producto = {p: 0 for p in ORDEN_PRODUCTOS}
        API_ESTANDAR = {'NAFTA': 65.0, 'KERO': 45.0, 'FO4': 35.0, 'FO6': 10.0}
        def api_a_sg(api): return 141.5 / (api + 131.5) if api != -131.5 else 0
        def sg_a_api(sg): return (141.5 / sg) - 131.5 if sg > 0 else 0
        sg_crudo_real = api_a_sg(api_crudo)
        sg_productos_estandar = {p: api_a_sg(api) for p, api in API_ESTANDAR.items()}
        sg_reconstituido = sum(rendimientos[p] / 100 * sg_productos_estandar[p] for p in ORDEN_PRODUCTOS if rendimientos[p] > 0)
        factor_ajuste_sg = sg_crudo_real / sg_reconstituido if sg_reconstituido > 0 else 1
        for p in ORDEN_PRODUCTOS:
            sg_ajustado = sg_productos_estandar[p] * factor_ajuste_sg
            api_por_producto[p] = round(sg_a_api(sg_ajustado), 1)

        # 4. Calcular Viscosidad por Producto
        viscosidad_por_producto = {p: 0 for p in ORDEN_PRODUCTOS}
        if viscosidad_crudo > 0:
            VISCOSIDAD_STD = {'NAFTA': 0.8, 'KERO': 2.0, 'FO4': 4.0, 'FO6': 380.0}
            log_visc_reconstituido = sum(rendimientos[p]/100 * math.log(VISCOSIDAD_STD[p]) for p in ORDEN_PRODUCTOS if VISCOSIDAD_STD.get(p, 0) > 0 and rendimientos.get(p, 0) > 0)
            visc_reconstituido = math.exp(log_visc_reconstituido) if log_visc_reconstituido != 0 else 1
            factor_ajuste_visc = viscosidad_crudo / visc_reconstituido if visc_reconstituido > 0 else 1
            for p in ORDEN_PRODUCTOS:
                viscosidad_por_producto[p] = round(VISCOSIDAD_STD[p] * factor_ajuste_visc, 2)

        # 5. Devolver respuesta completa y ordenada
        return jsonify({
            "success": True, "order": ORDEN_PRODUCTOS,
            "yields": {p: round(rendimientos.get(p, 0), 2) for p in ORDEN_PRODUCTOS},
            "sulfur_by_product": {p: azufre_por_producto.get(p, 0) for p in ORDEN_PRODUCTOS},
            "api_by_product": {p: api_por_producto.get(p, 0) for p in ORDEN_PRODUCTOS},
            "viscosity_by_product": {p: viscosidad_por_producto.get(p, 0) for p in ORDEN_PRODUCTOS}
        })

    except Exception as e:
        app.logger.error(f"Error en /api/calcular_rendimiento: {e}")
        return jsonify(success=False, message=f"Error interno del servidor: {e}"), 500

@login_required
@app.route('/api/crudos_guardados', methods=['GET'])
def get_crudos_guardados():
    """Obtiene la lista de todos los crudos guardados desde la base de datos."""
    crudos_db = DefinicionCrudo.query.order_by(DefinicionCrudo.nombre).all()
    
    if not crudos_db:
        # Añadimos valores por defecto para los nuevos campos
        datos_iniciales = {
            "DOROTEA": {"api": 33.1, "sulfur": 0.197, "viscosity": 5.1, "curva": [{"percent": 5, "tempC": 126.7}, {"percent": 10, "tempC": 160.0}, {"percent": 15, "tempC": 174.4}, {"percent": 20, "tempC": 215.6}, {"percent": 30, "tempC": 260.0}, {"percent": 40, "tempC": 304.4}, {"percent": 50, "tempC": 337.8}, {"percent": 60, "tempC": 351.0}]},
            "TULIPAN": {"api": 35.0, "sulfur": 0.3, "viscosity": 4.0, "curva": [{"percent": 5, "tempC": 82.2}, {"percent": 10, "tempC": 98.9}, {"percent": 20, "tempC": 124.4}, {"percent": 30, "tempC": 183.3}, {"percent": 40, "tempC": 224.4}, {"percent": 50, "tempC": 260.0}, {"percent": 60, "tempC": 295.6}, {"percent": 70, "tempC": 356.7}]},
            "INDICO": {"api": 35.0,"sulfur": 0.078, "viscosity": 5.0, "curva": [{"percent": 0, "tempC": 61.6}, {"percent": 5, "tempC": 113.6}, {"percent": 10, "tempC": 138.5}, {"percent": 20, "tempC": 187.0}, {"percent": 30, "tempC": 231.2}, {"percent": 40, "tempC": 265.8}, {"percent": 50, "tempC": 297.8}, {"percent": 60, "tempC": 331.4}, {"percent": 70, "tempC": 380.2}]},
            "JOROPO": {"api": 28.8, "sulfur": 0.20, "viscosity": 5.0, "curva": [{"percent": 0, "tempC": 143}, {"percent": 5, "tempC": 208.1}, {"percent": 10, "tempC": 235.3}, {"percent": 20, "tempC": 277.8}, {"percent": 30, "tempC": 314.1}, {"percent": 40, "tempC": 342.9}, {"percent": 50, "tempC": 374.0}]},
            "WTI": {"api": 43.0, "sulfur": 0.103, "viscosity": 2.4, "curva": [{"percent": 5, "tempC": 60.4}, {"percent": 10, "tempC": 84.7}, {"percent": 20, "tempC": 118.6}, {"percent": 30, "tempC": 156.3}, {"percent": 40, "tempC": 207.4}, {"percent": 50, "tempC": 265.0}, {"percent": 60, "tempC": 327.0}, {"percent": 70, "tempC": 398.0}, {"percent": 80, "tempC": 498.0}]}
        }
        for nombre, data in datos_iniciales.items():
            # Añadir los nuevos campos al crear el objeto
            nuevo_crudo = DefinicionCrudo(
                nombre=nombre, 
                api=data['api'], 
                sulfur=data.get('sulfur'),      # <-- AÑADIDO
                viscosity=data.get('viscosity'),# <-- AÑADIDO
                curva_json=json.dumps(data['curva'])
            )
            db.session.add(nuevo_crudo)
        db.session.commit()
        crudos_db = DefinicionCrudo.query.order_by(DefinicionCrudo.nombre).all()

    crudos_dict = {
        crudo.nombre: {
            "api": crudo.api,
            "sulfur": crudo.sulfur,            # <-- AÑADIDO
            "viscosity": crudo.viscosity,      # <-- AÑADIDO
            "curva": json.loads(crudo.curva_json)
        } for crudo in crudos_db
    }
    return jsonify(crudos_dict)

@login_required
@app.route('/api/crudos_guardados', methods=['POST'])
def save_crudo():
    data = request.get_json()
    nombre_crudo = data.get('nombre')
    api = data.get('api')
    sulfur = data.get('sulfur')        # <-- AÑADIDO
    viscosity = data.get('viscosity')  # <-- AÑADIDO
    curva = data.get('curva')

    if not nombre_crudo or not curva:
        return jsonify(success=False, message="El nombre y la curva son obligatorios."), 400
    
    crudo_existente = DefinicionCrudo.query.filter_by(nombre=nombre_crudo).first()
    
    if crudo_existente:
        crudo_existente.api = api
        crudo_existente.sulfur = sulfur      # <-- AÑADIDO
        crudo_existente.viscosity = viscosity# <-- AÑADIDO
        crudo_existente.curva_json = json.dumps(curva)
        msg = f"Crudo '{nombre_crudo}' actualizado."
    else:
        nuevo_crudo = DefinicionCrudo(
            nombre=nombre_crudo, 
            api=api, 
            sulfur=sulfur,                # <-- AÑADIDO
            viscosity=viscosity,          # <-- AÑADIDO
            curva_json=json.dumps(curva)
        )
        db.session.add(nuevo_crudo)
        msg = f"Crudo '{nombre_crudo}' guardado."
    
    db.session.commit()
    return jsonify(success=True, message=msg)

@login_required
@app.route('/api/crudos_guardados/<string:nombre_crudo>', methods=['DELETE'])
def delete_crudo(nombre_crudo):
    """Elimina un crudo guardado de la base de datos."""
    crudo_a_eliminar = DefinicionCrudo.query.filter_by(nombre=nombre_crudo).first()
    
    if crudo_a_eliminar:
        db.session.delete(crudo_a_eliminar)
        db.session.commit()
        return jsonify(success=True, message=f"Crudo '{nombre_crudo}' eliminado.")
    else:
        return jsonify(success=False, message="Crudo no encontrado."), 404


@app.route('/')
def home():
    """Redirige al usuario a su página de inicio correcta después de iniciar sesión."""
    if 'email' not in session:
        return redirect(url_for('login'))

    # Si el rol es 'admin', siempre va al dashboard completo.
    if session.get('rol') == 'admin':
        return redirect(url_for('dashboard_reportes'))
    
    user_areas = session.get('area', [])

    # Redirección para el área de Logística (Generar Guía)
    if 'guia_transporte' in user_areas and len(user_areas) == 1:
        return redirect(url_for('home_logistica'))

    # Redirección para el área de Inventario SIZA
    if 'zisa_inventory' in user_areas and len(user_areas) == 1:
        return redirect(url_for('home_siza'))

    # Todos los demás usuarios (o con múltiples permisos) van al dashboard general.
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