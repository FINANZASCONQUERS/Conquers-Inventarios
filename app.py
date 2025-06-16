import json
from datetime import datetime, time # 'time' es importante para HORA_LIMITE
import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file # Añadido send_file
from werkzeug.security import generate_password_hash, check_password_hash
import openpyxl # Para Excel - Recuerda: pip install openpyxl
from io import BytesIO # Para Excel
import logging # Para un logging más flexible
import copy

def formatear_info_actualizacion(fecha_str_original, usuario_str, tipo_fecha="underscore"):
    """
    Formatea la fecha y el usuario para el mensaje de "Última actualización".
    """
    try:
        if not fecha_str_original or not usuario_str:
            return "Información de actualización no disponible."

        # CORRECCIÓN: El formato ahora usa guiones bajos para coincidir con los datos guardados.
        formato_entrada = "%Y_%m_%d_%H_%M_%S"
        
        # Convierte el texto a un objeto datetime
        dt_obj = datetime.strptime(fecha_str_original, formato_entrada)

        # MEJORA: Formato con meses en español para mayor claridad
        meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        nombre_mes = meses[dt_obj.month - 1]
        
        fecha_formateada = dt_obj.strftime(f"%d de {nombre_mes} de %Y")
        hora_formateada = dt_obj.strftime("%I:%M %p") # Formato 12-horas con AM/PM

        # Crear el mensaje final
        mensaje = f"Última actualización guardada por {usuario_str} el {fecha_formateada} a las {hora_formateada}"
        return mensaje

    except (ValueError, TypeError) as e:
        # Si el parseo falla por alguna razón, se muestra este mensaje de error.
        print(f"Error al formatear fecha: {e}") 
        return f"Fecha de registro (error de formato): {fecha_str_original}"

app = Flask(__name__)
app.secret_key = 'clave_secreta_para_produccion_cambiar'

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
    {"ORIGEN": "", "FECHA": "", "GUIA": "", "PRODUCTO": "", "PLACA": "", "API": "", "BSW": "", "TOV": "", "GSV": "", "NSV": ""}
    for _ in range(10)  # O el número de filas que desees por defecto
]

PLANILLA_TRANSITO_REFINERIA = [
    {"ORIGEN": "", "FECHA": "", "GUIA": "", "PRODUCTO": "", "PLACA": "", "API": "", "BSW": "", "TOV": "", "GSV": "", "NSV": ""}
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
        fecha = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
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
        "REFINERIA": {"campos": {}},
        "EDSM": {"campos": {}}
    }
    try:
        if os.path.exists(ruta_config):
            with open(ruta_config, 'r', encoding='utf-8') as f:
                config = json.load(f)
            # Validaciones básicas
            if not isinstance(config, dict) or \
               "REFINERIA" not in config or "campos" not in config["REFINERIA"] or \
               "EDSM" not in config or "campos" not in config["EDSM"]:
                print(f"Advertencia: Estructura inválida en {ruta_config}. Usando configuración por defecto.")
                return default_config
            return config
        else:
            print(f"Advertencia: {ruta_config} no encontrado. Usando configuración por defecto.")
            return default_config
    except Exception as e:
        print(f"Error crítico al cargar {ruta_config}: {e}. Usando configuración por defecto.")

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
    carpeta_registros = os.path.join(BASE_DIR, "registros")
    os.makedirs(carpeta_registros, exist_ok=True)
    try:
        archivos_general = sorted([f for f in os.listdir(carpeta_registros) if f.startswith("transito_general_") and f.endswith(".json")], reverse=True)
        if archivos_general:
            with open(os.path.join(carpeta_registros, archivos_general[0]), 'r', encoding='utf-8') as f:
                datos_general = json.load(f).get('datos', [])
        else:
            datos_general = [] # Usar la lista vacía si no hay registros
    except Exception as e:
        print(f"Error cargando datos de tránsito general: {e}")
        datos_general = []

    # Cargar los últimos datos guardados para 'refineria'
    try:
        archivos_refineria = sorted([f for f in os.listdir(carpeta_registros) if f.startswith("transito_refineria_") and f.endswith(".json")], reverse=True)
        if archivos_refineria:
            with open(os.path.join(carpeta_registros, archivos_refineria[0]), 'r', encoding='utf-8') as f:
                datos_refineria = json.load(f).get('datos', [])
        else:
            datos_refineria = [] # Usar la lista vacía si no hay registros
    except Exception as e:
        print(f"Error cargando datos de tránsito refinería: {e}")
        datos_refineria = []

    transito_config_data = cargar_transito_config()

    # Ahora se pasan los datos cargados del último archivo, no las plantillas vacías.
    return render_template("transito.html",
        nombre=session.get("nombre"),
        datos_general=datos_general, 
        datos_refineria=datos_refineria,
        tipo_inicial="general",
        transito_config=transito_config_data
    )

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
   return render_template("planta.html", planilla=PLANILLA_PLANTA)

