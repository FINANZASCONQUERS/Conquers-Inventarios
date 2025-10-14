from sqlalchemy import or_
import json
import hashlib
from datetime import datetime, time, date, timedelta
import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file, current_app # Añadido send_file y current_app
from werkzeug.security import generate_password_hash, check_password_hash
import openpyxl 
from io import BytesIO # Para Excel
import logging # Para un logging más flexible
import copy
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
import pytz
import pandas as pd
import uuid
import re
from flask import g
from flask import Response
from weasyprint import HTML, CSS
import math
from sqlalchemy import or_
from flask_migrate import Migrate
import numpy as np
import re
import base64
from io import BytesIO
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from itertools import groupby
import io
from flask import Response
import base64

# --- Módulo modelo optimización (nuevo) ---
from modelo_optimizacion import ejecutar_modelo, EXCEL_DEFAULT

# Utilidad simple de permiso admin
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('rol') != 'admin':
            flash('Solo administradores pueden acceder a esta sección.', 'danger')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated

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
        
def componer_fecha_hora(hora_str, fecha_base=None):
    """
    Toma una hora en formato 'HH:MM' y la combina con una fecha base
    para crear un objeto datetime completo.
    """
    if not hora_str: return None
    
    # Si no se provee una fecha base, se usa la fecha del día actual.
    if fecha_base is None:
        fecha_base = date.today()
        
    try:
        # Crea un objeto 'time' desde el string "HH:MM"
        hora_obj = time.fromisoformat(hora_str)
        # Combina la fecha base con el objeto 'time'
        return datetime.combine(fecha_base, hora_obj)
    except (ValueError, TypeError):
        # Si el formato de hora es inválido (ej. "abc"), devuelve None.
        return None
    
def mes_espaniol(fecha_str):
    # fecha_str: '2025-01' o '2025-01-01'
    partes = fecha_str.split('-')
    anio = partes[0]
    mes = int(partes[1])
    meses_es = [
        '', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
        'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
    ]
    return f"{meses_es[mes]}-{anio}"
    
def convertir_plot_a_base64(fig):
    """Toma una figura de Matplotlib, la guarda en memoria y la devuelve como una cadena Base64."""
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)  # Cierra la figura para liberar memoria
    return base64.b64encode(buf.getvalue()).decode('utf-8')

def grafico_linea_base64(labels, data, ylabel):
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot(labels, data, marker='o', color='#007bff')
    ax.set_ylabel(ylabel)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha='right')
    for i, v in enumerate(data):
        ax.text(i, v, f'{v:.2f}', ha='center', va='bottom', fontsize=8)
    plt.tight_layout()
    buf = BytesIO()
    plt.savefig(buf, format='png')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')

def grafico_barra_base64(labels, data, ylabel):
    fig, ax = plt.subplots(figsize=(8, 3))
    bars = ax.bar(labels, data, color='#28a745')
    ax.set_ylabel(ylabel)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha='right')
    for bar in bars:
        height = bar.get_height()
        ax.annotate(f'{height:,.0f}', xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=8)
    plt.tight_layout()
    buf = BytesIO()
    plt.savefig(buf, format='png')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')

def procesar_analisis_remolcadores(registros):
    """
    Toma una lista de registros, ejecuta el análisis de Pandas y devuelve
    los resultados como HTML y gráficos en Base64.
    """
    if not registros:
        return None

    datos_df = [{
        "ID": r.maniobra_id, "BARCAZA": r.barcaza, "EVENTO ANTERIO": r.evento_anterior,
        "EVENTO ACTUAL": r.evento_actual, "HORA INICIO": r.hora_inicio, "HORA FIN": r.hora_fin,
        "MT ENTREGADAS": float(r.mt_entregadas) if r.mt_entregadas else 0.0,
        "CARGAS": r.carga_estado
    } for r in registros]
    
    if not datos_df:
        return None
        
    df = pd.DataFrame(datos_df)

    if df.empty or df['HORA FIN'].isnull().all():
        return None

    # --- Lógica de preparación de datos (sin cambios) ---
    df["HORA INICIO"] = pd.to_datetime(df["HORA INICIO"])
    df["HORA FIN"]   = pd.to_datetime(df["HORA FIN"])
    df.dropna(subset=['HORA INICIO', 'HORA FIN'], inplace=True)
    
    df["duration_hours"] = (df["HORA FIN"] - df["HORA INICIO"]).dt.total_seconds() / 3600
    df["pair"] = (df["EVENTO ANTERIO"].astype(str).str.strip().str.upper() + " -> " + df["EVENTO ACTUAL"].astype(str).str.strip().str.upper())
    df["trayecto_final"] = df["pair"]
    df = df.sort_values(["ID", "HORA INICIO"]).reset_index(drop=True)

    comb_rules = {
        ("LLEGADA SPD -> INICIO BASE OPS", "INICIO BASE OPS -> LLEGADA BASE OPS"): "INICIO SPD -> LLEGADA BASE OPS",
        ("LLEGADA SPD -> INICIO CONTECAR", "INICIO CONTECAR -> LLEGADA CONTECAR"): "INICIO SPD -> LLEGADA CONTECAR",
        ("LLEGADA SPD -> INICIO FONDEO", "INICIO FONDEO -> LLEGADA FONDEO"): "INICIO SPD -> LLEGADA FONDEO",
        ("LLEGADA SPD -> INICIO SPRC", "INICIO SPRC -> LLEGADA SPRC"): "INICIO SPD -> LLEGADA SPRC",
        ("LLEGADA SPD -> INICIO PUERTO BAHIA", "INICIO PUERTO BAHIA -> LLEGADA PUERTO BAHIA"): "INICIO SPD -> LLEGADA PUERTO BAHIA",
    
        ("LLEGADA BITA -> INICIO BASE OPS", "INICIO BASE OPS -> LLEGADA BASE OPS"): "INICIO BITA -> LLEGADA BASE OPS",
        ("LLEGADA BITA -> INICIO CONTECAR", "INICIO CONTECAR -> LLEGADA CONTECAR"): "INICIO BITA -> LLEGADA CONTECAR",
        ("LLEGADA BITA -> INICIO FONDEO", "INICIO FONDEO -> LLEGADA FONDEO"): "INICIO BITA -> LLEGADA FONDEO",
        ("LLEGADA BITA -> INICIO SPRC", "INICIO SPRC -> LLEGADA SPRC"): "INICIO BITA -> LLEGADA SPRC",
        ("LLEGADA BITA -> INICIO PUERTO BAHIA", "INICIO PUERTO BAHIA -> LLEGADA PUERTO BAHIA"): "INICIO BITA -> LLEGADA PUERTO BAHIA",
    }

    for i in range(len(df) - 1):
        if df.at[i, "ID"] != df.at[i + 1, "ID"]: continue
        key = (df.at[i, "pair"], df.at[i + 1, "pair"])
        if key in comb_rules:
            df.at[i, "duration_hours"] += df.at[i + 1, "duration_hours"]
            df.at[i, "HORA FIN"] = df.at[i + 1, "HORA FIN"]
            df.at[i, "trayecto_final"] = comb_rules[key]
            df.loc[i + 1, ["trayecto_final", "duration_hours"]] = [None, np.nan]

    def convertir_a_texto_legible(horas):
        if pd.isna(horas): return ""
        td = timedelta(hours=horas)
        h = int(td.total_seconds() // 3600)
        m = int((td.total_seconds() % 3600) // 60)
        partes = ([f"{h}h"] if h > 0 else []) + ([f"{m}m"] if m > 0 else [])
        return " ".join(partes) or "0m"

    # --- ANÁLISIS DE TRAYECTOS (sin cambios) ---
    pairs_loaded = [
        "INICIO SPD -> LLEGADA CONTECAR", "INICIO SPD -> LLEGADA SPRC", "INICIO SPD -> LLEGADA FONDEO", 
        "INICIO SPD -> LLEGADA PUERTO BAHIA", "INICIO BITA -> LLEGADA CONTECAR", "INICIO BITA -> LLEGADA SPRC", 
        "INICIO BITA -> LLEGADA FONDEO", "INICIO BITA -> LLEGADA PUERTO BAHIA", "ESPERAR AUTORIZACION -> AUTORIZADO"
    ]
    pairs_empty = [
    # Viajes directos
    "INICIO BASE OPS -> LLEGADA BITA",
    "INICIO BASE OPS -> LLEGADA SPD",
    "INICIO CONTECAR -> LLEGADA BASE OPS",
    "INICIO CONTECAR -> LLEGADA BITA",
    "INICIO CONTECAR -> LLEGADA SPD",
    "INICIO FONDEO -> LLEGADA BASE OPS",
    "INICIO FONDEO -> LLEGADA BITA",
    "INICIO FONDEO -> LLEGADA SPD",
    "INICIO PUERTO BAHIA -> LLEGADA SPD",
    "INICIO PUERTO BAHIA -> LLEGADA BASE OPS",
    "INICIO PUERTO BAHIA -> LLEGADA BITA",
    "INICIO SPRC -> LLEGADA BASE OPS",
    "INICIO SPRC -> LLEGADA SPD",
    "INICIO BITA -> LLEGADA BASE OPS",
    "INICIO SPD -> LLEGADA BASE OPS"
]
    df_valido = df[df["trayecto_final"].notnull() & df['CARGAS'].notna()]
    df_loaded = df_valido[(df_valido["trayecto_final"].isin(pairs_loaded)) & (df_valido["CARGAS"].str.upper() == "LLENO")]
    df_empty = df_valido[(df_valido["trayecto_final"].isin(pairs_empty)) & (df_valido["CARGAS"].str.upper() == "VACIO")]
    prom_loaded = df_loaded.groupby("trayecto_final", as_index=False).agg(avg_hours=("duration_hours", "mean"), n_samples=("duration_hours", "size"))
    prom_empty = df_empty.groupby("trayecto_final", as_index=False).agg(avg_hours=("duration_hours", "mean"), n_samples=("duration_hours", "size"))
    
    for df_prom in [prom_loaded, prom_empty]:
        if not df_prom.empty:
            df_prom.columns = ["Trayecto", "Promedio (h)", "Cantidad de registros"]
            df_prom["Promedio legible"] = df_prom["Promedio (h)"].apply(convertir_a_texto_legible)
            df_prom = df_prom[["Trayecto", "Promedio legible", "Promedio (h)", "Cantidad de registros"]]

    def estilo_tablas(df_sty, titulo, color_titulo):
        return (df_sty.style.set_caption(f'<span style="font-size:18px; color:{color_titulo}; font-weight:bold;">{titulo}</span>')
                .set_table_styles([{"selector": "thead", "props": [("background-color", "#f7f7f7"),("border-bottom", "2px solid #1a5f1a"),("font-weight", "bold")]},{"selector": "tbody tr", "props": [("border-bottom", "1px solid #ddd")]},{"selector": "td", "props": [("padding", "8px")]},{"selector": "caption", "props": [("caption-side", "top"), ("font-size", "0px")]},{"selector": "", "props": [("border-collapse", "collapse")]}])
                .background_gradient(subset=['Promedio (h)'], cmap='YlGn').background_gradient(subset=['Cantidad de registros'], cmap='Blues')
                .format({'Promedio (h)': "{:,.2f} h", 'Cantidad de registros': "{:,.0f} registros"})
                .set_properties(subset=['Promedio legible'], **{'text-align': 'left', 'font-style': 'italic', 'color': '#2c5f2c'})
                .set_properties(subset=['Trayecto'], **{'font-weight': '500', 'color': '#1a1a1a'}).hide(axis="index"))

    tabla_cargado_html = estilo_tablas(prom_loaded, "⛴️ TRAYECTOS CON CARGA (LLENO) - TIEMPOS PROMEDIO GENERALES", "#1a5f1a").to_html(escape=False)
    tabla_vacio_html = estilo_tablas(prom_empty, "🛳️ TRAYECTOS DE REGRESO (VACIO) - TIEMPOS PROMEDIO GENERALES", "#1a5f7a").to_html(escape=False)

    # --- GRÁFICOS ---
    grafico_tanqueo_b64 = None
    df_tanqueo = df[df["EVENTO ACTUAL"].astype(str).str.strip().str.upper() == "TANQUEO"].copy()
    
    if not df_tanqueo.empty:
        df_tanqueo["Duración Legible"] = df_tanqueo["duration_hours"].apply(convertir_a_texto_legible)
        meses_es = { 1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril', 5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto', 9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre' }
        df_tanqueo["Mes"] = df_tanqueo["HORA INICIO"].dt.month.map(meses_es) + " " + df_tanqueo["HORA INICIO"].dt.year.astype(str)
        df_tanqueo["Fecha_Orden"] = df_tanqueo["HORA INICIO"].dt.to_period("M")
        df_tanqueo_sorted = df_tanqueo.sort_values(["Fecha_Orden", "ID"]).reset_index(drop=True)
        df_tanqueo_sorted["Etiqueta"] = df_tanqueo_sorted["Mes"] + " | ID " + df_tanqueo_sorted["ID"].astype(str)
        promedio = df_tanqueo_sorted["duration_hours"].mean()
        promedio_texto = convertir_a_texto_legible(promedio)

        # ▼▼▼ CAMBIO 1: Se ajusta el tamaño del gráfico para que sea más compacto ▼▼▼
        fig_tanqueo, ax = plt.subplots(figsize=(18, max(6, len(df_tanqueo_sorted) * 0.4)))
        
        ax.barh(df_tanqueo_sorted["Etiqueta"], df_tanqueo_sorted["duration_hours"], color="#1f7a1f")
        ax.set_xlabel("Horas de Tanqueo")
        ax.set_ylabel("Mes y Maniobra ID")
        ax.invert_yaxis()
        for index, row in df_tanqueo_sorted.iterrows():
            duration = row['duration_hours']
            ax.text(0.2, index, row["Duración Legible"], ha="left", va="center", color="white", fontsize=9, fontweight="bold")
            ax.text(duration + 0.2, index, f"MT: {row['MT ENTREGADAS']:.2f}", ha="left", va="center", color="#333333", fontsize=9)
            
        if pd.notna(promedio):
            ax.axvline(x=promedio, color="red", linestyle="--", linewidth=1.5)
            ax.text(promedio + 0.1, len(df_tanqueo_sorted) - 0.5, f" Promedio: {promedio_texto}", color="red", fontsize=10)
        
        ax.set_title("Duración de Tanqueo por Mes y ID", fontsize=16)
        plt.tight_layout()
        
        grafico_tanqueo_b64 = convertir_plot_a_base64(fig_tanqueo)

    grafico_total_b64 = None
    meses_es = { 1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic' }
    df["Mes"] = df["HORA INICIO"].dt.month.map(meses_es) + "-" + df["HORA INICIO"].dt.year.astype(str)
    
    df_total = df.groupby("ID", as_index=False).agg(
        duration_hours=("duration_hours", "sum"),
        Mes=("Mes", lambda x: ", ".join(sorted(x.unique()))),
        BARCAZA=("BARCAZA", "first"),
        MT_ENTREGADAS=("MT ENTREGADAS", "first")
    )
    if not df_total.empty:
        df_total["Duración Legible"] = df_total["duration_hours"].apply(convertir_a_texto_legible)
        df_total["ID_Mes"] = "ID " + df_total["ID"].astype(str) + " | " + df_total["Mes"]
        df_total = df_total.sort_values("ID").reset_index(drop=True)
        promedio = df_total["duration_hours"].mean()
        promedio_texto = convertir_a_texto_legible(promedio)

        # ▼▼▼ CAMBIO 2: Se reduce el ancho del gráfico para que no se salga de la página ▼▼▼
        fig_total, ax = plt.subplots(figsize=(25, max(8, len(df_total) * 0.5)))
        ax.barh(df_total["ID_Mes"], df_total["duration_hours"], color="#004d99")
        
        for idx, row in df_total.iterrows():
            ax.text(0.2, idx, row["Duración Legible"], va="center", ha="left", color="white", fontsize=9, fontweight='bold')
            ax.text(row["duration_hours"] + 0.2, idx, f"MT: {row['MT_ENTREGADAS']:.2f}", va="center", ha="left", color="#333333", fontsize=9, fontweight='bold')
        
        if pd.notna(promedio):
            ax.axvline(x=promedio, color='red', linestyle='--', linewidth=1.5)
            ax.text(promedio + 0.1, 0, f"Promedio: {promedio_texto}", color='red', backgroundcolor='white')
        
        ax.set_title("Total de Horas por Maniobra", fontsize=14)
        ax.set_xlabel("Total de Horas")
        ax.set_ylabel("ID | Barcaza | Mes")
        ax.invert_yaxis()
        plt.tight_layout()
        grafico_total_b64 = convertir_plot_a_base64(fig_total)
    
    return {
        "tabla_cargado_html": tabla_cargado_html,
        "tabla_vacio_html": tabla_vacio_html,
        "grafico_tanqueo_b64": grafico_tanqueo_b64,
        "grafico_total_b64": grafico_total_b64
    }

app = Flask(__name__)
app.secret_key = 'clave_secreta_para_produccion_cambiar'

import os
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://postgres:Sara_121128@localhost:5432/inventario_dev')
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
    assay_json = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<DefinicionCrudo {self.nombre}>'
    
class RegistroRemolcador(db.Model):
    __tablename__ = 'registros_remolcador'

    id = db.Column(db.Integer, primary_key=True)
    
    # --- CAMBIOS EN EL MODELO ---
    maniobra_id = db.Column(db.Integer, nullable=False, index=True)
    barcaza = db.Column(db.String(100), nullable=True) # <-- NUEVA COLUMNA
    nombre_barco = db.Column(db.String(100), nullable=True)
    evento_anterior = db.Column(db.String(200), nullable=True)
    hora_inicio = db.Column(db.DateTime, nullable=False)
    evento_actual = db.Column(db.String(200), nullable=True)
    hora_fin = db.Column(db.DateTime, nullable=True)
    mt_entregadas = db.Column(db.Numeric(10, 2), nullable=True)
    carga_estado = db.Column(db.String(50), nullable=True)
    usuario_actualizacion = db.Column(db.String(100))
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # La propiedad 'duracion' ya funciona correctamente para fechas completas
    @property
    def duracion(self):
        if not self.hora_fin or not self.hora_inicio:
            return ""
        
        delta = self.hora_fin - self.hora_inicio
        total_minutos = delta.total_seconds() / 60
        horas = int(total_minutos // 60)
        minutos = int(total_minutos % 60)
        
        return f"{horas}h {minutos}m"
    
    def __repr__(self):
        return f'<RegistroRemolcador {self.id}>'    

class ProgramacionCargue(db.Model):
    __tablename__ = 'programacion_cargue'
    id = db.Column(db.Integer, primary_key=True)
    
    # Campos de Juliana y Samantha
    fecha_programacion = db.Column(db.Date, nullable=False, default=date.today)
    empresa_transportadora = db.Column(db.String(150))
    placa = db.Column(db.String(50))
    tanque = db.Column(db.String(50))
    nombre_conductor = db.Column(db.String(150))
    cedula_conductor = db.Column(db.String(50))
    celular_conductor = db.Column(db.String(50))
    hora_llegada_estimada = db.Column(db.Time)
    producto_a_cargar = db.Column(db.String(100))
    
    # Campos de Ana Maria
    destino = db.Column(db.String(150))
    cliente = db.Column(db.String(150))
    
    # Campos de Refinería
    estado = db.Column(db.String(50), default='PROGRAMADO') 
    galones = db.Column(db.Float)
    barriles = db.Column(db.Float)
    temperatura = db.Column(db.Float)
    api_obs = db.Column(db.Float)
    api_corregido = db.Column(db.Float)
    precintos = db.Column(db.String(200))
    
    # Campo de Samantha
    fecha_despacho = db.Column(db.Date, nullable=True)
    numero_guia = db.Column(db.String(100))

    # Auditoría
    ultimo_editor = db.Column(db.String(100))
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Nuevo: momento en que TODOS los campos de refinería quedaron completos (para iniciar conteo de 30 min)
    refineria_completado_en = db.Column(db.DateTime, nullable=True)

# ---------------- BLOQUEO DE CELDAS (EDICIÓN EN TIEMPO REAL) -----------------
class ProgramacionCargueLock(db.Model):
    __tablename__ = 'programacion_cargue_locks'
    id = db.Column(db.Integer, primary_key=True)
    registro_id = db.Column(db.Integer, nullable=False, index=True)
    campo = db.Column(db.String(100), nullable=False)
    usuario = db.Column(db.String(120), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    __table_args__ = (db.UniqueConstraint('registro_id', 'campo', name='uq_prog_lock_registro_campo'),)

    def expirado(self, minutos=2):
        return datetime.utcnow() - self.timestamp > timedelta(minutes=minutos)

def _init_lock_table():
    from sqlalchemy import inspect
    with app.app_context():
        insp = inspect(db.engine)
        if 'programacion_cargue_locks' not in insp.get_table_names():
            ProgramacionCargueLock.__table__.create(db.engine)

_init_lock_table()

# Asegurar columna nueva en runtime si no existe (SQLite permite ADD COLUMN simple)
def _ensure_refineria_completion_column():
    from sqlalchemy import inspect, text
    with app.app_context():
        insp = inspect(db.engine)
        # Evitar error si la tabla aún no existe (por ejemplo, primera vez o DB recién borrada)
        if 'programacion_cargue' not in insp.get_table_names():
            print("[INIT] Tabla 'programacion_cargue' no existe todavía; se omite verificación de columna 'refineria_completado_en'. Ejecuta migraciones o crea las tablas primero.")
            return
        cols = [c['name'] for c in insp.get_columns('programacion_cargue')]
        if 'refineria_completado_en' not in cols:
            try:
                # Elegir tipo correcto según motor (PostgreSQL no acepta DATETIME)
                dialect = db.engine.dialect.name
                if dialect == 'postgresql':
                    col_type = 'TIMESTAMP'
                elif dialect == 'mysql':
                    col_type = 'DATETIME'
                else:
                    col_type = 'DATETIME'
                ddl = f'ALTER TABLE programacion_cargue ADD COLUMN refineria_completado_en {col_type}'
                with db.engine.begin() as conn:
                    conn.execute(text(ddl))
                print(f'Columna refineria_completado_en añadida (tipo {col_type})')
            except Exception as e:
                print('No se pudo añadir columna refineria_completado_en:', e)

_ensure_refineria_completion_column()

# ---------------- EDICIONES EN VIVO (NO PERSISTIDAS) -----------------
# Estructura en memoria para broadcast simple (clave: (registro_id,campo))
LIVE_EDITS = {}
LIVE_EDIT_TTL_SECONDS = 25  # tiempo de vida de una edición mostrada

def _purge_live_edits():
    now = datetime.utcnow()
    expiradas = []
    for key, info in LIVE_EDITS.items():
        if (now - info['timestamp']).total_seconds() > LIVE_EDIT_TTL_SECONDS:
            expiradas.append(key)
    for k in expiradas:
        LIVE_EDITS.pop(k, None)

class EPPItem(db.Model):
    __tablename__ = 'epp_items'
    id = db.Column(db.Integer, primary_key=True)
    
    # Datos principales del item
    nombre = db.Column(db.String(150), nullable=False, index=True) # Ej: "Botas de Seguridad"
    categoria = db.Column(db.String(50), nullable=False, index=True) # "EPP", "Dotación", "Equipos de Emergencia"
    stock_actual = db.Column(db.Integer, default=0, nullable=False)

    # Campos para detalles específicos
    referencia = db.Column(db.String(150), nullable=True) # Ej: "Brahama", "MSA Safari"
    talla = db.Column(db.String(50), nullable=True)      # Ej: "42", "L", "N/A"
    fecha_vencimiento = db.Column(db.Date, nullable=True) # Para items que expiran
    observaciones = db.Column(db.Text, nullable=True)     # Ej: "20 LBS", "Color Verde"

    # Relación con las asignaciones
    asignaciones = db.relationship('EPPAssignment', backref='item', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<EPPItem {self.nombre} - {self.referencia} ({self.talla})>'

class EPPAssignment(db.Model):
    __tablename__ = 'epp_assignments'
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('epp_items.id'), nullable=False)
    
    # Datos de la asignación
    empleado_nombre = db.Column(db.String(200), nullable=False, index=True)
    cantidad_entregada = db.Column(db.Integer, nullable=False)
    fecha_entrega = db.Column(db.Date, nullable=False, default=date.today)
    observaciones = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<EPPAssignment for {self.empleado_nombre}>'
    
class RegistroCompra(db.Model):
    __tablename__ = 'registros_compra'
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, index=True)
    proveedor = db.Column(db.String(200), index=True)
    tarifa = db.Column(db.Float)
    producto = db.Column(db.String(200))
    cantidad_bls = db.Column(db.Float)
    cantidad_gln = db.Column(db.Float)
    brent = db.Column(db.Float)
    descuento = db.Column(db.Float)
    precio_uni_bpozo = db.Column(db.Float)
    total_neto = db.Column(db.Float)
    price_compra_pond = db.Column(db.Float)

    def __repr__(self):
        return f'<RegistroCompra {self.id} - {self.numero_factura}>'

# ================== DESPACHOS TK -> BARCAZA ==================
class TrasiegoTKBarcaza(db.Model):
    __tablename__ = 'trasiegos_tk_barcaza'

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    fecha = db.Column(db.Date, nullable=False, index=True)
    usuario = db.Column(db.String(120), nullable=False)

    origen_tk = db.Column(db.String(50), nullable=False)
    destino_barcaza = db.Column(db.String(120), nullable=False)  # Nombre barcaza (p.ej. Manzanillo)
    destino_compartimento = db.Column(db.String(50), nullable=True)  # p.ej. TK1, TK2

    tk_cm_inicial = db.Column(db.Integer, nullable=True)
    tk_mm_inicial = db.Column(db.Integer, nullable=True)
    tk_bbl_bruto_inicial = db.Column(db.Float, nullable=True)
    tk_bbl_inicial = db.Column(db.Float, nullable=True)
    tk_api = db.Column(db.Float, nullable=True)
    tk_temp = db.Column(db.Float, nullable=True)
    tk_cm_final = db.Column(db.Integer, nullable=True)
    tk_mm_final = db.Column(db.Integer, nullable=True)
    tk_bbl_bruto_final = db.Column(db.Float, nullable=True)
    tk_bbl_final = db.Column(db.Float, nullable=True)

    # Ingreso simultáneo al tanque (opcional)
    tk_caudal_bbl_min = db.Column(db.Float, nullable=True)
    tk_minutos_ingreso = db.Column(db.Float, nullable=True)
    tk_bbl_ingreso = db.Column(db.Float, nullable=True)

    bar_cm_inicial = db.Column(db.Integer, nullable=True)
    bar_mm_inicial = db.Column(db.Integer, nullable=True)
    bar_bbl_bruto_inicial = db.Column(db.Float, nullable=True)
    bar_bbl_inicial = db.Column(db.Float, nullable=True)
    bar_api = db.Column(db.Float, nullable=True)
    bar_temp = db.Column(db.Float, nullable=True)
    bar_cm_final = db.Column(db.Integer, nullable=True)
    bar_mm_final = db.Column(db.Integer, nullable=True)
    bar_bbl_bruto_final = db.Column(db.Float, nullable=True)
    bar_bbl_final = db.Column(db.Float, nullable=True)

    notas = db.Column(db.Text, nullable=True)
    tk_notas = db.Column(db.Text, nullable=True)

    @property
    def trasiego_segun_tanque(self):
            try:
                if self.tk_bbl_inicial is not None and self.tk_bbl_final is not None:
                    ini = float(self.tk_bbl_inicial)
                    fin = float(self.tk_bbl_final)
                    return round(ini - fin, 2)
                return None
            except Exception:
                return None

    @property
    def trasiego_segun_barcaza(self):
        try:
            ini = float(self.bar_bbl_inicial or 0)
            fin = float(self.bar_bbl_final or 0)
            return round(fin - ini, 2)
        except Exception:
            return None

    @property
    def diferencia(self):
        try:
            t = float(self.trasiego_segun_tanque or 0)
            b = float(self.trasiego_segun_barcaza or 0)
            return round(b - t, 2)
        except Exception:
            return None

    def __repr__(self):
        return f'<Trasiego {self.fecha} {self.origen_tk} -> {self.destino_barcaza}/{self.destino_compartimento or ""}>'

def _ensure_trasiegos_table():
    from sqlalchemy import inspect
    with app.app_context():
        insp = inspect(db.engine)
        if 'trasiegos_tk_barcaza' not in insp.get_table_names():
            try:
                TrasiegoTKBarcaza.__table__.create(db.engine)
                print('[INIT] Tabla trasiegos_tk_barcaza creada')
            except Exception as e:
                print('[INIT] No fue posible crear tabla trasiegos_tk_barcaza:', e)

_ensure_trasiegos_table()

def _ensure_trasiegos_columns():
    from sqlalchemy import inspect, text
    with app.app_context():
        insp = inspect(db.engine)
        if 'trasiegos_tk_barcaza' not in insp.get_table_names():
            return
        cols = [c['name'] for c in insp.get_columns('trasiegos_tk_barcaza')]
        to_add = []
        if 'tk_api' not in cols:
            to_add.append('ALTER TABLE trasiegos_tk_barcaza ADD COLUMN tk_api FLOAT')
        if 'bar_api' not in cols:
            to_add.append('ALTER TABLE trasiegos_tk_barcaza ADD COLUMN bar_api FLOAT')
        if 'tk_notas' not in cols:
            to_add.append('ALTER TABLE trasiegos_tk_barcaza ADD COLUMN tk_notas TEXT')
        # Nuevas columnas de BBL Bruto
        if 'tk_bbl_bruto_inicial' not in cols:
            to_add.append('ALTER TABLE trasiegos_tk_barcaza ADD COLUMN tk_bbl_bruto_inicial FLOAT')
        if 'tk_bbl_bruto_final' not in cols:
            to_add.append('ALTER TABLE trasiegos_tk_barcaza ADD COLUMN tk_bbl_bruto_final FLOAT')
        if 'bar_bbl_bruto_inicial' not in cols:
            to_add.append('ALTER TABLE trasiegos_tk_barcaza ADD COLUMN bar_bbl_bruto_inicial FLOAT')
        if 'bar_bbl_bruto_final' not in cols:
            to_add.append('ALTER TABLE trasiegos_tk_barcaza ADD COLUMN bar_bbl_bruto_final FLOAT')
        # Nuevas columnas para ingreso simultáneo al TK
        if 'tk_caudal_bbl_min' not in cols:
            to_add.append('ALTER TABLE trasiegos_tk_barcaza ADD COLUMN tk_caudal_bbl_min FLOAT')
        if 'tk_minutos_ingreso' not in cols:
            to_add.append('ALTER TABLE trasiegos_tk_barcaza ADD COLUMN tk_minutos_ingreso FLOAT')
        if 'tk_bbl_ingreso' not in cols:
            to_add.append('ALTER TABLE trasiegos_tk_barcaza ADD COLUMN tk_bbl_ingreso FLOAT')
        for ddl in to_add:
            try:
                with db.engine.begin() as conn:
                    conn.execute(text(ddl))
            except Exception as e:
                print('[INIT] No fue posible añadir columna en trasiegos_tk_barcaza:', e)

_ensure_trasiegos_columns()

# ================== NUEVOS MODELOS PARA FLUJO DE EFECTIVO (PERSISTENCIA) ==================
class FlujoUploadBatch(db.Model):
    __tablename__ = 'flujo_upload_batches'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255))
    usuario = db.Column(db.String(120))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    total_bancos = db.Column(db.Integer, default=0)
    total_odoo = db.Column(db.Integer, default=0)

class FlujoBancoMovimiento(db.Model):
    __tablename__ = 'flujo_bancos_movimientos'
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey('flujo_upload_batches.id'), index=True)
    fecha = db.Column(db.Date, index=True)
    empresa = db.Column(db.String(120), index=True)
    movimiento = db.Column(db.Text)
    monto = db.Column(db.Float)  # valor COP$
    banco = db.Column(db.String(120), index=True)
    tipo_banco = db.Column(db.String(120), nullable=True)
    unique_hash = db.Column(db.String(64), unique=True, index=True)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow, index=True)

class FlujoOdooMovimiento(db.Model):
    __tablename__ = 'flujo_odoo_movimientos'
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey('flujo_upload_batches.id'), index=True)
    fecha = db.Column(db.Date, index=True)
    empresa = db.Column(db.String(120), index=True)
    movimiento = db.Column(db.Text)
    debito = db.Column(db.Float, default=0)
    credito = db.Column(db.Float, default=0)
    tipo_flujo = db.Column(db.String(200))
    tercero = db.Column(db.String(200))
    rubro = db.Column(db.String(200))
    clase = db.Column(db.String(200))
    subclase = db.Column(db.String(200))
    banco = db.Column(db.String(120), index=True)
    tipo_banco = db.Column(db.String(120), nullable=True)
    unique_hash = db.Column(db.String(64), unique=True, index=True)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow, index=True)

# ================== TABLAS DE AFORO ==================
class AforoTabla(db.Model):
    __tablename__ = 'aforos_tablas'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    usuario = db.Column(db.String(120), nullable=False)
    # tipo: 'TK' para tanques de planta; 'BARCAZA' para compartimentos/tanques de barcazas
    tipo = db.Column(db.String(20), nullable=False, index=True)
    # nombre: identificador lógico, ej. 'TK-109' o '1P' o 'MARI TK-1C'
    nombre = db.Column(db.String(120), nullable=False, index=True)
    # datos: JSON con lista de filas [{"cm":int, "mm":int, "bbl":float}] (mm usualmente 0..9)
    datos_json = db.Column(db.Text, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('tipo', 'nombre', name='uq_aforo_tipo_nombre'),
    )

    def __repr__(self):
        return f"<AforoTabla {self.tipo}:{self.nombre} ({self.id})>"

def _ensure_aforos_table():
    from sqlalchemy import inspect
    with app.app_context():
        insp = inspect(db.engine)
        if 'aforos_tablas' not in insp.get_table_names():
            try:
                AforoTabla.__table__.create(db.engine)
                print('[INIT] Tabla aforos_tablas creada')
            except Exception as e:
                print('[INIT] No fue posible crear tabla aforos_tablas:', e)

_ensure_aforos_table()

def _hash_row(values: list) -> str:
    base = '|'.join('' if v is None else str(v).strip() for v in values)
    return hashlib.sha256(base.encode('utf-8')).hexdigest()
    
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

@app.context_processor
def inject_current_year():
    return {'current_year': datetime.now().year}

# --- Utilidades de aforos ---
def _parse_aforo_excel_to_json(ws):
    """
    Convierte una hoja de Excel a un JSON usable por el cálculo de aforo.

    Dos modos de salida (detectados automáticamente):
    - Modo 'step': Estructura por decímetro con 'base' (cada 10 cm),
      incrementos por centímetro 'inc_cm' (1..9) y por milímetro 'inc_mm' (1..9).
      Este modo replica el método de Excel: base(10 cm) + inc_cm + inc_mm.
    - Modo 'flat': Lista de registros {cm, mm, bbl} para hojas simples.

    Soporta hojas con pares horizontales 'NIVEL/VOLUMEN', 'NIVEL 2/VOLUMEN 2',
    'NIVEL 3/VOLUMEN 3' y también hojas simples con columnas 'cm', 'mm', 'bbl'.
    """
    # Construir texto de cabecera por columna combinando fila 1 y 2
    def _cell_text(cell):
        v = cell.value
        return str(v).strip().lower() if v is not None else ''

    max_cols = ws.max_column or 0
    row1 = [ _cell_text(c) for c in ws[1][:max_cols] ] if ws.max_row >= 1 else []
    row2 = [ _cell_text(c) for c in ws[2][:max_cols] ] if ws.max_row >= 2 else []
    headers = []
    for i in range(max_cols):
        h1 = row1[i] if i < len(row1) else ''
        h2 = row2[i] if i < len(row2) else ''
        headers.append((h1 + ' ' + h2).strip())

    # Heurísticas para identificar columnas de nivel y volumen
    def is_lvl(h: str) -> bool:
        return any(k in h for k in ['nivel', 'cm', 'mm'])

    def lvl_unit(h: str) -> str:
        if 'mm' in h and 'cm' not in h:
            return 'mm'
        return 'cm'

    def is_vol(h: str) -> bool:
        return any(k in h for k in ['bbl', 'bls', 'volumen'])

    # Determinar fila inicial de datos: si segunda fila parece cabecera también, empezamos en 3
    header_has_words = any(any(ch.isalpha() for ch in h) for h in row2)
    start_row = 3 if header_has_words else 2

    # Detectar pares (nivel, volumen) adyacentes
    pairs = []  # lista de tuplas (idx_level, idx_volume, unit)
    i = 0
    while i < len(headers) - 1:
        h_lvl = headers[i]
        h_vol = headers[i+1]
        if is_lvl(h_lvl) and is_vol(h_vol):
            pairs.append((i, i+1, lvl_unit(h_lvl)))
            i += 2
            continue
        i += 1

    # Intentar detectar estructura por decímetro (step). Heurística: hay al menos
    # dos pares en 'cm' (base + cm) y opcionalmente un par en 'mm'.
    cm_pairs = [p for p in pairs if p[2] == 'cm']
    mm_pairs = [p for p in pairs if p[2] == 'mm']

    if cm_pairs:
        # Elegimos el primer par 'cm' como BASE y el segundo (si existe) como CM.
        base_lvl_idx, base_vol_idx, _ = cm_pairs[0]
        cm_inc_idx = cm_pairs[1] if len(cm_pairs) > 1 else None
        mm_inc_idx = mm_pairs[0] if mm_pairs else None

        base_map = {}
        inc_cm_map = {}
        inc_mm_map = {}
        # Algunas hojas listan incrementos globales (no por decímetro)
        inc_cm_global = {}
        inc_mm_global = {}
        current_dec = None

        for row in ws.iter_rows(min_row=start_row, values_only=True):
            try:
                nivel_base = row[base_lvl_idx] if base_lvl_idx < len(row) else None
                vol_base = row[base_vol_idx] if base_vol_idx < len(row) else None
            except Exception:
                nivel_base = None
                vol_base = None

            # Si hay nivel base en esta fila, actualizamos decímetro actual
            if nivel_base not in (None, '') and vol_base not in (None, ''):
                try:
                    nb = float(str(nivel_base).replace(',', '.'))
                    vb = float(str(vol_base).replace(',', '.'))
                    dec = int(round(nb))
                    current_dec = dec
                    base_map[current_dec] = vb
                    if current_dec not in inc_cm_map:
                        inc_cm_map[current_dec] = {}
                    if current_dec not in inc_mm_map:
                        inc_mm_map[current_dec] = {}
                except Exception:
                    pass

            # Incrementos por centímetro (si existe el par y hay decímetro vigente)
            if cm_inc_idx:
                lvl_idx, vol_idx, _ = cm_inc_idx
                try:
                    n2 = row[lvl_idx] if lvl_idx < len(row) else None
                    v2 = row[vol_idx] if vol_idx < len(row) else None
                    if n2 not in (None, '') and v2 not in (None, ''):
                        n2i = int(round(float(str(n2).replace(',', '.'))))
                        v2f = float(str(v2).replace(',', '.'))
                        if 1 <= n2i <= 9:
                            inc_cm_global[n2i] = v2f
                            if current_dec is not None:
                                inc_cm_map.setdefault(current_dec, {})[n2i] = v2f
                except Exception:
                    pass

            # Incrementos por milímetro (si existe el par y hay decímetro vigente)
            if mm_inc_idx:
                lvl_idx, vol_idx, _ = mm_inc_idx
                try:
                    n3 = row[lvl_idx] if lvl_idx < len(row) else None
                    v3 = row[vol_idx] if vol_idx < len(row) else None
                    if n3 not in (None, '') and v3 not in (None, ''):
                        n3i = int(round(float(str(n3).replace(',', '.'))))
                        v3f = float(str(v3).replace(',', '.'))
                        if 1 <= n3i <= 9:
                            inc_mm_global[n3i] = v3f
                            if current_dec is not None:
                                inc_mm_map.setdefault(current_dec, {})[n3i] = v3f
                except Exception:
                    pass

        # Si logramos leer algún base, devolvemos modo step
        if base_map:
            # Normalizar claves a strings para JSON compacto
            def _norm(d):
                return {str(k): v for k, v in d.items()}
            def _norm_nest(d):
                return {str(k): {str(kk): vv for kk, vv in v.items()} for k, v in d.items() if v}
            return {
                'mode': 'step',
                'base': _norm(base_map),
                'inc_cm': _norm_nest(inc_cm_map),
                'inc_mm': _norm_nest(inc_mm_map),
                'inc_cm_global': {str(k): v for k, v in (inc_cm_global or {}).items()},
                'inc_mm_global': {str(k): v for k, v in (inc_mm_global or {}).items()},
            }

    # Si no hay pares 'cm' o no se pudo construir modo step, intentar modo 'flat'
    data = []
    if not pairs:
        try:
            idx_cm = next((i for i,h in enumerate(headers) if 'cm' in h), None)
            idx_mm = next((i for i,h in enumerate(headers) if 'mm' in h), None)
            idx_bbl = next((i for i,h in enumerate(headers) if any(k in h for k in ['bbl','bls','volumen'])), None)
            if idx_cm is None or idx_bbl is None:
                raise ValueError
            for row in ws.iter_rows(min_row=start_row, values_only=True):
                cm = row[idx_cm] if idx_cm is not None and idx_cm < len(row) else None
                mm = row[idx_mm] if idx_mm is not None and idx_mm < len(row) else 0
                bbl = row[idx_bbl] if idx_bbl is not None and idx_bbl < len(row) else None
                try:
                    cm_i = int(float(str(cm).replace(',', '.')))
                    mm_i = int(float(str(mm or 0).replace(',', '.')))
                    bbl_f = float(str(bbl).replace(',', '.'))
                    data.append({'cm': cm_i, 'mm': mm_i, 'bbl': bbl_f})
                except Exception:
                    continue
        except Exception:
            raise ValueError('No se identificaron columnas de NIVEL/CM/MM y VOLUMEN (BBL/BLS).')
    else:
        # Procesar pares detectados como lista plana (mejor que nada)
        for lvl_idx, vol_idx, unit in pairs:
            for row in ws.iter_rows(min_row=start_row, values_only=True):
                try:
                    nivel_v = row[lvl_idx] if lvl_idx < len(row) else None
                    vol_v = row[vol_idx] if vol_idx < len(row) else None
                except Exception:
                    continue
                if nivel_v in (None, '') or vol_v in (None, ''):
                    continue
                try:
                    nivel_f = float(str(nivel_v).replace(',', '.'))
                    bbl_f = float(str(vol_v).replace(',', '.'))
                except Exception:
                    continue
                if unit == 'cm':
                    cm_i = int(round(nivel_f))
                    mm_i = 0
                else:
                    total_mm = int(round(nivel_f))
                    if total_mm < 0:
                        continue
                    cm_i = total_mm // 10
                    mm_i = total_mm % 10
                data.append({'cm': cm_i, 'mm': mm_i, 'bbl': bbl_f})

    if not data:
        raise ValueError('No se leyeron filas válidas de aforo.')

    # Deduplicar por (cm,mm) manteniendo el último valor encontrado
    dedup = {}
    for r in data:
        key = (int(r['cm']), int(r['mm']))
        try:
            dedup[key] = float(r['bbl'])
        except Exception:
            continue
    out = [ {'cm': k[0], 'mm': k[1], 'bbl': v} for k,v in dedup.items() ]
    out.sort(key=lambda r: (r['cm'], r['mm']))
    return {'mode': 'flat', 'data': out}

def _parse_barge_columns_sheet(ws, prefer_tipo: str = 'BARCAZA', default_name: str | None = None):
    """
    Parser especializado para hojas con formato "TEMP LAMINA 60" donde:
    - Una columna contiene la lámina/altura (cm)
    - Varias columnas (una por tanque/compartimento) contienen volúmenes

    Devuelve un dict mapping nombre_tabla -> payload_json_dict (modo 'flat').

    Los encabezados se esperan tipo: "MAN TK 1", "MG6 1P", "CR 2S", "OD 3P", "OILTECH 1C", etc.
    Se normalizan a nombres compatibles con la UI de Trasiegos: "<GRUPO>-<COMP>"
    p.ej. CR-1P, MARGOTH-1S, MANZANILLO-1, ODISEA-3S, OILTECH-1C.
    """
    try:
        max_cols = ws.max_column or 0
        # Construir encabezados combinando fila 1 y 2 (por si hay títulos en dos filas)
        def _txt(cell):
            v = cell.value
            return str(v).strip() if v is not None else ''

        row1 = [_txt(c) for c in (ws[1][:max_cols] if ws.max_row >= 1 else [])]
        row2 = [_txt(c) for c in (ws[2][:max_cols] if ws.max_row >= 2 else [])]
        headers = []
        for i in range(max_cols):
            h1 = (row1[i] if i < len(row1) else '')
            h2 = (row2[i] if i < len(row2) else '')
            h = (h1 + ' ' + h2).strip().upper()
            headers.append(h)

        # Detectar columna de lámina
        lam_idx = None
        for i, h in enumerate(headers):
            if any(k in h for k in ['LAMINA', 'LÁMINA', 'ALTURA', 'NIVEL']):
                lam_idx = i
                break
        if lam_idx is None:
            return {}

        # Función de mapeo de prefijo a grupo
        def map_group(pref: str) -> str:
            p = pref.upper().replace('.', '').replace('_', '').strip()
            if p.startswith('MAN'):
                return 'MANZANILLO'
            if p.startswith('MG6') or p.startswith('MARG'):
                return 'MARGOTH'
            if p.startswith('CR'):
                return 'CR'
            if p.startswith('OD') or p.startswith('ODI'):
                return 'ODISEA'
            if 'OIL' in p:
                return 'OILTECH'
            return p

        # Extraer definiciones de columnas objetivo (todas menos lámina) con su nombre lógico
        targets = []  # (col_idx, nombre)
        import re as _re
        for i, h in enumerate(headers):
            if i == lam_idx:
                continue
            if not h:
                continue
            # Intentar patrones comunes
            # 1) PREF TK <num/opcional letra>, 2) PREF <num>[P|S|C], 3) simplemente etiqueta de tanque
            m = _re.search(r"^(MAN|MG6|CR|OD|ODISEA|OILTECH)[\s\-_/]*T?K?\s*([0-9]+[A-Z]?)$", h, _re.IGNORECASE)
            if not m:
                m = _re.search(r"^(MAN|MG6|CR|OD|ODISEA|OILTECH)[\s\-_/]*([0-9]+[A-Z]?)$", h, _re.IGNORECASE)
            if m:
                pref = m.group(1).upper()
                comp = m.group(2).upper()
                grupo = map_group(pref)
                nombre = f"{grupo}-{comp}"
                targets.append((i, nombre))
                continue
            # Si no matchea, ignorar columnas no numéricas
            # Si el encabezado es numérico o poco descriptivo, usar default_name si está disponible
            header_clean = h.strip().upper()
            if default_name:
                if not header_clean or _re.fullmatch(r"[0-9\s\.,°%-]+", header_clean):
                    targets.append((i, default_name.strip().upper()))
                    continue
            targets.append((i, header_clean))  # última opción: usar header completo

        if not targets:
            return {}

        # Si solo hay una columna objetivo y tenemos default_name, usarlo como nombre
        if len(targets) == 1 and default_name:
            targets = [(targets[0][0], default_name.strip().upper())]

        # Detectar desde qué fila empiezan los datos (si fila 2 parece cabecera, empezar en 3)
        start_row = 3 if any(any(ch.isalpha() for ch in (row2[i] if i < len(row2) else '')) for i in range(max_cols)) else 2

        tablas = {}  # nombre -> lista data
        for row in ws.iter_rows(min_row=start_row, values_only=True):
            lam = row[lam_idx] if lam_idx < len(row) else None
            if lam in (None, ''):
                continue
            try:
                lam_cm = int(round(float(str(lam).replace(',', '.'))))
            except Exception:
                continue
            for col_idx, nombre in targets:
                if col_idx >= len(row):
                    continue
                val = row[col_idx]
                if val in (None, ''):
                    continue
                try:
                    bbl = float(str(val).replace(',', '.'))
                except Exception:
                    continue
                tablas.setdefault(nombre.upper().strip(), []).append({'cm': lam_cm, 'mm': 0, 'bbl': bbl})

        # Post-proceso: ordenar y empaquetar
        out = {}
        for nombre, data in tablas.items():
            if not data:
                continue
            data.sort(key=lambda r: (r['cm'], r.get('mm', 0)))
            out[nombre] = {'mode': 'flat', 'data': data}
        return out
    except Exception:
        return {}

def _parse_simple_lamina_single_volume(ws):
    """
    Parser simple para hojas con columnas:
    - "LÁMINA" (o ALTURA/NIVEL) y
    - una única columna de volúmenes (encabezado puede ser numérico como "60").

    Devuelve dict {'mode':'flat','data':[{'cm':int,'mm':0,'bbl':float}, ...]}
    o {} si no logra identificar las columnas.
    """
    try:
        max_cols = ws.max_column or 0
        def _txt(cell):
            v = cell.value
            return str(v).strip() if v is not None else ''

        row1 = [_txt(c) for c in (ws[1][:max_cols] if ws.max_row >= 1 else [])]
        row2 = [_txt(c) for c in (ws[2][:max_cols] if ws.max_row >= 2 else [])]
        headers = []
        for i in range(max_cols):
            h1 = (row1[i] if i < len(row1) else '')
            h2 = (row2[i] if i < len(row2) else '')
            headers.append((h1 + ' ' + h2).strip().upper())

        # Buscar lamina
        lam_idx = None
        for i, h in enumerate(headers):
            if any(k in h for k in ['LAMINA', 'LÁMINA', 'ALTURA', 'NIVEL']):
                lam_idx = i
                break
        if lam_idx is None:
            return {}

        # Detectar fila inicial (si fila 2 tiene letras, empezar en 3)
        start_row = 3 if any(any(ch.isalpha() for ch in (row2[i] if i < len(row2) else '')) for i in range(max_cols)) else 2

        # Elegir la mejor columna de volumen por cantidad de valores numéricos
        def _is_num(x):
            try:
                float(str(x).replace(',', '.'))
                return True
            except Exception:
                return False

        best_idx = None
        best_count = -1
        sample_rows = list(ws.iter_rows(min_row=start_row, max_row=min(start_row + 50, ws.max_row), values_only=True))
        for j in range(max_cols):
            if j == lam_idx:
                continue
            cnt = 0
            for r in sample_rows:
                if j < len(r) and _is_num(r[j]):
                    cnt += 1
            if cnt > best_count:
                best_count = cnt
                best_idx = j
        if best_idx is None or best_count <= 0:
            return {}

        data = []
        for row in ws.iter_rows(min_row=start_row, values_only=True):
            lam = row[lam_idx] if lam_idx < len(row) else None
            vol = row[best_idx] if best_idx < len(row) else None
            if lam in (None, '') or vol in (None, ''):
                continue
            try:
                cm = int(round(float(str(lam).replace(',', '.'))))
                bbl = float(str(vol).replace(',', '.'))
            except Exception:
                continue
            data.append({'cm': cm, 'mm': 0, 'bbl': bbl})
        if not data:
            return {}
        data.sort(key=lambda r: (r['cm'], r['mm']))
        return {'mode': 'flat', 'data': data}
    except Exception:
        return {}

def _interp_bbl(datos, cm, mm):
    """
    Calcula BBL según datos de aforo. Soporta:
    - Modo 'step': base(10 cm) + inc_cm + inc_mm
    - Modo 'flat': lineal con mejoras: usa valores absolutos si existen para
      (cm,0) y (cm,mm); si no, interpola.
    """
    # Helper: lineal a partir de lista plana
    def _linear_from_flat(lista, cm_i, mm_i):
        nivel = cm_i + (mm_i or 0)/10.0
        niveles = [d['cm'] + d['mm']/10.0 for d in lista]
        bbllist = [d['bbl'] for d in lista]
        if not niveles:
            return 0.0
        if nivel <= niveles[0]:
            return bbllist[0]
        if nivel >= niveles[-1]:
            return bbllist[-1]
        for i in range(1, len(niveles)):
            if niveles[i] >= nivel:
                x0, x1 = niveles[i-1], niveles[i]
                y0, y1 = bbllist[i-1], bbllist[i]
                t = (nivel - x0) / (x1 - x0) if (x1 - x0) != 0 else 0
                return y0 + t * (y1 - y0)
        return bbllist[-1]

    # Modo STEP
    if isinstance(datos, dict) and datos.get('mode') == 'step':
        base_map = {int(k): float(v) for k, v in (datos.get('base') or {}).items()}
        inc_cm = {int(k): {int(kk): float(vv) for kk, vv in (sub or {}).items()} for k, sub in (datos.get('inc_cm') or {}).items()}
        inc_mm = {int(k): {int(kk): float(vv) for kk, vv in (sub or {}).items()} for k, sub in (datos.get('inc_mm') or {}).items()}
        inc_cm_global = {int(k): float(v) for k, v in (datos.get('inc_cm_global') or {}).items()}
        inc_mm_global = {int(k): float(v) for k, v in (datos.get('inc_mm_global') or {}).items()}

        if not base_map:
            return 0.0

        dec = (cm // 10) * 10
        # Buscar el decímetro igual o menor existente
        if dec not in base_map:
            menores = [k for k in base_map.keys() if k <= cm]
            if not menores:
                dec = min(base_map.keys())
            else:
                dec = max(menores)

        base = base_map.get(dec, 0.0)
        cm_intra = cm - dec
        total = base

        # Incremento por centímetro
        if cm_intra > 0:
            cm_table = inc_cm.get(dec, {})
            if cm_intra in cm_table:
                total += cm_table[cm_intra]
            elif cm_intra in inc_cm_global:
                total += inc_cm_global[cm_intra]
            else:
                # Aproximación lineal entre bases de decímetro
                nxt = base_map.get(dec + 10)
                if nxt is not None:
                    total += (nxt - base) * (cm_intra / 10.0)

        # Incremento por milímetro
        mm = int(mm or 0)
        if mm > 0:
            mm_table = inc_mm.get(dec, {})
            if mm in mm_table:
                total += mm_table[mm]
            elif mm in inc_mm_global:
                total += inc_mm_global[mm]
            else:
                # Aproximación dentro del centímetro con bases de (cm,0) y (cm+1,0) si están
                cm_table = inc_cm.get(dec, {})
                v_cm = cm_table.get(cm_intra, None) if cm_intra > 0 else 0.0
                v_cm_next = cm_table.get(cm_intra + 1, None)
                if v_cm is not None and v_cm_next is not None:
                    total += (v_cm_next - v_cm) * (mm / 10.0)
                else:
                    # Último recurso: usar salto entre base dec y próximo dec
                    nxt = base_map.get(dec + 10)
                    if nxt is not None:
                        total = base + (nxt - base) * ((cm_intra + mm/10.0) / 10.0)
        return total

    # Modo FLAT u otros
    lista = datos.get('data') if isinstance(datos, dict) and 'data' in datos else datos
    if not isinstance(lista, list) or not lista:
        return 0.0

    # Intentar método escalonado a partir de valores absolutos si existen
    # Mapa rápido
    M = {(int(d['cm']), int(d['mm'])): float(d['bbl']) for d in lista if 'cm' in d and 'mm' in d and 'bbl' in d}
    dec = (cm // 10) * 10
    base = M.get((dec, 0), None)
    total = None
    # Fallback estilo Excel: si el flat contiene incrementos globales de cm como (1..9,0)
    # y de mm como (0,1..9), usar: base(dec) + inc_cm(cm_intra) + inc_mm(mm)
    if base is not None:
        cm_intra = cm - dec
        inc_cm_glob = M.get((cm_intra, 0), None) if (1 <= cm_intra <= 9) else 0.0
        inc_mm_glob = M.get((0, int(mm)), None) if int(mm or 0) > 0 else 0.0
        if (inc_cm_glob is not None) or (inc_mm_glob is not None and int(mm or 0) > 0):
            # Si existen incrementos globales, aplicarlos como en Excel
            total = float(base) + float(inc_cm_glob or 0.0) + float(inc_mm_glob or 0.0)
            return total
    if base is not None:
        total = base
        # cm exacto disponible
        v_cm0 = M.get((cm, 0), None)
        if v_cm0 is not None:
            total = v_cm0
        else:
            # Interpolar entre (dec,0) y (dec+10,0)
            v_dec_next = M.get((dec + 10, 0), None)
            if v_dec_next is not None:
                total = base + (v_dec_next - base) * ((cm - dec) / 10.0)
        # mm incremento
        if mm and total is not None:
            v_cmmm = M.get((cm, int(mm)))
            if v_cmmm is not None and v_cm0 is not None:
                total = v_cmmm
            else:
                # Aproximación dentro del centímetro con (cm,0) y (cm+1,0)
                v_cm1 = M.get((cm + 1, 0), None)
                if v_cm0 is not None and v_cm1 is not None:
                    total = (v_cm0 + (v_cm1 - v_cm0) * (mm / 10.0))

    if total is not None:
        return total
    # Fallback: completamente lineal
    return _linear_from_flat(lista, cm, mm)

def _expand_preview_rows(datos, max_rows=200):
    """
    Genera una lista plana de filas {cm, mm, bbl} para vista previa.
    - Para modo 'flat': devuelve hasta max_rows primeras filas ordenadas.
    - Para modo 'step': muestrea mm=0 para cada centímetro entre el mínimo y máximo decímetro disponible.
    """
    try:
        # Vista previa especial para VCF/API6A
        if isinstance(datos, dict) and 'data' in datos and len(datos['data']) > 0:
            sample = datos['data'][0]
            if all(k in sample for k in ('api', 'temp', 'vcf')):
                lista = list(datos.get('data') or [])
                lista.sort(key=lambda r: (float(r.get('api', 0)), float(r.get('temp', 0))))
                return lista[:max_rows]
        if isinstance(datos, dict) and datos.get('mode') == 'flat':
            lista = list(datos.get('data') or [])
            lista.sort(key=lambda r: (int(r.get('cm', 0)), int(r.get('mm', 0))))
            return lista[:max_rows]
        if isinstance(datos, dict) and datos.get('mode') == 'step':
            base_map = {int(k): float(v) for k, v in (datos.get('base') or {}).items()}
            if not base_map:
                return []
            decs = sorted(base_map.keys())
            cm_min = decs[0]
            cm_max = decs[-1] + 9
            out = []
            for cm in range(cm_min, cm_max + 1):
                b = _interp_bbl(datos, cm, 0)
                out.append({'cm': int(cm), 'mm': 0, 'bbl': float(b)})
                if len(out) >= max_rows:
                    break
            return out
    except Exception:
        pass
    return []

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

    # Juan Diego  (Admin): Tiene acceso a todo.
    "numbers@conquerstrading.com": {
        "password": generate_password_hash("Conquers2025"),
        "nombre": "Juan Diego Ayala",
        "rol": "admin",
        "area": [] 
    },

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
        "area": ["barcaza_orion", "barcaza_bita", "programacion_cargue"] 
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
    "area": ["reportes", "planilla_precios", "simulador_rendimiento", "flujo_efectivo"]
},

    "david.restrepo@conquerstrading.com": {
        "password": generate_password_hash("Conquers2025"),
        "nombre": "David Restrepo",
        "rol": "viewer",
        "area": ["reportes", "planilla_precios", "simulador_rendimiento", "flujo_efectivo"] 
    },


    "finance@conquerstrading.com": {
        "password": generate_password_hash("Conquers2025"),
        "nombre": "German Galvis",
        "rol": "viewer",
    "area": ["reportes", "planilla_precios", "simulador_rendimiento", "control_remolcadores", "flujo_efectivo", "modelo_optimizacion"] 
    },
    
    # Ignacio (Editor): Solo acceso a Planta y Rendimientos
    "production@conquerstrading.com": {
        "password": generate_password_hash("Conquers2025"),
        "nombre": "Ignacio Quimbayo",
        "rol": "editor",
        "area": ["planta", "simulador_rendimiento", "programacion_cargue"] 
    },
    # Juliana (Editor): Tiene acceso a Tránsito y a Generar Guía.
    "ops@conquerstrading.com": {
        "password": generate_password_hash("Conquers2025"),
        "nombre": "Juliana Torres",
        "rol": "editor",
        "area": ["transito", "guia_transporte", "control_remolcadores", "programacion_cargue"]
    },
    # Samantha (Editor): Tiene acceso solo a Generar Guía.
    "logistic@conquerstrading.com": {
        "password": generate_password_hash("Conquers2025"),
        "nombre": "Samantha Roa",
        "rol": "editor",
        "area": ["guia_transporte", "programacion_cargue"]
    },

    "comex@conquerstrading.com": {
        "password": generate_password_hash("Conquers2025"),     
        "nombre": "Daniela Cuadrado",
        "rol": "editor",
        "area": ["zisa_inventory", "programacion_cargue"] 
    },

    "comexzf@conquerstrading.com": {
        "password": generate_password_hash("Conquers2025"),     
        "nombre": "Shirli Diaz",
        "rol": "editor",
        "area": ["programacion_cargue"] 
    },

    "felipe.delavega@conquerstrading.com": {
        "password": generate_password_hash("Conquers2025"),     
        "nombre": "Felipe De La Vega",
        "rol": "editor",
    "area": ["simulador_rendimiento", "flujo_efectivo", "modelo_optimizacion"] 
    },

        "accountingzf@conquerstrading.com": { 
        "password": generate_password_hash("Conquers2025"),       
        "nombre": "Kelly Suarez",
        "rol": "editor",
        "area": ["contabilidad"] 
    },
        "amariagallo@conquerstrading.com": {
        "password": generate_password_hash("Conquers2025"), 
        "nombre": "Ana Maria Gallo",
        "rol": "logistica_destino",
        "area": ["programacion_cargue","gestion_compras"]
    },

        "refinery.control@conquerstrading.com": {
        "password": generate_password_hash("Conquers2025"), 
        "nombre": "Control Refineria",
        "rol": "refineria",
        "area": ["programacion_cargue"] 
    },
        "opensean@conquerstrading.com": {
        "password": generate_password_hash("Conquers2025"), 
        "nombre": "Opensean", 
        "rol": "operador_remolcador", 
        "area": ["control_remolcadores"]
    },

    "safety@conquerstrading.com": {
    "password": generate_password_hash("Conquers2025"),
    "nombre": "Sebastian Blanco",
    "rol": "editor",
    "area": ["inventario_epp"]
}


}
   
PLANILLA_PLANTA = [
    {"TK": "TK-109", "PRODUCTO": "CRUDO RF.", "MAX_CAP": 22000, "BLS_60": "", "API": "", "BSW": "", "S": ""},
    {"TK": "TK-110", "PRODUCTO": "FO4",       "MAX_CAP": 22000, "BLS_60": "", "API": "", "BSW": "", "S": ""},
    {"TK": "TK-108", "PRODUCTO": "VLSFO",    "MAX_CAP": 28000, "BLS_60": "", "API": "", "BSW": "", "S": ""},
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
    {"TK": "5S", "PRODUCTO": "VLSFO", "MAX_CAP": 2933.93, "BLS_60": "", "API": "", "BSW": "", "S": "", "grupo": "ODISEA"},
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

# ---------------- Gestión de Aforos (Admin) -----------------
@login_required
@admin_required
@app.route('/aforos')
def aforos_page():
    tablas = db.session.query(AforoTabla).order_by(AforoTabla.tipo.asc(), AforoTabla.nombre.asc()).all()
    # Cargar una lista mínima para mostrar en tabla (sin los datos)
    return render_template('aforos.html', nombre=session.get('nombre'), tablas=tablas)

@login_required
@admin_required
@app.route('/api/aforos/get')
def aforos_get():
    try:
        tid = request.args.get('id')
        tipo = (request.args.get('tipo') or '').upper() or None
        nombre = (request.args.get('nombre') or '').upper() or None
        q = db.session.query(AforoTabla)
        if tid:
            q = q.filter(AforoTabla.id == int(tid))
        elif tipo and nombre:
            q = q.filter(AforoTabla.tipo == tipo, AforoTabla.nombre == nombre)
        else:
            return jsonify(success=False, message='Parámetros inválidos'), 400
        r = q.first()
        if not r:
            return jsonify(success=False, message='No encontrado'), 404
        datos = json.loads(r.datos_json)
        preview = _expand_preview_rows(datos, max_rows=200)
        mode = datos.get('mode') if isinstance(datos, dict) else 'flat'
        total_rows = 0
        if isinstance(datos, dict) and mode == 'flat':
            total_rows = len(datos.get('data') or [])
        elif isinstance(datos, dict) and mode == 'step':
            total_rows = len((datos.get('base') or {})) * 10
        return jsonify(success=True, tabla={
            'id': r.id, 'tipo': r.tipo, 'nombre': r.nombre,
            'timestamp': r.timestamp.isoformat(), 'usuario': r.usuario,
            'mode': mode, 'total_rows_est': total_rows
        }, preview=preview)
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500

@login_required
@admin_required
@app.route('/api/aforos/download')
def aforos_download():
    try:
        tid = request.args.get('id')
        if not tid:
            return jsonify(success=False, message='id requerido'), 400
        r = db.session.query(AforoTabla).filter(AforoTabla.id == int(tid)).first()
        if not r:
            return jsonify(success=False, message='No encontrado'), 404
        datos = json.loads(r.datos_json)
        rows = []
        if isinstance(datos, dict) and datos.get('mode') == 'flat':
            rows = list(datos.get('data') or [])
        else:
            rows = _expand_preview_rows(datos, max_rows=100000)
        # Generar CSV en memoria
        import csv
        from io import StringIO
        sio = StringIO()
        writer = csv.writer(sio)
        writer.writerow(['cm', 'mm', 'bbl'])
        for it in rows:
            writer.writerow([it.get('cm'), it.get('mm'), it.get('bbl')])
        sio.seek(0)
        resp = Response(sio.getvalue(), mimetype='text/csv')
        fname = f"aforo_{r.tipo}_{r.nombre}.csv".replace(' ', '_')
        resp.headers['Content-Disposition'] = f'attachment; filename="{fname}"'
        return resp
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500

@login_required
@admin_required
@app.route('/api/aforos/upload', methods=['POST'])
def aforos_upload():
    if 'archivo_excel' not in request.files:
        return jsonify(success=False, message='Archivo no recibido'), 400
    archivo = request.files['archivo_excel']
    tipo = (request.form.get('tipo') or '').upper()
    # Nuevo: permitir optar por el parser de múltiples columnas solo si se solicita explícitamente
    # Por defecto, para BARCAZA se usará el nombre de la hoja como "nombre" de la tabla
    parsear_columnas = (request.form.get('parsear_columnas') == '1')
    # nombre manual es opcional; si el archivo tiene una sola hoja, puede usarse como override
    nombre_override = (request.form.get('nombre') or '').upper().strip()
    if not archivo or not archivo.filename.lower().endswith('.xlsx'):
        return jsonify(success=False, message='Suba un archivo .xlsx'), 400
    if tipo not in ('TK','BARCAZA','VCF'):
        return jsonify(success=False, message='Tipo inválido (TK, BARCAZA o VCF)'), 400
    try:
        wb = openpyxl.load_workbook(archivo)
        hojas = wb.sheetnames
        total_ok = 0
        total_err = 0
        detalles = []
        for idx, sheet_name in enumerate(hojas):
            ws = wb[sheet_name]
            nombre_final = (nombre_override if (len(hojas) == 1 and nombre_override) else sheet_name).upper().strip()
            try:
                filas_count = 0
                datos = None
                # Si es VCF (API6A), procesar como tabla especial: matriz o vertical
                if tipo == 'VCF':
                    max_cols = ws.max_column or 0
                    row1 = [str(c.value).strip().lower() if c.value is not None else '' for c in ws[1][:max_cols]]
                    def is_temp_header(h):
                        h = h.lower().replace('.', '').replace(' ', '')
                        return any(x in h for x in ['temp', 'deg', 'degre', 't'])
                    is_matrix = row1[0] and is_temp_header(row1[0])
                    apis = []
                    data = []
                    if is_matrix:
                        # Formato matriz: encabezados API en la primera fila
                        for i in range(1, max_cols):
                            h = row1[i]
                            try:
                                apis.append(float(str(h).replace(',', '.')))
                            except Exception:
                                apis.append(None)
                        for row in ws.iter_rows(min_row=2, values_only=True):
                            try:
                                temp_v = row[0]
                                for j, api_v in enumerate(apis):
                                    vcf_v = row[j+1] if j+1 < len(row) else None
                                    if api_v is None or temp_v is None or vcf_v is None:
                                        continue
                                    api_f = float(api_v)
                                    temp_f = float(str(temp_v).replace(',', '.'))
                                    vcf_f = float(str(vcf_v).replace(',', '.'))
                                    data.append({'api': api_f, 'temp': temp_f, 'vcf': vcf_f})
                            except Exception:
                                continue
                    else:
                        # Formato vertical: columnas API, TEMP, VCF
                        idx_api = next((i for i, h in enumerate(row1) if 'api' in h), None)
                        idx_temp = next((i for i, h in enumerate(row1) if 'temp' in h or 't' in h), None)
                        idx_vcf = next((i for i, h in enumerate(row1) if 'vcf' in h or 'factor' in h), None)
                        for row in ws.iter_rows(min_row=2, values_only=True):
                            try:
                                api_v = row[idx_api] if idx_api is not None else None
                                temp_v = row[idx_temp] if idx_temp is not None else None
                                vcf_v = row[idx_vcf] if idx_vcf is not None else None
                                if api_v is None or temp_v is None or vcf_v is None:
                                    continue
                                api_f = float(str(api_v).replace(',', '.'))
                                temp_f = float(str(temp_v).replace(',', '.'))
                                vcf_f = float(str(vcf_v).replace(',', '.'))
                                data.append({'api': api_f, 'temp': temp_f, 'vcf': vcf_f})
                            except Exception:
                                continue
                    if data:
                        filas_count = len(data)
                        datos = {'data': data, 'mode': 'flat'}
                        payload = json.dumps(datos, ensure_ascii=False)
                        existente = db.session.query(AforoTabla).filter_by(tipo=tipo, nombre=nombre_final).first()
                        if existente:
                            existente.datos_json = payload
                            existente.usuario = session.get('nombre','No identificado')
                            existente.timestamp = datetime.utcnow()
                        else:
                            db.session.add(AforoTabla(
                                usuario=session.get('nombre','No identificado'),
                                tipo=tipo,
                                nombre=nombre_final,
                                datos_json=payload
                            ))
                        total_ok += 1
                        detalles.append(f"{sheet_name} -> {nombre_final}: OK ({filas_count} filas)")
                        continue
                # ...existing code for TK/BARCAZA...

                # 2) Si BARCAZA sin filas, intentar parser simple LÁMINA + 1 volumen
                if tipo == 'BARCAZA' and filas_count == 0 and not parsear_columnas:
                    datos_simple = _parse_simple_lamina_single_volume(ws)
                    if datos_simple and len(datos_simple.get('data') or []) > 0:
                        payload = json.dumps(datos_simple, ensure_ascii=False)
                        existente = db.session.query(AforoTabla).filter_by(tipo=tipo, nombre=nombre_final).first()
                        if existente:
                            existente.datos_json = payload
                            existente.usuario = session.get('nombre','No identificado')
                            existente.timestamp = datetime.utcnow()
                        else:
                            db.session.add(AforoTabla(
                                usuario=session.get('nombre','No identificado'),
                                tipo=tipo,
                                nombre=nombre_final,
                                datos_json=payload
                            ))
                        total_ok += 1
                        filas_s = len(datos_simple.get('data') or [])
                        detalles.append(f"{sheet_name} -> {nombre_final}: OK ({filas_s} filas)")
                        continue

                # 3) Fallback final: parser de múltiples columnas cuando corresponda
                if tipo == 'BARCAZA' and (parsear_columnas or filas_count == 0):
                    multi = _parse_barge_columns_sheet(ws, prefer_tipo='BARCAZA', default_name=nombre_final)
                    if multi:
                        for nom, datos_m in multi.items():
                            payload = json.dumps(datos_m, ensure_ascii=False)
                            existente = db.session.query(AforoTabla).filter_by(tipo=tipo, nombre=nom).first()
                            if existente:
                                existente.datos_json = payload
                                existente.usuario = session.get('nombre','No identificado')
                                existente.timestamp = datetime.utcnow()
                            else:
                                db.session.add(AforoTabla(
                                    usuario=session.get('nombre','No identificado'),
                                    tipo=tipo,
                                    nombre=nom,
                                    datos_json=payload
                                ))
                            total_ok += 1
                            filas_m = len(datos_m.get('data') or []) if isinstance(datos_m, dict) else 0
                            detalles.append(f"{sheet_name} -> {nom}: OK ({filas_m} filas)")
                        continue

                # Si llegó aquí, no se pudo interpretar la hoja
                raise ValueError('No se pudo interpretar columnas de nivel/volumen')
            except Exception as e:
                total_err += 1
                detalles.append(f"{sheet_name}: ERROR {e}")
        db.session.commit()
        msg = f"Procesado: {total_ok} hojas OK, {total_err} con error."
        return jsonify(success=True, message=msg, detalles=detalles)
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, message=str(e)), 500

@login_required
@app.route('/api/aforos/list')
def aforos_list():
    # acceso general para poder consultarlo desde Trasiegos
    tipo = (request.args.get('tipo') or '').upper() or None
    q = db.session.query(AforoTabla)
    if tipo in ('TK','BARCAZA'):
        q = q.filter(AforoTabla.tipo == tipo)
    filas = q.order_by(AforoTabla.tipo.asc(), AforoTabla.nombre.asc()).all()
    res = []
    for r in filas:
        res.append({
            'id': r.id,
            'tipo': r.tipo,
            'nombre': r.nombre,
            'timestamp': r.timestamp.isoformat(),
            'usuario': r.usuario
        })
    return jsonify(success=True, tablas=res)

@login_required
@app.route('/api/aforos/calcular')
def aforos_calcular():
    try:
        nombre = (request.args.get('nombre') or '').upper()
        tipo = (request.args.get('tipo') or '').upper()
        cm = int(request.args.get('cm') or 0)
        mm = int(request.args.get('mm') or 0)
        if not nombre or tipo not in ('TK','BARCAZA'):
            return jsonify(success=False, message='Parámetros inválidos'), 400
        tabla = db.session.query(AforoTabla).filter_by(tipo=tipo, nombre=nombre).first()
        if not tabla:
            return jsonify(success=False, message='Tabla de aforo no encontrada'), 404
        datos = json.loads(tabla.datos_json)
        # Para TK-01, TK-02 y barcaza MANZANILLO, buscar valor exacto
        nombres_exactos = ["TK-01", "TK-02"]
        # Barcaza MANZANILLO compartimentos
        nombres_exactos += ["1", "2", "3"]
        # Barcaza ODISEA compartimentos
        nombres_exactos += ["1P", "1S", "2P", "2S", "3P", "3S"]
        # Barcaza MARGOTH compartimentos SOLO con prefijo MG6-
        nombres_exactos += [
            "MG6-1P", "MG6-1S", "MG6-2P", "MG6-2S", "MG6-3P", "MG6-3S", "MG6-4P", "MG6-4S", "MG6-5P", "MG6-5S"
        ]
        # Barcaza CR compartimentos SOLO con prefijo CR
        nombres_exactos += ["CR 1S", "CR 1P", "CR 2S", "CR 2P", "CR 3S", "CR 3P", "CR 4S", "CR 4P", "CR 5S", "CR 5P"]
        if nombre in nombres_exactos:
            lista = datos.get('data') if isinstance(datos, dict) and 'data' in datos else datos
            if isinstance(lista, list):
                match = next((d for d in lista if int(d.get('cm', -1)) == cm and int(d.get('mm', 0)) == mm), None)
                if match:
                    bbl = match.get('bbl', 0.0)
                    return jsonify(success=True, bbl=round(float(bbl), 2))
        # Para otros tanques, usar interpolación
        bbl = _interp_bbl(datos, cm, mm)
        return jsonify(success=True, bbl=round(float(bbl), 2))
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500

@login_required
@admin_required
@app.route('/api/aforos/delete', methods=['POST'])
def aforos_delete():
    try:
        payload = request.get_json(silent=True) or {}
        tid = payload.get('id')
        tipo = (payload.get('tipo') or '').upper() or None
        nombre = (payload.get('nombre') or '').upper() or None
        prefix = (payload.get('prefix') or '').upper().strip() or None
        nombre_like = (payload.get('nombre_like') or '').upper().strip() or None

        if not (tid or (tipo and (nombre or prefix or nombre_like))):
            return jsonify(success=False, message='Parámetros requeridos: id OR (tipo + nombre|prefix|nombre_like)'), 400

        q = db.session.query(AforoTabla)
        if tid:
            q = q.filter(AforoTabla.id == int(tid))
        else:
            q = q.filter(AforoTabla.tipo == tipo)
            if nombre:
                q = q.filter(AforoTabla.nombre == nombre)
            elif prefix:
                q = q.filter(AforoTabla.nombre.like(f"{prefix}%"))
            elif nombre_like:
                q = q.filter(AforoTabla.nombre.like(f"%{nombre_like}%"))

        filas = q.all()
        if not filas:
            return jsonify(success=False, message='No se encontraron tablas a eliminar'), 404
        count = len(filas)
        for r in filas:
            db.session.delete(r)
        db.session.commit()
        return jsonify(success=True, deleted=count)
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, message=str(e)), 500
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

def permiso_exclusivo(email_requerido):
    """
    Decorador que da acceso SOLO al email especificado. Nadie más puede entrar.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if session.get('email') != email_requerido:
                flash("No tiene permiso para acceder a esta página.", "danger")
                return redirect(url_for('home'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def _to_float(value):
    if value in (None, ''):
        return None
    try:
        return float(str(value).replace(',', '.'))
    except Exception:
        return None

def _to_int(value):
    if value in (None, ''):
        return None
    try:
        return int(str(value).strip())
    except Exception:
        return None

@login_required
@app.route('/trasiegos', methods=['GET', 'POST'])
def trasiegos_page():
    nombre_usr = session.get('nombre', '')
    ALLOWED_TK = { 'Ignacio Quimbayo', 'Control Refineria' }
    ALLOWED_BAR = { 'Juan Diego Cuadros', 'Ricardo Congo' }
    can_tk = nombre_usr in ALLOWED_TK
    can_bar = nombre_usr in ALLOWED_BAR
    def _get_or_create(fecha_dt, origen_tk, destino_barcaza, destino_comp):
        q = (db.session.query(TrasiegoTKBarcaza)
             .filter(TrasiegoTKBarcaza.fecha == fecha_dt,
                     TrasiegoTKBarcaza.origen_tk == origen_tk,
                     TrasiegoTKBarcaza.destino_barcaza == destino_barcaza,
                     (TrasiegoTKBarcaza.destino_compartimento == (destino_comp or None))) )
        inst = q.first()
        if inst:
            return inst, False
        inst = TrasiegoTKBarcaza(
            fecha=fecha_dt,
            usuario=session.get('nombre','No identificado'),
            origen_tk=origen_tk,
            destino_barcaza=destino_barcaza,
            destino_compartimento=destino_comp or None
        )
        db.session.add(inst)
        return inst, True

    if request.method == 'POST':
        try:
            fecha = request.form.get('fecha') or date.today().isoformat()
            fecha_dt = date.fromisoformat(fecha)
            origen_tk = (request.form.get('origen_tk','') or '').upper()
            destino_barcaza = (request.form.get('destino_barcaza','') or '').upper()
            destino_compartimento = (request.form.get('destino_compartimento') or '').upper() or None
            seccion = request.form.get('seccion')  # 'tk' o 'bar'

            # Permisos por sección
            if seccion == 'tk' and not can_tk:
                flash('No tiene permiso para registrar datos del Tanque.', 'danger')
                return redirect(url_for('trasiegos_page'))
            if seccion == 'bar' and not can_bar:
                flash('No tiene permiso para registrar datos de la Barcaza.', 'danger')
                return redirect(url_for('trasiegos_page'))

            # TK: forzar clave sin barcaza/comp para que el bar vincule luego
            if seccion == 'tk':
                destino_barcaza = ''
                destino_compartimento = None

            # Si ya existe registro para esta clave, bloquear cambio de fecha al del primer registro
            clave_barcaza = destino_barcaza or ''
            existente = (db.session.query(TrasiegoTKBarcaza)
                         .filter(TrasiegoTKBarcaza.origen_tk == origen_tk,
                                 TrasiegoTKBarcaza.destino_barcaza == clave_barcaza,
                                 (TrasiegoTKBarcaza.destino_compartimento == (destino_compartimento or None)))
                         .order_by(TrasiegoTKBarcaza.id.asc()).first())
            if existente:
                fecha_dt = existente.fecha

            inst, created = _get_or_create(fecha_dt, origen_tk, destino_barcaza, destino_compartimento)
            inst.usuario = session.get('nombre','No identificado')

            if seccion == 'tk':
                inst.tk_cm_inicial = _to_int(request.form.get('tk_cm_inicial'))
                inst.tk_mm_inicial = _to_int(request.form.get('tk_mm_inicial'))
                inst.tk_bbl_bruto_inicial = _to_float(request.form.get('tk_bbl_bruto_inicial'))
                inst.tk_bbl_inicial = _to_float(request.form.get('tk_bbl_inicial'))
                inst.tk_api = _to_float(request.form.get('tk_api'))
                inst.tk_temp = _to_float(request.form.get('tk_temp'))
                inst.tk_cm_final = _to_int(request.form.get('tk_cm_final'))
                inst.tk_mm_final = _to_int(request.form.get('tk_mm_final'))
                inst.tk_bbl_bruto_final = _to_float(request.form.get('tk_bbl_bruto_final'))
                inst.tk_bbl_final = _to_float(request.form.get('tk_bbl_final'))
                inst.tk_notas = request.form.get('tk_notas')
                # Ingreso simultáneo al TK: caudal (BBL/h), minutos y total bbl
                caudal = _to_float(request.form.get('tk_caudal_bbl_min'))
                minutos = _to_float(request.form.get('tk_minutos_ingreso'))
                bbling = _to_float(request.form.get('tk_bbl_ingreso'))
                inst.tk_caudal_bbl_min = caudal
                inst.tk_minutos_ingreso = minutos
                # Si no se envía tk_bbl_ingreso explícito, calcularlo
                if bbling is None and caudal is not None and minutos is not None:
                    bbling = round(caudal * (minutos/60.0), 2)
                inst.tk_bbl_ingreso = bbling
                # Si no tiene barcaza definida, se almacena como cadena vacía (columna NOT NULL en SQLite)
                if inst.destino_barcaza is None:
                    inst.destino_barcaza = ''
            elif seccion == 'bar':
                # Intentar vincular con un registro TK previo (barcaza en blanco) si no encontramos uno exacto
                if created and destino_barcaza and origen_tk:
                    # Buscar registro con misma fecha y TK, barcaza en blanco/NULL
                    prev = (db.session.query(TrasiegoTKBarcaza)
                            .filter(TrasiegoTKBarcaza.origen_tk == origen_tk,
                                    TrasiegoTKBarcaza.fecha == fecha_dt,
                                    (TrasiegoTKBarcaza.destino_barcaza == '') )
                            .order_by(TrasiegoTKBarcaza.id.asc()).first())
                    if prev:
                        # Reutilizar registro y bloquear fecha del previo
                        db.session.expunge(inst)
                        inst = prev
                        created = False
                        inst.destino_barcaza = destino_barcaza
                        inst.destino_compartimento = destino_compartimento or None
                    else:
                        # Si existe uno para ese TK con barcaza en blanco pero con OTRA fecha, bloquea cambio de fecha
                        prev_any = (db.session.query(TrasiegoTKBarcaza)
                                    .filter(TrasiegoTKBarcaza.origen_tk == origen_tk,
                                            (TrasiegoTKBarcaza.destino_barcaza == ''))
                                    .order_by(TrasiegoTKBarcaza.id.desc()).first())
                        if prev_any and prev_any.fecha != fecha_dt:
                            flash(f'La fecha está bloqueada para este trasiego (use {prev_any.fecha}).', 'warning')
                            return redirect(url_for('trasiegos_page'))
                inst.bar_cm_inicial = _to_int(request.form.get('bar_cm_inicial'))
                inst.bar_mm_inicial = _to_int(request.form.get('bar_mm_inicial'))
                inst.bar_bbl_bruto_inicial = _to_float(request.form.get('bar_bbl_bruto_inicial'))
                inst.bar_bbl_inicial = _to_float(request.form.get('bar_bbl_inicial'))
                inst.bar_api = _to_float(request.form.get('bar_api'))
                inst.bar_temp = _to_float(request.form.get('bar_temp'))
                inst.bar_cm_final = _to_int(request.form.get('bar_cm_final'))
                inst.bar_mm_final = _to_int(request.form.get('bar_mm_final'))
                inst.bar_bbl_bruto_final = _to_float(request.form.get('bar_bbl_bruto_final'))
                inst.bar_bbl_final = _to_float(request.form.get('bar_bbl_final'))
            else:
                # compat: si no viene seccion, guardamos todo lo que venga
                inst.tk_cm_inicial = _to_int(request.form.get('tk_cm_inicial'))
                inst.tk_mm_inicial = _to_int(request.form.get('tk_mm_inicial'))
                inst.tk_bbl_bruto_inicial = _to_float(request.form.get('tk_bbl_bruto_inicial'))
                inst.tk_bbl_inicial = _to_float(request.form.get('tk_bbl_inicial'))
                inst.tk_api = _to_float(request.form.get('tk_api'))
                inst.tk_temp = _to_float(request.form.get('tk_temp'))
                inst.tk_cm_final = _to_int(request.form.get('tk_cm_final'))
                inst.tk_mm_final = _to_int(request.form.get('tk_mm_final'))
                inst.tk_bbl_bruto_final = _to_float(request.form.get('tk_bbl_bruto_final'))
                inst.tk_bbl_final = _to_float(request.form.get('tk_bbl_final'))
                # Ingreso simultáneo (modo compat)
                caudal = _to_float(request.form.get('tk_caudal_bbl_min'))
                minutos = _to_float(request.form.get('tk_minutos_ingreso'))
                bbling = _to_float(request.form.get('tk_bbl_ingreso'))
                inst.tk_caudal_bbl_min = caudal
                inst.tk_minutos_ingreso = minutos
                if bbling is None and caudal is not None and minutos is not None:
                    bbling = round(caudal * (minutos/60.0), 2)
                inst.tk_bbl_ingreso = bbling
                inst.bar_cm_inicial = _to_int(request.form.get('bar_cm_inicial'))
                inst.bar_mm_inicial = _to_int(request.form.get('bar_mm_inicial'))
                inst.bar_bbl_bruto_inicial = _to_float(request.form.get('bar_bbl_bruto_inicial'))
                inst.bar_bbl_inicial = _to_float(request.form.get('bar_bbl_inicial'))
                inst.bar_api = _to_float(request.form.get('bar_api'))
                inst.bar_temp = _to_float(request.form.get('bar_temp'))
                inst.bar_cm_final = _to_int(request.form.get('bar_cm_final'))
                inst.bar_mm_final = _to_int(request.form.get('bar_mm_final'))
                inst.bar_bbl_bruto_final = _to_float(request.form.get('bar_bbl_bruto_final'))
                inst.bar_bbl_final = _to_float(request.form.get('bar_bbl_final'))

            inst.notas = request.form.get('notas')
            db.session.commit()
            if seccion == 'tk':
                flash('Datos del Tanque guardados','success')
            elif seccion == 'bar':
                flash('Datos de la Barcaza guardados','success')
            else:
                flash('Trasiego guardado exitosamente','success')
            return redirect(url_for('trasiegos_page'))
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error guardando trasiego: {e}")
            flash(f'Error guardando: {e}','danger')
    # GET
    desde = request.args.get('desde')
    hasta = request.args.get('hasta')
    q = db.session.query(TrasiegoTKBarcaza)
    if desde:
        try:
            q = q.filter(TrasiegoTKBarcaza.fecha >= date.fromisoformat(desde))
        except Exception:
            pass
    if hasta:
        try:
            q = q.filter(TrasiegoTKBarcaza.fecha <= date.fromisoformat(hasta))
        except Exception:
            pass
    trasiegos = q.order_by(TrasiegoTKBarcaza.fecha.desc(), TrasiegoTKBarcaza.id.desc()).all()
    return render_template('trasiegos.html', nombre=session.get('nombre'), trasiegos=trasiegos, desde=desde or '', hasta=hasta or '', allowed_tk=can_tk, allowed_bar=can_bar)

@login_required
@app.route('/guardar_trasiegos_masivo', methods=['POST'])
def guardar_trasiegos_masivo():
    def to_float(v):
        if v is None:
            return None
        s = str(v).strip().replace(',', '.')
        if s == '':
            return None
        try:
            return float(s)
        except Exception:
            return None
    def to_int(v):
        if v is None:
            return None
        s = str(v).strip()
        if s == '':
            return None
        try:
            return int(float(s))
        except Exception:
            return None
    try:
        data = request.get_json()
        trasiegos = data.get('trasiegos', [])
        if not trasiegos or not isinstance(trasiegos, list):
            return jsonify(success=False, message='No se recibieron trasiegos válidos'), 400
        guardados = 0
        errores = []
        for t in trasiegos:
            try:
                fecha = t.get('fecha') or date.today().isoformat()
                fecha_dt = date.fromisoformat(fecha)
                origen_tk = (t.get('origen_tk','') or '').upper()
                destino_barcaza = (t.get('destino_barcaza','') or '').upper()
                destino_compartimento = (t.get('destino_compartimento') or '').upper() or None
                usuario = session.get('nombre','No identificado')
                # Crear registro
                reg = TrasiegoTKBarcaza(
                    fecha=fecha_dt,
                    usuario=usuario,
                    origen_tk=origen_tk,
                    destino_barcaza=destino_barcaza,
                    destino_compartimento=destino_compartimento,
                    tk_cm_inicial=to_int(t.get('tk_cm_inicial')),
                    tk_mm_inicial=to_int(t.get('tk_mm_inicial')),
                    tk_bbl_bruto_inicial=to_float(t.get('tk_bbl_bruto_inicial')),
                    tk_bbl_inicial=to_float(t.get('tk_bbl_inicial')),
                    tk_api=to_float(t.get('tk_api')),
                    tk_temp=to_float(t.get('tk_temp')),
                    tk_cm_final=to_int(t.get('tk_cm_final')),
                    tk_mm_final=to_int(t.get('tk_mm_final')),
                    tk_bbl_bruto_final=to_float(t.get('tk_bbl_bruto_final')),
                    tk_bbl_final=to_float(t.get('tk_bbl_final')),
                    tk_caudal_bbl_min=to_float(t.get('tk_caudal_bbl_min')),
                    tk_minutos_ingreso=to_float(t.get('tk_minutos_ingreso')),
                    tk_bbl_ingreso=to_float(t.get('tk_bbl_ingreso')),
                    bar_cm_inicial=to_int(t.get('bar_cm_inicial')),
                    bar_mm_inicial=to_int(t.get('bar_mm_inicial')),
                    bar_bbl_bruto_inicial=to_float(t.get('bar_bbl_bruto_inicial')),
                    bar_bbl_inicial=to_float(t.get('bar_bbl_inicial')),
                    bar_api=to_float(t.get('bar_api')),
                    bar_temp=to_float(t.get('bar_temp')),
                    bar_cm_final=to_int(t.get('bar_cm_final')),
                    bar_mm_final=to_int(t.get('bar_mm_final')),
                    bar_bbl_bruto_final=to_float(t.get('bar_bbl_bruto_final')),
                    bar_bbl_final=to_float(t.get('bar_bbl_final')),
                    notas=t.get('notas'),
                    tk_notas=t.get('tk_notas')
                )
                db.session.add(reg)
                guardados += 1
            except Exception as e:
                errores.append(str(e))
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify(success=False, message=f'Error al guardar: {e}', errores=errores), 500
        return jsonify(success=True, guardados=guardados, errores=errores)
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500

def _build_opciones_trasiegos():
    # Origen TK desde planilla de planta
    tks = [str(p.get('TK')) for p in PLANILLA_PLANTA if p.get('TK')]
    # Barcazas y compartimentos
    barcazas = {}
    # Orion por grupos
    try:
        from collections import defaultdict
        grp = defaultdict(list)
        for p in PLANILLA_BARCAZA_ORION:
            g = str(p.get('grupo') or 'ORION').upper()
            grp[g].append(str(p.get('TK')))
        for g, lst in grp.items():
            barcazas[g] = lst
    except Exception:
        pass
    # BITA: separar por prefijo
    try:
        marinse = [p['TK'] for p in PLANILLA_BARCAZA_BITA if str(p.get('TK','')).startswith('MARI ')]
        oidech = [p['TK'] for p in PLANILLA_BARCAZA_BITA if str(p.get('TK','')).startswith('OID ')]
        if marinse:
            barcazas['BITA-MARINSE'] = marinse
        if oidech:
            barcazas['BITA-OIDECH'] = oidech
    except Exception:
        pass
    # Aforos TK y Barcaza
    aforosTK = [r.nombre for r in db.session.query(AforoTabla).filter(AforoTabla.tipo == 'TK').order_by(AforoTabla.nombre.asc()).all()]
    aforosBAR = [r.nombre for r in db.session.query(AforoTabla).filter(AforoTabla.tipo == 'BARCAZA').order_by(AforoTabla.nombre.asc()).all()]
    return { 'tks': tks, 'barcazas': barcazas, 'aforosTK': aforosTK, 'aforosBAR': aforosBAR }

@login_required
@app.route('/api/trasiegos/opciones')
def api_trasiegos_opciones():
    try:
        return jsonify(success=True, **_build_opciones_trasiegos())
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500

@login_required
@app.route('/api/trasiegos/verificar_fecha')
def api_trasiegos_verificar_fecha():
    try:
        tk = (request.args.get('tk') or '').upper().strip()
        if not tk:
            return jsonify(success=True, fecha_bloqueada=False)
        reg = (db.session.query(TrasiegoTKBarcaza)
               .filter(TrasiegoTKBarcaza.origen_tk == tk,
                       or_(TrasiegoTKBarcaza.destino_barcaza == '', TrasiegoTKBarcaza.destino_barcaza.is_(None)))
               .order_by(TrasiegoTKBarcaza.id.desc())
               .first())
        if reg:
            return jsonify(success=True, fecha_bloqueada=True, fecha=reg.fecha.isoformat(), tk=reg.origen_tk or '')
        return jsonify(success=True, fecha_bloqueada=False)
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500

# Endpoint para buscar VCF en la tabla API6A
@login_required
@app.route('/api/vcf_api6a')
def api_vcf_api6a():
    try:
        api = request.args.get('api', type=float)
        temp = request.args.get('temp', type=float)
        unidad = request.args.get('unidad', default='C').upper()
        nombre = request.args.get('nombre')
        if api is None or temp is None:
            return jsonify(success=False, message='API y temperatura requeridos'), 400
        if nombre:
            tabla = db.session.query(AforoTabla).filter_by(tipo='VCF', nombre=nombre.upper()).first()
        else:
            tabla = db.session.query(AforoTabla).filter_by(tipo='VCF').order_by(AforoTabla.timestamp.desc()).first()
        if not tabla:
            return jsonify(success=False, message='Tabla VCF/API6A no encontrada'), 404
        datos = json.loads(tabla.datos_json)
        lista = datos.get('data') if isinstance(datos, dict) and 'data' in datos else datos
        if not isinstance(lista, list):
            return jsonify(success=False, message='Datos VCF inválidos'), 500
        # Buscar coincidencia exacta primero
        match = next((d for d in lista if abs(d.get('api',-1)-api)<0.01 and abs(d.get('temp',-1)-temp)<0.01), None)
        if match:
            return jsonify(success=True, vcf=match.get('vcf', 1))
        # Si no hay coincidencia exacta, buscar la más cercana (interpolación simple)
        # Ordenar por distancia
        lista_ordenada = sorted(lista, key=lambda d: ((d.get('api',0)-api)**2 + (d.get('temp',0)-temp)**2))
        if lista_ordenada:
            return jsonify(success=True, vcf=lista_ordenada[0].get('vcf', 1))
        return jsonify(success=False, message='No se encontró VCF para esos valores'), 404
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500

@login_required
@app.route('/trasiegos/eliminar/<int:id>', methods=['POST'])
def eliminar_trasiego(id):
    try:
        reg = TrasiegoTKBarcaza.query.get_or_404(id)
        db.session.delete(reg)
        db.session.commit()
        flash('Registro eliminado','success')
    except Exception as e:
        db.session.rollback()
        flash(f'No se pudo eliminar: {e}','danger')
    return redirect(url_for('trasiegos_page'))

@login_required
@app.route('/reporte_trasiegos')
def reporte_trasiegos():
    # Reporte tipo tabla como la imagen, por fecha
    fecha_str = request.args.get('fecha')
    try:
        fecha_sel = date.fromisoformat(fecha_str) if fecha_str else date.today()
    except Exception:
        fecha_sel = date.today()

    registros = (db.session.query(TrasiegoTKBarcaza)
                 .filter(TrasiegoTKBarcaza.fecha == fecha_sel)
                 .order_by(TrasiegoTKBarcaza.origen_tk.asc())
                 .all())

    # Columnas dinámicas: Tks origen y compartimentos destino
    columnas_tk = []
    columnas_bar = []
    for r in registros:
        if r.origen_tk and r.origen_tk not in columnas_tk:
            columnas_tk.append(r.origen_tk)
        comp = (r.destino_compartimento or r.destino_barcaza)
        if comp and comp not in columnas_bar:
            columnas_bar.append(comp)

    # Construir estructura para la plantilla
    def build_map(keys):
        return {k: { 'ini': {'cm':None,'mm':None,'bbl':None, 'bbl_bruto': None}, 'fin': {'cm':None,'mm':None,'bbl':None, 'bbl_bruto': None}, 'temp': None, 'api': None, 'trasiego': None } for k in keys}

    datos_tk = build_map(columnas_tk)
    datos_bar = build_map(columnas_bar)

    for r in registros:
        tkd = datos_tk.get(r.origen_tk)
        if tkd is not None:
            tkd['ini'] = {'cm': r.tk_cm_inicial, 'mm': r.tk_mm_inicial, 'bbl': r.tk_bbl_inicial, 'bbl_bruto': r.tk_bbl_bruto_inicial}
            tkd['fin'] = {'cm': r.tk_cm_final, 'mm': r.tk_mm_final, 'bbl': r.tk_bbl_final, 'bbl_bruto': r.tk_bbl_bruto_final}
            tkd['temp'] = r.tk_temp
            tkd['api'] = r.tk_api
            tkd['trasiego'] = r.trasiego_segun_tanque
        comp = (r.destino_compartimento or r.destino_barcaza)
        bd = datos_bar.get(comp)
        if bd is not None:
            bd['ini'] = {'cm': r.bar_cm_inicial, 'mm': r.bar_mm_inicial, 'bbl': r.bar_bbl_inicial, 'bbl_bruto': r.bar_bbl_bruto_inicial}
            bd['fin'] = {'cm': r.bar_cm_final, 'mm': r.bar_mm_final, 'bbl': r.bar_bbl_final, 'bbl_bruto': r.bar_bbl_bruto_final}
            bd['temp'] = r.bar_temp
            bd['api'] = r.bar_api
            bd['trasiego'] = r.trasiego_segun_barcaza

    diferencia_total = round(
        sum([d.get('trasiego') or 0 for d in datos_bar.values()]) - sum([d.get('trasiego') or 0 for d in datos_tk.values()])
        , 2)

    return render_template('reporte_trasiegos.html',
                           nombre=session.get('nombre'),
                           fecha_seleccionada=fecha_sel.isoformat(),
                           columnas_tk=columnas_tk,
                           columnas_bar=columnas_bar,
                           datos_tk=datos_tk,
                           datos_bar=datos_bar,
                           diferencia_total=diferencia_total)

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
        fecha_seleccionada = date.fromisoformat(fecha_str) if fecha_str else date.today()
    except (ValueError, TypeError):
        fecha_seleccionada = date.today()
    
    timestamp_limite = datetime.combine(fecha_seleccionada, time.max)

    # 2. Consulta para obtener el estado MÁS RECIENTE de CADA tanque EN O ANTES de la fecha seleccionada
    subquery = db.session.query(
        RegistroPlanta.tk,
        func.max(RegistroPlanta.timestamp).label('max_timestamp')
    ).filter(RegistroPlanta.timestamp <= timestamp_limite
             ).group_by(RegistroPlanta.tk).subquery()

    registros_recientes = db.session.query(RegistroPlanta).join(
        subquery,
        (RegistroPlanta.tk == subquery.c.tk) & (RegistroPlanta.timestamp == subquery.c.max_timestamp)
    ).all()
    
    # 3. Preparar y ORDENAR los datos según el orden deseado
    orden_deseado = ["TK-109", "TK-110", "TK-108", "TK-102", "TK-01", "TK-02"]
    orden_map = {tk: i for i, tk in enumerate(orden_deseado)}

    # Combinar defaults con últimos registros para asegurar que todos los TK de la planilla existan (por ejemplo, TK-108)
    datos_por_tk = {fila["TK"]: dict(fila) for fila in PLANILLA_PLANTA}
    if registros_recientes:
        for registro in registros_recientes:
            datos_por_tk[registro.tk] = {
                "TK": registro.tk,
                "PRODUCTO": registro.producto,
                "MAX_CAP": registro.max_cap,
                "BLS_60": registro.bls_60 or "",
                "API": registro.api or "",
                "BSW": registro.bsw or "",
                "S": registro.s or ""
            }
    datos_para_plantilla = list(datos_por_tk.values())

    # Ordenar la lista según el orden deseado
    datos_para_plantilla = sorted(
        datos_para_plantilla,
        key=lambda fila: orden_map.get(fila["TK"], 99)
    )

    # 4. Construimos listado de días con registros para colorear el calendario
    try:
        dias_rows = (db.session
            .query(func.date(RegistroPlanta.timestamp).label('dia'))
            .group_by(func.date(RegistroPlanta.timestamp))
            .all())
        fechas_con_registro = []
        for (dia,) in dias_rows:
            try:
                fechas_con_registro.append(dia.isoformat())
            except AttributeError:
                fechas_con_registro.append(str(dia))
    except Exception:
        fechas_con_registro = []

    # 5. Enviamos los datos y la fecha seleccionada de vuelta al HTML
    return render_template("planta.html", 
                           planilla=datos_para_plantilla, 
                           nombre=session.get("nombre", "Usuario"),
                           fecha_seleccionada=fecha_seleccionada.isoformat(),
                           today_iso=date.today().isoformat(),
                           fechas_con_registro=fechas_con_registro)

@login_required
@permiso_requerido('planta')
@app.route('/reporte_variaciones_tanques')
def reporte_variaciones_tanques():
    try:
        end_str = request.args.get('hasta')
        start_str = request.args.get('desde')
        hasta = date.fromisoformat(end_str) if end_str else None
        desde = date.fromisoformat(start_str) if start_str else None

        # Subconsulta: último registro por día y tanque (con rango opcional)
        fecha_dia = func.date(RegistroPlanta.timestamp)
        subq_query = db.session.query(func.max(RegistroPlanta.id).label('max_id'))
        if desde is not None:
            subq_query = subq_query.filter(RegistroPlanta.timestamp >= datetime.combine(desde, time.min))
        if hasta is not None:
            subq_query = subq_query.filter(RegistroPlanta.timestamp <= datetime.combine(hasta, time.max))
        subq = subq_query.group_by(RegistroPlanta.tk, fecha_dia).subquery()

        registros = (db.session.query(RegistroPlanta)
                     .filter(RegistroPlanta.id.in_(subq))
                     .order_by(RegistroPlanta.tk.asc(), RegistroPlanta.timestamp.asc())
                     .all())

        # Organizar por tanque y día
        por_tanque = {}
        for r in registros:
            if not r.tk:
                continue
            tk = r.tk
            dia = r.timestamp.date()
            bls = float(r.bls_60 or 0)
            por_tanque.setdefault(tk, {})[dia] = {
                'bls_60': bls,
                'max_cap': float(r.max_cap or 0),
                'producto': r.producto or ''
            }

        # Construir series por tanque: fechas, valores y variaciones
        series = {}
        for tk, mapa in por_tanque.items():
            fechas_ord = sorted(mapa.keys())
            valores = [mapa[f]['bls_60'] for f in fechas_ord]
            diffs = []
            prev = None
            for v in valores:
                if prev is None:
                    diffs.append(None)
                else:
                    diffs.append(round(v - prev, 2))
                prev = v
            # Convertir fechas a strings ISO para JS
            etiquetas = [f.isoformat() for f in fechas_ord]
            max_cap = next((mapa[f]['max_cap'] for f in fechas_ord if mapa[f]['max_cap'] > 0), 0)
            producto = next((mapa[f]['producto'] for f in fechas_ord if (mapa[f]['producto'] or '').strip()), '')
            series[tk] = {
                'labels': etiquetas,
                'bls_60': valores,
                'variacion': diffs,
                'max_cap': max_cap,
                'producto': producto
            }

        # Fechas con registro para colorear
        try:
            dias_rows = (db.session
                .query(func.date(RegistroPlanta.timestamp).label('dia'))
                .group_by(func.date(RegistroPlanta.timestamp))
                .all())
            fechas_con_registro = []
            for (dia,) in dias_rows:
                try:
                    fechas_con_registro.append(dia.isoformat())
                except AttributeError:
                    fechas_con_registro.append(str(dia))
        except Exception:
            fechas_con_registro = []

        return render_template('reporte_variaciones_tanques.html',
                               nombre=session.get('nombre'),
                               desde=desde.isoformat() if desde else '',
                               hasta=hasta.isoformat() if hasta else '',
                               series_por_tanque=series,
                               today_iso=date.today().isoformat(),
                               fechas_con_registro=fechas_con_registro)
    except Exception as e:
        app.logger.error(f"Error en reporte_variaciones_tanques: {e}")
        flash(f"Ocurrió un error al generar el reporte: {e}", 'danger')
        # Fallback a rango por defecto
    return render_template('reporte_variaciones_tanques.html',
                   nombre=session.get('nombre'),
                   desde='',
                   hasta='',
                   series_por_tanque={},
                   today_iso=date.today().isoformat(),
                   fechas_con_registro=[])
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
        orden_deseado = ["TK-109", "TK-110", "TK-108", "TK-102", "TK-01", "TK-02"]
        
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
        # Construir mapa por TK desde registros
        mapa_js = {r.tk: {
            "TK": r.tk,
            "PRODUCTO": r.producto,
            "MAX_CAP": r.max_cap,
            "BLS_60": r.bls_60,
            "API": r.api,
            "BSW": r.bsw,
            "S": r.s
        } for r in registros_ordenados if r.tk}

        # Asegurar que todos los TK definidos por defecto existan (ej. TK-108)
        for fila in PLANILLA_PLANTA:
            tk = fila.get("TK")
            if tk and tk not in mapa_js:
                mapa_js[tk] = {
                    "TK": tk,
                    "PRODUCTO": fila.get("PRODUCTO"),
                    "MAX_CAP": fila.get("MAX_CAP"),
                    "BLS_60": None,
                    "API": None,
                    "BSW": None,
                    "S": None
                }

        # Ordenar según orden deseado
        orden_deseado = ["TK-109", "TK-110", "TK-108", "TK-102", "TK-01", "TK-02"]
        orden_map = {tk: i for i, tk in enumerate(orden_deseado)}
        datos_planta_js = sorted(mapa_js.values(), key=lambda d: orden_map.get(d.get("TK"), 99))
        
        # La lógica para la fecha de actualización no cambia
        ultimo_registro_general = max(registros_recientes, key=lambda r: r.timestamp)
        fecha_formato = ultimo_registro_general.timestamp.strftime("%Y_%m_%d_%H_%M_%S")
        fecha_actualizacion_info = formatear_info_actualizacion(
            fecha_formato, 
            ultimo_registro_general.usuario
        )

    # 4. Renderizamos la plantilla con los datos ya ordenados
    # Fechas con registro para colorear
    try:
        dias_rows = (db.session
            .query(func.date(RegistroPlanta.timestamp).label('dia'))
            .group_by(func.date(RegistroPlanta.timestamp))
            .all())
        fechas_con_registro = []
        for (dia,) in dias_rows:
            try:
                fechas_con_registro.append(dia.isoformat())
            except AttributeError:
                fechas_con_registro.append(str(dia))
    except Exception:
        fechas_con_registro = []

    return render_template("reporte_planta.html", 
                           datos_planta_para_js=datos_planta_js,
                           fecha_actualizacion_info=fecha_actualizacion_info,
                           fecha_seleccionada=fecha_seleccionada.isoformat(),
                           today_iso=date.today().isoformat(),
                           fechas_con_registro=fechas_con_registro)


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
@app.route('/api/transito/eliminar-todo/<string:tipo_transito>', methods=['DELETE'])
def eliminar_todo_transito(tipo_transito):
    """
    Elimina TODOS los registros de un tipo de tránsito específico ('general' o 'refineria').
    """
    # Validamos que el tipo sea uno de los esperados
    if tipo_transito not in ['general', 'refineria']:
        return jsonify(success=False, message="Tipo de tránsito no válido."), 400

    try:
        # Ejecuta la eliminación masiva
        num_borrados = RegistroTransito.query.filter_by(tipo_transito=tipo_transito).delete()
        
        # Confirma la transacción
        db.session.commit()
        
        return jsonify(success=True, message=f"Se eliminaron {num_borrados} registros de la planilla '{tipo_transito}'.")

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error en eliminación masiva de tránsito '{tipo_transito}': {e}")
        return jsonify(success=False, message=f"Error interno del servidor: {str(e)}"), 500    
    
@login_required
@permiso_requerido('transito')
@app.route('/eliminar-registro-transito/<int:id>', methods=['DELETE'])
def eliminar_registro_transito(id):
    """
    Elimina un único registro de la tabla de tránsito por su ID.
    """
    try:
        # Busca el registro por su ID. Si no lo encuentra, devuelve un error 404.
        registro_a_eliminar = RegistroTransito.query.get_or_404(id)
        
        # Elimina el registro de la sesión de la base de datos
        db.session.delete(registro_a_eliminar)
        
        # Confirma los cambios en la base de datos
        db.session.commit()
        
        # Devuelve una respuesta de éxito en formato JSON
        return jsonify(success=True, message="Registro eliminado exitosamente.")

    except Exception as e:
        # Si algo sale mal, revierte los cambios y registra el error
        db.session.rollback()
        app.logger.error(f"Error al eliminar registro de tránsito ID {id}: {e}")
        return jsonify(success=False, message=f"Error interno del servidor: {str(e)}"), 500    
    
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
@permiso_requerido('control_remolcadores')
@app.route('/api/registros_remolcadores/<int:id>', methods=['DELETE'])
def eliminar_evento_remolcador(id):
    """Elimina un único evento de la maniobra."""
    
    usuario_puede_eliminar = (
        session.get('rol') == 'admin' or 
        session.get('email') == 'ops@conquerstrading.com' or
        session.get('email') == 'opensean@conquerstrading.com'
    )

    if not usuario_puede_eliminar:
        return jsonify(success=False, message="No tienes permiso para eliminar este evento."), 403
    
    try:
        registro = RegistroRemolcador.query.get_or_404(id)
        db.session.delete(registro)
        db.session.commit()
        return jsonify(success=True, message="Evento eliminado correctamente.")
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error al eliminar evento de remolcador: {e}")
        return jsonify(success=False, message=f"Error interno: {str(e)}"), 500

# ================== MODELO OPTIMIZACIÓN ==================
@login_required
@permiso_requerido('modelo_optimizacion')
@app.route('/modelo-optimizacion', methods=['GET','POST'])
def modelo_optimizacion_page():
    from flask import current_app
    error = None
    # Restricción extra: solo Felipe y German (y admin)
    allowed = {"felipe.delavega@conquerstrading.com", "finance@conquerstrading.com"}
    if session.get('rol') != 'admin' and session.get('email') not in allowed:
        flash('No tienes permiso para este módulo.', 'danger')
        return redirect(url_for('home'))
    resultados = None
    grafico_base64 = None
    excel_descargable = False
    # Importes numéricos (el template aplica el formato)
    total_volumen = 0.0
    total_costo_import = 0.0
    brent_valor = None
    trm_valor = None
    generado_en = datetime.utcnow().strftime('%d/%m/%Y %H:%M:%S')
    generar_excel = 'si'
    component_data = []
    componentes_cols = [
        'USD/BBL CRUDO + FLETE Marino', 'Remolcador a CZF', 'USD/BBL Ingreso a CZF (Alm+OperPort 2)',
        'USD/BBL %FIN mes', 'USD/BBL Alm+OperPort 1', 'Nacionalización USD/BBL', 'USD/Bbl Exportación', 'Transp Terrestre a CZF'
    ]
    componentes_alias = [
        'CRUDO + FLETE', 'REMOLCADOR', 'INGRESO CZF', 'FINANCIACIÓN', 'ALM+OPER PORT', 'NACIONALIZACIÓN', 'EXPORTACIÓN', 'TRANSP TERRESTRE'
    ]
    component_stats = []
    ranking_spread_imp = []
    ranking_spread_exp = []
    if request.method == 'POST':
        generar_excel = request.form.get('generar_excel','si')
        try:
            excel_path = EXCEL_DEFAULT
            if 'archivo_excel' in request.files and request.files['archivo_excel'].filename:
                # Guardar temporalmente
                up_file = request.files['archivo_excel']
                tmp_path = os.path.join(BASE_DIR, 'upload_modelo_temp.xlsx')
                up_file.save(tmp_path)
                excel_path = tmp_path
            data = ejecutar_modelo(excel_path, generar_excel == 'si')
            resultados = data['resumen']
            grafico_base64 = data['grafico_base64']
            # Enviar valores crudos como números; el template se encarga del formato
            brent_valor = float(data['BRENT']) if data['BRENT'] is not None else None
            trm_valor = float(data.get('TRM')) if data.get('TRM') is not None else None
            total_volumen = float(sum(r['Volumen'] for r in resultados))
            total_costo_import = float(sum(r['CostoTotalImp'] for r in resultados))
            # Construir datos detallados para gráfica interactiva
            df_det = data['df_result']
            if not df_det.empty:
                # Incluimos 'Flete Marino' (valor total) para poder calcular USD/BBL en el tooltip
                extra_cols = ['Flete Marino'] if 'Flete Marino' in df_det.columns else []
                sub = df_det[['ID','Producto','Volumen Compra BBL','Puerto Llegada'] + extra_cols + componentes_cols].copy()
                for _, row in sub.iterrows():
                    comp_entry = {
                        'ID': row['ID'],
                        'Producto': row['Producto'],
                        'Volumen Compra BBL': float(row['Volumen Compra BBL'] or 0) if row['Volumen Compra BBL'] is not None else 0,
                        'Puerto Llegada': row['Puerto Llegada'] or ''
                    }
                    # Guardamos Flete Marino total para calcular USD/BBL en el frontend (si existe)
                    if 'Flete Marino' in row.index:
                        try:
                            comp_entry['Flete Marino'] = float(row['Flete Marino'] or 0)
                        except Exception:
                            comp_entry['Flete Marino'] = 0.0
                    for col in componentes_cols:
                        val = row[col]
                        try:
                            comp_entry[col] = float(val) if val is not None else 0.0
                        except Exception:
                            comp_entry[col] = 0.0
                    component_data.append(comp_entry)
                # Estadísticas comparativas por componente
                for alias, col in zip(componentes_alias, componentes_cols):
                    serie = df_det[col].astype(float).fillna(0)
                    component_stats.append({
                        'alias': alias,
                        'min': round(float(serie.min()),4),
                        'max': round(float(serie.max()),4),
                        'avg': round(float(serie.mean()),4)
                    })
                # Rankings spreads
                if 'Spread Total on Brent IMPORTACIONES' in df_det.columns:
                    ranking_spread_imp = (
                        df_det[['ID','Producto','Spread Total on Brent IMPORTACIONES']]
                        .rename(columns={'Spread Total on Brent IMPORTACIONES':'valor'})
                        .sort_values('valor', ascending=False)
                        .head(10)
                        .to_dict(orient='records')
                    )
                if 'Spread Exportaciones' in df_det.columns:
                    ranking_spread_exp = (
                        df_det[['ID','Producto','Spread Exportaciones']]
                        .rename(columns={'Spread Exportaciones':'valor'})
                        .sort_values('valor', ascending=False)
                        .head(10)
                        .to_dict(orient='records')
                    )
            if data['excel_bytes']:
                # Guardar en archivo temporal (no en sesión para evitar exceder tamaño cookie)
                from uuid import uuid4
                tmp_dir = os.path.join(BASE_DIR, 'tmp_modelo_excel')
                os.makedirs(tmp_dir, exist_ok=True)
                # Limpieza simple de archivos viejos (> 2 horas)
                try:
                    import time
                    now = time.time()
                    for fname in os.listdir(tmp_dir):
                        fpath = os.path.join(tmp_dir, fname)
                        if os.path.isfile(fpath) and now - os.path.getmtime(fpath) > 7200:
                            try: os.remove(fpath)
                            except Exception: pass
                except Exception:
                    pass
                filename = f"modelo_{uuid4().hex}.xlsx"
                file_path = os.path.join(tmp_dir, filename)
                with open(file_path, 'wb') as f:
                    f.write(data['excel_bytes'])
                session['modelo_excel_path'] = file_path
                excel_descargable = True
        except Exception as e:
            current_app.logger.error(f"Error modelo optimización: {e}")
            error = str(e)
    return render_template('modelo_optimizacion.html',
                           nombre=session.get('nombre'),
                           resultados=resultados,
                           grafico_base64=grafico_base64,
                           excel_descargable=excel_descargable,
                           total_volumen=total_volumen,
                           total_costo_import=total_costo_import,
                           brent_valor=brent_valor,
                           trm_valor=trm_valor,
                           generado_en=generado_en,
                           generar_excel=generar_excel,
                           component_data=component_data,
                           componentes_cols=componentes_cols,
                           componentes_alias=componentes_alias,
                           component_stats=component_stats,
                           ranking_spread_imp=ranking_spread_imp,
                           ranking_spread_exp=ranking_spread_exp,
                           error=error)

@login_required
@permiso_requerido('modelo_optimizacion')
@app.route('/modelo-optimizacion/descargar')
def descargar_resultado_modelo():
    allowed = {"felipe.delavega@conquerstrading.com", "finance@conquerstrading.com"}
    if session.get('rol') != 'admin' and session.get('email') not in allowed:
        flash('No tienes permiso para este módulo.', 'danger')
        return redirect(url_for('home'))
    file_path = session.get('modelo_excel_path')
    if not file_path or not os.path.isfile(file_path):
        flash('No hay archivo para descargar', 'warning')
        return redirect(url_for('modelo_optimizacion_page'))
    return send_file(file_path, as_attachment=True, download_name='Resultados_modelo.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

       
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
    observaciones_camiones = {} 
    camiones_para_mapa = []
    
    fecha_actualizacion_info = "No se encontraron registros de tránsito."
    
    try:
        todos_los_registros = db.session.query(RegistroTransito).order_by(RegistroTransito.timestamp.desc()).all()

        if not todos_los_registros:
            return render_template("reporte_transito.html", 
                                   datos_consolidados=datos_consolidados, 
                                   datos_conteo_camiones=datos_conteo_camiones,
                                   observaciones_camiones=observaciones_camiones,
                                   camiones_mapa=camiones_para_mapa,
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

            # --- AGREGADO: Poblar camiones_para_mapa para el mapa ---
            ciudad = ""
            if reg.observaciones and "|" in reg.observaciones:
                ciudad = reg.observaciones.split("|")[0].strip()
            elif reg.observaciones:
                ciudad = reg.observaciones.strip()
            camiones_para_mapa.append({
                "ciudad": ciudad,
                "tipo_transito": tipo_destino_reporte,
                "placa": reg.placa,
                "origen": reg.origen,
                "producto": reg.producto,
                "NSV": reg.nsv,
                "OBSERVACIONES": reg.observaciones
                
            })
            
    except Exception as e:
        app.logger.error(f"Error crítico al generar reporte de tránsito desde BD: {e}")
        flash(f"Ocurrió un error al generar el reporte: {e}", "danger")
        fecha_actualizacion_info = "Error al cargar los datos."

    return render_template("reporte_transito.html",
                           datos_consolidados=datos_consolidados,
                           datos_conteo_camiones=datos_conteo_camiones,
                           observaciones_camiones=observaciones_camiones,
                           camiones_mapa=camiones_para_mapa,
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

    # Ordenar los tanques CR según el orden de PLANILLA_BARCAZA_ORION
    def ordenar_por_planilla(lista, grupo, planilla):
        orden = [t["TK"] for t in planilla if t["grupo"] == grupo]
        return sorted([t for t in lista if t["grupo"] == grupo], key=lambda x: orden.index(x["TK"]) if x["TK"] in orden else 999)

    tanques_principales = [tk for tk in datos_para_plantilla if tk.get('grupo') == 'PRINCIPAL']
    tanques_man = [tk for tk in datos_para_plantilla if tk.get('grupo') == 'MANZANILLO']
    tanques_cr = ordenar_por_planilla(datos_para_plantilla, 'CR', PLANILLA_BARCAZA_ORION)
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
                           fecha_seleccionada=fecha_seleccionada.isoformat(),
                           today_iso=date.today().isoformat())

@app.cli.command("sync-orion")
def sync_orion_tanks():
    """
    Revisa la planilla por defecto de Orion y añade los tanques que falten en la base de datos.
    Este comando es seguro y no borra datos existentes.
    VERSIÓN CORREGIDA: Revisa la tupla (TK, grupo) para evitar conflictos.
    """
    try:
        # Obtenemos una lista de tuplas (tk, grupo) que ya existen en la base de datos
        tanques_existentes_tuplas = db.session.query(
            RegistroBarcazaOrion.tk, 
            RegistroBarcazaOrion.grupo
        ).distinct().all()
        
        # Convertimos la lista de tuplas a un set para búsquedas rápidas y eficientes
        set_tanques_db = set(tanques_existentes_tuplas)
        
        nuevos_tanques_agregados = 0
        
        # Iteramos sobre la lista de tanques que DEBERÍA existir (la de tu código)
        for tanque_plantilla in PLANILLA_BARCAZA_ORION:
            tk_plantilla = tanque_plantilla["TK"]
            grupo_plantilla = tanque_plantilla["grupo"]
            
            # Revisamos si la combinación (tk, grupo) NO está en nuestro set de la BD
            if (tk_plantilla, grupo_plantilla) not in set_tanques_db:
                print(f"Tanque '{tk_plantilla}' del grupo '{grupo_plantilla}' no encontrado. Añadiendo...")
                
                nuevo_registro = RegistroBarcazaOrion(
                    usuario="system_sync",
                    tk=tk_plantilla,
                    producto=tanque_plantilla["PRODUCTO"],
                    max_cap=tanque_plantilla["MAX_CAP"],
                    grupo=grupo_plantilla,
                    bls_60=None, api=None, bsw=None, s=None
                )
                db.session.add(nuevo_registro)
                nuevos_tanques_agregados += 1

        if nuevos_tanques_agregados > 0:
            db.session.commit()
            print(f"¡Éxito! Se han añadido {nuevos_tanques_agregados} tanques nuevos a la Barcaza Orion.")
        else:
            print("La base de datos ya está sincronizada. No se añadieron tanques nuevos.")
            
    except Exception as e:
        db.session.rollback()
        print(f"Ocurrió un error durante la sincronización: {e}")

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
    """
    Muestra la guía de transporte. Si recibe datos en la URL, los pasa a la plantilla
    para autocompletar el formulario. Si no, pasa datos vacíos.
    """
    # Creamos un diccionario para guardar los datos que vienen de la URL.
    # Usamos .get('nombre_parametro', '') para que, si un dato no llega, no de error.
    datos_guia = {
        'placa': request.args.get('placa', ''),
        'conductor': request.args.get('nombre_conductor', ''),
        'cedula': request.args.get('cedula_conductor', ''),
        'destino': request.args.get('destino', ''),
        'producto': request.args.get('producto_a_cargar', ''),
        'galones': request.args.get('galones', ''),
        'transportadora': request.args.get('empresa_transportadora', ''),
        'cliente': request.args.get('cliente', ''),
        'temperatura': request.args.get('temperatura', ''),
        'api_obs': request.args.get('api_obs', ''),
        'api_corregido': request.args.get('api_corregido', ''),
        'precintos': request.args.get('precintos', ''),
        # Campos adicionales para poblar "PLACA DEL TANQUE" desde Programación
        'tanque': request.args.get('tanque', ''),
        'placa_tanque': request.args.get('placa_tanque', '')
    }
    
    # Pasamos el diccionario 'datos_guia' a la plantilla HTML.
    return render_template(
        "guia_transporte.html", 
        nombre=session.get("nombre"),
        datos_guia=datos_guia
    )

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
    def ordenar_por_planilla(lista, grupo, planilla):
        orden = [t["TK"] for t in planilla if t["grupo"] == grupo]
        return sorted([t for t in lista if t["grupo"] == grupo], key=lambda x: orden.index(x["TK"]) if x["TK"] in orden else 999)

    if todos_los_tanques_lista:
        for grupo_key, nombre_barcaza in nombres_display.items():
            if grupo_key == "CR":
                tanques_ordenados = ordenar_por_planilla(todos_los_tanques_lista, "CR", PLANILLA_BARCAZA_ORION)
            else:
                tanques_ordenados = [t for t in todos_los_tanques_lista if t.get("grupo") == grupo_key]
            if tanques_ordenados:
                datos_para_template[nombre_barcaza] = {"tanques": tanques_ordenados, "totales": {}}
                datos_para_template[nombre_barcaza]["totales"] = calcular_estadisticas(tanques_ordenados)

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
        def to_float(v):
            if v is None:
                return None
            s = str(v).strip().replace(',', '.')
            if s == '':
                return None
            try:
                return float(s)
            except Exception:
                return None
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
                registro_existente.bls_60 = to_float(datos_tanque.get('BLS_60'))
                registro_existente.api = to_float(datos_tanque.get('API'))
                registro_existente.bsw = to_float(datos_tanque.get('BSW'))
                registro_existente.s = to_float(datos_tanque.get('S'))
                registro_existente.timestamp = datetime.utcnow()
            else:
                # CREAR
                nuevo_registro = RegistroBarcazaBita(
                    timestamp=datetime.utcnow(),
                    usuario=session.get("nombre", "No identificado"),
                    tk=tk,
                    producto=datos_tanque.get('PRODUCTO'),
                    max_cap=to_float(datos_tanque.get('MAX_CAP')),
                    bls_60=to_float(datos_tanque.get('BLS_60')),
                    api=to_float(datos_tanque.get('API')),
                    bsw=to_float(datos_tanque.get('BSW')),
                    s=to_float(datos_tanque.get('S'))
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
        def to_float(v):
            if v is None:
                return None
            s = str(v).strip().replace(',', '.')
            if s == '':
                return None
            try:
                return float(s)
            except Exception:
                return None
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
                registro_existente.bls_60 = to_float(datos_tanque.get('BLS_60'))
                registro_existente.api = to_float(datos_tanque.get('API'))
                registro_existente.bsw = to_float(datos_tanque.get('BSW'))
                registro_existente.s = to_float(datos_tanque.get('S'))
                registro_existente.timestamp = datetime.utcnow()
            else:
                # CREAR
                nuevo_registro = RegistroBarcazaOrion(
                    timestamp=datetime.utcnow(),
                    usuario=session.get("nombre", "No identificado"),
                    tk=tk,
                    grupo=grupo,
                    producto=datos_tanque.get('PRODUCTO'),
                    max_cap=to_float(datos_tanque.get('MAX_CAP')),
                    bls_60=to_float(datos_tanque.get('BLS_60')),
                    api=to_float(datos_tanque.get('API')),
                    bsw=to_float(datos_tanque.get('BSW')),
                    s=to_float(datos_tanque.get('S'))
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

    # --- Construcción de ALERTAS ÚTILES ---
    alerts = []  # Cada alerta: {severity, category, message, icon}

    def add_alert(severity, category, message):
        icon_map = {
            'danger': 'exclamation-octagon-fill',
            'warning': 'exclamation-triangle-fill',
            'info': 'info-circle-fill',
            'success': 'check-circle-fill'
        }
        alerts.append({
            'severity': severity,
            'category': category,
            'message': message,
            'icon': icon_map.get(severity, 'info-circle')
        })

    now_utc = datetime.utcnow()

    # Helper para obtener último por clave (tk) de una lista de registros con timestamp
    def latest_by(records, attr):
        latest = {}
        for r in records:
            key = getattr(r, attr, None)
            if key is None:
                continue
            cur = latest.get(key)
            if not cur or r.timestamp > cur.timestamp:
                latest[key] = r
        return list(latest.values())

    # Planta: niveles bajos / altos y desactualización
    try:
        if planta_summary['datos']:
            latest_tanques = latest_by(planta_summary['datos'], 'tk')
            low, high = [], []
            for r in latest_tanques:
                if r.max_cap and r.bls_60 is not None:
                    try:
                        pct = (float(r.bls_60) / float(r.max_cap)) * 100 if r.max_cap else None
                    except Exception:
                        pct = None
                    if pct is not None:
                        if pct < 15:
                            low.append((r.tk, pct))
                        elif pct > 90:
                            high.append((r.tk, pct))
            if low:
                detalle = ', '.join(f"{tk}:{pct:.1f}%" for tk, pct in low[:4])
                add_alert('warning', 'PLANTA', f'Tanques con nivel bajo (<15%): {detalle}' + (' ...' if len(low) > 4 else ''))
            if high:
                detalle = ', '.join(f"{tk}:{pct:.1f}%" for tk, pct in high[:4])
                add_alert('info', 'PLANTA', f'Tanques con nivel alto (>90%): {detalle}' + (' ...' if len(high) > 4 else ''))
            # Staleness (último update > 24h)
            ultimo = max(planta_summary['datos'], key=lambda r: r.timestamp)
            if (now_utc - ultimo.timestamp).total_seconds() > 24*3600:
                add_alert('danger', 'PLANTA', 'Inventario sin actualización en las últimas 24 horas.')
        else:
            add_alert('info', 'PLANTA', 'Sin registros de inventario disponibles.')
    except Exception:
        add_alert('warning', 'PLANTA', 'Error evaluando niveles de planta.')

    # Barcaza Orion / BITA: evaluar porcentaje total consolidado y staleness (>36h)
    for summary, categoria in [
        (orion_summary, 'ORION'),
        (bita_summary, 'BITA')
    ]:
        try:
            if summary['datos']:
                latest_tanques = latest_by(summary['datos'], 'tk')
                total_cap = 0.0
                total_bls = 0.0
                for r in latest_tanques:
                    try:
                        cap = float(r.max_cap) if r.max_cap is not None else 0
                        bls = float(r.bls_60) if r.bls_60 is not None else 0
                    except Exception:
                        cap, bls = 0, 0
                    total_cap += cap
                    total_bls += bls
                pct_total = (total_bls / total_cap * 100) if total_cap > 0 else None
                if pct_total is not None:
                    if pct_total < 10:
                        add_alert('danger', categoria, f'Nivel crítico {pct_total:.1f}% (<10%).')
                    elif pct_total < 15:
                        add_alert('warning', categoria, f'Nivel consolidado bajo {pct_total:.1f}% (<15%).')
                    elif pct_total > 90:
                        add_alert('info', categoria, f'Nivel alto {pct_total:.1f}% (>90%).')
                ultimo = max(summary['datos'], key=lambda r: r.timestamp)
                if (now_utc - ultimo.timestamp).total_seconds() > 36*3600:
                    add_alert('danger', categoria, 'Sin actualización en las últimas 36 horas.')
            else:
                add_alert('info', categoria, 'Sin registros cargados.')
        except Exception:
            add_alert('warning', categoria, 'Error evaluando niveles consolidados.')

    # Tránsito: registros incompletos últimas 24h y volumen de actividad
    try:
        if transito_summary['datos']:
            recientes = [r for r in transito_summary['datos'] if (now_utc - r.timestamp).total_seconds() <= 24*3600]
            if recientes:
                incompletos = [r for r in recientes if r.api is None or r.bsw is None or r.nsv is None]
                if incompletos:
                    add_alert('warning', 'TRANSITO', f'Registros incompletos últimas 24h: {len(incompletos)} (API/BSW/NSV faltantes).')
                # Actividad baja: menos de 3 registros 24h
                if len(recientes) < 3:
                    add_alert('info', 'TRANSITO', 'Baja actividad en las últimas 24 horas.')
            else:
                add_alert('info', 'TRANSITO', 'Sin movimientos registrados en las últimas 24 horas.')
            ultimo = max(transito_summary['datos'], key=lambda r: r.timestamp)
            if (now_utc - ultimo.timestamp).total_seconds() > 48*3600:
                add_alert('danger', 'TRANSITO', 'Sin actualización en más de 48 horas.')
        else:
            add_alert('info', 'TRANSITO', 'Sin registros de tránsito disponibles.')
    except Exception:
        add_alert('warning', 'TRANSITO', 'Error evaluando registros de tránsito.')

    # Ordenar alertas por severidad importancia
    severity_rank = {'danger': 0, 'warning': 1, 'info': 2, 'success': 3}
    alerts.sort(key=lambda a: severity_rank.get(a['severity'], 99))

    # --- Renderizar la plantilla ---
    return render_template("dashboard_reportes.html",
                           nombre=session.get("nombre"),
                           planta_summary=planta_summary,
                           orion_summary=orion_summary,
                           bita_summary=bita_summary,
                           transito_summary=transito_summary,
                           alerts=alerts)

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
        def to_float(v):
            if v is None:
                return None
            s = str(v).strip().replace(',', '.')
            if s == '':
                return None
            try:
                return float(s)
            except Exception:
                return None
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
                registro_existente.bls_60 = to_float(datos_tanque.get('BLS_60'))
                registro_existente.api = to_float(datos_tanque.get('API'))
                registro_existente.bsw = to_float(datos_tanque.get('BSW'))
                registro_existente.s = to_float(datos_tanque.get('S'))
                registro_existente.timestamp = datetime.utcnow()
            else:
                # Si no existe para hoy, CREAMOS uno nuevo
                nuevo_registro = RegistroPlanta(
                    timestamp=datetime.utcnow(),
                    usuario=session.get("nombre", "No identificado"),
                    tk=tk,
                    producto=datos_tanque.get('PRODUCTO'),
                    max_cap=to_float(datos_tanque.get('MAX_CAP')),
                    bls_60=to_float(datos_tanque.get('BLS_60')),
                    api=to_float(datos_tanque.get('API')),
                    bsw=to_float(datos_tanque.get('BSW')),
                    s=to_float(datos_tanque.get('S'))
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

    # --- Lógica para Variaciones de Tanques (serie diaria) ---
    elif nombre_reporte == 'variaciones':
        start_dt = None
        end_dt = None
        try:
            if filtro_tipo == 'dia' and valor:
                d = date.fromisoformat(valor)
                start_dt = datetime.combine(d, time.min)
                end_dt = datetime.combine(d, time.max)
            elif filtro_tipo == 'mes' and valor:
                ano, mes = map(int, valor.split('-'))
                ini = date(ano, mes, 1)
                fin = (ini + timedelta(days=32)).replace(day=1) - timedelta(days=1)
                start_dt = datetime.combine(ini, time.min)
                end_dt = datetime.combine(fin, time.max)
            elif filtro_tipo == 'trimestre' and valor:
                ano_str, q_str = valor.split('-Q')
                ano, trimestre = int(ano_str), int(q_str)
                mes_ini = (trimestre - 1) * 3 + 1
                mes_fin = trimestre * 3
                ini = date(ano, mes_ini, 1)
                fin = (date(ano, mes_fin, 1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
                start_dt = datetime.combine(ini, time.min)
                end_dt = datetime.combine(fin, time.max)
            elif filtro_tipo == 'anual' and valor:
                ano = int(valor)
                ini = date(ano, 1, 1)
                fin = date(ano, 12, 31)
                start_dt = datetime.combine(ini, time.min)
                end_dt = datetime.combine(fin, time.max)
        except Exception:
            start_dt = None
            end_dt = None

        fecha_dia = func.date(RegistroPlanta.timestamp)
        subq = db.session.query(func.max(RegistroPlanta.id).label('max_id'))
        if start_dt:
            subq = subq.filter(RegistroPlanta.timestamp >= start_dt)
        if end_dt:
            subq = subq.filter(RegistroPlanta.timestamp <= end_dt)
        subq = subq.group_by(RegistroPlanta.tk, fecha_dia).subquery()

        registros_series = (db.session.query(RegistroPlanta)
                            .filter(RegistroPlanta.id.in_(subq))
                            .order_by(RegistroPlanta.tk.asc(), RegistroPlanta.timestamp.asc())
                            .all())

        # Organizar por tanque y fecha y calcular variaciones
        por_tanque = {}
        for r in registros_series:
            if not r.tk:
                continue
            dia = r.timestamp.date()
            por_tanque.setdefault(r.tk, []).append({
                'fecha': dia.isoformat(),
                'producto': r.producto or '',
                'max_cap': float(r.max_cap or 0),
                'bls_60': float(r.bls_60 or 0)
            })

        filas = []
        for tk, lista in por_tanque.items():
            lista.sort(key=lambda x: x['fecha'])
            prev = None
            for item in lista:
                bls = item['bls_60']
                delta = None if prev is None else round(bls - prev, 2)
                filas.append({
                    'fecha': item['fecha'],
                    'tk': tk,
                    'producto': item['producto'],
                    'max_cap': item['max_cap'],
                    'bls_60': bls,
                    'variacion': delta
                })
                prev = bls

        if not filas:
            flash("No hay datos para exportar con el filtro seleccionado.", "warning")
            return redirect(request.referrer or url_for('reporte_variaciones_tanques'))

        registros = filas
        columnas = ["fecha", "tk", "producto", "max_cap", "bls_60", "variacion"]

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
@app.route('/descargar-reporte-variaciones-pdf')
def descargar_reporte_variaciones_pdf():
    filtro_tipo = request.args.get('filtro_tipo', 'mes')
    valor = request.args.get('valor')

    # Determinar rango
    start_dt = None
    end_dt = None
    periodo_str = "General"
    try:
        if filtro_tipo == 'dia' and valor:
            d = date.fromisoformat(valor)
            start_dt = datetime.combine(d, time.min)
            end_dt = datetime.combine(d, time.max)
            periodo_str = f"del día {d.strftime('%d/%m/%Y')}"
        elif filtro_tipo == 'mes' and valor:
            ano, mes = map(int, valor.split('-'))
            ini = date(ano, mes, 1)
            fin = (ini + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            start_dt = datetime.combine(ini, time.min)
            end_dt = datetime.combine(fin, time.max)
            periodo_str = f"del mes de {ini.strftime('%B de %Y')}"
        elif filtro_tipo == 'trimestre' and valor:
            ano_str, q_str = valor.split('-Q')
            ano, trimestre = int(ano_str), int(q_str)
            mes_ini = (trimestre - 1) * 3 + 1
            mes_fin = trimestre * 3
            ini = date(ano, mes_ini, 1)
            fin = (date(ano, mes_fin, 1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            start_dt = datetime.combine(ini, time.min)
            end_dt = datetime.combine(fin, time.max)
            periodo_str = f"del Trimestre {trimestre} de {ano}"
        elif filtro_tipo == 'anual' and valor:
            ano = int(valor)
            ini = date(ano, 1, 1)
            fin = date(ano, 12, 31)
            start_dt = datetime.combine(ini, time.min)
            end_dt = datetime.combine(fin, time.max)
            periodo_str = f"del Año {ano}"
    except Exception:
        start_dt = None
        end_dt = None

    # Query: último registro por día y tanque dentro del rango
    fecha_dia = func.date(RegistroPlanta.timestamp)
    subq = db.session.query(func.max(RegistroPlanta.id).label('max_id'))
    if start_dt:
        subq = subq.filter(RegistroPlanta.timestamp >= start_dt)
    if end_dt:
        subq = subq.filter(RegistroPlanta.timestamp <= end_dt)
    subq = subq.group_by(RegistroPlanta.tk, fecha_dia).subquery()

    registros_series = (db.session.query(RegistroPlanta)
                        .filter(RegistroPlanta.id.in_(subq))
                        .order_by(RegistroPlanta.tk.asc(), RegistroPlanta.timestamp.asc())
                        .all())

    if not registros_series:
        flash("No hay datos para generar el PDF con el filtro seleccionado.", "warning")
        return redirect(url_for('reporte_variaciones_tanques'))

    # Organizar por tanque y calcular deltas
    por_tanque = {}
    for r in registros_series:
        tk = r.tk
        if not tk:
            continue
        dia = r.timestamp.date().isoformat()
        por_tanque.setdefault(tk, []).append({
            'fecha': dia,
            'producto': r.producto or '',
            'max_cap': float(r.max_cap or 0),
            'bls_60': float(r.bls_60 or 0)
        })

    for tk in list(por_tanque.keys()):
        por_tanque[tk].sort(key=lambda x: x['fecha'])
        prev = None
        for item in por_tanque[tk]:
            bls = item['bls_60']
            item['variacion'] = None if prev is None else round(bls - prev, 2)
            if item['variacion'] is None:
                item['tipo'] = '—'
            elif item['variacion'] > 0:
                item['tipo'] = 'Suma'
            elif item['variacion'] < 0:
                item['tipo'] = 'Descarga'
            else:
                item['tipo'] = 'Sin cambio'
            prev = bls

    # Orden sugerido
    orden = ['TK-109','TK-110','TK-102','TK-01','TK-02']
    tanques_ordenados = sorted(por_tanque.keys(), key=lambda k: (orden.index(k) if k in orden else 999, k))

    # Calcular estadísticas por tanque y globales
    stats_por_tanque = {}
    total_bls = 0.0
    total_suma = 0.0
    total_descarga = 0.0
    for tk in tanques_ordenados:
        lista = por_tanque.get(tk, [])
        if not lista:
            continue
        last_bls = float(lista[-1].get('bls_60') or 0)
        producto = next((it.get('producto') for it in lista if (it.get('producto') or '').strip()), '')
        cap = next((float(it.get('max_cap') or 0) for it in lista if float(it.get('max_cap') or 0) > 0), 0.0)
        suma = 0.0
        descarga = 0.0
        for it in lista:
            v = it.get('variacion')
            if isinstance(v, (int, float)):
                if v > 0: suma += v
                elif v < 0: descarga += abs(v)
        stats_por_tanque[tk] = {
            'producto': producto,
            'max_cap': cap,
            'last_bls': last_bls,
            'suma': round(suma, 2),
            'descarga': round(descarga, 2)
        }
        total_bls += last_bls
        total_suma += suma
        total_descarga += descarga

    resumen_global = {
        'total_tanques': len(tanques_ordenados),
        'total_bls': round(total_bls, 2),
        'total_suma': round(total_suma, 2),
        'total_descarga': round(total_descarga, 2)
    }

    # Generar gráficos (Matplotlib) para cada tanque con estilo y etiquetas de volumen
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import io, base64
    charts_map = {}
    for tk in tanques_ordenados:
        lista = por_tanque.get(tk, [])
        if not lista:
            continue
        fechas = [it['fecha'] for it in lista]
        bls = [float(it['bls_60'] or 0) for it in lista]
        cap = next((float(it.get('max_cap') or 0) for it in lista if float(it.get('max_cap') or 0) > 0), 0.0)
        # Usar eje categórico controlado para poder anotar fácilmente
        xs = list(range(len(fechas)))
        fig, ax = plt.subplots(figsize=(8.5, 3.3))
        fig.patch.set_facecolor('white')
        ax.set_facecolor('#f8fafc')
        # Línea principal estilo "despachos"
        ax.plot(xs, bls, color='#4e73df', linewidth=2, marker='o', markersize=3.5,
                markerfacecolor='#4e73df', markeredgecolor='white', markeredgewidth=0.8)
        if cap and cap > 0:
            ax.plot(xs, [cap]*len(xs), color='#6c757d', linestyle='--', linewidth=1)
        # Ejes y grid
        ax.set_xlabel('Fecha', color='#6c757d', fontsize=9)
        ax.set_ylabel('BLS @60', color='#6c757d', fontsize=9)
        ax.grid(True, axis='y', linestyle=':', color='#bfc7d1', alpha=0.6)
        for spine in ax.spines.values():
            spine.set_color('#e0e5ec')
        ax.tick_params(axis='x', colors='#6c757d', labelsize=8)
        ax.tick_params(axis='y', colors='#6c757d', labelsize=8)
        ax.set_xticks(xs)
        ax.set_xticklabels(fechas, rotation=45, ha='right')
        # Etiquetas de volumen sobre cada punto
        for i, y in enumerate(bls):
            try:
                label = f"{int(round(y)):,}".replace(',', '.')
            except Exception:
                label = f"{y:.0f}"
            ax.annotate(label, (xs[i], y), textcoords='offset points', xytext=(0, 6),
                        ha='center', va='bottom', fontsize=7.5, color='#224abe',
                        bbox=dict(boxstyle='round,pad=0.18', fc='white', ec='none', alpha=0.85))
        plt.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150)
        plt.close(fig)
        buf.seek(0)
        charts_map[tk] = base64.b64encode(buf.read()).decode('utf-8')

    # Cargar logo corporativo (opcional)
    logo_base64 = None
    logo_mime = 'image/jpeg'
    try:
        logo_candidates = ['Logo_de_empresa.jpeg', 'Conquers_4_Logo.png', 'logo.jpeg']
        for fname in logo_candidates:
            logo_path = os.path.join(current_app.root_path, 'static', fname)
            if os.path.exists(logo_path):
                import base64 as _b64
                with open(logo_path, 'rb') as f:
                    logo_base64 = _b64.b64encode(f.read()).decode('utf-8')
                if fname.lower().endswith('.png'):
                    logo_mime = 'image/png'
                break
    except Exception:
        logo_base64 = None

    # Renderizar plantilla PDF con estilo tipo despachos
    html_para_pdf = render_template('reportes_pdf/variaciones_tanques_pdf.html',
                                    por_tanque=por_tanque,
                                    tanques_ordenados=tanques_ordenados,
                                    charts_map=charts_map,
                                    stats_por_tanque=stats_por_tanque,
                                    resumen_global=resumen_global,
                                    logo_base64=logo_base64,
                                    logo_mime=logo_mime,
                                    periodo_str=periodo_str,
                                    fecha_generacion=datetime.now().strftime('%d/%m/%Y %H:%M'))

    pdf = HTML(string=html_para_pdf, base_url=current_app.root_path).write_pdf()
    return Response(pdf,
                  mimetype='application/pdf',
                  headers={'Content-Disposition': 'attachment;filename=reporte_variaciones_tanques.pdf'})

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

    # ===== HISTORIAL SEGÚN FILTRO =====
    # Determinar rango de fechas para el historial (inicio y fin) según filtro_tipo y valor
    start_dt = None
    end_dt = None
    try:
        if valor:
            if filtro_tipo == 'dia':
                fecha_obj = date.fromisoformat(valor)
                start_dt = datetime.combine(fecha_obj, time.min)
                end_dt = datetime.combine(fecha_obj, time.max)
            elif filtro_tipo == 'mes':
                ano, mes = map(int, valor.split('-'))
                fecha_ini = date(ano, mes, 1)
                fecha_fin = (fecha_ini + timedelta(days=32)).replace(day=1) - timedelta(days=1)
                start_dt = datetime.combine(fecha_ini, time.min)
                end_dt = datetime.combine(fecha_fin, time.max)
            elif filtro_tipo == 'trimestre':
                ano_str, q_str = valor.split('-Q')
                ano = int(ano_str)
                trimestre = int(q_str)
                mes_ini = (trimestre - 1) * 3 + 1
                mes_fin = trimestre * 3
                fecha_ini = date(ano, mes_ini, 1)
                fecha_fin = (date(ano, mes_fin, 1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
                start_dt = datetime.combine(fecha_ini, time.min)
                end_dt = datetime.combine(fecha_fin, time.max)
            elif filtro_tipo == 'anual':
                ano = int(valor)
                fecha_ini = date(ano, 1, 1)
                fecha_fin = date(ano, 12, 31)
                start_dt = datetime.combine(fecha_ini, time.min)
                end_dt = datetime.combine(fecha_fin, time.max)
        # Si no se especifica filtro, se considera todo el histórico (start_dt permanece None)
    except Exception:
        # En caso de error en parsing, ignorar y no limitar historial
        start_dt = None
        end_dt = None

    historial_query = db.session.query(RegistroPlanta)
    if end_dt:
        historial_query = historial_query.filter(RegistroPlanta.timestamp <= end_dt)
    if start_dt:
        historial_query = historial_query.filter(RegistroPlanta.timestamp >= start_dt)

    historial_db = (historial_query
                     .order_by(RegistroPlanta.timestamp.desc(), RegistroPlanta.tk.asc())
                     .all())

    historial_registros = [
        {
            'fecha': r.timestamp.strftime('%Y-%m-%d %H:%M'),
            'tk': r.tk,
            'producto': r.producto,
            'bls_60': r.bls_60 or 0.0,
            'api': r.api or 0.0,
            'bsw': r.bsw or 0.0,
            's': r.s or 0.0,
            'usuario': r.usuario
        }
        for r in historial_db
    ]

    # Agrupación por fecha (día) para mostrar un cuadro por fecha
    from collections import OrderedDict
    grupos = OrderedDict()
    for item in historial_registros:
        dia = item['fecha'][:10]  # 'YYYY-MM-DD'
        if dia not in grupos:
            grupos[dia] = []
        grupos[dia].append(item)
    # Construir lista ordenada (ya viene en orden descendente por timestamp)
    historial_grouped = []
    for dia, regs in grupos.items():
        historial_grouped.append({
            'dia': dia,
            'registros': regs
        })

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

    # Totales para badges (estilo similar a reporte gráfico despachos)
    total_bls = sum(r['bls_60'] for r in registros_limpios)
    total_cap = sum(r['max_cap'] for r in registros_limpios)

    # Cargar logo como base64
    logo_base64 = None
    try:
        logo_candidates = ['Logo_de_empresa.jpeg', 'Conquers_4_Logo.png', 'logo.jpeg']
        for fname in logo_candidates:
            logo_path = os.path.join(current_app.root_path, 'static', fname)
            if os.path.exists(logo_path):
                import base64
                with open(logo_path, 'rb') as f:
                    logo_base64 = base64.b64encode(f.read()).decode('utf-8')
                break
    except Exception as e:
        print(f"Error cargando logo para planta PDF: {e}")

    html_para_pdf = render_template('reportes_pdf/planta_pdf.html',
                                    registros=registros_limpios,
                                    historial=historial_registros,
                                    historial_grouped=historial_grouped,
                                    fecha_reporte=fecha_reporte_str,
                                    total_bls=total_bls,
                                    total_cap=total_cap,
                                    logo_base64=logo_base64,
                                    fecha_generacion=datetime.now().strftime('%d/%m/%Y %H:%M'))
    
    pdf = HTML(string=html_para_pdf, base_url=current_app.root_path).write_pdf()
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
    # ===== Historial Orion (agrupado por día) =====
    historial_query = db.session.query(RegistroBarcazaOrion)
    historial_query = historial_query.filter(RegistroBarcazaOrion.timestamp <= timestamp_limite)
    historial_db = historial_query.order_by(RegistroBarcazaOrion.timestamp.desc(), RegistroBarcazaOrion.tk.asc()).all()
    historial_registros = [
        {
            'fecha': r.timestamp.strftime('%Y-%m-%d %H:%M'),
            'tk': r.tk,
            'producto': r.producto,
            'bls_60': r.bls_60 or 0.0,
            'api': r.api or 0.0,
            'bsw': r.bsw or 0.0,
            's': r.s or 0.0,
            'usuario': r.usuario,
            'grupo': r.grupo
        } for r in historial_db
    ]
    from collections import OrderedDict
    grupos = OrderedDict()
    for item in historial_registros:
        dia = item['fecha'][:10]
        if dia not in grupos:
            grupos[dia] = []
        grupos[dia].append(item)
    historial_grouped = [{'dia': dia, 'registros': regs} for dia, regs in grupos.items()]

    # Cargar logo base64 (mismo método que planta)
    logo_base64 = None
    try:
        logo_candidates = ['Logo_de_empresa.jpeg', 'Conquers_4_Logo.png', 'logo.jpeg']
        for fname in logo_candidates:
            logo_path = os.path.join(current_app.root_path, 'static', fname)
            if os.path.exists(logo_path):
                import base64 as _b64
                with open(logo_path, 'rb') as f:
                    logo_base64 = _b64.b64encode(f.read()).decode('utf-8')
                break
    except Exception as e:
        print(f"Error cargando logo Orion PDF: {e}")

    html_para_pdf = render_template('reportes_pdf/orion_pdf.html',
                                    historial_grouped=historial_grouped,
                                    fecha_reporte=fecha_seleccionada.strftime('%d de %B de %Y'),
                                    logo_base64=logo_base64,
                                    fecha_generacion=datetime.now().strftime('%d/%m/%Y %H:%M'))
    
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
    # ===== Historial BITA (agrupado por día) =====
    historial_query = db.session.query(RegistroBarcazaBita)
    if timestamp_limite:
        historial_query = historial_query.filter(RegistroBarcazaBita.timestamp <= timestamp_limite)
    historial_db = historial_query.order_by(RegistroBarcazaBita.timestamp.desc(), RegistroBarcazaBita.tk.asc()).all()
    historial_registros = [
        {
            'fecha': r.timestamp.strftime('%Y-%m-%d %H:%M'),
            'tk': r.tk,
            'producto': r.producto,
            'bls_60': r.bls_60 or 0.0,
            'api': r.api or 0.0,
            'bsw': r.bsw or 0.0,
            's': r.s or 0.0,
            'usuario': r.usuario
        } for r in historial_db
    ]
    from collections import OrderedDict
    grupos_bita = OrderedDict()
    for item in historial_registros:
        dia = item['fecha'][:10]
        if dia not in grupos_bita:
            grupos_bita[dia] = []
        grupos_bita[dia].append(item)
    historial_grouped = [{'dia': dia, 'registros': regs} for dia, regs in grupos_bita.items()]

    # Cargar logo base64 para BITA
    logo_base64 = None
    try:
        logo_candidates = ['Logo_de_empresa.jpeg', 'Conquers_4_Logo.png', 'logo.jpeg']
        for fname in logo_candidates:
            logo_path = os.path.join(current_app.root_path, 'static', fname)
            if os.path.exists(logo_path):
                import base64 as _b64
                with open(logo_path, 'rb') as f:
                    logo_base64 = _b64.b64encode(f.read()).decode('utf-8')
                break
    except Exception as e:
        print(f"Error cargando logo BITA PDF: {e}")

    html_para_pdf = render_template('reportes_pdf/bita_pdf.html',
                                    historial_grouped=historial_grouped,
                                    fecha_reporte=fecha_reporte_str,
                                    logo_base64=logo_base64,
                                    fecha_generacion=datetime.now().strftime('%d/%m/%Y %H:%M'))

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
@app.route('/inicio-simulador')
def home_simulador():
    """Página de inicio para el área del simulador."""
    return render_template('home_simulador.html')

@login_required
@permiso_requerido('simulador_rendimiento')
@app.route('/simulador_rendimiento')
def simulador_rendimiento():
    """
    Renderiza la página del Simulador de Rendimiento de Crudo.
    """
    return render_template('simulador_rendimiento.html', nombre=session.get("nombre"))

@login_required
@permiso_requerido('simulador_rendimiento')
@app.route('/descargar_reporte_mezcla_pdf', methods=['POST'])
def descargar_reporte_mezcla_pdf():
    """Genera un PDF del reporte de mezcla de crudos con el mismo estilo visual que
    el reporte gráfico de despachos. Espera un JSON con la estructura:
    {
        total_barrels: number,
        products: { PROD: { barrels, yield_pct, api, sulfur }, ... },
        components: [ { name, mixture_volume, barrels_by_product, api_by_product, sulfur_by_product, total_barrels_input }, ... ]
    }
    """
    try:
        payload = request.get_json(silent=True) or {}
        total_barrels = float(payload.get('total_barrels') or 0)
        products_map = payload.get('products') or {}
        components = payload.get('components') or []
        # Orden de productos (mantener orden estable)
        product_names = list(products_map.keys())
        # Preparar filas para tabla resumen de mezcla
        mezcla_product_rows = []
        for prod in product_names:
            info = products_map.get(prod, {})
            mezcla_product_rows.append({
                'producto': prod,
                'yield_pct': info.get('yield_pct', 0),
                'barrels': info.get('barrels', 0),
                'api': info.get('api', 0),
                'sulfur': info.get('sulfur', 0)
            })
        # Mapa rápido de mezcla por producto
        mezcla_map = {r['producto']: r for r in mezcla_product_rows}
        # API y azufre global de la mezcla (ponderado por barriles, API con SG)
        try:
            sg_total = 0.0; vol_total_products = 0.0; sulfur_total = 0.0
            for r in mezcla_product_rows:
                bbl = float(r['barrels'] or 0)
                api_p = float(r['api'] or 0)
                sg = 141.5 / (api_p + 131.5) if (api_p + 131.5) != 0 else 0
                sg_total += sg * bbl
                vol_total_products += bbl
                sulfur_total += (float(r['sulfur'] or 0) * bbl)
            mezcla_overall_api = ( (141.5 / (sg_total / vol_total_products)) - 131.5 ) if vol_total_products > 0 and sg_total>0 else 0
            mezcla_overall_sulfur = (sulfur_total / vol_total_products) if vol_total_products>0 else 0
        except Exception:
            mezcla_overall_api = 0
            mezcla_overall_sulfur = 0
        # Preparar tabla de componentes (por crudo y por producto)
        componente_rows = []
        # Para comparativo por crudo con/sin KERO, agrupamos por base_crude
        comparativo_por_crudo = {}
        for comp in components:
            row = {
                'name': comp.get('name') or comp.get('nombre') or 'CRUDO',
                'total_volume': comp.get('mixture_volume') or 0,
                'productos': []
            }
            # Añadir temperaturas de corte si vienen desde el front (pueden faltar si eran antiguas corridas)
            cp = comp.get('cut_points') or comp.get('cutPoints') or {}
            try:
                row['cut_points'] = {
                    'nafta': cp.get('nafta'),
                    'kero': cp.get('kero'),
                    'fo4': cp.get('fo4')
                }
            except Exception:
                row['cut_points'] = {'nafta': None, 'kero': None, 'fo4': None}
            barrels_by_product = comp.get('barrels_by_product') or {}
            api_by_product = comp.get('api_by_product') or {}
            sulfur_by_product = comp.get('sulfur_by_product') or {}
            total_volume = float(row['total_volume'] or 0) or 0
            # variables para overall
            sg_sum_comp = 0.0; sulfur_sum_comp = 0.0
            for prod in product_names:
                base_bbl = float(barrels_by_product.get(prod, 0) or 0)
                total_input = float(comp.get('total_barrels_input') or 0) or 1
                # Escala a volumen de mezcla real
                scale = (row['total_volume'] / total_input) if total_input > 0 else 0
                bbl_scaled = base_bbl * scale
                pct = (bbl_scaled / row['total_volume'] * 100) if row['total_volume'] else 0
                api_p = api_by_product.get(prod, 0) or 0
                sulfur_p = sulfur_by_product.get(prod, 0) or 0
                # acumular para overall
                if bbl_scaled>0 and (api_p + 131.5)!=0:
                    sg_sum_comp += (141.5/(api_p+131.5)) * bbl_scaled
                sulfur_sum_comp += sulfur_p * bbl_scaled
                row['productos'].append({
                    'yield_pct': pct,
                    'barrels': bbl_scaled,
                    'api': api_p,
                    'sulfur': sulfur_p,
                    'delta_yield_pct': pct - (mezcla_map.get(prod, {}).get('yield_pct', 0)),
                    'delta_api': api_p - (mezcla_map.get(prod, {}).get('api', 0)),
                    'delta_sulfur': sulfur_p - (mezcla_map.get(prod, {}).get('sulfur', 0))
                })
            # overall metrics component
            if total_volume>0 and sg_sum_comp>0:
                overall_api_comp = (141.5 / (sg_sum_comp / total_volume)) - 131.5
            else:
                overall_api_comp = 0
            overall_sulfur_comp = (sulfur_sum_comp / total_volume) if total_volume>0 else 0
            row['overall_api'] = overall_api_comp
            row['overall_sulfur'] = overall_sulfur_comp
            row['delta_overall_api'] = overall_api_comp - mezcla_overall_api
            row['delta_overall_sulfur'] = overall_sulfur_comp - mezcla_overall_sulfur
            componente_rows.append(row)

            # --- Construcción de comparativo por crudo (con/sin KERO) ---
            try:
                base_name = (comp.get('base_crude') or comp.get('name') or comp.get('nombre') or '').strip()
                inc_kero = bool(comp.get('include_kero'))
                if base_name:
                    grp = comparativo_por_crudo.setdefault(base_name, {'con': None, 'sin': None})
                    # Guardamos rendimientos (%) por producto de este componente
                    rend = {p: 0 for p in product_names}
                    for i, p in enumerate(product_names):
                        try:
                            rend[p] = float(row['productos'][i]['yield_pct'] or 0)
                        except Exception:
                            rend[p] = 0
                    # Guardamos una versión compacta
                    compact = {
                        'name': row['name'],
                        'order': product_names,
                        'yields_pct': rend,
                        'api_by_product': {p: float(api_by_product.get(p, 0) or 0) for p in product_names}
                    }
                    if inc_kero:
                        grp['con'] = compact
                    else:
                        grp['sin'] = compact
            except Exception:
                pass
        # Logo base64 (igual estilo al reporte de despachos)
        logo_base64 = None
        try:
            logo_path = os.path.join(current_app.root_path, 'static', 'Logo_de_empresa.jpeg')
            if os.path.exists(logo_path):
                with open(logo_path, 'rb') as f:
                    logo_base64 = base64.b64encode(f.read()).decode('utf-8')
        except Exception:
            logo_base64 = None
        html_para_pdf = render_template(
            'reportes_pdf/reporte_mezcla_crudos_pdf.html',
            total_barrels=total_barrels,
            mezcla_product_rows=mezcla_product_rows,
            producto_headers=product_names,
            componente_rows=componente_rows,
            mezcla_overall_api=mezcla_overall_api,
            mezcla_overall_sulfur=mezcla_overall_sulfur,
            comparativo_por_crudo=comparativo_por_crudo,
            fecha_generacion=datetime.now().strftime('%d/%m/%Y %H:%M'),
            logo_base64=logo_base64
        )
        pdf = HTML(string=html_para_pdf, base_url=current_app.root_path).write_pdf()
        return Response(pdf, mimetype='application/pdf', headers={'Content-Disposition':'attachment;filename=reporte_mezcla_crudos.pdf'})
    except Exception as e:
        current_app.logger.error(f"Error generando PDF mezcla: {e}")
        return jsonify(success=False, message='Error generando PDF'), 500

@login_required
@permiso_requerido('simulador_rendimiento')
@app.route('/descargar_comparativo_kero_pdf', methods=['POST'])
def descargar_comparativo_kero_pdf():
    """Genera un PDF comparativo Con vs Sin KERO por crudo.
    Espera JSON: { resultados: [ { base_crude, include_kero, order:[], yields:{}, api_by_product:{}, sulfur_by_product:{} }, ... ] }"""
    try:
        data = request.get_json(silent=True) or {}
        resultados = data.get('resultados') or []
        # Agrupar por base_crude -> {'con': {...}, 'sin': {...}}
        grupos = {}
        all_products = []
        for r in resultados:
            base = (r.get('base_crude') or r.get('base') or '').strip()
            if not base:
                continue
            g = grupos.setdefault(base, {'con': None, 'sin': None, 'order': r.get('order') or list((r.get('yields') or {}).keys())})
            orden = r.get('order') or g['order']
            if orden and len(orden) > len(g['order']):
                g['order'] = orden
            all_products.extend(g['order'])
            compact = {
                'yields_pct': r.get('yields') or {},
                'api_by_product': r.get('api_by_product') or {},
                'sulfur_by_product': r.get('sulfur_by_product') or {}
            }
            if r.get('include_kero'):
                g['con'] = compact
            else:
                g['sin'] = compact
        # Normalizar listas productos global
        all_products = list(dict.fromkeys(all_products))
        # Resumen global simple: cantidad crudos con/sin pares completos
        total_bases = len(grupos)
        pares_completos = sum(1 for v in grupos.values() if v.get('con') and v.get('sin'))
        resumen_global = [
            {'nombre': 'Crudos distintos', 'valor': total_bases, 'nota': None},
            {'nombre': 'Pares completos', 'valor': pares_completos, 'nota': None},
            {'nombre': 'Fecha', 'valor': datetime.now().strftime('%d/%m/%Y %H:%M'), 'nota': None}
        ]
        # Logo
        logo_base64 = None
        try:
            logo_path = os.path.join(current_app.root_path, 'static', 'Logo_de_empresa.jpeg')
            if os.path.exists(logo_path):
                with open(logo_path, 'rb') as f:
                    logo_base64 = base64.b64encode(f.read()).decode('utf-8')
        except Exception:
            pass
        html_para_pdf = render_template('reportes_pdf/comparativo_kero_pdf.html',
                                        comparativos=grupos,
                                        resumen_global=resumen_global,
                                        fecha_generacion=datetime.now().strftime('%d/%m/%Y %H:%M'),
                                        logo_base64=logo_base64)
        pdf = HTML(string=html_para_pdf, base_url=current_app.root_path).write_pdf()
        return Response(pdf, mimetype='application/pdf', headers={'Content-Disposition': 'attachment;filename=comparativo_kero.pdf'})
    except Exception as e:
        current_app.logger.error(f"Error comparativo KERO PDF: {e}")
        return jsonify(success=False, message='Error generando PDF comparativo'), 500

@login_required
@permiso_requerido('simulador_rendimiento')
@app.route('/descargar_comparativo_kero_excel', methods=['POST'])
def descargar_comparativo_kero_excel():
    """Genera Excel comparativo KERO. Hoja por crudo o una consolidada.
    Estructura: misma que PDF endpoint."""
    try:
        import io, xlsxwriter
        data = request.get_json(silent=True) or {}
        resultados = data.get('resultados') or []
        grupos = {}
        all_products = []
        for r in resultados:
            base = (r.get('base_crude') or r.get('base') or '').strip()
            if not base:
                continue
            g = grupos.setdefault(base, {'con': None, 'sin': None, 'order': r.get('order') or list((r.get('yields') or {}).keys())})
            orden = r.get('order') or g['order']
            if orden and len(orden) > len(g['order']):
                g['order'] = orden
            all_products.extend(g['order'])
            compact = {
                'yields_pct': r.get('yields') or {},
                'api_by_product': r.get('api_by_product') or {},
                'sulfur_by_product': r.get('sulfur_by_product') or {}
            }
            if r.get('include_kero'):
                g['con'] = compact
            else:
                g['sin'] = compact
        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {'in_memory': True})
        fmt_pct = wb.add_format({'num_format': '0.00'} )
        fmt_api = wb.add_format({'num_format': '0.00'} )
        fmt_s  = wb.add_format({'num_format': '0.0000'} )
        fmt_delta_pos = wb.add_format({'font_color':'#0b8552'})
        fmt_delta_neg = wb.add_format({'font_color':'#c0392b'})
        # Hoja consolidada
        ws = wb.add_worksheet('Consolidado')
        headers = ['Crudo','Producto','% Con','% Sin','Δ %','API Con','API Sin','Δ API','%S Con','%S Sin','Δ %S']
        for c,h in enumerate(headers): ws.write(0,c,h)
        row_idx=1
        for base, pair in grupos.items():
            order = pair.get('order') or []
            for prod in order:
                con_y = (pair.get('con') or {}).get('yields_pct',{}).get(prod,0)
                sin_y = (pair.get('sin') or {}).get('yields_pct',{}).get(prod,0)
                d_y = con_y - sin_y
                api_c = (pair.get('con') or {}).get('api_by_product',{}).get(prod,0)
                api_s = (pair.get('sin') or {}).get('api_by_product',{}).get(prod,0)
                d_api = api_c - api_s
                s_c = (pair.get('con') or {}).get('sulfur_by_product',{}).get(prod,0)
                s_s = (pair.get('sin') or {}).get('sulfur_by_product',{}).get(prod,0)
                d_s = s_c - s_s
                ws.write(row_idx,0,base)
                ws.write(row_idx,1,prod)
                ws.write_number(row_idx,2,con_y,fmt_pct)
                ws.write_number(row_idx,3,sin_y,fmt_pct)
                ws.write_number(row_idx,4,d_y, fmt_delta_pos if d_y>0 else fmt_delta_neg if d_y<0 else None)
                ws.write_number(row_idx,5,api_c,fmt_api)
                ws.write_number(row_idx,6,api_s,fmt_api)
                ws.write_number(row_idx,7,d_api, fmt_delta_pos if d_api>0 else fmt_delta_neg if d_api<0 else None)
                ws.write_number(row_idx,8,s_c,fmt_s)
                ws.write_number(row_idx,9,s_s,fmt_s)
                ws.write_number(row_idx,10,d_s, fmt_delta_pos if d_s>0 else fmt_delta_neg if d_s<0 else None)
                row_idx+=1
        wb.close()
        output.seek(0)
        return Response(output.read(), mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition':'attachment;filename=comparativo_kero.xlsx'})
    except Exception as e:
        current_app.logger.error(f"Error comparativo KERO Excel: {e}")
        return jsonify(success=False, message='Error generando Excel comparativo'), 500

@login_required
@app.route('/api/calcular_rendimiento', methods=['POST'])
def api_calcular_rendimiento():
    """
    Calcula rendimiento, API, azufre y viscosidad de productos.
    VERSIÓN FINAL Y CORREGIDA (CON TOGGLE PARA KERO).
    """
    try:
        data = request.get_json()
        puntos_curva = data.get('distillationCurve')
        puntos_corte = data.get('cutPoints')
        azufre_crudo = data.get('sulfurCrude') or 0
        api_crudo = data.get('apiCrude') or 0
        viscosidad_crudo = data.get('viscosityCrude') or 0
        # <<-- NUEVO: Obtener el estado del interruptor, por defecto es True
        incluir_kero = data.get('includeKero', True)

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

    # 1. Calcular Rendimientos (Lógica condicional)
        porc_nafta = interpolar_porcentaje(puntos_corte.get('nafta', 0))
        porc_fo4_acumulado = interpolar_porcentaje(puntos_corte.get('fo4', 0))

        if incluir_kero:
            porc_kero_acumulado = interpolar_porcentaje(puntos_corte.get('kero', 0))
            ORDEN_PRODUCTOS = ["NAFTA", "KERO", "FO4", "FO6"]
            # Cálculo base de rendimientos por cortes acumulados
            rendimientos = {
                "NAFTA": max(0, porc_nafta),
                "KERO": max(0, porc_kero_acumulado - porc_nafta),
                "FO4": max(0, porc_fo4_acumulado - porc_kero_acumulado),
                "FO6": max(0, 100 - porc_fo4_acumulado)
            }
            # Ajuste solicitado original: KERO = KERO - 5% NAFTA + 10% FO4.
            # Tras el ajuste vamos a NORMALIZAR todos los cortes para que la suma sea 100 antes de cálculos de propiedades.
            kero_base = rendimientos["KERO"]
            nafta_y = rendimientos["NAFTA"]
            fo4_y = rendimientos["FO4"]
            kero_ajustado = kero_base - 0.05 * nafta_y + 0.10 * fo4_y
            rendimientos["KERO"] = max(0, kero_ajustado)  # sin redondear todavía, mantenemos precisión
        else: # Si no se incluye kero
            ORDEN_PRODUCTOS = ["NAFTA", "FO4", "FO6"]
            rendimientos = {
                "NAFTA": max(0, porc_nafta),
                "KERO": 0, # Se asigna 0 para consistencia en cálculos intermedios
                "FO4": max(0, porc_fo4_acumulado - porc_nafta), # FO4 absorbe el corte de KERO
                "FO6": max(0, 100 - porc_fo4_acumulado)
            }
        # --- NORMALIZACIÓN (para evitar sesgo en API y %S) ---
        suma_original = sum(rendimientos.values()) or 0
        if suma_original > 0:
            for k in rendimientos.keys():
                rendimientos[k] = (rendimientos[k] * 100.0) / suma_original
        # Guardamos la suma original para referencia / auditoría (puede diferir de 100 si hubo ajuste)
        suma_post_norm = sum(rendimientos.values())
        
        # 2. Calcular Azufre por Producto
        azufre_por_producto = {}
        FACTORES_AZUFRE = {'NAFTA': 0.05, 'KERO': 0.15, 'FO4': 1.0, 'FO6': 2.5}
        if azufre_crudo > 0:
            # Usamos los rendimientos NORMALIZADOS (sum=100) para evitar sesgo.
            denominador_k_s = sum(rendimientos.get(p, 0) * FACTORES_AZUFRE[p] for p in FACTORES_AZUFRE)
            # azufre_crudo = (Σ yield_p * (k_s * factor_p)) / 100  => k_s = 100 * azufre_crudo / denominador
            k_s = (100 * azufre_crudo) / denominador_k_s if denominador_k_s > 0 else 0
            for p in FACTORES_AZUFRE:
                azufre_por_producto[p] = round(k_s * FACTORES_AZUFRE.get(p, 0), 4)

        # 3. Calcular API por Producto
        api_por_producto = {}
        API_ESTANDAR = {'NAFTA': 56.6, 'KERO': 42, 'FO4': 30,'FO6':21}
        def api_a_sg(api): return 141.5 / (api + 131.5) if api != -131.5 else 0
        def sg_a_api(sg): return (141.5 / sg) - 131.5 if sg > 0 else 0
        sg_crudo_real = api_a_sg(api_crudo)
        sg_estandar = {p: api_a_sg(a) for p, a in API_ESTANDAR.items()}
        # Usamos fracciones normalizadas (rendimientos ya suman 100) => fracción = y/100
        sg_reconstituido = sum((rendimientos.get(p, 0)/100.0) * sg_estandar[p] for p in API_ESTANDAR if rendimientos.get(p,0) > 0)
        factor_ajuste_sg = (sg_crudo_real / sg_reconstituido) if sg_reconstituido > 0 else 1
        for p in API_ESTANDAR:
            sg_adj = sg_estandar[p] * factor_ajuste_sg
            api_por_producto[p] = round(sg_a_api(sg_adj), 2)  # más precisión

        # 4. Calcular Viscosidad por Producto
        viscosidad_por_producto = {}
        VISCOSIDAD_STD = {'NAFTA': 0.8, 'KERO': 2.0, 'FO4': 4.0, 'FO6': 380.0}
        if viscosidad_crudo > 0:
            log_visc_reconstituido = sum((rendimientos.get(p,0)/100.0) * math.log(VISCOSIDAD_STD[p]) for p in VISCOSIDAD_STD if VISCOSIDAD_STD.get(p, 0) > 0 and rendimientos.get(p, 0) > 0)
            visc_reconstituido = math.exp(log_visc_reconstituido) if log_visc_reconstituido != 0 else 1
            factor_ajuste_visc = viscosidad_crudo / visc_reconstituido if visc_reconstituido > 0 else 1
            for p in VISCOSIDAD_STD:
                viscosidad_por_producto[p] = round(VISCOSIDAD_STD[p] * factor_ajuste_visc, 2)

        # 5. Devolver respuesta completa y ordenada, filtrando solo los productos relevantes
        return jsonify({
            "success": True, 
            "order": ORDEN_PRODUCTOS,
            "yields": {p: round(rendimientos.get(p, 0), 2) for p in ORDEN_PRODUCTOS},  # ya normalizados
            "sum_percent_original": round(suma_original, 4),
            "sum_percent_normalized": round(suma_post_norm, 4),
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
            "curva": json.loads(crudo.curva_json),
            "assay": json.loads(crudo.assay_json) if crudo.assay_json else []
        } for crudo in crudos_db
    }
    response = jsonify(crudos_dict)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return jsonify(crudos_dict)

@login_required
@app.route('/api/crudos_guardados', methods=['POST'])
def save_crudo():
    data = request.get_json()
    nombre_crudo = data.get('nombre')
    assay_data = data.get('assay')
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
        crudo_existente.assay_json = json.dumps(assay_data)
        msg = f"Crudo '{nombre_crudo}' actualizado."
    else:
        nuevo_crudo = DefinicionCrudo(
            nombre=nombre_crudo, 
            api=api, 
            sulfur=sulfur,                # <-- AÑADIDO
            viscosity=viscosity,          # <-- AÑADIDO
            curva_json=json.dumps(curva),
            assay_json=json.dumps(assay_data) 
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
    
@login_required
@permiso_exclusivo('accountingzf@conquerstrading.com')
@app.route('/inicio-contabilidad')
def home_contabilidad():
    """Página de inicio exclusiva para Contabilidad."""
    return render_template('home_contabilidad.html')
    
@login_required
@permiso_requerido('accountingzf@conquerstrading.com')
@app.route('/consolidar-facturas')
def consolidar_facturas():
    return render_template('consolidar_facturas.html', nombre=session.get("nombre"))

@login_required
@permiso_exclusivo('accountingzf@conquerstrading.com')
@app.route('/api/comparar_facturas', methods=['POST'])
def api_comparar_facturas():
    if 'odoo_file' not in request.files or 'dian_file' not in request.files:
        return jsonify(success=False, message="Ambos archivos son requeridos."), 400

    try:
        df_odoo = pd.read_excel(request.files['odoo_file'], engine='openpyxl')
        df_dian = pd.read_excel(request.files['dian_file'], engine='openpyxl')

        # --- Verificación de Columnas Clave ---
        if 'Referencia' not in df_odoo.columns:
            return jsonify(success=False, message="La columna 'Referencia' no se encontró en el archivo de Odoo."), 400
        if 'Prefijo' not in df_dian.columns or 'Folio' not in df_dian.columns or 'Nombre Emisor' not in df_dian.columns:
            return jsonify(success=False, message="El archivo de la DIAN debe tener 'Prefijo', 'Folio' y 'Nombre Emisor'."), 400

        # --- Función de Normalización Inteligente (Definitiva) ---
        def normalizar_factura(ref):
            if pd.isna(ref): return None
            s_ref = str(ref).strip().upper()
            
            # Busca un prefijo de letras/guiones y luego los números
            partes = re.match(r"([A-Z\-]+)0*(\d+)", s_ref)
            if partes:
                # Une el prefijo (sin guion) con el número
                prefijo = partes.group(1).replace('-', '')
                folio = int(partes.group(2))
                return f"{prefijo}-{folio}"
            
            # Si no encuentra el patrón, devuelve solo los números y letras
            return re.sub(r'[^A-Z0-9]', '', s_ref)

        # 1. Procesar datos de Odoo
        set_odoo = set(df_odoo['Referencia'].dropna().apply(normalizar_factura))
        
        # 2. Procesar datos de la DIAN
        def unir_prefijo_folio(row):
            prefijo = str(row['Prefijo']).strip() if pd.notna(row['Prefijo']) else ""
            folio = str(row['Folio']).strip() if pd.notna(row['Folio']) else ""
            # Si el prefijo está vacío, es 'nan', o ya está en el folio, usa solo el folio
            if not prefijo or prefijo.lower() == 'nan' or prefijo in folio:
                return folio
            return prefijo + folio

        df_dian['referencia_completa'] = df_dian.apply(unir_prefijo_folio, axis=1)
        
        dian_map = {
            normalizar_factura(row['referencia_completa']): {
                "factura": row['referencia_completa'],
                "emisor": str(row['Nombre Emisor']) if pd.notna(row['Nombre Emisor']) else "Sin Nombre"
            }
            for _, row in df_dian.dropna(subset=['referencia_completa']).iterrows()
        }
        set_dian = set(dian_map.keys())

        # 3. Comparación Invertida: Lo que está en DIAN y falta en Odoo
        faltantes_normalizados = sorted(list(set_dian - set_odoo))
        
        # Recuperar el formato original y el nombre del emisor desde el mapa de la DIAN
        facturas_faltantes = [dian_map[key] for key in faltantes_normalizados if key in dian_map]
        
        return jsonify(
            success=True,
            faltantes=facturas_faltantes,
            conteo=len(facturas_faltantes)
        )

    except Exception as e:
        app.logger.error(f"Error al comparar archivos: {e}")
        return jsonify(success=False, message=f"Ocurrió un error al procesar los archivos: {str(e)}"), 500
    
@login_required
@permiso_exclusivo('accountingzf@conquerstrading.com')
@app.route('/api/exportar_facturas_excel', methods=['POST'])
def exportar_facturas_excel():
    """Recibe un JSON con la lista de facturas faltantes (tras posibles exclusiones de Caja Menor)
    y devuelve un archivo Excel descargable."""
    try:
        data = request.get_json(silent=True) or {}
        facturas = data.get('facturas', [])
        if not isinstance(facturas, list) or not facturas:
            return jsonify(success=False, message='No se recibieron facturas válidas.'), 400

        # Estructurar DataFrame
        df = pd.DataFrame([
            {
                'Factura (Normalizada)': f.get('factura'),
                'Emisor (DIAN)': f.get('emisor')
            }
            for f in facturas if f.get('factura')
        ])

        if df.empty:
            return jsonify(success=False, message='La lista está vacía tras el filtrado.'), 400

        # Generar Excel en memoria
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Faltantes')
            ws = writer.sheets['Faltantes']
            # Auto ancho simple
            for col in ws.columns:
                max_length = 0
                col_letter = col[0].column_letter
                for cell in col:
                    try:
                        val = str(cell.value) if cell.value is not None else ''
                        if len(val) > max_length:
                            max_length = len(val)
                    except Exception:
                        pass
                ws.column_dimensions[col_letter].width = min(max_length + 2, 60)
        output.seek(0)

        filename = f"facturas_faltantes_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(output,
                         as_attachment=True,
                         download_name=filename,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e:
        app.logger.error(f"Error exportando Excel faltantes: {e}")
        return jsonify(success=False, message='Error interno al generar el Excel.'), 500

@login_required
@permiso_requerido('control_remolcadores')    
@app.route('/control_remolcadores')
def control_remolcadores_page():
    return render_template('control_remolcadores.html', nombre=session.get("nombre"))

@login_required
@permiso_requerido('control_remolcadores')
@app.route('/api/remolcadores/upload_excel', methods=['POST'])
def upload_remolcadores_excel():
    if 'excel_file' not in request.files:
        return jsonify(success=False, message="No se encontró ningún archivo."), 400
    
    file = request.files['excel_file']
    if not file.filename.endswith('.xlsx'):
        return jsonify(success=False, message="Archivo no válido. Debe ser .xlsx"), 400

    try:
        df = pd.read_excel(file)
        df.columns = [str(c).strip().title() for c in df.columns]

        # ✅ 1. Renombrar 'Barco' a 'Nombre Del Barco' si la columna existe
        if 'Barco' in df.columns:
            df.rename(columns={'Barco': 'Nombre Del Barco'}, inplace=True)

        required_columns = ['Id', 'Barcaza', 'Mt Entregadas', 'Evento Anterior', 'Hora Inicio', 'Evento Actual', 'Hora Fin', 'Carga']
        if not all(col in df.columns for col in required_columns):
            missing = [col for col in required_columns if col not in df.columns]
            return jsonify(success=False, message=f"Faltan columnas obligatorias en el Excel: {', '.join(missing)}"), 400

        nuevos_registros = []
        for maniobra_id, group in df.groupby('Id'):
            for _, row in group.iterrows():
                barcaza = row['Barcaza'] if pd.notna(row['Barcaza']) else None
                mt_val = row['Mt Entregadas']
                mt_entregadas = float(mt_val) if pd.notna(mt_val) else None
                hora_inicio = pd.to_datetime(row['Hora Inicio'], dayfirst=True)
                hora_fin = pd.to_datetime(row['Hora Fin'], dayfirst=True) if pd.notna(row['Hora Fin']) else None

                # Lógica para manejar el campo opcional 'Nombre Del Barco'
                nombre_barco_valor = None
                if 'Nombre Del Barco' in df.columns:
                    nombre_barco_valor = row['Nombre Del Barco'] if pd.notna(row['Nombre Del Barco']) else None
                
                registro = RegistroRemolcador(
                    maniobra_id=int(maniobra_id),
                    barcaza=barcaza,
                    nombre_barco=nombre_barco_valor, # ✅ 2. Asignar el valor a la nueva columna
                    mt_entregadas=mt_entregadas,
                    carga_estado=row['Carga'],
                    evento_anterior=row['Evento Anterior'],
                    hora_inicio=hora_inicio,
                    evento_actual=row['Evento Actual'],
                    hora_fin=hora_fin,
                    usuario_actualizacion=session.get('nombre')
                )
                nuevos_registros.append(registro)

        # Usar el nombre correcto de la tabla que descubrimos ('registro_remolcador')
        db.session.query(RegistroRemolcador).delete()
        db.session.add_all(nuevos_registros)
        db.session.commit()

        return jsonify(success=True, message=f"Se han cargado {len(nuevos_registros)} eventos de {len(df.groupby('Id'))} maniobras.")

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error al procesar Excel de remolcadores: {e}")
        return jsonify(success=False, message=f"Error interno al procesar el archivo: {str(e)}"), 500

@login_required
@permiso_requerido('control_remolcadores')
@app.route('/api/maniobra/<int:maniobra_id>', methods=['PUT'])
def update_maniobra_details(maniobra_id):
    """Actualiza la barcaza y las MT para todos los eventos de una maniobra."""
    
    # #{ CAMBIO 1 } - Se añade el email 'opensean@conquerstrading.com' a la lista de permisos.
    if not (session.get('rol') == 'admin' or 
            session.get('email') == 'ops@conquerstrading.com' or 
            session.get('email') == 'opensean@conquerstrading.com'):
        return jsonify(success=False, message="Permiso denegado."), 403

    data = request.get_json()
    barcaza = data.get('barcaza')
    nombre_barco = data.get('nombre_barco')

    try:
        registros = RegistroRemolcador.query.filter_by(maniobra_id=maniobra_id).all()
        for registro in registros:
            # Todos los roles con permiso pueden actualizar la barcaza.
            registro.barcaza = barcaza
            registro.nombre_barco = nombre_barco
            
            # #{ CAMBIO 2 } - Se añade una condición para que solo admin y ops@conquerstrading.com
            # puedan modificar las MT Entregadas. El usuario 'opensean' no podrá hacerlo.
            if session.get('rol') == 'admin' or session.get('email') == 'ops@conquerstrading.com':
                if 'mt_entregadas' in data:
                    mt_entregadas_str = data.get('mt_entregadas')
                    mt_entregadas = float(mt_entregadas_str) if mt_entregadas_str else None
                    registro.mt_entregadas = mt_entregadas
        
        db.session.commit()
        return jsonify(success=True, message=f"Datos de la Maniobra #{maniobra_id} actualizados.")
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, message=str(e)), 500

@login_required
@permiso_requerido('control_remolcadores')
@app.route('/api/maniobra/<int:maniobra_id>', methods=['DELETE'])
def eliminar_maniobra(maniobra_id):
    """Elimina todos los registros asociados a un ID de maniobra."""
    
    if not (session.get('rol') == 'admin' or 
            session.get('email') == 'ops@conquerstrading.com' or 
            session.get('email') == 'opensean@conquerstrading.com'):
        return jsonify(success=False, message="Permiso denegado."), 403

    try:
        num_borrados = RegistroRemolcador.query.filter_by(maniobra_id=maniobra_id).delete()
        if num_borrados == 0:
            return jsonify(success=False, message="No se encontró la maniobra para eliminar."), 404
            
        db.session.commit()
        return jsonify(success=True, message=f"Maniobra #{maniobra_id} y sus {num_borrados} eventos han sido eliminados.")
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error al eliminar maniobra: {e}")
        return jsonify(success=False, message=f"Error interno: {str(e)}"), 500 
    
@login_required
@permiso_requerido('control_remolcadores')
@app.route('/api/registros_remolcadores', methods=['GET'])
def get_registros_remolcadores():
    try:
        # Tu lógica de filtrado por fecha está bien

        fecha_inicio_str = request.args.get('fecha_inicio')
        fecha_fin_str = request.args.get('fecha_fin')
        filtro_mes = request.args.get('filtro_mes')  # formato YYYY-MM

        query = RegistroRemolcador.query

        # Si hay filtro de mes, priorizarlo
        if filtro_mes:
            try:
                anio, mes = map(int, filtro_mes.split('-'))
                fecha_inicio_obj = date(anio, mes, 1)
                if mes == 12:
                    fecha_fin_obj = date(anio + 1, 1, 1) - timedelta(days=1)
                else:
                    fecha_fin_obj = date(anio, mes + 1, 1) - timedelta(days=1)
                query = query.filter(RegistroRemolcador.hora_inicio >= fecha_inicio_obj)
                query = query.filter(RegistroRemolcador.hora_inicio <= datetime.combine(fecha_fin_obj, time.max))
            except Exception:
                pass
        else:
            if fecha_inicio_str:
                fecha_inicio_obj = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
                query = query.filter(RegistroRemolcador.hora_inicio >= fecha_inicio_obj)
            if fecha_fin_str:
                fecha_fin_obj = datetime.strptime(fecha_fin_str, '%Y-%m-%d')
                fecha_fin_obj_end_of_day = datetime.combine(fecha_fin_obj, time.max)
                query = query.filter(RegistroRemolcador.hora_inicio <= fecha_fin_obj_end_of_day)

        registros = query.order_by(RegistroRemolcador.maniobra_id, RegistroRemolcador.hora_inicio).all()
        
        # --- ✅ INICIO DE LA LÓGICA CORREGIDA PARA CALCULAR EL TOTAL DE HORAS ---
        duraciones_totales = {}
        if registros:
            # Agrupa todos los eventos por su ID de maniobra
            grupos = groupby(registros, key=lambda r: r.maniobra_id)
            
            for maniobra_id, grupo_eventos in grupos:
                lista_eventos = list(grupo_eventos)
                if not lista_eventos: continue
                
                # Encuentra la primera hora de inicio y la última hora de fin de la maniobra
                primera_hora_inicio = min(r.hora_inicio for r in lista_eventos)
                horas_fin_validas = [r.hora_fin for r in lista_eventos if r.hora_fin]
                
                if horas_fin_validas:
                    ultima_hora_fin = max(horas_fin_validas)
                    # Calcula la diferencia total
                    delta_total = ultima_hora_fin - primera_hora_inicio
                    horas, rem = divmod(delta_total.total_seconds(), 3600)
                    minutos, _ = divmod(rem, 60)
                    duraciones_totales[maniobra_id] = f"{int(horas)}h {int(minutos)}m"
                else:
                    duraciones_totales[maniobra_id] = "En Proceso"
        # --- ✅ FIN DE LA LÓGICA DE CÁLCULO ---

        data = []
        es_opensean = session.get('email') == 'opensean@conquerstrading.com'
        for r in registros:
            registro_data = {
                "id": r.id,
                "maniobra_id": r.maniobra_id,
                "barcaza": r.barcaza,
                "nombre_barco": r.nombre_barco,
                "evento_anterior": r.evento_anterior,
                "hora_inicio": r.hora_inicio.strftime('%Y-%m-%dT%H:%M'), # Formato para <input>
                "evento_actual": r.evento_actual,
                "hora_fin": r.hora_fin.strftime('%Y-%m-%dT%H:%M') if r.hora_fin else '',
                "duracion": r.duracion,
                "carga_estado": r.carga_estado,
                "total_horas": duraciones_totales.get(r.maniobra_id, "")
            }
            if not es_opensean:
                registro_data["mt_entregadas"] = float(r.mt_entregadas) if r.mt_entregadas is not None else ''

            data.append(registro_data)
            
        return jsonify(data)

    except Exception as e:
        app.logger.error(f"Error en get_registros_remolcadores: {e}")
        return jsonify({"error": str(e)}), 500

@login_required
@permiso_requerido('control_remolcadores')
@app.route('/api/registros_remolcadores', methods=['POST'])
def crear_registro_remolcador():
    """Crea un nuevo evento de remolcador."""
    data = request.get_json()
    if not data:
        return jsonify(success=False, message="No se recibieron datos."), 400

    try:
        maniobra_id = data.get('maniobra_id')

        # Si no hay ID de maniobra, es una nueva, así que calculamos el siguiente.
        if not maniobra_id:
            max_id = db.session.query(func.max(RegistroRemolcador.maniobra_id)).scalar()
            maniobra_id = (max_id or 0) + 1

        # --- CORRECCIÓN 1: Manejo seguro de fechas vacías ---
        hora_inicio_str = data.get('hora_inicio')
        hora_fin_str = data.get('hora_fin')

        hora_inicio = datetime.fromisoformat(hora_inicio_str) if hora_inicio_str else None
        hora_fin = datetime.fromisoformat(hora_fin_str) if hora_fin_str else None

        if not hora_inicio:
            return jsonify(success=False, message="La hora de inicio es obligatoria."), 400

        nuevo_registro = RegistroRemolcador(
            maniobra_id=maniobra_id,
            evento_anterior=data.get('evento_anterior'),
            hora_inicio=hora_inicio,
            evento_actual=data.get('evento_actual'),
            hora_fin=hora_fin,
            usuario_actualizacion=session.get('nombre')
        )

        # --- CORRECIÓN 2: Permisos actualizados para opensean ---
        usuario_puede_gestionar = (
            session.get('rol') == 'admin' or 
            session.get('email') == 'ops@conquerstrading.com' or
            session.get('email') == 'opensean@conquerstrading.com'
        )
        if usuario_puede_gestionar:
            nuevo_registro.barcaza = data.get('barcaza')
            nuevo_registro.nombre_barco = data.get('nombre_barco')
            nuevo_registro.mt_entregadas = data.get('mt_entregadas') if data.get('mt_entregadas') else None
            nuevo_registro.carga_estado = data.get('carga_estado')

        if session.get('rol') == 'admin' or session.get('email') == 'ops@conquerstrading.com':
            if 'mt_entregadas' in data:
                nuevo_registro.mt_entregadas = data.get('mt_entregadas') if data.get('mt_entregadas') else None

        db.session.add(nuevo_registro)
        db.session.commit()
        
        return jsonify(success=True, message="Evento creado exitosamente.", nuevo_maniobra_id=maniobra_id)

    except ValueError as e:
        db.session.rollback()
        app.logger.error(f"Error de formato en la fecha al crear evento: {e}")
        return jsonify(success=False, message=f"Formato de fecha no válido: {e}"), 400
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error al crear evento: {e}")
        return jsonify(success=False, message=f"Error interno: {str(e)}"), 500

@login_required
@permiso_requerido('control_remolcadores')
@app.route('/api/registros_remolcadores/<int:id>', methods=['PUT'])
def update_registro_remolcador(id):
    """Actualiza un evento existente, respetando los permisos de cada rol."""
    registro = RegistroRemolcador.query.get_or_404(id)
    data = request.get_json()

    estados_carga_permitidos = ["LLENO", "VACIO", "N/A"]
    
    # Valores permitidos para opensean
    eventos_anteriores_permitidos = [
        "AUTORIZADO", "CAMBIO DE RR", "CANCELACION", "ESPERAR AUTORIZACION",
        "INICIO BASE OPS", "INICIO BITA", "INICIO CONTECAR", "INICIO FONDEO", "INICIO PUERTO BAHIA", "INICIO SPRC",
        "LLEGADA BASE OPS", "LLEGADA BITA", "LLEGADA CONTECAR", "LLEGADA FONDEO", "LLEGADA SPD", "LLEGADA PUERTO BAHIA"
        "LLEGADA SPRC", "REPOSICIONAMIENTO BARCAZAS"
    ]
    
    eventos_actuales_permitidos = [
        "ACODERADO", "AUTORIZADO", "CAMBIO DE RR", "CANCELACION", 
        "ESPERAR AUTORIZACION", "INICIO BASE OPS", "INICIO BITA", "INICIO CONTECAR", 
        "INICIO FONDEO", "INICIO PUERTO BAHIA","INICIO SPRC", "LLEGADA BASE OPS", "LLEGADA BITA",
        "LLEGADA CONTECAR", "LLEGADA FONDEO", "LLEGADA SPD", "LLEGADA PUERTO BAHIA",
        "REUBICACION BARCAZAS", "TANQUEO"
    ]

    try:
        # El usuario opensean solo puede modificar los campos permitidos
        if session.get('email') == 'opensean@conquerstrading.com':

            if 'carga_estado' in data and data['carga_estado'] not in estados_carga_permitidos:
                return jsonify(success=False, message="Estado de carga no permitido"), 400
            # Validar eventos
            if 'evento_anterior' in data and data['evento_anterior'] not in eventos_anteriores_permitidos:
                return jsonify(success=False, message="Evento anterior no permitido"), 400
            if 'evento_actual' in data and data['evento_actual'] not in eventos_actuales_permitidos:
                return jsonify(success=False, message="Evento actual no permitido"), 400
            
            campos_permitidos = ['evento_anterior', 'hora_inicio', 'evento_actual', 'hora_fin', 'carga_estado', 'nombre_barco']
            for campo in campos_permitidos:
                if campo in data:
                    valor = data[campo]
                    if 'hora' in campo and valor:
                        setattr(registro, campo, datetime.fromisoformat(valor))
                    else:
                        setattr(registro, campo, valor)
        
        # El admin o Juliana pueden editar todos los campos
        elif session.get('rol') == 'admin' or session.get('email') == 'ops@conquerstrading.com':
            for campo, valor in data.items():
                if hasattr(registro, campo):
                    if 'hora' in campo and valor:
                        setattr(registro, campo, datetime.fromisoformat(valor))
                    elif campo == 'carga_estado':
                        setattr(registro, campo, valor if valor != 'N/A' else None)    
                    elif campo != 'id':
                        setattr(registro, campo, valor)
        
        registro.usuario_actualizacion = session.get('nombre')
        db.session.commit()
        return jsonify(success=True, message="Registro actualizado.")
        
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, message=f"Error al actualizar: {str(e)}"), 500

@login_required
@permiso_requerido('control_remolcadores')
@app.route('/reporte_analisis_remolcadores')
def reporte_analisis_remolcadores():
    try:
        # 1. Leer los filtros desde la URL
        fecha_inicio_str = request.args.get('fecha_inicio')
        fecha_fin_str = request.args.get('fecha_fin')
        filtro_mes = request.args.get('filtro_mes')  # formato YYYY-MM

        query = RegistroRemolcador.query

        # 2. Prioridad: si hay filtro de mes, usarlo y limpiar fechas
        if filtro_mes:
            # Calcular primer y último día del mes
            try:
                anio, mes = map(int, filtro_mes.split('-'))
                fecha_inicio_obj = date(anio, mes, 1)
                if mes == 12:
                    fecha_fin_obj = date(anio + 1, 1, 1) - timedelta(days=1)
                else:
                    fecha_fin_obj = date(anio, mes + 1, 1) - timedelta(days=1)
                query = query.filter(RegistroRemolcador.hora_inicio >= fecha_inicio_obj)
                query = query.filter(RegistroRemolcador.hora_inicio <= datetime.combine(fecha_fin_obj, time.max))
                fecha_inicio_str = fecha_inicio_obj.strftime('%Y-%m-%d')
                fecha_fin_str = fecha_fin_obj.strftime('%Y-%m-%d')
            except Exception:
                pass
        else:
            # 3. Si no hay filtro de mes, usar fechas normales
            if fecha_inicio_str:
                fecha_inicio_obj = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
                query = query.filter(RegistroRemolcador.hora_inicio >= fecha_inicio_obj)
            if fecha_fin_str:
                fecha_fin_obj = datetime.strptime(fecha_fin_str, '%Y-%m-%d')
                query = query.filter(RegistroRemolcador.hora_inicio <= datetime.combine(fecha_fin_obj, time.max))

        # 4. Obtener solo los registros filtrados
        registros_filtrados = query.all()
        
        # 5. Procesar ÚNICAMENTE los datos filtrados
        resultados = procesar_analisis_remolcadores(registros_filtrados)
        
        if not resultados:
            flash("No hay suficientes datos para generar el análisis en el rango de fechas seleccionado.", "warning")
        
        # Guardamos los filtros para pasarlos de vuelta a la plantilla
        filtros_activos = {
            'fecha_inicio': fecha_inicio_str,
            'fecha_fin': fecha_fin_str,
            'filtro_mes': filtro_mes
        }

        return render_template(
            'reporte_analisis_remolcadores.html',
            resultados=resultados,
            filtros=filtros_activos # Pasamos los filtros para los inputs y el botón de PDF
        )
    except Exception as e:
        flash(f"Error al generar el reporte: {str(e)}", "danger")
        return redirect(url_for('control_remolcadores_page'))

@login_required
@permiso_requerido('control_remolcadores')
@app.route('/descargar_analisis_remolcadores_pdf')
def descargar_reporte_analisis_remolcadores_pdf():
    try:
        # (Tu lógica de filtrado por fechas se mantiene igual)
        fecha_inicio_str = request.args.get('fecha_inicio')
        fecha_fin_str = request.args.get('fecha_fin')
        query = RegistroRemolcador.query
        if fecha_inicio_str:
            fecha_inicio_obj = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
            query = query.filter(RegistroRemolcador.hora_inicio >= fecha_inicio_obj)
        if fecha_fin_str:
            fecha_fin_obj = datetime.strptime(fecha_fin_str, '%Y-%m-%d')
            query = query.filter(RegistroRemolcador.hora_inicio <= datetime.combine(fecha_fin_obj, time.max))
        
        registros_filtrados = query.all()
        resultados = procesar_analisis_remolcadores(registros_filtrados)
        
        if not resultados:
            flash("No hay datos para generar el PDF.", "warning")
            return redirect(url_for('reporte_analisis_remolcadores'))

        # --- INICIO DE LA CORRECCIÓN DEFINITIVA ---
        logo_base64 = None
        try:
            # 1. Construir la ruta absoluta al logo
            logo_path = os.path.join(app.root_path, 'static', 'Logo_de_empresa.jpeg')
            # 2. Leer el archivo en modo binario y convertirlo a Base64
            with open(logo_path, "rb") as image_file:
                logo_base64 = base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            print(f"Error al cargar el logo: {e}") # En caso de que el logo no se encuentre
        # --- FIN DE LA CORRECCIÓN DEFINITIVA ---

        html_para_pdf = render_template(
            'reportes_pdf/analisis_remolcadores_pdf.html',
            resultados=resultados,
            fecha_reporte=date.today().strftime('%d de %B de %Y'),
            now=datetime.utcnow(),
            logo_base64=logo_base64  # <-- Pasamos la nueva variable
        )
        
        pdf = HTML(string=html_para_pdf).write_pdf()
        
        return Response(
            pdf,
            mimetype='application/pdf',
            headers={'Content-Disposition': 'attachment;filename=reporte_analisis_remolcadores.pdf'}
        )
    except Exception as e:
        flash(f"Error al generar el PDF: {str(e)}", "danger")
        return redirect(url_for('reporte_analisis_remolcadores'))

@login_required
@permiso_requerido('control_remolcadores')
@app.route('/descargar_reporte_analisis_remolcadores')
def descargar_reporte_analisis_remolcadores():
    """Genera y descarga un PDF con el análisis completo."""
    # 1. Obtener todos los registros de la base de datos
    registros = RegistroRemolcador.query.all()
    
    # 2. Procesar los datos con tu función de análisis
    resultados = procesar_analisis_remolcadores(registros)
    
    if not resultados:
        flash("No hay datos suficientes para generar el PDF.", "warning")
        return redirect(url_for('reporte_analisis_remolcadores'))

    # 3. Renderiza una plantilla HTML especial para el PDF
    html_para_pdf = render_template(
        'reportes_pdf/analisis_remolcadores_pdf.html',
        resultados=resultados,
        fecha_reporte=date.today().strftime('%d de %B de %Y')
    )
    
    # 4. Convierte el HTML a PDF usando WeasyPrint
    pdf = HTML(string=html_para_pdf).write_pdf()
    
    # 5. Devuelve el PDF como un archivo para descargar
    return Response(
        pdf,
        mimetype='application/pdf',
        headers={'Content-Disposition': 'attachment;filename=reporte_analisis_remolcadores.pdf'}
    )

@login_required
@permiso_requerido('control_remolcadores')
@app.route('/download_remolcadores_excel')
def download_remolcadores_excel():
    try:
        # 1. Obtener registros (con filtros)
        fecha_inicio_str = request.args.get('fecha_inicio')
        fecha_fin_str = request.args.get('fecha_fin')
        query = RegistroRemolcador.query

        if fecha_inicio_str:
            fecha_inicio_obj = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
            query = query.filter(RegistroRemolcador.hora_inicio >= fecha_inicio_obj)
        if fecha_fin_str:
            fecha_fin_obj = datetime.strptime(fecha_fin_str, '%Y-%m-%d')
            query = query.filter(RegistroRemolcador.hora_inicio <= datetime.combine(fecha_fin_obj, time.max))
        
        # Ordenar es clave para agrupar correctamente
        registros = query.order_by(RegistroRemolcador.maniobra_id, RegistroRemolcador.hora_inicio).all()

        # ✅ 2. AÑADIR LÓGICA PARA CALCULAR EL TOTAL DE HORAS POR MANIOBRA
        duraciones_totales = {}
        if registros:
            grupos = groupby(registros, key=lambda r: r.maniobra_id)
            for maniobra_id, grupo_eventos in grupos:
                lista_eventos = list(grupo_eventos)
                if not lista_eventos: continue
                
                primera_hora_inicio = min(r.hora_inicio for r in lista_eventos)
                horas_fin_validas = [r.hora_fin for r in lista_eventos if r.hora_fin]
                
                if horas_fin_validas:
                    ultima_hora_fin = max(horas_fin_validas)
                    delta_total = ultima_hora_fin - primera_hora_inicio
                    horas, rem = divmod(delta_total.total_seconds(), 3600)
                    minutos, _ = divmod(rem, 60)
                    duraciones_totales[maniobra_id] = f"{int(horas)}h {int(minutos)}m"
                else:
                    duraciones_totales[maniobra_id] = "En Proceso"

        # ✅ 3. PREPARAR DATOS PARA EXCEL, INCLUYENDO LAS NUEVAS COLUMNAS
        datos_para_excel = [{
            "Maniobra ID": r.maniobra_id,
            "Barcaza": r.barcaza,
            "Nombre Del Barco": r.nombre_barco,
            "Evento Anterior": r.evento_anterior,
            "Hora Inicio": r.hora_inicio.strftime('%d/%m/%Y %I:%M %p') if r.hora_inicio else '',
            "Evento Actual": r.evento_actual,
            "Hora Fin": r.hora_fin.strftime('%d/%m/%Y %I:%M %p') if r.hora_fin else '',
            "Duración": r.duracion,  # Se asume que tu modelo tiene una propiedad @property para 'duracion'
            "Total Horas Maniobra": duraciones_totales.get(r.maniobra_id, ''),
            "Carga": r.carga_estado,
            "MT Entregadas": r.mt_entregadas
        } for r in registros]
        
        df = pd.DataFrame(datos_para_excel)

        # 4. Crear y devolver el archivo Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Registros Remolcadores')
            # Auto-ajustar el ancho de las columnas
            for column in df:
                column_width = max(df[column].astype(str).map(len).max(), len(column))
                writer.sheets['Registros Remolcadores'].set_column(df.columns.get_loc(column), df.columns.get_loc(column), column_width + 1)
        output.seek(0)

        return Response(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment;filename=registros_remolcadores.xlsx"}
        )

    except Exception as e:
        app.logger.error(f"Error al generar Excel: {e}")
        return "Error al generar el archivo Excel.", 500

@login_required
@permiso_requerido('control_remolcadores')
@app.route('/inicio-remolcadores')
def home_remolcadores():
    """Página de bienvenida exclusiva para el control de remolcadores."""
    return render_template('home_remolcadores.html')

@login_required
@permiso_requerido('control_remolcadores')
@app.route('/control-remolcadores')
def control_remolcadores():
    """Muestra la planilla de control de remolcadores."""
    # Pasamos el rol del usuario a la plantilla para que el JavaScript sepa qué hacer.
    return render_template('control_remolcadores.html', rol_usuario=session.get('rol'))

@login_required
@permiso_requerido('programacion_cargue')
@app.route('/home-programacion')
def home_programacion():
    """Página de inicio para usuarios que solo ven la programación de cargue."""
    return render_template('home_programacion.html', nombre=session.get("nombre"))

@login_required
@permiso_requerido('programacion_cargue')
@app.route('/programacion-cargue')
def programacion_cargue():
    """Muestra la página de programación de vehículos."""
    return render_template('programacion_cargue.html', 
                           rol_usuario=session.get('rol'), 
                           email_usuario=session.get('email'),
                           nombre=session.get('nombre'))

@login_required
@permiso_requerido('programacion_cargue')
@app.route('/api/programacion', methods=['GET', 'POST'])
def handle_programacion():
    """Obtiene o crea registros de programación."""
    if request.method == 'POST':
        # Lógica para crear un nuevo registro vacío
        nuevo = ProgramacionCargue(ultimo_editor=session.get('nombre'))
        db.session.add(nuevo)
        db.session.commit()
        return jsonify(success=True, message="Nueva fila creada.", id=nuevo.id)
    
    # Lógica GET
    mostrar_todas = request.args.get('all', '0') == '1'
    query = ProgramacionCargue.query.order_by(ProgramacionCargue.fecha_programacion.desc())
    if not mostrar_todas:
        registros = query.limit(10).all()
    else:
        registros = query.all()
    # Convierte los datos a un formato JSON friendly
    data = []
    ahora = datetime.utcnow()
    for r in registros:
        fila = {}
        for c in r.__table__.columns:
            val = getattr(r, c.name)
            if isinstance(val, (datetime, date, time)):
                fila[c.name] = val.isoformat()
            else:
                fila[c.name] = val
        # Añadimos flag calculado: si ya pasaron 30 min desde completado
        if r.refineria_completado_en:
            fila['refineria_bloqueado'] = (ahora - r.refineria_completado_en) > timedelta(minutes=30)
        else:
            fila['refineria_bloqueado'] = False
        data.append(fila)
    return jsonify(data)

@login_required
@permiso_requerido('programacion_cargue')
@app.route('/api/programacion/<int:id>', methods=['PUT'])
def update_programacion(id):
    """Actualiza un registro de programación con permisos por campo. (VERSIÓN CORREGIDA)"""
    registro = ProgramacionCargue.query.get_or_404(id)
    data = request.get_json()
    
    # La lógica de permisos no necesita cambios, está bien.
    permisos = {
        'ops@conquerstrading.com': ['fecha_programacion', 'empresa_transportadora', 'placa', 'tanque', 'nombre_conductor', 'cedula_conductor', 'celular_conductor', 'hora_llegada_estimada', 'producto_a_cargar', 'numero_guia', 'destino', 'cliente', 'fecha_despacho','estado', 'galones', 'barriles', 'temperatura', 'api_obs', 'api_corregido', 'precintos', 'fecha_despacho'],
        'logistic@conquerstrading.com': ['fecha_programacion', 'empresa_transportadora', 'placa', 'tanque', 'nombre_conductor', 'cedula_conductor', 'celular_conductor', 'hora_llegada_estimada', 'producto_a_cargar', 'numero_guia', 'destino', 'cliente', 'fecha_despacho','estado', 'galones', 'barriles', 'temperatura', 'api_obs', 'api_corregido', 'precintos', 'fecha_despacho'],
        'production@conquerstrading.com': ['fecha_programacion', 'empresa_transportadora', 'placa', 'tanque', 'nombre_conductor', 'cedula_conductor', 'celular_conductor', 'hora_llegada_estimada', 'producto_a_cargar', 'numero_guia', 'destino', 'cliente', 'fecha_despacho','estado', 'galones', 'barriles', 'temperatura', 'api_obs', 'api_corregido', 'precintos', 'fecha_despacho'],
        'oci@conquerstrading.com': ['fecha_programacion', 'empresa_transportadora', 'placa', 'tanque', 'nombre_conductor', 'cedula_conductor', 'celular_conductor', 'hora_llegada_estimada', 'producto_a_cargar', 'numero_guia', 'destino', 'cliente', 'fecha_despacho'],
        'amariagallo@conquerstrading.com': ['destino', 'cliente'],
        'refinery.control@conquerstrading.com': ['estado', 'galones', 'barriles', 'temperatura', 'api_obs', 'api_corregido', 'precintos', 'fecha_despacho'],
        'qualitycontrol@conquerstrading.com': ['estado', 'galones', 'barriles', 'temperatura', 'api_obs', 'api_corregido', 'precintos']
    }
    
    campos_permitidos = permisos.get(session.get('email'), [])
    if session.get('rol') == 'admin':
        # El admin puede editar todos los campos excepto los de auditoría que son automáticos.
        campos_permitidos = [c.name for c in ProgramacionCargue.__table__.columns if c.name not in ['id', 'ultimo_editor', 'fecha_actualizacion']]

    if not campos_permitidos:
        return jsonify(success=False, message="No tienes permisos para editar."), 403

    try:
        # Bloqueo nuevo: si TODOS los campos de refinería estuvieron completos y pasaron >30 min, refinería ya no puede editar
        campos_refineria = ['estado','galones','barriles','temperatura','api_obs','api_corregido','precintos','fecha_despacho']
        ahora = datetime.utcnow()
        if registro.refineria_completado_en and (ahora - registro.refineria_completado_en) > timedelta(minutes=30):
            # Si quien intenta editar es refinería y el campo pertenece a su lista, bloquear
            if session.get('email') == 'refinery.control@conquerstrading.com':
                # Si intenta cambiar cualquier campo que sea suyo
                if any(campo in campos_refineria for campo in data.keys()):
                    return jsonify(success=False, message="Bloqueado: Han pasado más de 30 minutos desde que refinería completó todos sus campos."), 403

        # --- INICIO DE LA CORRECCIÓN ---
        campos_numericos = ['galones', 'barriles', 'temperatura', 'api_obs', 'api_corregido']

        for campo, valor in data.items():
            if campo in campos_permitidos:
                
                # 1. Manejo específico para la fecha de programación
                if campo == 'fecha_programacion'or campo == 'fecha_despacho':
                    # Convierte el string 'YYYY-MM-DD' a un objeto `date`
                    # Si el valor está vacío o es nulo, no hace nada para no borrar la fecha obligatoria.
                    if valor:
                        setattr(registro, campo, date.fromisoformat(valor))

                # 2. Manejo específico para la hora de llegada
                elif campo == 'hora_llegada_estimada':
                    # Si hay un valor, lo convierte a objeto `time`. Si no (el usuario lo borró), lo establece a None.
                    setattr(registro, campo, time.fromisoformat(valor) if valor else None)
                
                # 3. Manejo específico para todos los campos numéricos (float)
                elif campo in campos_numericos:
                    # Intenta convertir a float. Si el valor está vacío o no es un número, lo establece a None.
                    try:
                        setattr(registro, campo, float(valor) if valor is not None and valor != '' else None)
                    except (ValueError, TypeError):
                        setattr(registro, campo, None) # Si la conversión falla, pone None
                
                # 4. Para todos los demás campos (strings), simplemente asigna el valor
                else:
                    setattr(registro, campo, valor)

        # --- FIN DE LA CORRECCIÓN ---

        # Actualizar editor
        registro.ultimo_editor = session.get('nombre')

        # Evaluar completitud de refinería después de aplicar cambios
        def valor_lleno(v):
            return v not in (None, '')
        try:
            completo = all(valor_lleno(getattr(registro, f)) for f in campos_refineria)
        except Exception:
            completo = False

        if completo and not registro.refineria_completado_en:
            registro.refineria_completado_en = ahora
        elif not completo and registro.refineria_completado_en:
            # Si aún no ha pasado el bloqueo definitivo, permitir reiniciar el reloj
            if (ahora - registro.refineria_completado_en) <= timedelta(minutes=30):
                registro.refineria_completado_en = None

        db.session.commit()
        
        return jsonify(success=True, message="Registro actualizado correctamente.")

    except Exception as e:
        db.session.rollback()
        # Imprime el error en la consola del servidor para que puedas depurarlo
        print(f"ERROR AL ACTUALIZAR PROGRAMACIÓN: {e}") 
        return jsonify(success=False, message=f"Error interno del servidor: {str(e)}"), 500

@login_required
@permiso_requerido('programacion_cargue')
@app.route('/api/programacion/locks', methods=['GET'])
def listar_locks_programacion():
    # Limpieza de expirados
    locks = ProgramacionCargueLock.query.all()
    activos = []
    for l in locks:
        if l.expirado():
            db.session.delete(l)
        else:
            activos.append({
                'registro_id': l.registro_id,
                'campo': l.campo,
                'usuario': l.usuario,
                'timestamp': l.timestamp.isoformat()
            })
    db.session.commit()
    return jsonify(activos)

@login_required
@permiso_requerido('programacion_cargue')
@app.route('/api/programacion/lock', methods=['POST'])
def crear_lock_programacion():
    data = request.get_json() or {}
    registro_id = data.get('registro_id')
    campo = data.get('campo')
    if not registro_id or not campo:
        return jsonify(success=False, message='Datos incompletos'), 400
    nombre = session.get('nombre')
    lock = ProgramacionCargueLock.query.filter_by(registro_id=registro_id, campo=campo).first()
    if lock:
        if lock.expirado() or lock.usuario == nombre:
            lock.usuario = nombre
            lock.timestamp = datetime.utcnow()
            db.session.commit()
            return jsonify(success=True, message='Lock actualizado', usuario=nombre)
        return jsonify(success=False, message=f"Editando: {lock.usuario}"), 409
    nuevo = ProgramacionCargueLock(registro_id=registro_id, campo=campo, usuario=nombre)
    db.session.add(nuevo)
    db.session.commit()
    return jsonify(success=True, message='Lock creado', usuario=nombre)

@login_required
@permiso_requerido('programacion_cargue')
@app.route('/api/programacion/lock', methods=['DELETE'])
def borrar_lock_programacion():
    registro_id = request.args.get('registro_id', type=int)
    campo = request.args.get('campo')
    if not registro_id or not campo:
        return jsonify(success=False, message='Datos incompletos'), 400
    nombre = session.get('nombre')
    lock = ProgramacionCargueLock.query.filter_by(registro_id=registro_id, campo=campo).first()
    if lock:
        if lock.usuario == nombre or lock.expirado():
            db.session.delete(lock)
            db.session.commit()
            return jsonify(success=True, message='Lock liberado')
        return jsonify(success=False, message='No puedes liberar lock de otro usuario'), 403
    return jsonify(success=True, message='No existe lock')

@login_required
@permiso_requerido('programacion_cargue')
@app.route('/api/programacion/live_edit', methods=['POST'])
def registrar_live_edit_programacion():
    """Recibe el texto que el usuario está escribiendo en tiempo real (sin guardar todavía)."""
    data = request.get_json() or {}
    registro_id = data.get('registro_id')
    campo = data.get('campo')
    valor = data.get('valor')
    if not registro_id or not campo:
        return jsonify(success=False, message='Datos incompletos'), 400
    _purge_live_edits()
    LIVE_EDITS[(int(registro_id), campo)] = {
        'registro_id': int(registro_id),
        'campo': campo,
        'valor': valor if valor is not None else '',
        'usuario': session.get('nombre'),
        'timestamp': datetime.utcnow()
    }
    return jsonify(success=True)

@login_required
@permiso_requerido('programacion_cargue')
@app.route('/api/programacion/live_edits', methods=['GET'])
def obtener_live_edits_programacion():
    """Devuelve todas las ediciones activas (texto parcial) y locks vigentes."""
    _purge_live_edits()
    edits = list(LIVE_EDITS.values())
    # Serializar timestamp
    for e in edits:
        e['timestamp'] = e['timestamp'].isoformat()
    return jsonify({'edits': edits})
    
@login_required
@permiso_requerido('programacion_cargue')
@app.route('/exportar_programacion_cargue/<string:formato>')
def exportar_programacion_cargue(formato):
    """
    Genera un reporte de Programación de Cargue en Excel o PDF,
    filtrando por un rango de fechas si se proporciona.
    """
    try:
        # Leemos las fechas desde los parámetros de la URL.
        fecha_inicio_str = request.args.get('fecha_inicio')
        fecha_fin_str = request.args.get('fecha_fin')

        # Empezamos la consulta base.
        query = ProgramacionCargue.query

        # Aplicamos el filtro de fecha de inicio si existe.
        if fecha_inicio_str:
            fecha_inicio_obj = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
            query = query.filter(ProgramacionCargue.fecha_programacion >= fecha_inicio_obj)

        # Aplicamos el filtro de fecha de fin si existe.
        if fecha_fin_str:
            fecha_fin_obj = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
            query = query.filter(ProgramacionCargue.fecha_programacion <= fecha_fin_obj)

        # Ejecutamos la consulta final ya filtrada.
        registros = query.order_by(ProgramacionCargue.fecha_programacion.desc()).all()

    except Exception as e:
        flash(f"Error al procesar las fechas: {e}", "danger")
        return redirect(url_for('programacion_cargue'))

    if not registros:
        flash("No hay registros para generar un reporte con el filtro seleccionado.", "warning")
        return redirect(url_for('programacion_cargue'))

    # 2. Lógica para generar el archivo EXCEL
    if formato == 'excel':
        # Preparamos los datos en una lista de diccionarios
        datos_para_df = [{
            'Fecha Programación': r.fecha_programacion.strftime('%Y-%m-%d') if r.fecha_programacion else '',
            'Hora Estimada': r.hora_llegada_estimada.strftime('%H:%M') if r.hora_llegada_estimada else '',
            'Empresa Transportadora': r.empresa_transportadora,
            'Placa': r.placa,
            'Conductor': r.nombre_conductor,
            'Cédula': r.cedula_conductor,
            'Celular': r.celular_conductor,
            'Producto': r.producto_a_cargar,
            'Destino': r.destino,
            'Cliente': r.cliente,
            'Estado': r.estado,
            'Fecha Despacho': r.fecha_despacho,
            'Número Guía': r.numero_guia,
            'Galones': r.galones,
            'Barriles': r.barriles,
            'Temperatura': r.temperatura,
            'API Observado': r.api_obs,
            'API Corregido': r.api_corregido,
            'Precintos': r.precintos,
            'Último Editor': r.ultimo_editor,
            'Fecha Actualización': r.fecha_actualizacion.strftime('%Y-%m-%d %H:%M') if r.fecha_actualizacion else ''
        } for r in registros]

        df = pd.DataFrame(datos_para_df)

        # Creamos el archivo Excel en memoria
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Programacion_Cargue')
        output.seek(0)

        # Enviamos el archivo al navegador
        filename = f"reporte_programacion_cargue_{date.today().strftime('%Y-%m-%d')}.xlsx"
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )

    # 3. Lógica para generar el archivo PDF
    elif formato == 'pdf':
        # Cargar logo en base64 (igual que otros reportes)
        logo_base64 = None
        try:
            logo_path = os.path.join(current_app.root_path, 'static', 'Logo_de_empresa.jpeg')
            if os.path.exists(logo_path):
                with open(logo_path, 'rb') as f:
                    import base64
                    logo_base64 = base64.b64encode(f.read()).decode('utf-8')
        except Exception as e:
            print(f"Error cargando logo para programación cargue: {e}")

        # Renderizamos una plantilla HTML especial para el PDF
        html_para_pdf = render_template(
            'reportes_pdf/programacion_cargue_pdf.html',
            registros=registros,
            fecha_reporte=datetime.now().strftime('%d de %B de %Y'),
            logo_base64=logo_base64
        )

        # Usamos WeasyPrint para convertir el HTML a PDF (base_url para recursos relativos)
        pdf = HTML(string=html_para_pdf, base_url=current_app.root_path).write_pdf()
        
        # Devolvemos el PDF como una descarga
        return Response(
            pdf,
            mimetype='application/pdf',
            headers={'Content-Disposition': 'attachment;filename=reporte_programacion_cargue.pdf'}
        )

    # Si el formato no es ni 'excel' ni 'pdf', redirigimos
    return redirect(url_for('programacion_cargue'))

@login_required
@permiso_requerido('programacion_cargue')
@app.route('/api/programacion/<int:id>', methods=['DELETE'])
def delete_programacion(id):
    """Elimina un registro de programación de cargue."""
    # Solo pueden eliminar Juliana (ops), Ignacio (production) y Samantha (logistic)
    usuarios_autorizados = {
        'ops@conquerstrading.com',
        'production@conquerstrading.com',
        'logistic@conquerstrading.com'
    }
    if session.get('email') not in usuarios_autorizados and session.get('rol') != 'admin':
        return jsonify(success=False, message='No tienes permiso para eliminar registros.'), 403

    registro = ProgramacionCargue.query.get_or_404(id)

    # Bloqueo: si último editor fue Refinería y han pasado >30 min, prohibir eliminación (para todos)
    if registro.ultimo_editor and registro.ultimo_editor.strip().lower() == 'control refineria':
        if registro.fecha_actualizacion and (datetime.utcnow() - registro.fecha_actualizacion) > timedelta(minutes=30):
            return jsonify(success=False, message='Registro bloqueado: no puede eliminarse después de 30 minutos de la edición de Refinería.'), 403
    try:
        db.session.delete(registro)
        db.session.commit()
        return jsonify(success=True, message="Registro eliminado correctamente.")
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, message=str(e)), 500

@login_required
@permiso_requerido('programacion_cargue')
@app.route('/reporte_grafico_despachos')
def reporte_grafico_despachos():
    today = date.today()
    fecha_inicio_str = request.args.get('fecha_inicio', '')
    fecha_fin_str = request.args.get('fecha_fin', '')
    mes_str = request.args.get('mes', '')  # formato esperado YYYY-MM
    cliente_filtro = request.args.get('cliente', '')
    tipo_grafico = request.args.get('tipo', 'bar')  # 'bar' (horizontal) o 'pie'
    producto_filtro = request.args.get('producto', 'ambos').lower()  # 'ambos' | 'fo4' | 'diluyente'

    # Prioridad: si se elige mes, se ignoran fechas individuales
    fecha_inicio = None
    fecha_fin = None
    if mes_str:
        try:
            anio, mes = map(int, mes_str.split('-'))
            fecha_inicio = date(anio, mes, 1)
            # calcular último día del mes
            if mes == 12:
                fecha_fin = date(anio, 12, 31)
            else:
                fecha_fin = date(anio, mes + 1, 1) - timedelta(days=1)
        except Exception:
            fecha_inicio = None
            fecha_fin = None
    else:
        # Si no hay fechas, no filtrar por fecha (mostrar todo)
        if fecha_inicio_str:
            try:
                fecha_inicio = date.fromisoformat(fecha_inicio_str)
            except (ValueError, TypeError):
                fecha_inicio = None
        if fecha_fin_str:
            try:
                fecha_fin = date.fromisoformat(fecha_fin_str)
            except (ValueError, TypeError):
                fecha_fin = None

    # Obtener lista de clientes únicos
    clientes = [c[0] for c in db.session.query(ProgramacionCargue.cliente).distinct().filter(ProgramacionCargue.cliente.isnot(None)).all() if c[0]]
    clientes = sorted(clientes)

    # Consulta agrupada por cliente (para el gráfico principal)
    query = db.session.query(
        ProgramacionCargue.cliente,
        func.sum(ProgramacionCargue.barriles).label('total_barriles')
    ).filter(
        ProgramacionCargue.estado == 'DESPACHADO',
        ProgramacionCargue.cliente.isnot(None),
        ProgramacionCargue.barriles.isnot(None)
    )
    # Filtro por producto (FO4, Diluyente, Ambos)
    if producto_filtro == 'fo4':
        query = query.filter(ProgramacionCargue.producto_a_cargar.isnot(None), ProgramacionCargue.producto_a_cargar.ilike('%FO4%'))
    elif producto_filtro == 'diluyente':
        query = query.filter(ProgramacionCargue.producto_a_cargar.isnot(None), ProgramacionCargue.producto_a_cargar.ilike('%DILUYENTE%'))
    else:  # ambos
        query = query.filter(ProgramacionCargue.producto_a_cargar.isnot(None), (
            ProgramacionCargue.producto_a_cargar.ilike('%FO4%') | ProgramacionCargue.producto_a_cargar.ilike('%DILUYENTE%')
        ))
    if fecha_inicio:
        query = query.filter(ProgramacionCargue.fecha_despacho >= fecha_inicio)
    if fecha_fin:
        query = query.filter(ProgramacionCargue.fecha_despacho <= fecha_fin)
    if cliente_filtro:
        query = query.filter(ProgramacionCargue.cliente == cliente_filtro)
    datos_despacho = query.group_by(ProgramacionCargue.cliente).order_by(func.sum(ProgramacionCargue.barriles).desc()).all()

    # Resumen por producto para el cliente seleccionado
    resumen_productos = []
    if cliente_filtro:
        resumen_query = db.session.query(
            ProgramacionCargue.producto_a_cargar,
            func.sum(ProgramacionCargue.barriles).label('total_barriles')
        ).filter(
            ProgramacionCargue.estado == 'DESPACHADO',
            ProgramacionCargue.cliente == cliente_filtro,
            ProgramacionCargue.producto_a_cargar.isnot(None),
            ProgramacionCargue.barriles.isnot(None)
        )
        if fecha_inicio:
            resumen_query = resumen_query.filter(ProgramacionCargue.fecha_despacho >= fecha_inicio)
        if fecha_fin:
            resumen_query = resumen_query.filter(ProgramacionCargue.fecha_despacho <= fecha_fin)
        resumen_productos = resumen_query.group_by(ProgramacionCargue.producto_a_cargar).order_by(func.sum(ProgramacionCargue.barriles).desc()).all()

    grafico_base64 = None
    total_box_text = None  # Texto para tarjeta externa (solo barras)
    total_barriles_general = 0
    if datos_despacho:
        clientes_graf = [resultado[0] for resultado in datos_despacho]
        barriles = [float(resultado[1]) for resultado in datos_despacho]
        total_barriles_general = sum(barriles)
        # Periodo para títulos
        if fecha_inicio and fecha_fin:
            periodo = f"{fecha_inicio.strftime('%d/%m/%Y')} - {fecha_fin.strftime('%d/%m/%Y')}"
        elif fecha_inicio:
            periodo = f"Desde {fecha_inicio.strftime('%d/%m/%Y')}"
        elif fecha_fin:
            periodo = f"Hasta {fecha_fin.strftime('%d/%m/%Y')}"
        else:
            periodo = "Todo el periodo"

        # ---- Calcular FO4 y Diluyente por cliente (solo si se muestran ambos) ----
        fo4_vals = []
        diluyente_vals = []
        fo4_total_general = 0
        diluyente_total_general = 0
        if producto_filtro == 'ambos':
            base_filters = [
                ProgramacionCargue.estado == 'DESPACHADO',
                ProgramacionCargue.cliente.isnot(None),
                ProgramacionCargue.barriles.isnot(None),
                ProgramacionCargue.producto_a_cargar.isnot(None)
            ]
            fo4_query = db.session.query(
                ProgramacionCargue.cliente,
                func.sum(ProgramacionCargue.barriles).label('fo4_barriles')
            ).filter(*base_filters, ProgramacionCargue.producto_a_cargar.ilike('%FO4%'))
            dil_query = db.session.query(
                ProgramacionCargue.cliente,
                func.sum(ProgramacionCargue.barriles).label('dil_barriles')
            ).filter(*base_filters, ProgramacionCargue.producto_a_cargar.ilike('%DILUYENTE%'))
            if fecha_inicio:
                fo4_query = fo4_query.filter(ProgramacionCargue.fecha_despacho >= fecha_inicio)
                dil_query = dil_query.filter(ProgramacionCargue.fecha_despacho >= fecha_inicio)
            if fecha_fin:
                fo4_query = fo4_query.filter(ProgramacionCargue.fecha_despacho <= fecha_fin)
                dil_query = dil_query.filter(ProgramacionCargue.fecha_despacho <= fecha_fin)
            if cliente_filtro:
                fo4_query = fo4_query.filter(ProgramacionCargue.cliente == cliente_filtro)
                dil_query = dil_query.filter(ProgramacionCargue.cliente == cliente_filtro)
            fo4_map = {c: float(v) for c, v in fo4_query.group_by(ProgramacionCargue.cliente).all()}
            dil_map = {c: float(v) for c, v in dil_query.group_by(ProgramacionCargue.cliente).all()}
            fo4_vals = [fo4_map.get(c, 0.0) for c in clientes_graf]
            diluyente_vals = [dil_map.get(c, 0.0) for c in clientes_graf]
            fo4_total_general = sum(fo4_vals)
            diluyente_total_general = sum(diluyente_vals)

        if tipo_grafico == 'pie':
            import numpy as np
            from matplotlib import cm
            fig, ax = plt.subplots(figsize=(16, 16))
            # Paletas según producto seleccionado
            if producto_filtro == 'fo4':
                colors = ['#ff9f43'] * len(barriles)
            elif producto_filtro == 'diluyente':
                colors = ['#1d7ed6'] * len(barriles)
            else:  # ambos
                colors = cm.Blues(np.linspace(0.35, 0.85, len(barriles)))

            # Etiquetas incluyendo FO4 cuando exista
            etiquetas = []
            if producto_filtro == 'ambos':
                for i, c in enumerate(clientes_graf):
                    partes = []
                    if fo4_vals[i] > 0:
                        partes.append(f"FO4 {fo4_vals[i]:,.0f}")
                    if diluyente_vals[i] > 0:
                        partes.append(f"DIL {diluyente_vals[i]:,.0f}")
                    etiquetas.append(f"{c}\n" + ' | '.join(partes) if partes else c)
            else:
                etiquetas = clientes_graf

            def autopct_func(pct):
                valor_abs = pct * total_barriles_general / 100.0
                return f"{pct:.1f}%\n{valor_abs:,.0f}"

            wedges, texts, autotexts = ax.pie(
                barriles,
                labels=etiquetas,
                startangle=150,
                colors=colors,
                autopct=autopct_func,
                pctdistance=0.72,
                labeldistance=1.1,
                wedgeprops={'linewidth': 1, 'edgecolor': 'white'}
            )
            # Donut interior
            centro = plt.Circle((0, 0), 0.48, fc='white')
            fig.gca().add_artist(centro)
            texto_centro = f"TOTAL\n{total_barriles_general:,.0f} BBL"
            fig.text(0.5, 0.5, texto_centro, ha='center', va='center', fontsize=18, fontweight='bold', color='#0b8552')
            titulo = "Distribución de Despachos (Donut)"
            if producto_filtro == 'fo4':
                titulo += " – FO4"
            elif producto_filtro == 'diluyente':
                titulo += " – Diluyente"
            elif fo4_total_general > 0 or diluyente_total_general > 0:
                titulo += " – FO4 + Diluyente"
            ax.set_title(f"{titulo}\nPeriodo: {periodo}", fontsize=20, pad=28, fontweight='bold')
            for t in texts:
                t.set_fontsize(9.5)
            for at in autotexts:
                at.set_fontsize(9)
        else:
            # --- Barras horizontales mejoradas ---
            from matplotlib.ticker import FuncFormatter
            from matplotlib.colors import LinearSegmentedColormap
            altura = max(10, len(clientes_graf) * 0.75)
            fig, ax = plt.subplots(figsize=(32, altura))
            cmap = LinearSegmentedColormap.from_list('verde_prof', ['#0b8552', '#3bbf84'])
            max_val = max(barriles)
            min_val = min(barriles)
            if max_val == min_val:
                norm_vals = [0.6 for _ in barriles]
            else:
                norm_vals = [(v - min_val) / (max_val - min_val) for v in barriles]
            y_pos = list(range(len(clientes_graf)))
            labels_rank = [f"{i+1}. {c}" for i, c in enumerate(clientes_graf)]
            if producto_filtro == 'ambos':
                # Barras apiladas FO4 y Diluyente
                bars_dil = ax.barh(
                    y_pos,
                    diluyente_vals,
                    color=[cmap(n) for n in norm_vals],
                    edgecolor='#0b8552', linewidth=0.5, height=0.72, label='Diluyente'
                )
                bars_fo4 = ax.barh(
                    y_pos,
                    fo4_vals,
                    left=diluyente_vals,
                    color='#ff9f43', edgecolor='#c86e00', linewidth=0.5, height=0.72, label='FO4'
                )
                # Etiquetas internas por segmento (Diluyente y FO4)
                umbral_seg = max_val * 0.035 if max_val > 0 else 0
                for i, (dil, fo4) in enumerate(zip(diluyente_vals, fo4_vals)):
                    if dil > 0 and dil >= umbral_seg:
                        ax.text(dil / 2, i, f"DIL {dil:,.0f}", ha='center', va='center', color='white', fontsize=10, fontweight='bold')
                    if fo4 > 0 and fo4 >= umbral_seg:
                        ax.text(dil + fo4 / 2, i, f"FO4 {fo4:,.0f}", ha='center', va='center', color='white', fontsize=10, fontweight='bold')
            else:
                color_single = '#ff9f43' if producto_filtro == 'fo4' else '#1d7ed6'
                bars_single = ax.barh(
                    y_pos,
                    barriles,
                    color=[color_single] * len(barriles),
                    edgecolor='#0b8552', linewidth=0.6, height=0.72,
                    label='FO4' if producto_filtro == 'fo4' else 'Diluyente'
                )
            ax.set_yticks(y_pos)
            ax.set_yticklabels(labels_rank, fontsize=12)
            ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _ : f'{x:,.0f}'))
            ax.set_xlabel('Barriles despachados', fontweight='bold', fontsize=14, labelpad=12)
            titulo_bar = "Total de Barriles Despachados por Cliente"
            if producto_filtro == 'fo4':
                titulo_bar += " – FO4"
            elif producto_filtro == 'diluyente':
                titulo_bar += " – Diluyente"
            elif producto_filtro == 'ambos':
                titulo_bar += " – FO4 + Diluyente"
            ax.set_title(f"{titulo_bar}\nPeriodo: {periodo}", fontsize=20, pad=22, fontweight='bold')
            total_box_text = f"TOTAL {total_barriles_general:,.2f} BBL"
            if producto_filtro == 'ambos':
                for i, (dil, fo4) in enumerate(zip(diluyente_vals, fo4_vals)):
                    total_width = dil + fo4
                    ax.text(total_width + (max_val * 0.008), i, f'{total_width:,.2f}', ha='left', va='center', color='#0b8552', fontweight='bold', fontsize=11)
                ax.legend(loc='lower right')
            else:
                for i, total_width in enumerate(barriles):
                    ax.text(total_width + (max_val * 0.008), i, f'{total_width:,.2f}', ha='left', va='center', color='#0b8552', fontweight='bold', fontsize=11)
                ax.legend(loc='lower right')
            ax.invert_yaxis()
            for spine in ['top', 'right', 'left']:
                ax.spines[spine].set_visible(False)
            ax.spines['bottom'].set_color('#9aa0ac')
            ax.tick_params(axis='y', length=0)
            ax.xaxis.grid(True, linestyle='--', linewidth=0.6, alpha=0.35)
            ax.set_axisbelow(True)
            ax.set_facecolor('#fcfdfd')
            fig.patch.set_facecolor('#ffffff')

    # Margen y ajuste de layout
    plt.tight_layout(rect=[0.03, 0.02, 0.98, 0.95])
    grafico_base64 = convertir_plot_a_base64(fig)

    return render_template(
        'reporte_grafico_despachos.html',
        grafico_base64=grafico_base64,
        datos_tabla=datos_despacho,
        total_barriles=total_barriles_general,
    total_box_text=total_box_text,
        filtros={
            'fecha_inicio': fecha_inicio.isoformat() if (fecha_inicio_str and fecha_inicio and not mes_str) else '',
            'fecha_fin': fecha_fin.isoformat() if (fecha_fin_str and fecha_fin and not mes_str) else '',
            'mes': mes_str,
        'cliente': cliente_filtro,
            'producto': producto_filtro
        },
        clientes=clientes,
        resumen_productos=resumen_productos,
    now=datetime.now(),
    tipo=tipo_grafico,
    producto=producto_filtro
    )

@login_required
@permiso_requerido('programacion_cargue')
@app.route('/descargar_reporte_grafico_despachos_pdf')
def descargar_reporte_grafico_despachos_pdf():
    # Parámetros y lógica equivalente a la vista HTML
    today = date.today()
    fecha_inicio_str = request.args.get('fecha_inicio', '')
    fecha_fin_str = request.args.get('fecha_fin', '')
    mes_str = request.args.get('mes', '')
    cliente_filtro = request.args.get('cliente', '')
    producto_filtro = request.args.get('producto', 'ambos').lower()  # ambos | fo4 | diluyente
    tipo_grafico = request.args.get('tipo', 'bar')

    fecha_inicio = None
    fecha_fin = None
    if mes_str:
        try:
            anio, mes = map(int, mes_str.split('-'))
            fecha_inicio = date(anio, mes, 1)
            fecha_fin = date(anio, mes, 28) + timedelta(days=4)
            fecha_fin = fecha_fin - timedelta(days=fecha_fin.day)
        except Exception:
            fecha_inicio = None
            fecha_fin = None
    else:
        if fecha_inicio_str:
            try:
                fecha_inicio = date.fromisoformat(fecha_inicio_str)
            except Exception:
                fecha_inicio = None
        if fecha_fin_str:
            try:
                fecha_fin = date.fromisoformat(fecha_fin_str)
            except Exception:
                fecha_fin = None

    base_query = db.session.query(
        ProgramacionCargue.cliente,
        func.sum(ProgramacionCargue.barriles).label('total_barriles')
    ).filter(
        ProgramacionCargue.estado == 'DESPACHADO',
        ProgramacionCargue.cliente.isnot(None),
        ProgramacionCargue.barriles.isnot(None),
        ProgramacionCargue.producto_a_cargar.isnot(None)
    )
    if producto_filtro == 'fo4':
        base_query = base_query.filter(ProgramacionCargue.producto_a_cargar.ilike('%FO4%'))
    elif producto_filtro == 'diluyente':
        base_query = base_query.filter(ProgramacionCargue.producto_a_cargar.ilike('%DILUYENTE%'))
    else:
        base_query = base_query.filter(
            ProgramacionCargue.producto_a_cargar.ilike('%FO4%') | ProgramacionCargue.producto_a_cargar.ilike('%DILUYENTE%')
        )
    if fecha_inicio:
        base_query = base_query.filter(ProgramacionCargue.fecha_despacho >= fecha_inicio)
    if fecha_fin:
        base_query = base_query.filter(ProgramacionCargue.fecha_despacho <= fecha_fin)
    if cliente_filtro:
        base_query = base_query.filter(ProgramacionCargue.cliente == cliente_filtro)
    datos_despacho = base_query.group_by(ProgramacionCargue.cliente).order_by(func.sum(ProgramacionCargue.barriles).desc()).all()

    total_barriles_general = sum(float(r[1]) for r in datos_despacho) if datos_despacho else 0

    grafico_base64 = None
    total_box_text = None
    tabla_detalle = []  # (cliente, diluyente, fo4, total)
    total_fo4 = 0.0
    total_dil = 0.0

    if datos_despacho:
        clientes_graf = [r[0] for r in datos_despacho]
        barriles = [float(r[1]) for r in datos_despacho]
        # Mapas por producto (calculamos siempre para poder mostrar columnas aun si se filtró uno)
        def build_product_map(pattern):
            q = db.session.query(ProgramacionCargue.cliente, func.sum(ProgramacionCargue.barriles).label('val')).filter(
                ProgramacionCargue.estado=='DESPACHADO',
                ProgramacionCargue.barriles.isnot(None),
                ProgramacionCargue.producto_a_cargar.isnot(None),
                ProgramacionCargue.producto_a_cargar.ilike(pattern)
            )
            if fecha_inicio:
                q = q.filter(ProgramacionCargue.fecha_despacho >= fecha_inicio)
            if fecha_fin:
                q = q.filter(ProgramacionCargue.fecha_despacho <= fecha_fin)
            if cliente_filtro:
                q = q.filter(ProgramacionCargue.cliente==cliente_filtro)
            return {c: float(v) for c,v in q.group_by(ProgramacionCargue.cliente).all()}
        fo4_map = build_product_map('%FO4%')
        dil_map = build_product_map('%DILUYENTE%')
        fo4_vals = [fo4_map.get(c,0.0) for c in clientes_graf]
        dil_vals = [dil_map.get(c,0.0) for c in clientes_graf]
        total_fo4 = sum(fo4_vals)
        total_dil = sum(dil_vals)
        # Construir tabla detalle
        for c, d, f in zip(clientes_graf, dil_vals, fo4_vals):
            tabla_detalle.append((c, d, f, d+f))
        # Crear gráfico (solo barras para PDF por estabilidad)
        from matplotlib.colors import LinearSegmentedColormap
        from matplotlib.ticker import FuncFormatter
        altura = max(10, len(clientes_graf) * 0.75)
        fig, ax = plt.subplots(figsize=(24, altura))
        cmap = LinearSegmentedColormap.from_list('dil_cmap', ['#1d7ed6', '#63b3ff'])
        max_val = max(barriles)
        min_val = min(barriles)
        norm_vals = [0.5 if max_val==min_val else (v-min_val)/(max_val-min_val) for v in barriles]
        y_pos = list(range(len(clientes_graf)))
        labels_rank = [f"{i+1}. {c}" for i,c in enumerate(clientes_graf)]
        if producto_filtro == 'fo4':
            ax.barh(y_pos, fo4_vals, color='#ff9f43', edgecolor='#c86e00', height=0.68, label='FO4')
        elif producto_filtro == 'diluyente':
            ax.barh(y_pos, dil_vals, color=[cmap(n) for n in norm_vals], edgecolor='#0b3d66', height=0.68, label='Diluyente')
        else:  # ambos
            ax.barh(y_pos, dil_vals, color=[cmap(n) for n in norm_vals], edgecolor='#0b3d66', height=0.68, label='Diluyente')
            ax.barh(y_pos, fo4_vals, left=dil_vals, color='#ff9f43', edgecolor='#c86e00', height=0.68, label='FO4')
        if producto_filtro == 'ambos':
            ax.legend(loc='lower right', frameon=False, fontsize=10)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels_rank, fontsize=11)
        ax.xaxis.set_major_formatter(FuncFormatter(lambda x,_: f"{x:,.0f}"))
        ax.set_xlabel('Barriles despachados', fontweight='bold')
        titulo_pdf = 'Total Despachado por Cliente'
        if producto_filtro=='ambos':
            titulo_pdf += ' – FO4 + Diluyente'
        elif producto_filtro=='fo4':
            titulo_pdf += ' – FO4'
        else:
            titulo_pdf += ' – Diluyente'
        ax.set_title(titulo_pdf, fontweight='bold', fontsize=16, pad=16)
        # Etiquetas finales
        totales_linea = [d+f for d,f in zip(dil_vals, fo4_vals)]
        for i,v in enumerate(totales_linea):
            ax.text(v + (max_val*0.006), i, f"{v:,.0f}", va='center', fontsize=9, color='#0b3d66')
        if producto_filtro=='ambos':
            for i,(d,f) in enumerate(zip(dil_vals, fo4_vals)):
                umbral_seg = max_val * 0.05 if max_val>0 else 0
                if d>0 and d>=umbral_seg:
                    ax.text(d/2, i, f"DIL {d:,.0f}", ha='center', va='center', color='white', fontsize=7, fontweight='bold')
                if f>0 and f>=umbral_seg:
                    ax.text(d+f/2, i, f"FO4 {f:,.0f}", ha='center', va='center', color='white', fontsize=7, fontweight='bold')
        ax.invert_yaxis()
        ax.xaxis.grid(True, linestyle='--', alpha=0.3)
        for spine in ['top','right','left']:
            ax.spines[spine].set_visible(False)
        fig.patch.set_facecolor('#ffffff')
        plt.tight_layout()
        grafico_base64 = convertir_plot_a_base64(fig)
        # Texto total
        total_box_text = f"TOTAL {total_barriles_general:,.2f} BBL"\
            + (f" | FO4 {total_fo4:,.0f} BBL" if total_fo4>0 else '')\
            + (f" | Diluyente {total_dil:,.0f} BBL" if total_dil>0 else '')

    periodo_txt = 'Todo el periodo'
    if fecha_inicio and fecha_fin:
        periodo_txt = f"{fecha_inicio.strftime('%d/%m/%Y')} - {fecha_fin.strftime('%d/%m/%Y')}"
    elif fecha_inicio:
        periodo_txt = f"Desde {fecha_inicio.strftime('%d/%m/%Y')}"
    elif fecha_fin:
        periodo_txt = f"Hasta {fecha_fin.strftime('%d/%m/%Y')}"

    # Obtener logo como base64
    logo_base64 = None
    try:
        logo_path = os.path.join(current_app.root_path, 'static', 'Logo_de_empresa.jpeg')
        if os.path.exists(logo_path):
            import base64
            with open(logo_path, 'rb') as f:
                logo_base64 = base64.b64encode(f.read()).decode('utf-8')
    except Exception:
        logo_base64 = None

    html_para_pdf = render_template(
        'reportes_pdf/reporte_grafico_despachos_pdf.html',
    grafico_base64=grafico_base64,
    datos_tabla=tabla_detalle,
        total_barriles=total_barriles_general,
        total_box_text=total_box_text,
        periodo=periodo_txt,
        producto=producto_filtro,
        tipo=tipo_grafico,
        fecha_generacion=datetime.now().strftime('%d/%m/%Y %H:%M'),
        logo_base64=logo_base64
    )
    # Proveer base_url para que recursos relativos funcionen si se agregan
    pdf = HTML(string=html_para_pdf, base_url=current_app.root_path).write_pdf()
    return Response(pdf, mimetype='application/pdf', headers={'Content-Disposition':'attachment;filename=reporte_grafico_despachos.pdf'})
  
@login_required
@permiso_requerido('inventario_epp')
@app.route('/inventario_epp_home')
def inventario_epp_home():
    """Página de inicio para el módulo de inventario EPP."""
    return render_template('inventario_epp_home.html', nombre=session.get("nombre"))

@login_required
@permiso_requerido('inventario_epp')
@app.route('/inventario_epp')
def inventario_epp():
    """Página principal para gestionar el inventario de EPP."""
    return render_template('inventario_epp.html', nombre=session.get("nombre"))

@login_required
@permiso_requerido('inventario_epp')
@app.route('/epp_asignaciones')
def epp_asignaciones():
    """Página para ver el historial de asignaciones de EPP."""
    return render_template('epp_asignaciones.html', nombre=session.get("nombre"))

@login_required
@permiso_requerido('inventario_epp')
@app.route('/api/epp/items', methods=['GET'])
def get_epp_items():
    """API para obtener todos los items del inventario con alertas inteligentes."""
    items_query = EPPItem.query.order_by(EPPItem.categoria, EPPItem.nombre).all()
    
    today = date.today()
    items_list = []
    for item in items_query:
        item_dict = {
            "id": item.id,
            "nombre": item.nombre,
            "categoria": item.categoria,
            "referencia": item.referencia,
            "talla": item.talla,
            "stock_actual": item.stock_actual,
            "observaciones": item.observaciones,
            "fecha_vencimiento": item.fecha_vencimiento.isoformat() if item.fecha_vencimiento else None,
            "dias_para_vencer": (item.fecha_vencimiento - today).days if item.fecha_vencimiento else None,
            # Alerta de stock bajo solo si NO es Equipos de Emergencia
            "stock_bajo": (item.categoria != 'Equipos de Emergencia') and (item.stock_actual <= 5)
        }
        items_list.append(item_dict)
    return jsonify(items_list)

@login_required
@permiso_requerido('inventario_epp')
@app.route('/api/epp/items', methods=['POST'])
def create_epp_item():
    """API para crear un nuevo item en el inventario."""
    data = request.get_json()
    try:
        nuevo_item = EPPItem(
            nombre=data['nombre'],
            categoria=data['categoria'],
            referencia=data.get('referencia'),
            talla=data.get('talla'),
            stock_actual=int(data.get('stock_actual', 0)),
            fecha_vencimiento=date.fromisoformat(data['fecha_vencimiento']) if data.get('fecha_vencimiento') else None,
            observaciones=data.get('observaciones')
        )
        db.session.add(nuevo_item)
        db.session.commit()
        return jsonify(success=True, message="Item creado exitosamente.", id=nuevo_item.id)
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, message=f"Error al crear: {str(e)}"), 500

@login_required
@permiso_requerido('inventario_epp')
@app.route('/api/epp/items/<int:id>', methods=['PUT'])
def update_epp_item(id):
    """API para actualizar un item existente."""
    item = EPPItem.query.get_or_404(id)
    data = request.get_json()
    try:
        for key, value in data.items():
            if key == 'fecha_vencimiento':
                value = date.fromisoformat(value) if value else None
            if hasattr(item, key):
                setattr(item, key, value)
        db.session.commit()
        return jsonify(success=True, message="Item actualizado.")
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, message=f"Error al actualizar: {str(e)}"), 500

@login_required
@permiso_requerido('inventario_epp')
@app.route('/api/epp/asignar', methods=['POST'])
def assign_epp_item():
    """API para asignar un item a un empleado y descontar del stock."""
    data = request.get_json()
    item_id = data.get('item_id')
    cantidad_a_entregar = int(data.get('cantidad_entregada', 0))
    item = EPPItem.query.get_or_404(item_id)

    if cantidad_a_entregar <= 0:
        return jsonify(success=False, message="La cantidad debe ser mayor a cero."), 400
    if item.stock_actual < cantidad_a_entregar:
        return jsonify(success=False, message=f"Stock insuficiente. Disponible: {item.stock_actual}."), 400

    try:
        # 1. Descontar del stock
        item.stock_actual -= cantidad_a_entregar

        # 2. Crear el registro de la asignación
        nueva_asignacion = EPPAssignment(
            item_id=item_id,
            empleado_nombre=data['empleado_nombre'],
            cantidad_entregada=cantidad_a_entregar,
            fecha_entrega=date.fromisoformat(data['fecha_entrega']),
            observaciones=data.get('observaciones')
        )
        db.session.add(nueva_asignacion)
        db.session.commit()
        return jsonify(success=True, message="Asignación registrada y stock actualizado.")
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, message=f"Error en la asignación: {str(e)}"), 500

@login_required
@permiso_requerido('inventario_epp')
@app.route('/api/epp/asignaciones', methods=['GET'])
def get_epp_assignments():
    """API para obtener el historial de asignaciones."""
    query = db.session.query(EPPAssignment).join(EPPItem).order_by(EPPAssignment.fecha_entrega.desc())
    
    # Ejemplo de filtro por empleado
    empleado = request.args.get('empleado')
    if empleado:
        query = query.filter(EPPAssignment.empleado_nombre.ilike(f'%{empleado}%'))

    asignaciones = query.all()
    data = [{
        "id": a.id, "fecha_entrega": a.fecha_entrega.isoformat(), "empleado_nombre": a.empleado_nombre,
        "cantidad_entregada": a.cantidad_entregada, "observaciones": a.observaciones,
        "item_nombre": a.item.nombre, "item_referencia": a.item.referencia, "item_talla": a.item.talla
    } for a in asignaciones]
    
    return jsonify(data)

# --- API para editar y eliminar asignaciones de EPP ---
@login_required
@permiso_requerido('inventario_epp')
@app.route('/api/epp/asignaciones/<int:id>', methods=['PUT'])
def update_epp_assignment(id):
    """API para actualizar una asignación de EPP."""
    asignacion = EPPAssignment.query.get_or_404(id)
    data = request.get_json()
    try:
        if 'fecha_entrega' in data:
            asignacion.fecha_entrega = date.fromisoformat(data['fecha_entrega']) if data['fecha_entrega'] else asignacion.fecha_entrega
        if 'empleado_nombre' in data:
            asignacion.empleado_nombre = data['empleado_nombre']
        if 'item_nombre' in data:
            # Cambia el item solo si existe un item con ese nombre
            item = EPPItem.query.filter_by(nombre=data['item_nombre']).first()
            if item:
                asignacion.item_id = item.id
        if 'item_referencia' in data:
            item = EPPItem.query.get(asignacion.item_id)
            if item:
                item.referencia = data['item_referencia']
        if 'item_talla' in data:
            item = EPPItem.query.get(asignacion.item_id)
            if item:
                item.talla = data['item_talla']
        if 'cantidad_entregada' in data:
            asignacion.cantidad_entregada = int(data['cantidad_entregada'])
        if 'observaciones' in data:
            asignacion.observaciones = data['observaciones']
        db.session.commit()
        return jsonify(success=True, message="Asignación actualizada.")
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, message=f"Error al actualizar: {str(e)}"), 500

@login_required
@permiso_requerido('inventario_epp')
@app.route('/api/epp/asignaciones/<int:id>', methods=['DELETE'])
def delete_epp_assignment(id):
    """API para eliminar una asignación de EPP."""
    asignacion = EPPAssignment.query.get_or_404(id)
    try:
        db.session.delete(asignacion)
        db.session.commit()
        return jsonify(success=True, message="Asignación eliminada.")
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, message=f"Error al eliminar: {str(e)}"), 500

@login_required
@permiso_requerido('programacion_cargue')
@app.route('/api/programacion/upload_excel', methods=['POST'])
def upload_programacion_excel():
    """Carga masiva de ProgramacionCargue desde un archivo Excel (.xlsx).

    Reglas:
    - Si se pasa ?replace=1 se eliminan los registros existentes antes de insertar.
    - Columnas aceptadas: nombres iguales a los campos del modelo; se permiten variantes con espacios o mayúsculas.
    - Campos fecha/hora se parsean; numéricos se convierten a float.
    - Si falta 'fecha_programacion' se usa la fecha de hoy.
    - Si no viene 'barriles' pero sí 'galones', se calcula barriles = galones/42.
    """
    if 'excel_file' not in request.files:
        return jsonify(success=False, message='No se encontró archivo (campo excel_file).'), 400
    f = request.files['excel_file']
    if not f.filename.lower().endswith('.xlsx'):
        return jsonify(success=False, message='Formato no soportado. Use .xlsx'), 400
    try:
        import pandas as pd
        from pandas.api.types import is_numeric_dtype
        df = pd.read_excel(f)
        # Normalizar nombres de columnas -> minusculas sin espacios dobles
        original_cols = list(df.columns)
        norm_map = {}
        for c in original_cols:
            norm = str(c).strip().lower().replace(' ', '_')
            norm_map[c] = norm
        df.rename(columns=norm_map, inplace=True)
        # Mapeo alternativo (por si el usuario usa variantes comunes)
        alias = {
            'empresa': 'empresa_transportadora',
            'transportadora': 'empresa_transportadora',
            'conductor': 'nombre_conductor',
            'cedula': 'cedula_conductor',
            'celular': 'celular_conductor',
            'producto': 'producto_a_cargar',
            'fecha': 'fecha_programacion',
            'fecha_de_programacion': 'fecha_programacion',
            'fecha_programada': 'fecha_programacion',
            'fecha_despacho_programada': 'fecha_despacho',
            'hora_llegada': 'hora_llegada_estimada',
            'hora_estimacion': 'hora_llegada_estimada',
            'guia': 'numero_guia'
        }
        for c in list(df.columns):
            if c in alias and alias[c] not in df.columns:
                df.rename(columns={c: alias[c]}, inplace=True)
        # Lista de campos manejados
        campos_modelo = {c.name for c in ProgramacionCargue.__table__.columns if c.name not in ('id')}
        filas_creadas = 0
        registros = []
        hoy = date.today()
        def parse_fecha(val):
            if pd.isna(val) or val == '':
                return None
            if isinstance(val, (datetime, date)):
                return val.date() if isinstance(val, datetime) else val
            for fmt in ('%Y-%m-%d','%d/%m/%Y','%Y/%m/%d','%d-%m-%Y'):
                try:
                    return datetime.strptime(str(val).strip(), fmt).date()
                except Exception:
                    pass
            return None
        def parse_hora(val):
            if pd.isna(val) or val == '':
                return None
            if isinstance(val, time):
                return val
            if isinstance(val, datetime):
                return val.time().replace(microsecond=0)
            try:
                # Aceptar formatos HH:MM o HH:MM:SS
                partes = str(val).strip().split(':')
                if len(partes) >= 2:
                    h = int(partes[0]); m = int(partes[1]); s = int(partes[2]) if len(partes) > 2 else 0
                    return time(hour=h, minute=m, second=s)
            except Exception:
                return None
            return None
        for _, row in df.iterrows():
            datos = {}
            for campo in campos_modelo:
                if campo in row.index:
                    val = row[campo]
                    if campo in ('fecha_programacion','fecha_despacho'):
                        val = parse_fecha(val)
                    elif campo == 'hora_llegada_estimada':
                        val = parse_hora(val)
                    elif campo in ('galones','barriles','temperatura','api_obs','api_corregido'):
                        try:
                            val = float(val) if not pd.isna(val) and val != '' else None
                        except Exception:
                            val = None
                    elif pd.isna(val):
                        val = None
                    datos[campo] = val
            # Defaults
            # Si no viene fecha_programacion pero sí fecha_despacho, usar esa (registros históricos)
            if not datos.get('fecha_programacion') and datos.get('fecha_despacho'):
                datos['fecha_programacion'] = datos['fecha_despacho']
            # Si aún no tenemos fecha_programacion, último recurso: hoy
            if not datos.get('fecha_programacion'):
                datos['fecha_programacion'] = hoy
            if datos.get('galones') and not datos.get('barriles'):
                try:
                    datos['barriles'] = float(datos['galones'])/42.0
                except Exception:
                    pass
            datos['ultimo_editor'] = session.get('nombre')
            # Normalizar estado
            if datos.get('estado'):
                est = str(datos['estado']).strip().upper()
                if est not in ('PROGRAMADO','CARGANDO','DESPACHADO'):
                    est = 'PROGRAMADO'
                datos['estado'] = est
            registro = ProgramacionCargue(**{k:v for k,v in datos.items() if k in campos_modelo})
            registros.append(registro)
        if request.args.get('replace') == '1':
            db.session.query(ProgramacionCargue).delete()
        db.session.add_all(registros)
        db.session.commit()
        filas_creadas = len(registros)
        return jsonify(success=True, message=f'Se cargaron {filas_creadas} registros.', total=filas_creadas, replace=bool(request.args.get('replace')=='1'))
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error al cargar Excel programación: {e}')
        return jsonify(success=False, message='Error procesando el archivo: ' + str(e)), 500

@login_required
@permiso_requerido('inventario_epp')
@app.route('/api/epp/items/<int:id>', methods=['DELETE'])
def delete_epp_item(id):
    """API para eliminar un item."""
    item = EPPItem.query.get_or_404(id)
    try:
        db.session.delete(item)
        db.session.commit()
        return jsonify(success=True, message="Item eliminado exitosamente.")
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, message=f"Error al eliminar: {str(e)}."), 500

@login_required
@permiso_requerido('inventario_epp')    
@app.route('/api/epp/items/batch_add', methods=['POST'])
def batch_add_epp_items():
    """API para crear múltiples items (variantes) de una sola vez."""
    items_data = request.get_json()
    if not isinstance(items_data, list) or not items_data:
        return jsonify(success=False, message="Formato de datos incorrecto."), 400

    try:
        creados_count = 0
        for item_data in items_data:
            # Evita duplicados revisando la combinación de nombre, referencia y talla
            existe = EPPItem.query.filter_by(
                nombre=item_data.get('nombre'),
                referencia=item_data.get('referencia'),
                talla=item_data.get('talla')
            ).first()

            if not existe:
                nuevo_item = EPPItem(
                    nombre=item_data.get('nombre'),
                    categoria=item_data.get('categoria'),
                    referencia=item_data.get('referencia'),
                    talla=item_data.get('talla'),
                    stock_actual=item_data.get('stock_actual', 0)
                )
                db.session.add(nuevo_item)
                creados_count += 1

        db.session.commit()
        return jsonify(success=True, message=f"Se han agregado {creados_count} nuevos items/variantes exitosamente.")

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error en carga rápida de EPP: {e}")
        return jsonify(success=False, message=f"Error interno del servidor: {str(e)}"), 500

@login_required
@permiso_requerido('inventario_epp')
@app.route('/exportar_inventario_epp/<string:formato>')
def exportar_inventario_epp(formato):
    # Obtener filtros desde la URL
    nombre = request.args.get('nombre', '')
    categoria = request.args.get('categoria', '')
    alertas = request.args.get('alertas', 'false') == 'true'

    # Construir la consulta a la base de datos
    query = EPPItem.query.order_by(EPPItem.categoria, EPPItem.nombre)

    if nombre:
        query = query.filter(or_(EPPItem.nombre.ilike(f'%{nombre}%'), EPPItem.referencia.ilike(f'%{nombre}%')))
    if categoria:
        query = query.filter(EPPItem.categoria == categoria)
    if alertas:
        today = date.today()
        thirty_days = today + timedelta(days=30)
        query = query.filter(or_(EPPItem.stock_actual <= 5, EPPItem.fecha_vencimiento.between(today, thirty_days)))

    items = query.all()

    if not items:
        flash('No hay datos para exportar con los filtros seleccionados.', 'warning')
        return redirect(url_for('inventario_epp'))

    # Generar el archivo según el formato
    if formato == 'excel':
        datos_df = [{
            'Categoría': item.categoria,
            'Elemento': item.nombre,
            'Referencia/Tipo': item.referencia,
            'Talla/Medida': item.talla,
            'Stock Actual': item.stock_actual,
            'Fecha Vencimiento': item.fecha_vencimiento.strftime('%Y-%m-%d') if item.fecha_vencimiento else 'N/A',
            'Observaciones': item.observaciones
        } for item in items]
        df = pd.DataFrame(datos_df)
        
        output = BytesIO()
        df.to_excel(output, index=False, sheet_name='Inventario EPP')
        output.seek(0)
        
        return send_file(output, as_attachment=True, download_name='reporte_inventario_epp.xlsx',
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    elif formato == 'pdf':
        html_para_pdf = render_template('reportes_pdf/reporte_inventario_pdf.html',
                                        items=items,
                                        fecha_reporte=datetime.now().strftime('%d de %B de %Y'))
        pdf = HTML(string=html_para_pdf).write_pdf()
        return Response(pdf, mimetype='application/pdf',
                        headers={'Content-Disposition': 'attachment;filename=reporte_inventario_epp.pdf'})
    
    return redirect(url_for('inventario_epp'))

@login_required
@permiso_requerido('inventario_epp')
@app.route('/exportar_asignaciones_epp/<string:formato>')
def exportar_asignaciones_epp(formato):
    empleado = request.args.get('empleado', '')
    fecha_inicio_str = request.args.get('fecha_inicio', '')
    fecha_fin_str = request.args.get('fecha_fin', '')

    query = db.session.query(EPPAssignment).join(EPPItem).order_by(EPPAssignment.fecha_entrega.desc())

    if empleado:
        query = query.filter(EPPAssignment.empleado_nombre.ilike(f'%{empleado}%'))
    if fecha_inicio_str:
        query = query.filter(EPPAssignment.fecha_entrega >= date.fromisoformat(fecha_inicio_str))
    if fecha_fin_str:
        query = query.filter(EPPAssignment.fecha_entrega <= date.fromisoformat(fecha_fin_str))

    asignaciones = query.all()

    if not asignaciones:
        flash('No hay asignaciones para exportar con los filtros seleccionados.', 'warning')
        return redirect(url_for('epp_asignaciones'))

    if formato == 'excel':
        datos_df = [{
            'Fecha Entrega': a.fecha_entrega.strftime('%Y-%m-%d'),
            'Empleado': a.empleado_nombre,
            'Elemento': a.item.nombre,
            'Referencia': a.item.referencia,
            'Talla/Medida': a.item.talla,
            'Cantidad': a.cantidad_entregada,
            'Observaciones': a.observaciones
        } for a in asignaciones]
        df = pd.DataFrame(datos_df)
        
        output = BytesIO()
        df.to_excel(output, index=False, sheet_name='Historial Asignaciones')
        output.seek(0)
        
        return send_file(output, as_attachment=True, download_name='reporte_asignaciones_epp.xlsx',
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    elif formato == 'pdf':
        html_para_pdf = render_template('reportes_pdf/reporte_asignaciones_pdf.html',
                                        asignaciones=asignaciones,
                                        fecha_reporte=datetime.now().strftime('%d de %B de %Y'))
        pdf = HTML(string=html_para_pdf).write_pdf()
        return Response(pdf, mimetype='application/pdf',
                        headers={'Content-Disposition': 'attachment;filename=reporte_asignaciones_epp.pdf'})

    return redirect(url_for('epp_asignaciones'))  

@login_required
@permiso_requerido('gestion_compras')
@app.route('/gestion_compras')
def gestion_compras():
    # Obtener filtro de proveedor si existe
    proveedor_filtro = request.args.get('proveedor', '')

    query = RegistroCompra.query

    if proveedor_filtro:
        query = query.filter(RegistroCompra.proveedor == proveedor_filtro)

    compras = query.order_by(RegistroCompra.fecha.desc()).all()
    
    # Obtener lista de proveedores únicos para el filtro
    proveedores = sorted([p[0] for p in db.session.query(RegistroCompra.proveedor).distinct().all() if p[0]])

    return render_template('gestion_compras.html', 
                         compras=compras, 
                         proveedores=proveedores,
                         filtros={'proveedor': proveedor_filtro})

@login_required
@permiso_requerido('gestion_compras')
@app.route('/cargar_compras_excel', methods=['POST'])
def cargar_compras_excel():
    if 'excel_file' not in request.files:
        flash('No se encontró el archivo.', 'danger')
        return redirect(url_for('gestion_compras'))

    file = request.files['excel_file']
    if not file or not file.filename.endswith('.xlsx'):
        flash('Archivo no válido. Debe ser .xlsx', 'danger')
        return redirect(url_for('gestion_compras'))

    try:
        # Leer el archivo Excel manteniendo los nombres originales de columnas
        df = pd.read_excel(file, sheet_name='2025')
        
        nuevas = 0
        actualizadas = 0

        for _, row in df.iterrows():
            # Buscar registro existente por campos clave
            compra = RegistroCompra.query.filter_by(
                fecha=pd.to_datetime(row['MES']).date(),
                proveedor=row['PROVEEDOR'],
                producto=row['PRODUCTO'],
                cantidad_bls=row['CANTIDAD BLS']
            ).first()

            if not compra:
                compra = RegistroCompra()
                db.session.add(compra)
                nuevas += 1

            # Asignar valores directamente del Excel
            compra.fecha = pd.to_datetime(row['MES']).date()
            compra.proveedor = row['PROVEEDOR']
            compra.tarifa = row['TARIFA'] if pd.notna(row['TARIFA']) else None
            compra.producto = row['PRODUCTO']
            compra.cantidad_bls = row['CANTIDAD BLS']
            compra.cantidad_gln = row['CANITDAD GLN']
            compra.brent = row['BRENT US$B']
            compra.descuento = row['DESCUENTO US$B']
            compra.precio_uni_bpozo = row['PRECIO UNI. B.POZO US$B']
            compra.total_neto = row['TOTAL NETO US$B']
            compra.price_compra_pond = row['PRICE COMPRA POND. US$/BL']
            compra.fecha_carga = datetime.utcnow()
        
        db.session.commit()
        flash(f'Datos cargados: {nuevas} nuevos, {actualizadas} actualizados', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error al cargar: {str(e)}', 'danger')
        app.logger.error(f"Error carga Excel: {str(e)}")

    return redirect(url_for('gestion_compras'))

@login_required
@permiso_requerido('gestion_compras')
@app.route('/reporte_compras')
def reporte_compras():
    # Histórico de precios
    historico_precios_raw = db.session.query(
        func.date(RegistroCompra.fecha).label('fecha'),
        func.avg(RegistroCompra.price_compra_pond).label('precio_promedio')
    ).group_by(func.date(RegistroCompra.fecha)).all()
    historico_precios = [
        {"mes": str(row[0]), "precio": float(row[1]) if row[1] is not None else 0}
        for row in historico_precios_raw
    ]

    # Histórico de volúmenes
    historico_volumenes_raw = db.session.query(
        func.date(RegistroCompra.fecha).label('fecha'),
        func.sum(RegistroCompra.cantidad_bls).label('volumen_total')
    ).group_by(func.date(RegistroCompra.fecha)).all()
    historico_volumenes = [
        {"mes": str(row[0]), "volumen": float(row[1]) if row[1] is not None else 0}
        for row in historico_volumenes_raw
    ]

    # Resumen mensual
    resumen_mensual_raw = db.session.query(
        func.to_char(RegistroCompra.fecha, 'YYYY-MM').label('mes'),
        RegistroCompra.proveedor,
        RegistroCompra.producto,
        func.sum(RegistroCompra.cantidad_bls).label('cantidad_bls')
    ).group_by('mes', RegistroCompra.proveedor, RegistroCompra.producto).all()
    resumen_mensual = [
        {
            "mes": row[0],
            "proveedor": row[1],
            "producto": row[2],
            "cantidad_bls": float(row[3]) if row[3] is not None else 0
        }
        for row in resumen_mensual_raw
    ]

    proveedores = sorted([p[0] for p in db.session.query(RegistroCompra.proveedor).distinct().all() if p[0]])
    productos = sorted([p[0] for p in db.session.query(RegistroCompra.producto).distinct().all() if p[0]])

    return render_template(
        'reporte_compras.html',
        historico_precios=historico_precios,
        historico_volumenes=historico_volumenes,
        resumen_mensual=resumen_mensual,
        proveedores=proveedores,
        productos=productos
    )

@login_required
@permiso_requerido('gestion_compras')
@app.route('/reporte_compras_pdf')
def reporte_compras_pdf():
    # Función auxiliar corregida para formatear meses
    def formatear_mes(fecha_str):
        try:
            # Maneja diferentes formatos de fecha
            if len(fecha_str) == 10:  # Formato YYYY-MM-DD
                fecha = datetime.strptime(fecha_str, '%Y-%m-%d')
            elif len(fecha_str) == 7:  # Formato YYYY-MM
                fecha = datetime.strptime(fecha_str, '%Y-%m')
            else:
                return fecha_str  # Si no reconoce el formato, devuelve original
            
            meses = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 
                    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
            return f"{meses[fecha.month]} {fecha.year}"
        except:
            return fecha_str  # En caso de error, devuelve el valor original

    # Consulta de precios históricos
    historico_precios_raw = db.session.query(
        func.to_char(RegistroCompra.fecha, 'YYYY-MM').label('mes'),
        func.avg(RegistroCompra.price_compra_pond).label('precio_promedio')
    ).group_by('mes').order_by('mes').all()
    
    historico_precios = [
        {"mes": formatear_mes(row[0]), "precio": float(row[1]) if row[1] is not None else 0}
        for row in historico_precios_raw
    ]

    # Consulta de volúmenes históricos
    historico_volumenes_raw = db.session.query(
        func.to_char(RegistroCompra.fecha, 'YYYY-MM').label('mes'),
        func.sum(RegistroCompra.cantidad_bls).label('volumen_total')
    ).group_by('mes').order_by('mes').all()
    
    historico_volumenes = [
        {"mes": formatear_mes(row[0]), "volumen": float(row[1]) if row[1] is not None else 0}
        for row in historico_volumenes_raw
    ]

    # Leer filtros de la URL
    filtro_mes = request.args.get('mes')
    filtro_proveedor = request.args.get('proveedor')
    filtro_producto = request.args.get('producto')

    # Consulta base
    resumen_query = db.session.query(
        func.strftime('%Y-%m', RegistroCompra.fecha).label('mes'),
        RegistroCompra.proveedor,
        RegistroCompra.producto,
        func.sum(RegistroCompra.cantidad_bls).label('cantidad_bls')
    )
    # Aplicar filtros si existen
    if filtro_mes:
        resumen_query = resumen_query.filter(func.to_char(RegistroCompra.fecha, 'YYYY-MM') == filtro_mes)
    if filtro_proveedor:
        resumen_query = resumen_query.filter(RegistroCompra.proveedor == filtro_proveedor)
    if filtro_producto:
        resumen_query = resumen_query.filter(RegistroCompra.producto == filtro_producto)

    resumen_mensual_raw = resumen_query.group_by('mes', RegistroCompra.proveedor, RegistroCompra.producto).order_by('mes').all()

    resumen_mensual = [
        {
            "mes": formatear_mes(row[0]),
            "proveedor": row[1],
            "producto": row[2],
            "cantidad_bls": float(row[3]) if row[3] is not None else 0
        }
        for row in resumen_mensual_raw
    ]

    # Obtener listas de proveedores y productos
    proveedores = sorted([p[0] for p in db.session.query(RegistroCompra.proveedor).distinct().all() if p[0]])
    productos = sorted([p[0] for p in db.session.query(RegistroCompra.producto).distinct().all() if p[0]])

    # Generar gráficos
    labels_precios = [x['mes'] for x in historico_precios]
    data_precios = [x['precio'] for x in historico_precios]
    labels_volumenes = [x['mes'] for x in historico_volumenes]
    data_volumenes = [x['volumen'] for x in historico_volumenes]

    img_precios = grafico_linea_base64(labels_precios, data_precios, 'Precio Compra Ponderado (US$/BL)')
    img_volumenes = grafico_barra_base64(labels_volumenes, data_volumenes, 'Volumen Comprado (BLS)')

    # Renderizar template para PDF
    html_para_pdf = render_template(
        'reportes_pdf/reporte_compras_pdf.html',
        historico_precios=historico_precios,
        historico_volumenes=historico_volumenes,
        resumen_mensual=resumen_mensual,
        proveedores=proveedores,
        productos=productos,
        pdf=True,
        img_precios=img_precios,
        img_volumenes=img_volumenes,
        now=datetime.now
    )
    
    # Generar PDF
    pdf = HTML(string=html_para_pdf, base_url=request.base_url).write_pdf()
    return Response(
        pdf, 
        mimetype='application/pdf',
        headers={'Content-Disposition': 'attachment;filename=reporte_compras.pdf'}
    )

@login_required
@permiso_requerido('flujo_efectivo')
@app.route('/flujo_efectivo')
def flujo_efectivo():
    """
    Renderiza la página principal del Flujo de Efectivo.
    """
    return render_template('flujo_efectivo.html', nombre=session.get("nombre"))


@login_required
@permiso_requerido('flujo_efectivo')
@app.route('/api/procesar_flujo_efectivo', methods=['POST'])
def procesar_flujo_efectivo_api():
    """Procesa Excel y persiste TODOS los movimientos (bancos/odoo) sin eliminar duplicados. Responde dataset completo persistido."""
    if 'archivo_excel' not in request.files:
        return jsonify(success=False, message="No se encontró el archivo en la solicitud."), 400
    archivo = request.files['archivo_excel']
    if archivo.filename == '' or not archivo.filename.lower().endswith(('.xlsx','.xls')):
        return jsonify(success=False, message="Archivo inválido."), 400
    try:
        xls = pd.ExcelFile(archivo)
        sheet_map = {name.strip().lower(): name for name in xls.sheet_names}

        if 'bancos' not in sheet_map or 'odoo' not in sheet_map:
            return jsonify(success=False, message='El archivo debe contener las hojas "Bancos" y "Odoo".'), 400
        df_bancos = pd.read_excel(xls, sheet_name=sheet_map['bancos'])
        df_odoo = pd.read_excel(xls, sheet_name=sheet_map['odoo'])

        # Normalizar nombres de columnas (trim)
        df_bancos.columns = df_bancos.columns.str.strip()
        df_odoo.columns = df_odoo.columns.str.strip()

        # --- NUEVO: detectar y normalizar columna de Banco aunque venga con otro nombre ---
        def _ensure_banco_col(df):
            if 'Banco' in df.columns:
                return
            # Posibles variantes que han aparecido en archivos reales
            variantes = {
                'banco','bancos','tipo banco','tipo_banco','banco/cuenta','banco - cuenta',
                'cuenta','cuenta bancaria','entidad','entidad financiera','banco cuenta'
            }
            for c in df.columns:
                if c.strip().lower() in variantes:
                    df.rename(columns={c: 'Banco'}, inplace=True)
                    return
        _ensure_banco_col(df_bancos)
        _ensure_banco_col(df_odoo)

        # Validar columnas mínimas
        required_bancos = {'FECHA DE OPERACIÓN', 'Movimiento', 'COP$', 'Empresa'}
        required_odoo = {'Fecha', 'Movimiento', 'Débito', 'Crédito', 'Empresa'}
        missing_b = required_bancos - set(df_bancos.columns)
        missing_o = required_odoo - set(df_odoo.columns)
        if missing_b:
            return jsonify(success=False, message=f"Faltan columnas en Bancos: {missing_b}"), 400
        if missing_o:
            return jsonify(success=False, message=f"Faltan columnas en Odoo: {missing_o}"), 400

        # Limpiar y convertir montos
        def clean_numeric(series):
            return (series.astype(str)
                    .str.replace(r"[^0-9\-.,]", '', regex=True)
                    .str.replace(',', '', regex=False)
                    .replace('', '0')
                    .pipe(pd.to_numeric, errors='coerce').fillna(0))

        df_bancos['COP$'] = clean_numeric(df_bancos['COP$'])
        df_odoo['Débito'] = clean_numeric(df_odoo['Débito'])
        df_odoo['Crédito'] = clean_numeric(df_odoo['Crédito'])

        # Normalizar variantes de EGRESO GMF -> EGRESO_GMF (soporta espacios, guiones o múltiples separadores)
        def _norm_mov(txt: str):
            if not isinstance(txt, str):
                return txt
            t = txt.strip()
            if re.search(r'EGRESO\s*[_\-]?\s*GMF', t, re.IGNORECASE):
                return 'EGRESO_GMF'
            return t
        if 'Movimiento' in df_bancos.columns:
            df_bancos['Movimiento'] = df_bancos['Movimiento'].astype(str).apply(_norm_mov)
        if 'Movimiento' in df_odoo.columns:
            df_odoo['Movimiento'] = df_odoo['Movimiento'].astype(str).apply(_norm_mov)

        # Fechas seguras
        df_bancos['FECHA DE OPERACIÓN'] = pd.to_datetime(df_bancos['FECHA DE OPERACIÓN'], errors='coerce')
        df_bancos = df_bancos.dropna(subset=['FECHA DE OPERACIÓN'])
        df_odoo['Fecha'] = pd.to_datetime(df_odoo['Fecha'], errors='coerce')
        df_odoo = df_odoo.dropna(subset=['Fecha'])

        # Normalizar columnas Banco (ambas hojas pueden o no traerla). Si no existe se crea vacía para tener consistencia.
        if 'Banco' not in df_bancos.columns:
            df_bancos['Banco'] = ''
        if 'Banco' not in df_odoo.columns:
            df_odoo['Banco'] = ''
        df_bancos['Banco'] = df_bancos['Banco'].fillna('').astype(str)
        df_odoo['Banco'] = df_odoo['Banco'].fillna('').astype(str)

        # Ingresos / Egresos agrupando por Banco también
        mask_b_ing = df_bancos['Movimiento'].str.contains('INGRESO', case=False, na=False)
        ing_b = df_bancos.loc[mask_b_ing].copy(); ing_b['fecha'] = ing_b['FECHA DE OPERACIÓN'].dt.date
        bancos_ingresos = ing_b.groupby(['fecha', 'Empresa', 'Banco'])['COP$'].sum().reset_index().rename(columns={'COP$': 'ingresos_bancos'})
        mask_b_eg = df_bancos['Movimiento'].str.contains('EGRESO', case=False, na=False)
        eg_b = df_bancos.loc[mask_b_eg].copy(); eg_b['fecha'] = eg_b['FECHA DE OPERACIÓN'].dt.date
        eg_b['egresos_bancos'] = eg_b['COP$'].abs()
        bancos_egresos = eg_b.groupby(['fecha', 'Empresa', 'Banco'])['egresos_bancos'].sum().reset_index()

        mask_o_ing = df_odoo['Movimiento'].str.contains('INGRESO', case=False, na=False)
        ing_o = df_odoo.loc[mask_o_ing].copy(); ing_o['fecha'] = ing_o['Fecha'].dt.date
        odoo_ingresos = ing_o.groupby(['fecha', 'Empresa', 'Banco'])['Débito'].sum().reset_index().rename(columns={'Débito': 'ingresos_odoo'})
        mask_o_eg = df_odoo['Movimiento'].str.contains('EGRESO', case=False, na=False)
        eg_o = df_odoo.loc[mask_o_eg].copy(); eg_o['fecha'] = eg_o['Fecha'].dt.date
        odoo_egresos = eg_o.groupby(['fecha', 'Empresa', 'Banco'])['Crédito'].sum().reset_index().rename(columns={'Crédito': 'egresos_odoo'})

        comparativo_df = pd.merge(bancos_ingresos, bancos_egresos, on=['fecha', 'Empresa', 'Banco'], how='outer')
        comparativo_df = pd.merge(comparativo_df, odoo_ingresos, on=['fecha', 'Empresa', 'Banco'], how='outer')
        comparativo_df = pd.merge(comparativo_df, odoo_egresos, on=['fecha', 'Empresa', 'Banco'], how='outer')
        comparativo_df.fillna(0, inplace=True)
        comparativo_df['diferencia_ingresos'] = comparativo_df['ingresos_bancos'] - comparativo_df['ingresos_odoo']
        comparativo_df['diferencia_egresos'] = comparativo_df['egresos_bancos'] - comparativo_df['egresos_odoo']
        comparativo_df = comparativo_df.sort_values(by=['fecha', 'Empresa'], ascending=True)
        comparativo_df['fecha'] = comparativo_df['fecha'].astype(str)
        comparativo_df.rename(columns={'Banco':'tipo_banco'}, inplace=True)
        daily_comparison_data = comparativo_df.to_dict(orient='records')

        # Lista de empresas para el frontend
        todas_las_empresas = sorted(set(df_bancos['Empresa'].dropna().unique().tolist() + df_odoo['Empresa'].dropna().unique().tolist()))

        # Agrupación por Tipo de Flujo y Tercero (si las columnas existen)
        def group_by_flow_type_safe(df, value_col):
            cols = set(df.columns)
            if not {'Tipo Flujo Efectivo', 'Tercero', value_col}.issubset(cols):
                return {}
            g = df.groupby(['Tipo Flujo Efectivo', 'Tercero'])[value_col].sum()
            nested = {}
            for (flow_type, tercero), total in g.items():
                nested.setdefault(flow_type, {})[tercero] = total
            return nested

        outflows_by_type = group_by_flow_type_safe(df_odoo, 'Crédito')
        inflows_by_type = group_by_flow_type_safe(df_odoo, 'Débito')

        # --- Detalle completo de movimientos Odoo para expansiones frontend ---
        rubro_col = None
        for candidate in ['Rubro', 'RUBRO', 'rubro']:
            if candidate in df_odoo.columns:
                rubro_col = candidate
                break
        tipo_flujo_col = 'Tipo Flujo Efectivo' if 'Tipo Flujo Efectivo' in df_odoo.columns else None
        tercero_col = 'Tercero' if 'Tercero' in df_odoo.columns else None
        # Detectar columnas de Clase / Subclase para poder reconstruir el TOP filtrado en frontend
        clase_col = None
        for c in ['Clase', 'CLASE', 'clase']:
            if c in df_odoo.columns:
                clase_col = c
                break
        subclase_col = None
        for c in ['Sub Clase', 'Sub_Clase', 'SubClase', 'Subclase', 'SUBCLASE', 'SUB CLASE']:
            if c in df_odoo.columns:
                subclase_col = c
                break
        df_detalle = df_odoo.copy()
        df_detalle['__fecha_date'] = pd.to_datetime(df_detalle['Fecha'], errors='coerce')
        df_detalle = df_detalle.dropna(subset=['__fecha_date'])
        df_detalle['fecha'] = df_detalle['__fecha_date'].dt.strftime('%Y-%m-%d')
        # Construcción segura del detalle, reemplazando NaN por valores neutros
        import math
        detalle_records = []
        for _, r in df_detalle.iterrows():
            # Utilizamos pd.isna para cubrir np.nan, pandas.NA, None
            def safe_text(val, default=''):
                try:
                    if pd.isna(val):
                        return default
                except Exception:
                    pass
                return str(val) if val is not None else default
            def safe_number(val):
                try:
                    if pd.isna(val):
                        return 0.0
                except Exception:
                    pass
                try:
                    f = float(val)
                    if math.isnan(f) or math.isinf(f):
                        return 0.0
                    return f
                except Exception:
                    return 0.0
            detalle_records.append({
                'fecha': safe_text(r.get('fecha')),  # ya es string formateada
                'empresa': safe_text(r.get('Empresa')),
                'tipo_flujo': safe_text(r.get(tipo_flujo_col) if tipo_flujo_col else 'SIN TIPO', 'SIN TIPO'),
                'tercero': safe_text(r.get(tercero_col) if tercero_col else 'SIN TERCERO', 'SIN TERCERO'),
                'rubro': safe_text(r.get(rubro_col) if rubro_col else ''),
                'debito': safe_number(r.get('Débito', 0)),
                'credito': safe_number(r.get('Crédito', 0)),
                'movimiento': safe_text(r.get('Movimiento', '')),
                # Nuevos campos necesarios para filtrar y recalcular TOP en frontend
                'clase': safe_text(r.get(clase_col) if clase_col else ''),
                'subclase': safe_text(r.get(subclase_col) if subclase_col else ''),
                'banco': safe_text(r.get('Banco') if 'Banco' in df_detalle.columns else '')
            })

        # --- TOP CLIENTES VENTAS EXW CTG (ingresos) ---
        top_clientes_exw = None
        # (Columnas clase_col y subclase_col ya detectadas arriba; se reutilizan)
        tercero_col_original = 'Tercero' if 'Tercero' in df_odoo.columns else None
        # Filtrar sólo si existen columnas necesarias
        if clase_col and tercero_col_original and 'Débito' in df_odoo.columns:
            df_exw = df_odoo[df_odoo[clase_col].astype(str).str.upper() == 'VENTAS EXW CTG'].copy()
            if not df_exw.empty:
                # Normalizar valores
                df_exw['__tercero_safe'] = df_exw[tercero_col_original].fillna('SIN TERCERO').astype(str)
                if subclase_col:
                    df_exw['__subclase_safe'] = df_exw[subclase_col].fillna('SIN SUBCLASE').astype(str)
                else:
                    df_exw['__subclase_safe'] = 'SIN SUBCLASE'
                # Asegurar numérico
                df_exw['__debito_val'] = pd.to_numeric(df_exw['Débito'], errors='coerce').fillna(0)
                # Agrupar por cliente y subclase
                grp = df_exw.groupby(['__tercero_safe', '__subclase_safe'])['__debito_val'].sum().reset_index()
                # Totales por cliente para ranking
                tot_clientes = grp.groupby('__tercero_safe')['__debito_val'].sum().reset_index().rename(columns={'__debito_val': 'total'})
                # Ordenar y tomar top 10
                tot_clientes = tot_clientes.sort_values('total', ascending=False).head(10)
                top_set = set(tot_clientes['__tercero_safe'])
                grp_top = grp[grp['__tercero_safe'].isin(top_set)]
                # Construir estructura
                clientes_struct = []
                for _, row_cli in tot_clientes.iterrows():
                    cliente = row_cli['__tercero_safe']
                    total_cli = float(row_cli['total'])
                    subs_rows = grp_top[grp_top['__tercero_safe'] == cliente]
                    sub_list = [
                        {
                            'subclase': str(sr['__subclase_safe']),
                            'total': float(sr['__debito_val'])
                        }
                        for _, sr in subs_rows.iterrows()
                    ]
                    clientes_struct.append({
                        'cliente': str(cliente),
                        'total': total_cli,
                        'subclases': sub_list
                    })
                top_clientes_exw = {
                    'clientes': clientes_struct,
                    'total_general': float(tot_clientes['total'].sum())
                }

        # Movimientos Bancos crudos para recomputar resumen con filtros en frontend
        bancos_movimientos = []
        df_bancos_mov = df_bancos.copy()
        df_bancos_mov['__fecha_date'] = pd.to_datetime(df_bancos_mov['FECHA DE OPERACIÓN'], errors='coerce')
        df_bancos_mov = df_bancos_mov.dropna(subset=['__fecha_date'])
        df_bancos_mov['fecha'] = df_bancos_mov['__fecha_date'].dt.strftime('%Y-%m-%d')
        for _, r in df_bancos_mov.iterrows():
            movimiento_txt = str(r.get('Movimiento') or '')
            mov_upper = movimiento_txt.upper()
            tipo = 'otro'
            if 'SALDO INICIAL' in mov_upper:
                tipo = 'saldo_inicial'
            elif 'INGRESO' in mov_upper:
                tipo = 'ingreso'
            elif 'EGRESO' in mov_upper:
                tipo = 'egreso_gmf' if 'GMF' in mov_upper else 'egreso'
            bancos_movimientos.append({
                'fecha': r.get('fecha'),
                'empresa': r.get('Empresa'),
                'movimiento': movimiento_txt,
                'monto': float(r.get('COP$', 0) or 0),
                'clasificacion': tipo,
                'tipo_banco': str(r.get('Banco') or ''),
                'banco': str(r.get('Banco') or '')
            })

        # ======================= PERSISTENCIA / DEDUP =======================
        batch = FlujoUploadBatch(filename=archivo.filename, usuario=session.get('nombre','Desconocido'))
        db.session.add(batch)
        db.session.flush()  # obtener batch.id

        # Insertar SIEMPRE todas las filas (sin deduplicación). Se genera unique_hash aleatorio.
        bancos_count = 0
        for _, r in df_bancos_mov.iterrows():
            monto_val = float(r.get('COP$', 0) or 0)
            if monto_val == 0:
                continue  # Ignorar filas donde COP$ es vacío o cero
            mov_txt = str(r.get('Movimiento') or '')
            banco_val = str(r.get('Banco') or '')
            db.session.add(FlujoBancoMovimiento(
                batch_id=batch.id,
                fecha=pd.to_datetime(r.get('__fecha_date')).date(),
                empresa=r.get('Empresa'),
                movimiento=mov_txt,
                monto=monto_val,
                banco=banco_val,
                tipo_banco=banco_val,
                unique_hash=uuid.uuid4().hex
            ))
            bancos_count += 1

        odoo_count = 0
        for rec in detalle_records:
            db.session.add(FlujoOdooMovimiento(
                batch_id=batch.id,
                fecha=pd.to_datetime(rec['fecha']).date(),
                empresa=rec['empresa'],
                movimiento=rec['movimiento'],
                debito=rec['debito'],
                credito=rec['credito'],
                tipo_flujo=rec.get('tipo_flujo'),
                tercero=rec.get('tercero'),
                rubro=rec.get('rubro'),
                clase=rec.get('clase'),
                subclase=rec.get('subclase'),
                banco=rec.get('banco'),
                unique_hash=uuid.uuid4().hex
            ))
            odoo_count += 1

        batch.total_bancos = bancos_count
        batch.total_odoo = odoo_count

        db.session.commit()

        # ======================= RECONSTRUCCIÓN DESDE BD =======================
        bancos_rows = FlujoBancoMovimiento.query.all()
        odoo_rows = FlujoOdooMovimiento.query.all()

        # Reconstruir daily comparison desde persistencia
        # Agrupar ingresos/egresos bancos por fecha/empresa según reglas (Movimiento contiene palabras clave)
        bancos_ing_map = {}
        bancos_eg_map = {}
        for r in bancos_rows:
            # Solo contabilizar movimientos INGRESO y EGRESO; SALDO INICIAL se ignora (pero ya NO filtramos GMF aquí para incluirlo en egresos_gmf por separado si se quiere)
            mtxt = (r.movimiento or '').upper()
            if 'SALDO INICIAL' in mtxt:
                continue
            # Asegurar consistencia de banco (None -> '')
            banco_key = (r.banco or '').strip()
            key = (r.fecha.isoformat(), r.empresa, banco_key)
            if 'INGRESO' in mtxt:
                bancos_ing_map[key] = bancos_ing_map.get(key,0) + r.monto
            elif 'EGRESO' in mtxt:
                bancos_eg_map[key] = bancos_eg_map.get(key,0) + abs(r.monto)

        odoo_ing_map = {}
        odoo_eg_map = {}
        for r in odoo_rows:
            mtxt = (r.movimiento or '').upper()
            key = (r.fecha.isoformat(), r.empresa, r.banco or '')
            if 'INGRESO' in mtxt:
                odoo_ing_map[key] = odoo_ing_map.get(key,0) + (r.debito or 0)
            if 'EGRESO' in mtxt:
                odoo_eg_map[key] = odoo_eg_map.get(key,0) + (r.credito or 0)

        keys_all = sorted(set(list(bancos_ing_map.keys()) + list(bancos_eg_map.keys()) + list(odoo_ing_map.keys()) + list(odoo_eg_map.keys())))
        daily_comparison_data = []
        for (f,e,bk) in keys_all:
            ib = bancos_ing_map.get((f,e,bk),0)
            eb = bancos_eg_map.get((f,e,bk),0)
            io = odoo_ing_map.get((f,e,bk),0)
            eo = odoo_eg_map.get((f,e,bk),0)
            daily_comparison_data.append({
                'fecha': f,
                'Empresa': e,
                'tipo_banco': bk or '',
                'banco': bk or '',  # alias legacy
                'ingresos_bancos': ib,
                'egresos_bancos': eb,
                'ingresos_odoo': io,
                'egresos_odoo': eo,
                'diferencia_ingresos': ib-io,
                'diferencia_egresos': eb-eo
            })

        # Reconstruir detalle Odoo para frontend
        detalle_records = []
        for r in odoo_rows:
            detalle_records.append({
                'fecha': r.fecha.isoformat(),
                'empresa': r.empresa,
                'movimiento': r.movimiento,
                'debito': r.debito,
                'credito': r.credito,
                'tipo_flujo': r.tipo_flujo or 'SIN TIPO',
                'tercero': r.tercero or 'SIN TERCERO',
                'rubro': r.rubro or '',
                'clase': r.clase or '',
                'subclase': r.subclase or '',
                'banco': r.banco or ''
            })
        todas_las_empresas = sorted({r.empresa for r in bancos_rows+odoo_rows if r.empresa})

        # Recalcular agrupaciones flujo / tercero
        inflows_by_type = {}
        outflows_by_type = {}
        for r in odoo_rows:
            tf = (r.tipo_flujo or 'SIN TIPO')
            terc = (r.tercero or 'SIN TERCERO')
            if (r.debito or 0) > 0:
                inflows_by_type.setdefault(tf, {})[terc] = inflows_by_type.setdefault(tf, {}).get(terc,0) + (r.debito or 0)
            if (r.credito or 0) > 0:
                outflows_by_type.setdefault(tf, {})[terc] = outflows_by_type.setdefault(tf, {}).get(terc,0) + (r.credito or 0)

        # TOP EXW (si clase contiene 'VENTAS EXW CTG')
        top_clientes_exw = None
        exw_rows = [r for r in odoo_rows if (r.clase or '').upper() == 'VENTAS EXW CTG' and (r.debito or 0) > 0]
        if exw_rows:
            agg = {}
            for r in exw_rows:
                cli = (r.tercero or 'SIN TERCERO')
                sub = (r.subclase or 'SIN SUBCLASE')
                agg.setdefault(cli, {}).setdefault(sub,0)
                agg[cli][sub] += r.debito or 0
            ranking = sorted([(cli, sum(subs.values()), subs) for cli, subs in agg.items()], key=lambda x: x[1], reverse=True)[:10]
            clientes_struct = []
            for cli, total, subs in ranking:
                clientes_struct.append({
                    'cliente': cli,
                    'total': total,
                    'subclases': [{'subclase': s, 'total': v} for s,v in subs.items()]
                })
            top_clientes_exw = {'clientes': clientes_struct, 'total_general': sum(x[1] for x in ranking)}

        # Reconstruir movimientos bancos simplificados para frontend (clasificacion)
        bancos_movimientos = []
        for r in bancos_rows:
            mov_upper = (r.movimiento or '').upper()
            tipo = 'otro'
            if 'SALDO INICIAL' in mov_upper:
                tipo = 'saldo_inicial'
            elif 'INGRESO' in mov_upper:
                tipo = 'ingreso'
            elif 'EGRESO' in mov_upper:
                tipo = 'egreso_gmf' if 'GMF' in mov_upper else 'egreso'
            if tipo == 'otro':
                continue
            bancos_movimientos.append({
                'fecha': r.fecha.isoformat(),
                'empresa': r.empresa,
                'movimiento': r.movimiento,
                'monto': r.monto,
                'clasificacion': tipo,
                'tipo_banco': (r.tipo_banco or r.banco or '').strip(),
                'banco': (r.banco or r.tipo_banco or '').strip()
            })

        # Calcular GMF separado para mostrarlo sumado en la tarjeta de egresos
        egresos_gmf_raw = df_bancos.loc[
            df_bancos['Movimiento'].str.contains('GMF', case=False, na=False), 'COP$'
        ].abs().sum()
        response_data = {
            'success': True,
            'nuevos_bancos': batch.total_bancos,
            'nuevos_odoo': batch.total_odoo,
            'daily_comparison': daily_comparison_data,
            'outflows_by_type': outflows_by_type,
            'inflows_by_type': inflows_by_type,
            'todas_las_empresas': todas_las_empresas,
            'odoo_detalle': detalle_records,
            'bancos_movimientos': bancos_movimientos,
            # Resumen Método Directo básico desde hoja Bancos (incluye ahora egresos_gmf y egresos_total)
            'resumen_directo': (lambda saldo_ini, ingresos, egresos_sin_gmf, egresos_gmf: {
                'saldo_inicial': float(saldo_ini),
                'ingresos': float(ingresos),
                'saldo_antes_egresos': float(saldo_ini + ingresos),
                'egresos': float(egresos_sin_gmf),
                'egresos_gmf': float(egresos_gmf),
                'egresos_total': float(egresos_sin_gmf + egresos_gmf),
                'saldo_final': float(saldo_ini + ingresos - (egresos_sin_gmf + egresos_gmf))
            })(
                # saldo inicial
                (lambda df: (
                    0.0 if df.empty else df[df['FECHA DE OPERACIÓN'].dt.date == df['FECHA DE OPERACIÓN'].dt.date.min()]['COP$'].sum()
                ))(df_bancos[df_bancos['Movimiento'].str.contains('SALDO INICIAL', case=False, na=False)]),
                # ingresos (sin SALDO INICIAL / GMF)
                df_bancos.loc[
                    df_bancos['Movimiento'].str.contains('INGRESO', case=False, na=False)
                    & ~df_bancos['Movimiento'].str.contains('SALDO INICIAL', case=False, na=False)
                    & ~df_bancos['Movimiento'].str.contains('GMF', case=False, na=False),
                    'COP$'
                ].sum(),
                # egresos sin GMF
                df_bancos.loc[
                    df_bancos['Movimiento'].str.contains('EGRESO', case=False, na=False)
                    & ~df_bancos['Movimiento'].str.contains('GMF', case=False, na=False),
                    'COP$'
                ].abs().sum(),
                # egresos GMF
                egresos_gmf_raw
            )
        }
        if top_clientes_exw:
            response_data['top_clientes_ventas_exw'] = top_clientes_exw

        # Sanitizar recursivamente cualquier NaN/Infinity residual antes de serializar
        def sanitize(obj):
            import math
            if isinstance(obj, dict):
                return {k: sanitize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [sanitize(v) for v in obj]
            if isinstance(obj, float):
                if math.isnan(obj) or math.isinf(obj):
                    return None
                return obj
            # Intentar detectar pandas NA en tipos no-float
            try:
                if pd.isna(obj):
                    return None
            except Exception:
                pass
            return obj

        return jsonify(sanitize(response_data))

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        return jsonify(success=False, message=f'Error interno: {str(e)}', details=tb), 500

@login_required
@permiso_requerido('flujo_efectivo')
@app.route('/api/flujo_efectivo_simple', methods=['POST'])
def flujo_efectivo_simple():
    """Comparativo SIMPLE: (fecha, empresa) -> ingresos_bancos, saldo_inicial_bancos, ingresos_odoo.
    Reglas:
      - SALDO INICIAL (en Movimiento Bancos) se reporta separado (no suma en ingresos_bancos).
      - INGRESO (Movimiento contiene 'INGRESO' y NO 'SALDO INICIAL') suma a ingresos_bancos.
      - Ingresos Odoo = suma de Débito donde Movimiento contiene 'INGRESO'.
      - No se calcula egresos ni diferencias, sólo comparativa de ingreso y saldo inicial.
    """
    if 'archivo_excel' not in request.files:
        return jsonify(success=False, message='Falta archivo_excel'), 400
    archivo = request.files['archivo_excel']
    if archivo.filename == '' or not archivo.filename.lower().endswith(('.xlsx','.xls')):
        return jsonify(success=False, message='Archivo inválido'), 400
    try:
        xls = pd.ExcelFile(archivo)
        sheet_map = {n.strip().lower(): n for n in xls.sheet_names}
        if 'bancos' not in sheet_map or 'odoo' not in sheet_map:
            return jsonify(success=False, message='Debe incluir hojas Bancos y Odoo'), 400
        df_b = pd.read_excel(xls, sheet_name=sheet_map['bancos'])
        df_o = pd.read_excel(xls, sheet_name=sheet_map['odoo'])
        # Normalizar
        df_b.columns = df_b.columns.str.strip(); df_o.columns = df_o.columns.str.strip()
        req_b = {'FECHA DE OPERACIÓN','Movimiento','COP$','Empresa'}
        req_o = {'Fecha','Movimiento','Débito','Empresa'}
        if req_b - set(df_b.columns):
            return jsonify(success=False, message=f"Faltan columnas Bancos: {req_b - set(df_b.columns)}"), 400
        if req_o - set(df_o.columns):
            return jsonify(success=False, message=f"Faltan columnas Odoo: {req_o - set(df_o.columns)}"), 400
        # Limpieza montos
        def _cln(s):
            return (s.astype(str)
                     .str.replace(r"[^0-9\-.,]",'', regex=True)
                     .str.replace(',','', regex=False)
                     .replace('', '0')
                     .pipe(pd.to_numeric, errors='coerce').fillna(0))
        df_b['COP$'] = _cln(df_b['COP$'])
        df_o['Débito'] = _cln(df_o['Débito'])
        # Fechas
        df_b['FECHA DE OPERACIÓN'] = pd.to_datetime(df_b['FECHA DE OPERACIÓN'], errors='coerce')
        df_o['Fecha'] = pd.to_datetime(df_o['Fecha'], errors='coerce')
        df_b = df_b.dropna(subset=['FECHA DE OPERACIÓN'])
        df_o = df_o.dropna(subset=['Fecha'])
        df_b['fecha'] = df_b['FECHA DE OPERACIÓN'].dt.date.astype(str)
        df_o['fecha'] = df_o['Fecha'].dt.date.astype(str)
        # Clasificaciones bancos
        df_b['__mov'] = df_b['Movimiento'].astype(str).str.upper()
        saldo_ini = df_b[df_b['__mov'].str.contains('SALDO INICIAL', na=False)]
        ingresos_b = df_b[df_b['__mov'].str.contains('INGRESO', na=False) & ~df_b['__mov'].str.contains('SALDO INICIAL', na=False)]
        # Ingresos Odoo
        df_o['__mov'] = df_o['Movimiento'].astype(str).str.upper()
        ingresos_o = df_o[df_o['__mov'].str.contains('INGRESO', na=False)]
        # Agrupar
        saldo_ini_grp = saldo_ini.groupby(['fecha','Empresa'])['COP$'].sum().reset_index().rename(columns={'COP$':'saldo_inicial_bancos'})
        ing_b_grp = ingresos_b.groupby(['fecha','Empresa'])['COP$'].sum().reset_index().rename(columns={'COP$':'ingresos_bancos'})
        ing_o_grp = ingresos_o.groupby(['fecha','Empresa'])['Débito'].sum().reset_index().rename(columns={'Débito':'ingresos_odoo'})
        # Merge
        out = pd.merge(saldo_ini_grp, ing_b_grp, on=['fecha','Empresa'], how='outer')
        out = pd.merge(out, ing_o_grp, on=['fecha','Empresa'], how='outer')
        out = out.fillna(0)
        # Orden
        out = out.sort_values(['fecha','Empresa'])
        return jsonify(success=True, comparativo=out.to_dict(orient='records'))
    except Exception as e:
        app.logger.exception('Error flujo_efectivo_simple')
        return jsonify(success=False, message='Error interno'), 500

@login_required
@permiso_requerido('flujo_efectivo')
@app.route('/api/flujo_efectivo_cached', methods=['GET'])
def flujo_efectivo_cached():
    """Devuelve los datos consolidados desde la base sin necesidad de re-subir archivo."""
    try:
        bancos_rows = FlujoBancoMovimiento.query.all()
        odoo_rows = FlujoOdooMovimiento.query.all()
        if not bancos_rows and not odoo_rows:
            return jsonify(success=False, message='No hay datos cargados aún.')
        # Reutilizar lógica mínima (podríamos DRY, pero breve por claridad)
        # Daily comparison
        bancos_ing_map = {}; bancos_eg_map = {}; odoo_ing_map={}; odoo_eg_map={}
        for r in bancos_rows:
            mtxt=(r.movimiento or '').upper(); key=(r.fecha.isoformat(), r.empresa, r.banco or '')
            if 'SALDO INICIAL' in mtxt or 'GMF' in mtxt:
                continue
            if 'INGRESO' in mtxt:
                bancos_ing_map[key]=bancos_ing_map.get(key,0)+r.monto
            elif 'EGRESO' in mtxt:
                bancos_eg_map[key]=bancos_eg_map.get(key,0)+abs(r.monto)
        for r in odoo_rows:
            mtxt=(r.movimiento or '').upper(); key=(r.fecha.isoformat(), r.empresa, r.banco or '')
            if 'INGRESO' in mtxt: odoo_ing_map[key]=odoo_ing_map.get(key,0)+(r.debito or 0)
            if 'EGRESO' in mtxt: odoo_eg_map[key]=odoo_eg_map.get(key,0)+(r.credito or 0)
        keys_all = sorted(set(list(bancos_ing_map.keys())+list(bancos_eg_map.keys())+list(odoo_ing_map.keys())+list(odoo_eg_map.keys())))
        daily=[]
        for (f,e,b) in keys_all:
            ib=bancos_ing_map.get((f,e,b),0); eb=bancos_eg_map.get((f,e,b),0); io=odoo_ing_map.get((f,e,b),0); eo=odoo_eg_map.get((f,e,b),0)
            banco_norm = (b or '').strip()
            daily.append({'fecha':f,'Empresa':e,'tipo_banco':banco_norm,'banco':banco_norm,'ingresos_bancos':ib,'egresos_bancos':eb,'ingresos_odoo':io,'egresos_odoo':eo,'diferencia_ingresos':ib-io,'diferencia_egresos':eb-eo})
        detalle=[{'fecha':r.fecha.isoformat(),'empresa':r.empresa,'movimiento':r.movimiento,'debito':r.debito,'credito':r.credito,'tipo_flujo':r.tipo_flujo or 'SIN TIPO','tercero':r.tercero or 'SIN TERCERO','rubro':r.rubro or '','clase':r.clase or '','subclase':r.subclase or '','banco':r.banco or ''} for r in odoo_rows]
        inflows_by_type={}; outflows_by_type={}
        for r in odoo_rows:
            tf=(r.tipo_flujo or 'SIN TIPO'); terc=(r.tercero or 'SIN TERCERO')
            if (r.debito or 0)>0: inflows_by_type.setdefault(tf,{}).setdefault(terc,0); inflows_by_type[tf][terc]+=r.debito or 0
            if (r.credito or 0)>0: outflows_by_type.setdefault(tf,{}).setdefault(terc,0); outflows_by_type[tf][terc]+=r.credito or 0
        exw_rows=[r for r in odoo_rows if (r.clase or '').upper()=='VENTAS EXW CTG' and (r.debito or 0)>0]
        top_exw=None
        if exw_rows:
            agg={}
            for r in exw_rows:
                cli=(r.tercero or 'SIN TERCERO'); sub=(r.subclase or 'SIN SUBCLASE'); agg.setdefault(cli,{}).setdefault(sub,0); agg[cli][sub]+=r.debito or 0
            ranking=sorted([(cli,sum(subs.values()),subs) for cli,subs in agg.items()], key=lambda x:x[1], reverse=True)[:10]
            clientes_struct=[]
            for cli,total,subs in ranking:
                clientes_struct.append({'cliente':cli,'total':total,'subclases':[{'subclase':s,'total':v} for s,v in subs.items()]})
            top_exw={'clientes':clientes_struct,'total_general':sum(x[1] for x in ranking)}
        bancos_mov=[]
        for r in bancos_rows:
            mu=(r.movimiento or '').upper()
            if 'SALDO INICIAL' in mu:
                tipo='saldo_inicial'
            elif 'INGRESO' in mu:
                tipo='ingreso'
            elif 'EGRESO' in mu:
                tipo='egreso_gmf' if 'GMF' in mu else 'egreso'
            else:
                continue
            banco_norm = (r.tipo_banco or r.banco or '').strip()
            bancos_mov.append({'fecha':r.fecha.isoformat(),'empresa':r.empresa,'movimiento':r.movimiento,'monto':r.monto,'clasificacion':tipo,'tipo_banco':banco_norm,'banco':banco_norm})
        empresas=sorted({r.empresa for r in bancos_rows+odoo_rows if r.empresa})
        # Calcular saldo inicial: sumatoria SALDO INICIAL del primer día (todos bancos)
        saldo_inicial_rows = [r for r in bancos_rows if 'SALDO INICIAL' in (r.movimiento or '').upper()]
        if saldo_inicial_rows:
            # fecha mínima
            first_date = min(r.fecha for r in saldo_inicial_rows)
            saldo_inicial_total = sum(r.monto for r in saldo_inicial_rows if r.fecha == first_date)
        else:
            saldo_inicial_total = 0.0
        ingresos_total = sum(r.monto for r in bancos_rows if 'INGRESO' in (r.movimiento or '').upper() and 'SALDO INICIAL' not in (r.movimiento or '').upper())
        egresos_sin_gmf = sum(abs(r.monto) for r in bancos_rows if 'EGRESO' in (r.movimiento or '').upper() and 'GMF' not in (r.movimiento or '').upper())
        egresos_gmf = sum(abs(r.monto) for r in bancos_rows if 'GMF' in (r.movimiento or '').upper())
        egresos_total = egresos_sin_gmf + egresos_gmf
        resumen_directo = {
            'saldo_inicial': float(saldo_inicial_total),
            'ingresos': float(ingresos_total),
            'saldo_antes_egresos': float(saldo_inicial_total + ingresos_total),
            'egresos': float(egresos_sin_gmf),
            'egresos_gmf': float(egresos_gmf),
            'egresos_total': float(egresos_total),
            'saldo_final': float(saldo_inicial_total + ingresos_total - egresos_total)
        }
        payload={'success':True,'daily_comparison':daily,'outflows_by_type':outflows_by_type,'inflows_by_type':inflows_by_type,'todas_las_empresas':empresas,'odoo_detalle':detalle,'bancos_movimientos':bancos_mov,'resumen_directo':resumen_directo}
        if top_exw:
            payload['top_clientes_ventas_exw']=top_exw
        return jsonify(payload)
    except Exception:
        app.logger.exception('Error recuperando cache flujo efectivo')
        return jsonify(success=False, message='Error interno.'), 500

@login_required
@permiso_requerido('flujo_efectivo')
@app.route('/api/flujo_efectivo_delete_all', methods=['DELETE'])
def flujo_efectivo_delete_all():
    """Elimina TODOS los registros cargados del módulo Flujo de Efectivo (batches, bancos y odoo).

    Uso previsto: antes de volver a subir un archivo completo actualizado para evitar duplicados
    de meses anteriores. Tras la eliminación se puede subir un Excel que contenga histórico + meses nuevos.
    """
    try:
        # Primero eliminar movimientos hijos para respetar FK (no hay cascade definido)
        deleted_bancos = db.session.query(FlujoBancoMovimiento).delete(synchronize_session=False)
        deleted_odoo = db.session.query(FlujoOdooMovimiento).delete(synchronize_session=False)
        deleted_batches = db.session.query(FlujoUploadBatch).delete(synchronize_session=False)
        db.session.commit()
        return jsonify(success=True,
                       message="Datos de Flujo de Efectivo eliminados correctamente.",
                       eliminados_bancos=deleted_bancos,
                       eliminados_odoo=deleted_odoo,
                       eliminados_batches=deleted_batches)
    except Exception as e:
        db.session.rollback()
        app.logger.exception('Error eliminando datos de flujo de efectivo')
        return jsonify(success=False, message=f'Error interno: {e}'), 500

@login_required
@permiso_requerido('flujo_efectivo')
@app.route('/api/procesar_facturacion', methods=['POST'])
def procesar_facturacion_api():
    """Procesa un Excel de facturación para extender la gráfica de ingresos.
    Columnas mínimas: (Numero Factura / Factura), (Cliente / Tercero), (COP$ / Valor / Monto).
    Opcional: Bbl / Barriles.
    Devuelve lista de facturas normalizada.
    """
    if 'archivo_excel' not in request.files:
        return jsonify(success=False, message='No se encontró archivo.'), 400
    archivo = request.files['archivo_excel']
    if archivo.filename == '':
        return jsonify(success=False, message='Nombre de archivo vacío.'), 400
    try:
        df = pd.read_excel(archivo)
        df.columns = df.columns.str.strip()

        def find_col(cands):
            for c in cands:
                if c in df.columns:
                    return c
            return None

        col_num = find_col(['Numero Factura','Número Factura','Nro Factura','Factura','FACTURA','NUMERO FACTURA','Número','NUMERO','Numero'])
        col_cli = find_col(['Cliente','CLIENTE','Tercero','TERCERO','Asociado','ASOCIADO'])
        col_cop = find_col(['COP$','Valor','VALOR','Monto','MONTO'])
        col_bbl = find_col(['Bbl','BBL','Barriles','BARRILES'])
        col_gln = find_col(['Gln','GLN','Galones','GALONES','Galón','GALÓN','gln','galones'])
        col_ton = find_col(['Ton','TON','Toneladas','TONELADAS','Tonelada','TONELADA','ton','toneladas'])
        col_etiqueta = find_col(['Etiqueta','ETIQUETA'])
        col_fecha = find_col(['Fecha','FECHA','Date','DATE'])

        if not (col_num and col_cli and col_cop):
            return jsonify(success=False, message=f"Faltan columnas obligatorias (Factura, Cliente/Tercero, Valor). Columnas disponibles: {list(df.columns)}"), 400

        def clean(series):
            return (series.astype(str)
                          .str.replace(r"[^0-9\-.,]",'', regex=True)
                          .str.replace(',', '', regex=False)
                          .replace('', '0')
                          .pipe(pd.to_numeric, errors='coerce').fillna(0))

        df[col_cop] = clean(df[col_cop])
        if col_bbl:
            df[col_bbl] = clean(df[col_bbl])
        if col_gln:
            df[col_gln] = clean(df[col_gln])
        if col_ton:
            df[col_ton] = clean(df[col_ton])

        # Normalizar fecha si existe
        if col_fecha:
            try:
                df[col_fecha] = pd.to_datetime(df[col_fecha], errors='coerce')
            except Exception:
                df[col_fecha] = pd.NaT

        facturas = []
        for _, r in df.iterrows():
            fila = {
                'factura': str(r.get(col_num)),
                'tercero': str(r.get(col_cli) or 'SIN TERCERO'),
                'valor': float(r.get(col_cop) or 0),
                'bbl': float(r.get(col_bbl) or 0) if col_bbl else None,
                'gln': float(r.get(col_gln) or 0) if col_gln else None,
                'ton': float(r.get(col_ton) or 0) if col_ton else None
            }
            if col_etiqueta:
                fila['etiqueta'] = str(r.get(col_etiqueta) or '').strip()
            if col_fecha:
                fv = r.get(col_fecha)
                if pd.notna(fv):
                    try:
                        fila['fecha'] = pd.to_datetime(fv).date().isoformat()
                    except Exception:
                        pass
            facturas.append(fila)
        return jsonify(success=True, facturas=facturas)
    except Exception as e:
        app.logger.exception('Error procesando facturación')
        return jsonify(success=False, message=str(e)), 500

@app.route('/')
def home():
    """Redirige al usuario a su página de inicio correcta después de iniciar sesión."""
    if 'email' not in session:
        return redirect(url_for('login'))
    
    user_areas = session.get('area', [])
    user_email = session.get('email')

    # --- REGLA 1: Usuarios con roles o emails exclusivos ---
    if session.get('rol') == 'admin':
        return redirect(url_for('dashboard_reportes'))

    # ✅ REGLA PARA SAMANTHA: Si es ella, siempre va a su home de logística.
    if user_email == 'logistic@conquerstrading.com':
        return redirect(url_for('home_logistica'))
    
    if user_email == 'accountingzf@conquerstrading.com':
        return redirect(url_for('home_contabilidad'))


    # --- EXCEPCIÓN PARA DANIELA, FELIPE Y ANA: Siempre dashboard general ---
    if user_email in ['comex@conquerstrading.com', 'felipe.delavega@conquerstrading.com', 'amariagallo@conquerstrading.com']:
        return redirect(url_for('dashboard_reportes'))

    # --- EXCEPCIÓN PARA SEBASTIAN: Siempre home de Inventario EPP ---
    if user_email == 'safety@conquerstrading.com':
        return redirect(url_for('inventario_epp_home'))

    # --- REGLA 2: Usuarios con un único permiso específico ---
    if len(user_areas) == 1:
        area_unica = user_areas[0]
        if area_unica == 'programacion_cargue':
            return redirect(url_for('home_programacion'))
        if area_unica == 'control_remolcadores':
            return redirect(url_for('home_remolcadores'))
        if area_unica == 'simulador_rendimiento':
            return redirect(url_for('home_simulador'))
        if area_unica == 'guia_transporte':
            return redirect(url_for('home_logistica'))
        if area_unica == 'zisa_inventory':
            return redirect(url_for('home_siza'))
        if area_unica == 'inventario_epp':
            return redirect(url_for('inventario_epp_home'))

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


# Modelos SQLAlchemy para Cliente, Conductor y Empresa
from flask_sqlalchemy import SQLAlchemy
db: SQLAlchemy  # Asegúrate de que tu app ya tiene db = SQLAlchemy(app)

class Cliente(db.Model):
    __tablename__ = 'clientes'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(255), nullable=False, unique=True)
    direccion = db.Column(db.String(255), nullable=False)
    ciudad_departamento = db.Column(db.String(255), nullable=False)

class Conductor(db.Model):
    __tablename__ = 'conductores'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(255), nullable=False)
    cedula = db.Column(db.String(64), nullable=False, unique=True)
    placa = db.Column(db.String(64), nullable=False)

class Empresa(db.Model):
    __tablename__ = 'empresas_transportadoras'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(255), nullable=False, unique=True)

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
    # Verificar si el cliente ya existe en JSON
    if any(c['NOMBRE_CLIENTE'].lower() == nombre.lower() for c in clientes):
        flash(f"El cliente '{nombre}' ya existe en la base de datos.", "warning")
        return redirect(url_for('gestionar_clientes'))

    nuevo_cliente = {
        "NOMBRE_CLIENTE": nombre.upper(),
        "DIRECCION": direccion.upper(),
        "CIUDAD_DEPARTAMENTO": ciudad.upper()
    }
    clientes.append(nuevo_cliente)
    clientes.sort(key=lambda x: x['NOMBRE_CLIENTE'])
    guardar_clientes(clientes)

    # Guardar también en PostgreSQL
    try:
        if not Cliente.query.filter_by(nombre=nombre.upper()).first():
            cliente_db = Cliente(
                nombre=nombre.upper(),
                direccion=direccion.upper(),
                ciudad_departamento=ciudad.upper()
            )
            db.session.add(cliente_db)
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f"Error al guardar en la base de datos: {e}", "danger")
        return redirect(url_for('gestionar_clientes'))

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

    # Guardar también en PostgreSQL
    try:
        if not Cliente.query.filter_by(nombre=nombre.upper()).first():
            cliente_db = Cliente(
                nombre=nombre.upper(),
                direccion=direccion.upper(),
                ciudad_departamento=ciudad.upper()
            )
            db.session.add(cliente_db)
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, message=f"Error al guardar en la base de datos: {e}"), 500

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
    conductores.sort(key=lambda x: x.get('CONDUCTOR', ''))
    guardado_exitoso = guardar_conductores(conductores)

    # Guardar también en PostgreSQL
    try:
        if not Conductor.query.filter_by(cedula=cedula.upper()).first():
            conductor_db = Conductor(
                nombre=nombre.upper(),
                cedula=cedula.upper(),
                placa=placa.upper()
            )
            db.session.add(conductor_db)
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, message=f"Error al guardar en la base de datos: {e}"), 500

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

    # Guardar también en PostgreSQL
    try:
        if not Empresa.query.filter_by(nombre=nombre.upper()).first():
            empresa_db = Empresa(nombre=nombre.upper())
            db.session.add(empresa_db)
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, message=f"Error al guardar en la base de datos: {e}"), 500

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