@login_required
@app.route('/reporte_planta')
def reporte_planta():
    carpeta = "registros"
    datos_planta_js = []
    # Usaremos una variable más descriptiva para la info completa
    fecha_actualizacion_info = "No hay registros guardados." 

    try:
        archivos_planta = sorted(
            [a for a in os.listdir(carpeta) if a.startswith("planta_") and a.endswith(".json")], 
            reverse=True
        )
        if archivos_planta:
            ruta_mas_reciente = os.path.join(carpeta, archivos_planta[0])
            with open(ruta_mas_reciente, encoding='utf-8') as f:
                planta_data_cargada = json.load(f)
            
            datos_planta_js = planta_data_cargada.get("datos", [])
            
            # Usar las claves correctas guardadas por guardar_registro_generico
            fecha_guardado = planta_data_cargada.get("fecha") 
            usuario_guardado = planta_data_cargada.get("usuario")
            
            fecha_actualizacion_info = formatear_info_actualizacion(fecha_guardado, usuario_guardado, tipo_fecha="underscore")

        else:
            datos_planta_js = PLANILLA_PLANTA 
            # fecha_actualizacion_info ya tiene "No hay registros guardados."
            
    except Exception as e:
        print(f"Error crítico al cargar datos para /reporte_planta: {e}")
        datos_planta_js = [] 
        fecha_actualizacion_info = "Error al cargar la información de actualización."
        flash(f"No se pudo cargar el reporte de planta: {str(e)}", "danger")

    return render_template("reporte_planta.html", 
                           datos_planta_para_js=datos_planta_js,
                           fecha_actualizacion_info=fecha_actualizacion_info)

@login_required
@app.route('/guardar-registro-transito-<tipo_transito>', methods=['POST'])
def guardar_transito(tipo_transito): # tipo_transito será 'general' o 'refineria'
    app.logger.info(f"Solicitud para guardar tránsito tipo: {tipo_transito}")
    
    # --- INICIO VERIFICACIÓN DE HORA PARA TRÁNSITO ---
    '''
    try:
        HORA_LIMITE = time(10, 0, 0) # Definición de la hora límite
        hora_actual_servidor = datetime.now().time()
        app.logger.info(f"Guardar Tránsito - Hora actual: {hora_actual_servidor}, Hora límite: {HORA_LIMITE}")

        if hora_actual_servidor >= HORA_LIMITE:
            mensaje = f"No se pueden registrar datos de tránsito ('{tipo_transito}') después de las {HORA_LIMITE.strftime('%I:%M %p').replace('AM','a.m.').replace('PM','p.m.')}."
            app.logger.warning(f"Intento de guardado denegado por hora límite: {mensaje} para usuario {session.get('nombre')}")
            return jsonify(success=False, message=mensaje), 403 # 403 Forbidden es apropiado
    except NameError as ne:
        app.logger.error(f"Error de programación en guardar_transito (verificación de hora): {ne}. ¿Falta importar 'time' de 'datetime'?")
        return jsonify(success=False, message="Error de configuración del servidor (verificación de hora)."), 500
    except Exception as e_time_check:
        app.logger.error(f"Error inesperado en verificación de hora para guardar_transito: {e_time_check}")
        return jsonify(success=False, message="Error del servidor al verificar la hora del registro."), 500
 '''
    
    # --- FIN VERIFICACIÓN DE HORA ---

    try:
        datos_recibidos = request.get_json()
        if not isinstance(datos_recibidos, list):
            app.logger.error(f"Guardar Tránsito: Los datos recibidos no son una lista. Tipo: {type(datos_recibidos)}")
            return jsonify(success=False, message="El formato de datos enviados es incorrecto (se esperaba una lista)."), 400
        app.logger.info(f"Guardar Tránsito: {len(datos_recibidos)} filas recibidas. Muestra de la primera fila (si existe): {json.dumps(datos_recibidos[0] if datos_recibidos else {}, indent=2)}")
    except Exception as e_json_load:
        app.logger.error(f"Guardar Tránsito: Error al obtener o parsear JSON de la solicitud: {e_json_load}")
  
    # Validar que tipo_transito sea uno de los esperados
    if tipo_transito not in ["general", "refineria"]: # Asumiendo que estos son los valores que usa tu JS en la URL
        app.logger.error(f"Guardar Tránsito: tipo_transito inválido recibido en la URL: '{tipo_transito}'")
        return jsonify(success=False, message=f"Tipo de planilla de tránsito '{tipo_transito}' no es válido."), 400

    fecha_registro_dt = datetime.now() 
    fecha_str_para_nombre_archivo = fecha_registro_dt.strftime("%Y-%m-%d_%H-%M-%S") 

    # Usar BASE_DIR para asegurar la ruta correcta de la carpeta 'registros'
    carpeta_registros_path = os.path.join(BASE_DIR, "registros")
    try:
        os.makedirs(carpeta_registros_path, exist_ok=True)
    except OSError as e_mkdir:
        app.logger.error(f"Guardar Tránsito: Error crítico al crear directorio de registros '{carpeta_registros_path}': {e_mkdir}")
        return jsonify(success=False, message="Error del servidor al preparar el almacenamiento de registros."), 500

    nombre_archivo_final = f"transito_{tipo_transito}_{fecha_str_para_nombre_archivo}.json"
    ruta_archivo_final = os.path.join(carpeta_registros_path, nombre_archivo_final)
    app.logger.info(f"Guardar Tránsito: Se intentará guardar en: {ruta_archivo_final}")

    datos_procesados_para_guardar = []
    for fila_idx, fila_original in enumerate(datos_recibidos):
        if not isinstance(fila_original, dict):
            app.logger.warning(f"Guardar Tránsito: Fila {fila_idx} no es un diccionario, se omitirá. Contenido: {fila_original}")
            continue
        fila_procesada = {}
        for k, v_original in fila_original.items():
            if k == "FECHA" and v_original and isinstance(v_original, str) and "/" in v_original:
                try:
                    dt_obj = datetime.strptime(v_original, "%d/%m/%Y")
                    fila_procesada[k] = dt_obj.strftime("%Y-%m-%d") # Guardar en formato ISO YYYY-MM-DD
                except ValueError:
                    app.logger.warning(f"Guardar Tránsito: Formato de fecha inválido '{v_original}' en fila {fila_idx}, se guardará como texto.")
                    fila_procesada[k] = v_original 
            else:
                fila_procesada[k] = v_original
        datos_procesados_para_guardar.append(fila_procesada)


    data_to_save_in_file = {
        "timestamp_iso": fecha_registro_dt.isoformat(), 
        "fecha_guardado_str": fecha_str_para_nombre_archivo, 
        "tipo_transito": tipo_transito, # 'general' o 'refineria'
        "usuario": session.get("nombre"),
        "datos": datos_procesados_para_guardar # La lista de filas que vino del frontend (con fechas procesadas)
    }

    try:
        with open(ruta_archivo_final, 'w', encoding='utf-8') as f:
            json.dump(data_to_save_in_file, f, ensure_ascii=False, indent=2)
        app.logger.info(f"REGISTRO DE TRÁNSITO GUARDADO EXITOSAMENTE: {nombre_archivo_final}")
        
        # Actualizar las planillas globales en memoria (si tu vista de edición directa las usa)
        # Esto es opcional y depende de cómo cargues los datos en la vista de edición /transito
        if tipo_transito == "general":
            global PLANILLA_TRANSITO_GENERAL
            PLANILLA_TRANSITO_GENERAL = [dict(d) for d in datos_procesados_para_guardar] # Actualizar con los datos guardados
        elif tipo_transito == "refineria":
            global PLANILLA_TRANSITO_REFINERIA
            PLANILLA_TRANSITO_REFINERIA = [dict(d) for d in datos_procesados_para_guardar]

        return jsonify(success=True, message=f"Registro de tránsito '{tipo_transito}' guardado exitosamente.")
    except Exception as e_write_file:
        app.logger.error(f"Guardar Tránsito: Error crítico al escribir el archivo de registro '{ruta_archivo_final}': {e_write_file}")
        return jsonify(success=False, message=f"Error del servidor al guardar el archivo de registro: {str(e_write_file)}"), 500
    
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
@app.route('/reporte_transito')
def reporte_transito():
    app.logger.info("Accediendo a /reporte_transito")
    datos_consolidados = {}
    datos_conteo_camiones = {}
    fecha_actualizacion_info = "No hay registros de tránsito para mostrar."
    
    carpeta_registros_path = os.path.join(BASE_DIR, "registros")
    os.makedirs(carpeta_registros_path, exist_ok=True)

    try:
        # 1. Obtener todos los archivos de registro de tránsito
        todos_los_archivos = [a for a in os.listdir(carpeta_registros_path) if a.startswith("transito_") and a.endswith(".json")]

        if not todos_los_archivos:
            return render_template("reporte_transito.html", datos_consolidados=datos_consolidados, datos_conteo_camiones=datos_conteo_camiones, nombre=session.get("nombre"), fecha_actualizacion_info=fecha_actualizacion_info)

        # 2. Encontrar la fecha más reciente de los archivos
        fechas = set()
        for archivo in todos_los_archivos:
            try:
                # Extrae la fecha del nombre del archivo, ej: transito_general_YYYY-MM-DD_...
                fecha_str = archivo.split('_')[2]
                fechas.add(fecha_str)
            except IndexError:
                continue # Ignora archivos con formato de nombre incorrecto

        if not fechas:
            raise ValueError("No se encontraron archivos de registro con formato de fecha válido.")

        fecha_mas_reciente = max(fechas)

        # 3. Filtrar archivos que corresponden solo al día más reciente
        archivos_del_dia = [a for a in todos_los_archivos if fecha_mas_reciente in a]
        
        # Actualizar la info con el primer archivo del día
        if archivos_del_dia:
            ruta_primer_archivo = os.path.join(carpeta_registros_path, sorted(archivos_del_dia, reverse=True)[0])
            with open(ruta_primer_archivo, 'r', encoding='utf-8') as f:
                data_primer_archivo = json.load(f)
            usuario_guardado = data_primer_archivo.get("usuario", "N/A")
            fecha_actualizacion_info = f"Mostrando registros consolidados del día {fecha_mas_reciente}. Último guardado por {usuario_guardado}."


        # 4. Procesar y consolidar los datos de los archivos de ese día
        for archivo_nombre in archivos_del_dia:
            ruta_completa = os.path.join(carpeta_registros_path, archivo_nombre)
            with open(ruta_completa, 'r', encoding='utf-8') as f:
                data_archivo = json.load(f)

            tipo_archivo_guardado = data_archivo.get("tipo_transito") # 'general' o 'refineria'
            registros_individuales = data_archivo.get("datos", [])

            if not tipo_archivo_guardado or not isinstance(registros_individuales, list):
                continue

            tipo_destino_reporte = "Refinería" if tipo_archivo_guardado == "refineria" else "EDSM"
            
            for reg in registros_individuales:
                origen = reg.get("ORIGEN", "").strip()
                producto = reg.get("PRODUCTO", "").strip()
                
                # Saltar filas que no tengan origen y producto
                if not origen or not producto:
                    continue
                
                try:
                    nsv_str = str(reg.get("NSV", "0")).replace(',', '.')
                    nsv = float(nsv_str) if nsv_str else 0.0
                except (ValueError, TypeError):
                    nsv = 0.0

                # Consolidar datos de NSV
                datos_consolidados.setdefault(tipo_destino_reporte, {}).setdefault(origen, {}).setdefault(producto, 0.0)
                datos_consolidados[tipo_destino_reporte][origen][producto] += nsv
                
                # Contar viajes
                datos_conteo_camiones.setdefault(tipo_destino_reporte, {}).setdefault(origen, {}).setdefault(producto, 0)
                datos_conteo_camiones[tipo_destino_reporte][origen][producto] += 1
                
    except Exception as e:
        app.logger.error(f"Error crítico al generar reporte de tránsito: {e}")
        flash(f"Ocurrió un error al generar el reporte: {e}", "danger")
        fecha_actualizacion_info = "Error al cargar los datos."

    return render_template("reporte_transito.html",
                           datos_consolidados=datos_consolidados,
                           datos_conteo_camiones=datos_conteo_camiones,
                           nombre=session.get("nombre"),
                           fecha_actualizacion_info=fecha_actualizacion_info)
@login_required
@permiso_requerido('barcaza_orion')
@app.route('/barcaza_orion')
def barcaza_orion():
    # Lógica para cargar datos guardados (esta parte no cambia)
    datos_guardados = []
    try:
        carpeta = "registros"
        archivos_orion = sorted([a for a in os.listdir(carpeta) if a.startswith("barcaza_orion_") and a.endswith(".json")], reverse=True)
        if archivos_orion:
            ruta_reciente = os.path.join(carpeta, archivos_orion[0])
            with open(ruta_reciente, 'r', encoding='utf-8') as f:
                contenido = json.load(f)
            datos_guardados = contenido.get("datos", [])
    except Exception:
        pass
    
    fuente_de_datos = datos_guardados if datos_guardados else PLANILLA_BARCAZA_ORION

    # --- INICIO DE LA CORRECCIÓN ---
    # Ahora filtramos usando la clave "grupo" que añadiste. Es mucho más limpio.
    tanques_principales = [tk for tk in fuente_de_datos if tk.get('grupo') == 'PRINCIPAL']
    tanques_man = [tk for tk in fuente_de_datos if tk.get('grupo') == 'MANZANILLO']
    tanques_cr = [tk for tk in fuente_de_datos if tk.get('grupo') == 'CR']
    tanques_margoth = [tk for tk in fuente_de_datos if tk.get('grupo') == 'MARGOTH']
    tanques_odisea = [tk for tk in fuente_de_datos if tk.get('grupo') == 'ODISEA']
    # --- FIN DE LA CORRECCIÓN ---

    return render_template("barcaza_orion.html",
                           titulo="Planilla Barcaza Orion",
                           tanques_principales=tanques_principales,
                           tanques_man=tanques_man,
                           tanques_cr=tanques_cr,
                           tanques_margoth=tanques_margoth,
                           tanques_odisea=tanques_odisea,
                           nombre=session.get("nombre"))
@login_required
@permiso_requerido('barcaza_bita')
@app.route('/barcaza_bita')
def barcaza_bita():
    datos_guardados = []
    try:
        carpeta = "registros"
        archivos_bita = sorted([a for a in os.listdir(carpeta) if a.startswith("barcaza_bita_") and a.endswith(".json")], reverse=True)
        if archivos_bita:
            ruta_reciente = os.path.join(carpeta, archivos_bita[0])
            with open(ruta_reciente, 'r', encoding='utf-8') as f:
                contenido = json.load(f)
            datos_guardados = contenido.get("datos", [])
    except Exception:
        # Si hay algún error (ej. la carpeta no existe), no hace nada y usará la planilla en blanco.
        pass

    # 3. DECIDIR QUÉ DATOS MOSTRAR
    # Si 'datos_guardados' tiene algo, úsalo. Si no, usa la planilla por defecto.
    fuente_de_datos = datos_guardados if datos_guardados else PLANILLA_BARCAZA_BITA

    # 4. CREAR LOS GRUPOS PARA LA PÁGINA
    grupos = {
        "BARCAZA MARINSE": [tk for tk in fuente_de_datos if tk.get('TK', '').startswith('MARI')],
        "BARCAZA OIDECH": [tk for tk in fuente_de_datos if tk.get('TK', '').startswith('OID')]
    }
    
    # 5. RENDERIZAR LA PÁGINA CON LOS DATOS CARGADOS
    return render_template(
        "barcaza_bita.html", 
        titulo="Planilla Barcaza BITA", 
        grupos=grupos,
        nombre=session.get('nombre', 'Desconocido') 
    )

@login_required
@permiso_requerido('guia_transporte') 
@app.route('/guia_transporte')
def guia_transporte():
    # El if de permisos ya no es necesario aquí.
    return render_template("guia_transporte.html", nombre=session.get("nombre"))

@login_required
@app.route('/reporte_barcaza')
def reporte_barcaza():
    """
    Muestra el reporte de la Barcaza Orion, calculando un total consolidado
    y luego desglosando por cada grupo de tanques.
    """
    # --- 1. Carga de datos del archivo JSON más reciente ---
    carpeta = "registros"
    fecha_actualizacion_info = "No hay registros de Barcaza Orion guardados."
    datos_barcaza_reporte = []
    
    try:
        os.makedirs(carpeta, exist_ok=True)
        archivos_orion = sorted([a for a in os.listdir(carpeta) if a.startswith("barcaza_orion_") and a.endswith(".json")], reverse=True)

        if archivos_orion:
            ruta_reciente = os.path.join(carpeta, archivos_orion[0])
            with open(ruta_reciente, 'r', encoding='utf-8') as f:
                contenido = json.load(f)
            
            datos_barcaza_reporte = contenido.get("datos", [])
            fecha_guardado = contenido.get("fecha")
            usuario_guardado = contenido.get("usuario")
            fecha_actualizacion_info = formatear_info_actualizacion(fecha_guardado, usuario_guardado)

    except Exception as e:
        flash(f"Error al generar el reporte de barcaza: {e}", "danger")
        fecha_actualizacion_info = "Error al cargar la información."

    total_consolidado = calcular_estadisticas(datos_barcaza_reporte)

    barcazas_agrupadas = {}
    nombres_display = {
        "PRINCIPAL": "Tanque Principal (TK-101)", "MANZANILLO": "Barcaza Manzanillo (MGO)",
        "CR": "Barcaza CR", "MARGOTH": "Barcaza Margoth", "ODISEA": "Barcaza Odisea"
    }
    if datos_barcaza_reporte:
        for tanque in datos_barcaza_reporte:
            grupo_key = tanque.get("grupo")
            if grupo_key in nombres_display:
                nombre_barcaza = nombres_display[grupo_key]
                if nombre_barcaza not in barcazas_agrupadas:
                    barcazas_agrupadas[nombre_barcaza] = []
                barcazas_agrupadas[nombre_barcaza].append(tanque)

    datos_para_template = {}
    for nombre_barcaza, tanques_list in barcazas_agrupadas.items():
        estadisticas = calcular_estadisticas(tanques_list)
        datos_para_template[nombre_barcaza] = {
            "tanques": tanques_list,
            "totales": estadisticas 
        }
    return render_template("reporte_barcaza_orion.html",
                           datos_para_template=datos_para_template,
                           total_consolidado=total_consolidado,
                           fecha_actualizacion_info=fecha_actualizacion_info,
                           todos_los_tanques_json=json.dumps(datos_barcaza_reporte)
                          )

@login_required   
@app.route('/reporte_barcaza_bita')
def reporte_barcaza_bita():
    """
    Muestra el reporte interactivo de la Barcaza BITA.
    """
    # --- 1. Carga de datos del archivo JSON más reciente ---
    carpeta = "registros"
    fecha_actualizacion_info = "No hay registros de Barcaza BITA guardados."
    datos_reporte = []
    
    try:
        os.makedirs(carpeta, exist_ok=True)
        archivos_bita = sorted([a for a in os.listdir(carpeta) if a.startswith("barcaza_bita_") and a.endswith(".json")], reverse=True)
        
        if archivos_bita:
            ruta_reciente = os.path.join(carpeta, archivos_bita[0])
            with open(ruta_reciente, 'r', encoding='utf-8') as f:
                contenido = json.load(f)
            datos_reporte = contenido.get("datos", [])
            fecha_guardado = contenido.get("fecha")
            usuario_guardado = contenido.get("usuario")
            fecha_actualizacion_info = formatear_info_actualizacion(fecha_guardado, usuario_guardado)
    except Exception as e:
        flash(f"Error al generar el reporte de barcaza BITA: {e}", "danger")
        fecha_actualizacion_info = "Error al cargar la información."

    # --- 2. Calcular el total consolidado inicial ---
    total_consolidado = calcular_estadisticas(datos_reporte)

    # --- 3. Separación de datos para la vista inicial ---
    tanques_marinse = [tk for tk in datos_reporte if tk.get('TK','').startswith('MARI')]
    tanques_oidech = [tk for tk in datos_reporte if tk.get('TK','').startswith('OID')]

    # --- 4. Cálculo de estadísticas para cada grupo ---
    stats_marinse = calcular_estadisticas(tanques_marinse)
    stats_oidech = calcular_estadisticas(tanques_oidech)
    
    # --- 5. Renderizado de la plantilla con las nuevas variables ---
    return render_template(
        "reporte_barcaza_bita.html",
        titulo="Reporte Interactivo - Barcaza BITA",
        fecha_actualizacion_info=fecha_actualizacion_info,
        nombre=session.get('nombre', 'Desconocido'),
        
        # Nuevas variables para la interactividad
        total_consolidado=total_consolidado,
        todos_los_tanques_json=json.dumps(datos_reporte),

        # Datos para los grupos (la plantilla los usará para la estructura inicial)
        tanques_marinse=tanques_marinse,
        stats_marinse=stats_marinse,
        tanques_oidech=tanques_oidech,
        stats_oidech=stats_oidech
    )



@login_required
@app.route('/guardar_celda_bita', methods=['POST'])
def guardar_celda_bita():
    # PERMISO: Ricardo puede editar celdas de BITA
    if session.get('email') != "quality.manager@conquerstrading.com":
        return jsonify(success=False, message="Permiso denegado"), 403

    data = request.get_json()
    tk = data.get("tk")
    field = data.get("field")
    value = data.get("value")

    if not all([tk, field is not None]):
        return jsonify(success=False, message="Datos incompletos"), 400

    # Busca en la planilla de BITA
    for fila in PLANILLA_BARCAZA_BITA:
        if fila["TK"] == tk:
            fila[field] = value
            return jsonify(success=True)

    return jsonify(success=False, message="Tanque no encontrado en la planilla BITA"), 404

@login_required
@permiso_requerido('barcaza_orion') 
@app.route('/guardar_celda_barcaza', methods=['POST'])
def guardar_celda_barcaza():
    # El 'if' manual que causaba el error de permisos ya no es necesario
    
    data = request.get_json()
    tk = data.get("tk")
    field = data.get("field")
    value = data.get("value")
    grupo = data.get("grupo") 

    if not all([tk, field is not None, grupo is not None]):
        return jsonify(success=False, message="Datos incompletos"), 400

    # Búsqueda usando la clave compuesta TK + GRUPO para más seguridad
    tanque_encontrado = False
    for fila in PLANILLA_BARCAZA_ORION:
        if fila.get("TK") == tk and fila.get("grupo") == grupo:
            fila[field] = value
            tanque_encontrado = True
            break # Encontramos el único tanque, podemos salir del bucle

    if tanque_encontrado:
        return jsonify(success=True, message=f"Celda {field} de {tk} ({grupo}) actualizada.")
    else:
        return jsonify(success=False, message=f"Tanque no encontrado: {tk} en grupo {grupo}"), 404

@login_required
@permiso_requerido('barcaza_orion')
@app.route('/guardar_registro_barcaza', methods=['POST'])
def guardar_registro_barcaza():
    datos_actualizados = request.get_json()
    
    # 3. Valida que los datos se recibieron correctamente
    if not datos_actualizados or not isinstance(datos_actualizados, list):
        return jsonify(success=False, message="No se recibieron datos o el formato es incorrecto."), 400

    # 4. Lógica de guardado explícita y completa
    try:
        ahora = datetime.now()
        timestamp = ahora.strftime('%Y_%m_%d_%H_%M_%S')
        usuario_actual = session.get('nombre', 'Usuario Desconocido')

        carpeta = "registros"
        os.makedirs(carpeta, exist_ok=True) # Crea la carpeta si no existe
        
        # Nombre de archivo específico para Orion
        nombre_archivo = f"barcaza_orion_{timestamp}.json"
        ruta_completa = os.path.join(carpeta, nombre_archivo)

        # Contenido completo a guardar en el archivo
        contenido_a_guardar = {
            "fecha": timestamp,
            "usuario": usuario_actual,
            "datos": datos_actualizados
        }

        # Escribir el archivo .json
        with open(ruta_completa, 'w', encoding='utf-8') as f:
            json.dump(contenido_a_guardar, f, ensure_ascii=False, indent=4)
        
        # Devolver respuesta de éxito al JavaScript
        return jsonify(success=True, message="Registro de Barcaza Orion guardado exitosamente.")

    except Exception as e:
        # Si algo sale mal durante el guardado, se informa el error
        print(f"Error al guardar registro de Orion: {e}")
        return jsonify(success=False, message=f"Error interno del servidor al guardar el archivo: {e}"), 500
    

@login_required
@app.route('/dashboard_reportes')
def dashboard_reportes():
    # El permiso de acceso no necesita cambios
    user_areas = session.get('area', [])
    if session.get('rol') != 'admin' and len(user_areas) == 1 and user_areas[0] == 'guia_transporte':
        return redirect(url_for('home_logistica'))

    carpeta = "registros"
    os.makedirs(carpeta, exist_ok=True)
    
    # --- INICIO DE LA LÓGICA MEJORADA ---

    def crear_resumen(prefijo_archivo):
        """
        Función auxiliar para cargar el último registro de un área y formatear su información.
        """
        resumen = {
            "datos": [], 
            "info_completa": "Sin Registros"
        }
        try:
            archivos = sorted([a for a in os.listdir(carpeta) if a.startswith(prefijo_archivo) and a.endswith(".json")], reverse=True)
            if archivos:
                ruta_reciente = os.path.join(carpeta, archivos[0])
                with open(ruta_reciente, 'r', encoding='utf-8') as f:
                    contenido = json.load(f)
                
                # Guarda la lista de datos para cálculos en la plantilla (ej. total BLS)
                resumen["datos"] = contenido.get("datos", [])
                
                # Usa la función que ya tienes para crear el texto con fecha, hora y usuario
                resumen["info_completa"] = formatear_info_actualizacion(
                    contenido.get("fecha"),
                    contenido.get("usuario")
                )
        except Exception as e:
            print(f"Error cargando resumen para {prefijo_archivo}: {e}")
            resumen["info_completa"] = "Error al cargar datos"
            
        return resumen

    # Llama a la función auxiliar para cada tipo de reporte
    planta_summary = crear_resumen("planta_")
    transito_summary = crear_resumen("transito_")
    orion_summary = crear_resumen("barcaza_orion_")
    bita_summary = crear_resumen("barcaza_bita_")
    
    recent_activities = []
    try:
        # 1. Obtener TODOS los archivos .json de la carpeta de registros
        todos_los_archivos = [f for f in os.listdir(carpeta) if f.endswith(".json")]
        
        # 2. Ordenarlos por nombre para tener los más recientes primero
        todos_los_archivos.sort(reverse=True)
        
        # 3. Tomar solo los últimos 7 registros para mostrar
        for archivo in todos_los_archivos[:7]:
            ruta = os.path.join(carpeta, archivo)
            with open(ruta, 'r', encoding='utf-8') as f:
                contenido = json.load(f)

            # Extraer la información relevante
            fecha_str = contenido.get("fecha", "")
            usuario = contenido.get("usuario", "N/A")
            
            # Determinar el módulo y el color basado en el nombre del archivo
            if "planta" in archivo:
                modulo = {"nombre": "Planta", "color": "planta"}
            elif "transito" in archivo:
                modulo = {"nombre": "Tránsito", "color": "transito"}
            elif "barcaza_orion" in archivo:
                modulo = {"nombre": "Barcaza Orion", "color": "orion"}
            elif "barcaza_bita" in archivo:
                modulo = {"nombre": "Barcaza BITA", "color": "bita"}
            else:
                modulo = {"nombre": "Desconocido", "color": "secondary"}

            # Formatear solo la hora
            try:
                hora = datetime.strptime(fecha_str, "%Y_%m_%d_%H_%M_%S").strftime("%I:%M %p")
            except:
                hora = "Hora inválida"

            recent_activities.append({
                "module": modulo["nombre"],
                "module_color": modulo["color"],
                "action": "Registro guardado",
                "user": usuario,
                "time": hora
            })
    except Exception as e:
        print(f"Error al generar actividad reciente: {e}")

    # --- FIN DE LA NUEVA LÓGICA ---

   

    # Renderiza la plantilla pasándole los nuevos diccionarios de resumen
    return render_template("dashboard_reportes.html",
                           nombre=session.get("nombre"),
                           planta_summary=planta_summary,
                           transito_summary=transito_summary,
                           orion_summary=orion_summary,
                           bita_summary=bita_summary)

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
@app.route('/guardar-registro-planta', methods=['POST'])
def guardar_registro_planta():
    # --- VERIFICACIÓN DE HORA (TEMPORALMENTE DESACTIVADA) ---
    # Se ha añadido y comentado un bloque similar para la planta.
    '''
    try:
        HORA_LIMITE = time(10, 0, 0)
        hora_actual_servidor = datetime.now().time()
        if hora_actual_servidor >= HORA_LIMITE:
            mensaje = f"No se pueden registrar datos de planta después de las {HORA_LIMITE.strftime('%I:%M %p').replace('AM','a.m.').replace('PM','p.m.')}."
            return jsonify(success=False, message=mensaje), 403
    except Exception as e_time_check:
        app.logger.error(f"Error inesperado en verificación de hora para guardar_planta: {e_time_check}")
        return jsonify(success=False, message="Error del servidor al verificar la hora del registro."), 500
    '''
    # --- FIN VERIFICACIÓN DE HORA ---

    # Corrección para que la función procese los datos y llame a guardar_registro_generico
    datos_actualizados = request.get_json()
    if not datos_actualizados or not isinstance(datos_actualizados, list):
        return jsonify(success=False, message="No se recibieron datos o el formato es incorrecto."), 400

    return guardar_registro_generico(datos_actualizados, "planta")


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
    """Muestra la página para añadir nuevos clientes y ver los existentes."""
    # Define qué áreas pueden gestionar clientes
    areas_permitidas = ['transito', 'logistica', 'barcaza']
    if session.get('area') not in areas_permitidas and session.get('rol') != 'admin':
        flash("No tienes permisos para gestionar clientes.", "danger")
        return redirect(url_for('home'))
        
    clientes_actuales = cargar_clientes()
    return render_template('gestionar_clientes.html', clientes=clientes_actuales)

@login_required
@app.route('/guardar_cliente', methods=['POST'])
def guardar_cliente():
    """Recibe los datos del formulario y guarda el nuevo cliente."""
    # Define qué áreas pueden guardar clientes
    areas_permitidas = ['transito', 'logistica', 'barcaza']
    if session.get('area') not in areas_permitidas and session.get('rol') != 'admin':
        flash("No tienes permisos para guardar clientes.", "danger")
        return redirect(url_for('home'))

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
    """Recibe datos de un nuevo cliente vía AJAX y los guarda."""
    # Revisa permisos
    areas_permitidas = ['transito', 'logistica', 'barcaza']
    if session.get('area') not in areas_permitidas and session.get('rol') != 'admin':
        return jsonify(success=False, message="Permiso denegado."), 403

    data = request.get_json()
    nombre = data.get('nombre')
    direccion = data.get('direccion')
    ciudad = data.get('ciudad')

    if not nombre or not direccion or not ciudad:
        return jsonify(success=False, message="Todos los campos son obligatorios."), 400

    clientes = cargar_clientes()

    if any(c['NOMBRE_CLIENTE'].lower() == nombre.lower() for c in clientes):
        return jsonify(success=False, message=f"El cliente '{nombre}' ya existe."), 409 # 409 Conflict

    nuevo_cliente = {
        "NOMBRE_CLIENTE": nombre.upper(),
        "DIRECCION": direccion.upper(),
        "CIUDAD_DEPARTAMENTO": ciudad.upper()
    }
    clientes.append(nuevo_cliente)
    clientes.sort(key=lambda x: x['NOMBRE_CLIENTE'])
    guardar_clientes(clientes)

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
    ruta_conductores = os.path.join(BASE_DIR, 'static', 'Conductores.json')
    with open(ruta_conductores, 'w', encoding='utf-8') as f:
        json.dump(conductores, f, ensure_ascii=False, indent=4)

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
    """Recibe datos de un nuevo conductor vía AJAX y los guarda."""
    # Revisa permisos
    areas_permitidas = ['transito', 'logistica', 'barcaza']
    if session.get('area') not in areas_permitidas and session.get('rol') != 'admin':
        return jsonify(success=False, message="Permiso denegado."), 403

    data = request.get_json()
    nombre = data.get('nombre')
    cedula = data.get('cedula')
    placa = data.get('placa')

    if not nombre or not cedula or not placa:
        return jsonify(success=False, message="Todos los campos son obligatorios."), 400

    conductores = cargar_conductores()

    # Verificar si la cédula ya existe para no duplicar conductores
    if any(c['CEDULA'].lower() == cedula.lower() for c in conductores):
        return jsonify(success=False, message=f"Un conductor con la cédula '{cedula}' ya existe."), 409

    nuevo_conductor = {
        "CONDUCTOR": nombre.upper(),
        "CEDULA": cedula.upper(),
        "PLACA": placa.upper()
    }
    conductores.append(nuevo_conductor)
    conductores.sort(key=lambda x: x['CONDUCTOR'])
    guardar_conductores(conductores)

    return jsonify(success=True, message="Conductor agregado exitosamente.", nuevo_conductor=nuevo_conductor)
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

if __name__ == '__main__':
    app.run(debug=True)
