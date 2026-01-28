from flask import Blueprint, render_template, request, flash, redirect, url_for
from datetime import date, datetime, timedelta
import pandas as pd
import yfinance as yf
import requests
from io import BytesIO
import io

# Definicion del Blueprint
pricing_bp = Blueprint('pricing_bp', __name__, template_folder='templates')

@pricing_bp.route('/pricing', methods=['GET'])
def index():
    from pricing.models import HistorialCombustibles
    records = HistorialCombustibles.query.order_by(HistorialCombustibles.fecha.desc()).all()
    
    # 1. Calcular TRM Promedio Mensual (basado en registros)
    trm_sums = {}
    trm_counts = {}
    
    for r in records:
        if r.trm and r.trm > 0:
            key = (r.fecha.year, r.fecha.month)
            trm_sums[key] = trm_sums.get(key, 0) + r.trm
            trm_counts[key] = trm_counts.get(key, 0) + 1

            
    trm_avgs = {k: trm_sums[k]/trm_counts[k] for k in trm_sums}
    
    # 2. Enriquecer registros con "Premium COP"
    # Formula: (USD_BLL original / 42.0) * TRM_Mensual
    for r in records:
        trm_mes = trm_avgs.get((r.fecha.year, r.fecha.month), r.trm or 0)
        r.trm_mensual_used = trm_mes
        
        # Helper interno
        def to_cop_gal(usd_val):
            if not usd_val: return 0.0
            return (usd_val / 42.0) * trm_mes
            
        r.premium_cop_f04_base = to_cop_gal(r.f04_base_usd)
        r.premium_cop_f04_total = to_cop_gal(r.f04_total_usd)
        r.premium_cop_fuel_oil = to_cop_gal(r.fuel_oil_usd)
        r.premium_cop_bpi = to_cop_gal(r.bpi_usd_bll)

    return render_template('pricing/f04_premium.html', records=records)

@pricing_bp.route('/pricing/reset', methods=['POST'])
def reset_prices():
    from extensions import db
    from pricing.models import HistorialCombustibles
    
    try:
        num_deleted = db.session.query(HistorialCombustibles).delete()
        db.session.commit()
        flash(f"Historial eliminado correctamente ({num_deleted} registros). El sistema se reiniciará desde 2025.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error eliminando historial: {e}", "danger")
        
    return redirect(url_for('pricing_bp.index'))

@pricing_bp.route('/pricing/update', methods=['POST'])
def update_prices():
    from extensions import db
    from pricing.models import HistorialCombustibles
    
    # Optimización: Buscar última fecha registrada
    latest_record = HistorialCombustibles.query.order_by(HistorialCombustibles.fecha.desc()).first()

    start_date = date(2025, 1, 1)
    
    start_date = date(2025, 1, 1)
    
    if latest_record:
        # Si el ultimo registro tiene los datos completos, continuamos desde el dia siguiente
        # Si no (ej. esquema viejo), recargamos todo 2025 para corregir.
        if getattr(latest_record, 'diff_f04_base', None) is None:
             start_date = date(2025, 1, 1)
        else:
             start_date = latest_record.fecha + timedelta(days=1)
    
    today = date.today()
    
    # Validar si el ultimo registro esta corrupto (Brent = 0 o None)
    # getattr devuelve el valor del atributo (que puede ser None), no el default si existe.
    start_year = date(2025, 1, 1)
    
    # NUEVA LOGICA: Buscar cualquier hueco (Gap) en el pasado, no solo mirar el ultimo dia.
    # Buscamos el primer registro desde 2025 que tenga Brent=0 o F04=0
    from sqlalchemy import or_
    bad_record = HistorialCombustibles.query.filter(
        HistorialCombustibles.fecha >= start_year,
        or_(
            HistorialCombustibles.brent <= 0.01,
            HistorialCombustibles.f04_base_cop <= 0.01,
            HistorialCombustibles.f04_total_cop <= 0.01
        )
    ).order_by(HistorialCombustibles.fecha.asc()).first()
    
    if bad_record:
        # Si encontramos un dia con ceros, forzamos iniciar desde ahi para repararlo
        start_date = bad_record.fecha
        flash(f"Se encontraron datos incompletos (ceros) desde el {start_date}. Reparando historial...", "warning")
    
    # Si no hay huecos, usamos la logica normal de continuar desde el ultimo
    elif latest_record:
        if getattr(latest_record, 'diff_f04_base', None) is None:
             start_date = start_year
        else:
             start_date = latest_record.fecha + timedelta(days=1)
    
    # Proteccion limite futuro
    if start_date > today:
       flash("La base de datos ya está actualizada hasta hoy y sin huecos aparentes.", "info")
       return redirect(url_for('pricing_bp.index'))

    ECOPETROL_URL = "https://www.ecopetrol.com.co/wps/wcm/connect/94bf0826-889a-4937-a6c0-668e35b1ea55/PME-VPRECIOSCRUDOSYFUELOILPARAIFOS-15.xls?MOD=AJPERES&attachment=true&id=1589474858686"
    
    # 1. BRENT - SISTEMA MULTI-FUENTE (EIA -> Yahoo -> BD)
    brent_df = pd.DataFrame()
    latest_brent = latest_record.brent if (latest_record and latest_record.brent) else 75.0
    
    # FUENTE 1: EIA (US Energy Information Administration - Oficial, gratis, sin key)
    try:
        print("Intentando obtener Brent desde EIA API...")
        fetch_start = start_date - timedelta(days=10)
        
        # EIA endpoint para Brent (Europe Brent Spot Price FOB)
        eia_url = "https://api.eia.gov/v2/petroleum/pri/spt/data/"
        eia_api_key = "1436df7a36c507c936056b2c8646e38b" # Public key or user provided
        params = {
            "frequency": "daily",
            "data[0]": "value",
            "facets[series][]": "RBRTE",
            "start": fetch_start.strftime("%Y-%m-%d"),
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
            "offset": 0,
            "length": 5000,
            "api_key": eia_api_key
        }
        
        response = requests.get(eia_url, params=params, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            if 'response' in data and 'data' in data['response']:
                records = data['response']['data']
                
                if records:
                    # Convertir a DataFrame
                    df_temp = pd.DataFrame(records)
                    df_temp['date'] = pd.to_datetime(df_temp['period'])
                    df_temp = df_temp.set_index('date')
                    df_temp = df_temp.sort_index()
                    df_temp['brent'] = pd.to_numeric(df_temp['value'], errors='coerce')
                    
                    brent_df = df_temp[['brent']].dropna()
                    
                    if not brent_df.empty:
                        latest_brent = float(brent_df['brent'].iloc[-1])
                        print(f"✓ EIA: Último Brent = {latest_brent} ({brent_df.index[-1].date()})")
                    else:
                        raise ValueError("EIA data empty after processing")
                else:
                    raise ValueError("No EIA records found")
        else:
            raise ValueError(f"EIA HTTP {response.status_code}")
            
    except Exception as e_eia:
        print(f"✗ EIA falló: {e_eia}")
        
        # FUENTE 2: Yahoo Finance (Respaldo)
        try:
            print("Intentando Yahoo Finance como respaldo...")
            import yfinance as yf
            import time
            import random
            
            # Intento de descarga robusta con yfinance para historial completo 2025-2026
            max_retries = 3
            success = False
            
            for attempts in range(1, max_retries + 1):
                try:
                    # RANGO: Desde 2025 para asegurar historial completo y variaciones
                    # yf.download es más confiable que Ticker.history para rangos largos en batch
                    brent_df_yf = yf.download("BZ=F", start="2025-01-01", progress=False, timeout=20)

                    if not brent_df_yf.empty:
                        success = True
                        
                        # Limpieza de MultiIndex (comun en versiones recientes yfinance)
                        if isinstance(brent_df_yf.columns, pd.MultiIndex):
                            try:
                                # Prioridad: Close o Adj Close
                                if 'Close' in brent_df_yf.columns.get_level_values(0):
                                     brent_df_yf = brent_df_yf.xs('Close', level=0, axis=1)
                                elif 'Adj Close' in brent_df_yf.columns.get_level_values(0):
                                     brent_df_yf = brent_df_yf.xs('Adj Close', level=0, axis=1)
                            except:
                                brent_df_yf.columns = [c[0] for c in brent_df_yf.columns]

                        # Asegurar normalización a una sola columna 'brent'
                        if isinstance(brent_df_yf, pd.DataFrame) and brent_df_yf.shape[1] >= 1:
                            # Tomar la primera columna si quedo alguna limpieza pendiente explícita
                            val_series = brent_df_yf.iloc[:, 0]
                        else:
                            val_series = brent_df_yf # Ya es serie

                        brent_df = pd.DataFrame({'brent': val_series})
                        
                        # CRITICO: Eliminar zona horaria
                        if brent_df.index.tz is not None:
                             brent_df.index = brent_df.index.tz_localize(None)

                        latest_valid = brent_df['brent'].last_valid_index()
                        if latest_valid:
                             latest_brent = float(brent_df.loc[latest_valid, 'brent'])
                             print(f"✓ Yahoo Download Completo (2025-Pres). Último: {latest_brent} ({latest_valid})")
                        break 
                    else:
                        print(f"⚠ Yahoo devolvió vacío en intento {attempts}")
                        time.sleep(2)
                except Exception as e_down:
                    print(f"⚠ Yahoo intento {attempts} falló: {e_down}")
                    time.sleep(random.uniform(1.0, 3.0))
            
            if not success:
                 print("✗ Yahoo Finance falló definitivamente tras reintentos.")
                
        except Exception as e_yahoo:
            print(f"✗ Yahoo Finance falló: {e_yahoo}")
            print(f"⚠ Usando último valor conocido de BD: {latest_brent}")
    
    
    # Asegurar orden
    brent_df = brent_df.sort_index()


    # 2. TRM (Datos.gov.co) - Fuente Oficial
    trm_map = {}
    latest_trm = 4000.0 # Default seguro
    try:
        # Consultar API (Buffer de seguridad)
        fetch_start = start_date - timedelta(days=7)
        f_str = fetch_start.strftime('%Y-%m-%d')
        url_trm = f"https://www.datos.gov.co/resource/32sa-8pi3.json?$where=vigenciadesde >= '{f_str}T00:00:00.000'"
        resp_trm = requests.get(url_trm, timeout=30)
        resp_trm.raise_for_status()
        data_trm = resp_trm.json()
        
        last_date_found = None

        for item in data_trm:
            # Formato fecha: 2025-01-01T00:00:00.000
            f_desde_str = item.get('vigenciadesde')
            f_hasta_str = item.get('vigenciahasta')
            val = float(item.get('valor', 0))
            
            if f_desde_str and f_hasta_str:
                d_desde = datetime.strptime(f_desde_str[:10], '%Y-%m-%d').date()
                d_hasta = datetime.strptime(f_hasta_str[:10], '%Y-%m-%d').date()
                
                # Rastrear la fecha mas reciente vista
                if last_date_found is None or d_hasta > last_date_found:
                    last_date_found = d_hasta
                    latest_trm = val
                
                # Llenar rango
                curr_trm = d_desde
                while curr_trm <= d_hasta:
                    trm_map[curr_trm] = val
                    curr_trm += timedelta(days=1)
        
        print(f"Ultima TRM Real: {latest_trm} ({last_date_found})")
                    
    except Exception as e:
        print(f"Error Datos.gov.co TRM: {e}")


    # 2. Descargar y Procesar Hoja "Fuel Oil No 4" - Lógica APIAY por Semanas
    eco_data_f04 = {} 
    
    try:
        resp = requests.get(ECOPETROL_URL, headers={'User-Agent': 'Mozilla/5.0'}, timeout=60, verify=False)
        resp.raise_for_status()
        excel_file = BytesIO(resp.content)
        
        xl = pd.ExcelFile(excel_file)
        # Listar hojas para debug
        sheet_names = xl.sheet_names
        print(f"DEBUG: Hojas encontradas: {sheet_names}")
        
        # Buscar hoja "Fuel Oil No. 4" (flexible)
        sheet_name = next((s for s in sheet_names if "FUEL" in s.upper() and "4" in s), None)
        
        if not sheet_name: 
            # Si falla, intentar una búsqueda más laxa o usar la segunda si existe
            sheet_name = sheet_names[1] if len(sheet_names) > 1 else sheet_names[0]
            flash(f"Aviso: No se halló hoja exacta 'Fuel Oil No 4'. Usando: '{sheet_name}'. Hojas disponibles: {', '.join(sheet_names)}", "info")
                
        df = pd.read_excel(excel_file, sheet_name=sheet_name, header=None)
        
        # Mapa de meses español (completo y abreviado)
        meses = {
            'enero': 1, 'ene': 1, 'jan': 1,
            'febrero': 2, 'feb': 2,
            'marzo': 3, 'mar': 3,
            'abril': 4, 'abr': 4, 'apr': 4,
            'mayo': 5, 'may': 5,
            'junio': 6, 'jun': 6,
            'julio': 7, 'jul': 7,
            'agosto': 8, 'ago': 8, 'aug': 8,
            'septiembre': 9, 'sep': 9, 'set': 9,
            'octubre': 10, 'oct': 10,
            'noviembre': 11, 'nov': 11,
            'diciembre': 12, 'dic': 12, 'dec': 12
        }

        def parse_spanish_date(date_val, year_hint=None):
            # Si ya es un objeto fecha, devolverlo
            if isinstance(date_val, (pd.Timestamp, datetime, date)):
                return date_val.date() if hasattr(date_val, 'date') else date_val
            
            # Si es string
            date_str = str(date_val).strip()
            
            # Intento 1: Formato pandas default y formatos comunes cortos
            try:
                # Si contiene texto, a veces pd.to_datetime falla en locale EN si no entiende "Ene"
                # Intentamos parsear directamente solo si parece formato ISO o standard
                 if '-' in date_str and date_str[0].isdigit() and date_str.split('-')[1].isdigit():
                     ts = pd.to_datetime(date_str, errors='raise')
                     return ts.date()
            except:
                pass

            # Intento 2: Parseo manual robusto para Español / Texto sucio
            try:
                # Pre-limpieza de basura específica
                s_clean = date_str.lower()
                s_clean = s_clean.replace('sujeto', ' sujeto ')
                s_clean = s_clean.replace('hasta', ' ')
                s_clean = s_clean.replace(u'\xa0', ' ') # Non-breaking space
                # Reemplazar separadores por espacios
                s_clean = s_clean.replace(',', ' ').replace('.', ' ').replace('-', ' ').replace('/', ' ')
                s_clean = s_clean.replace('del', ' ').replace('de', ' ')
                
                parts = s_clean.split()
                day, month, year = None, None, None
                
                for part in parts:
                    if part.isdigit():
                        val = int(part)
                        if val > 31: 
                            year = val
                        else: 
                            if not day: day = val
                            else: year = val # Conflicto dia/año, asumir segundo es año si hay duda
                    elif part in meses:
                        month = meses[part]
                
                # Inferencia: Si tenemos día y mes pero falta año
                if day and month and not year:
                    if year_hint:
                        year = int(year_hint)
                    else:
                        year = datetime.now().year

                if day and month and year:
                    return date(year, month, day)
            except Exception as e_parse:
                print(f"Error parsing date '{date_str}': {e_parse}")
                pass
                
            # Ultimo intento: pd.to_datetime genérico (puede fallar en locale incorrecto)
            try:
                ts = pd.to_datetime(date_str, errors='coerce')
                if not pd.isna(ts): return ts.date()
            except: pass
            
            # Solo logear si parece una fecha real pero falló
            if len(date_str) > 5 and any(c.isdigit() for c in date_str):
                print(f"WARN: Could not parse date string: '{date_str}'")
            
            return None

        # Buscar bloque "Fuel Oil No. 4 Apiay"
        # Estrategia: Buscar fila con texto "Fuel Oil No. 4 Apiay"
        # Las columnas de datos (Ingreso, IVA, Carbono) suelen estar relativas a ese encabezado
        
        if True:
             print("DEBUG: Buscando encabezados...")
             start_row = None
             
             # 1. Buscar la fila de encabezados (Promote Headers)
             for r_idx, row in df.iterrows():
                 row_str = row.astype(str).str.upper().str.cat()
                 if "INGRESO" in row_str and "PRODUCTOR" in row_str:
                     start_row = r_idx + 1 # Datos empiezan despues de esta linea
                     print(f"DEBUG: Encabezados encontrados en fila {r_idx}")
                     break
            
             if start_row is None:
                 print("DEBUG: No se encontró fila de encabezados explícita. Intentando escaneo completo.")
                 start_row = 0

             found_dates = 0
             
             # 2. Iterar filas de datos (Filtrar filas)
             for r_idx in range(start_row, len(df)):
                 row = df.iloc[r_idx]
                 
                 # Limpieza básica de fechas (trim)
                 fecha_inicio_raw = str(row[0]).strip() if pd.notnull(row[0]) else ""
                 fecha_fin_raw = str(row[1]).strip() if pd.notnull(row[1]) else ""
                 
                 # Si no hay texto de fecha, saltar (Filas vacías)
                 if len(fecha_inicio_raw) < 5: continue
                 
                 d_inicio = parse_spanish_date(fecha_inicio_raw)
                 d_fin_hint = d_inicio.year if d_inicio else None
                 d_fin = parse_spanish_date(fecha_fin_raw, year_hint=d_fin_hint)
                 
                 if not d_inicio:
                    # Debug solo para fechas recientes (potenciales) para no ensuciar log
                    if "2025" in fecha_inicio_raw or "25" in fecha_inicio_raw:
                         print(f"DEBUG FAIL PARSE: Raw='{fecha_inicio_raw}' -> Parsed=None")
                    continue 

                 # Debug éxito para confirmar formato
                 if d_inicio.year == 2025 or d_inicio.year == 2026:
                     print(f"DEBUG SUCCESS: Raw='{fecha_inicio_raw}' -> {d_inicio}") 
                 
                 if not d_fin or d_fin == d_inicio:
                     # Intentar buscar la FECHA DE INICIO de la SIGUIENTE fila válida para cerrar este rango
                     # Escaneamos hacia abajo buscando la proxima fecha valida
                     next_start_found = None
                     for lookahead_idx in range(r_idx + 1, min(r_idx + 10, len(df))): # Mirar 10 filas adelante
                         try:
                             row_next = df.iloc[lookahead_idx]
                             next_raw = str(row_next[0]).strip() if pd.notnull(row_next[0]) else ""
                             if len(next_raw) > 5:
                                 next_date = parse_spanish_date(next_raw)
                                 if next_date and next_date > d_inicio:
                                     next_start_found = next_date
                                     break
                         except: pass
                     
                     if next_start_found:
                         d_fin = next_start_found - timedelta(days=1)
                         print(f"DEBUG: Fecha fin inferida para {d_inicio} -> {d_fin}")
                     else:
                         # Si no hay siguiente, asumir 6 dias (semana estandar ecopetrol)
                         d_fin = d_inicio + timedelta(days=6)
                         print(f"DEBUG: Fecha fin asumida (default 1 sem) para {d_inicio} -> {d_fin}")
                 
                 found_dates += 1
                 
                 # 3. Extraer valores numéricos (Columna personalizada / Tipo cambiado)
                 def get_val(idx):
                     try: 
                         v = row.iloc[idx]
                         if pd.isna(v): return 0.0
                         
                         # Si ya es número, devolverlo directo (evitar bug de eliminar punto decimal)
                         if isinstance(v, (int, float)):
                             return float(v)
                             
                         # Manejo español solo si es STRING: 1.234,56 -> 1234.56
                         s = str(v).strip()
                         s = s.replace('.', '').replace(',', '.')
                         return float(s)
                     except: return 0.0

                 # Mapeo fijo basado en estructura visual del usuario
                 # Col 3 (D): Ingreso (COP/BLL)
                 # Col 4 (E): IVA
                 # Col 5 (F): Impuesto Carbono ($/GLN)
                 
                 # DEBUG: Show raw cell values for Jan 2025/2026
                 if (d_inicio.year == 2025 or d_inicio.year == 2026) and d_inicio.month == 1:
                     print(f"DEBUG RAW {d_inicio}: D=[{row.iloc[3]}] E=[{row.iloc[4]}] F=[{row.iloc[5]}]")
                  
                 val_ingreso = get_val(3)
                 val_iva = get_val(4)
                 val_carbono = get_val(5)
                 
                 # 4. Transformaciones (Expandir fechas)
                 val_carbono_bll = val_carbono * 42.0 # GLN a BLL
                 
                 # DEBUG: Show parsed values for Jan 2025/2026
                 if (d_inicio.year == 2025 or d_inicio.year == 2026) and d_inicio.month == 1:
                     print(f"DEBUG PARSED {d_inicio}->{d_fin}: Base={val_ingreso} IVA={val_iva} Carb={val_carbono}")
                  
                 curr = d_inicio
                 while curr <= d_fin:
                     # Protección contra rangos absurdamente largos (error de data)
                     if (curr - d_inicio).days > 60: break
                     
                     eco_data_f04[curr] = {
                         'base': val_ingreso,
                         'impuestos': val_iva + val_carbono_bll
                     }
                     curr += timedelta(days=1)

             
             if found_dates == 0:
                 flash("Tabla encontrada pero no se pudieron parsear fechas. Formato desconocido.", "warning")
             # else:
             #    pass # Debug removed

        else:
             flash(f"No se encontraron columnas 'Ingreso al productor' e 'IVA' en hoja '{sheet_name}'.", "warning")
        
        if not eco_data_f04:
             flash("Advertencia: No se extrajeron datos. Verifique mensajes anteriores.", "warning")

    except Exception as e:
        print(f"Error procesando Ecopetrol Apiay: {e}")
        flash(f"Error lectura Excel: {e}", "warning")

    # 3. Descargar y Procesar Hoja "Fuel Oil" (Standard)
    eco_data_fo = {}
    try:
        # sheet_name ya fue definido arriba, buscar ahora la hoja de Fuel Oil standard
        # Asumimos que xl sigue abierto o disponible, si no, reusamos xl (pd.ExcelFile)
        # Re-buscar hoja: Que tenga "FUEL" pero NO "4"
        sheet_name_fo = next((s for s in sheet_names if "FUEL" in s.upper() and "4" not in s), None)
        
        if sheet_name_fo:
            df_fo = pd.read_excel(excel_file, sheet_name=sheet_name_fo, header=None)
            
            # Buscar encabezados
            start_row_fo = None
            col_ingreso_fo = None
            
            if True: # Busqueda headers
                for r_idx, row in df_fo.iterrows():
                    row_str = row.astype(str).str.upper().str.cat()
                    if "INGRESO" in row_str and "PRODUCTOR" in row_str:
                         start_row_fo = r_idx + 1
                         # Identificar columna
                         for c_idx, val in row.items():
                             if "INGRESO" in str(val).upper():
                                 col_ingreso_fo = c_idx
                         break
            
            if start_row_fo is None:
                 print(f"WARN: No se encontró header 'INGRESO PRODUCTOR' en hoja '{sheet_name_fo}'. Intentando escaneo completo.")
                 start_row_fo = 0

            # Iterar siempre si start_row_fo tiene valor (aunque sea 0)
            if start_row_fo is not None:
                print(f"DEBUG: Escaneando Fuel Oil desde fila {start_row_fo}")
                for r_idx in range(start_row_fo, len(df_fo)):
                    row = df_fo.iloc[r_idx]
                    
                    # Fechas (igual structura rango)
                    f_inicio = parse_spanish_date(row[0])
                    f_fin = parse_spanish_date(row[1])
                    
                    if not f_inicio: continue
                    if not f_fin: f_fin = f_inicio
                    
                    # Valor
                    val_fo = 0.0
                    if col_ingreso_fo is not None:
                         # Extraction segura
                         try:
                             v = row.iloc[col_ingreso_fo]
                             if isinstance(v, (int, float)): val_fo = float(v)
                             else:
                                 s = str(v).strip().replace('.', '').replace(',', '.')
                                 val_fo = float(s)
                         except: val_fo = 0.0
                    else:
                        # Fallback a columna fija si no halló header (usualmente D=3)
                        try:
                             v = row.iloc[3]
                             if isinstance(v, (int, float)): val_fo = float(v)
                             else:
                                 s = str(v).strip().replace('.', '').replace(',', '.')
                                 val_fo = float(s)
                        except: val_fo = 0.0

                    # Llenar rango
                    curr = f_inicio
                    while curr <= f_fin:
                         if (curr - f_inicio).days > 60: break
                         eco_data_fo[curr] = val_fo
                         curr += timedelta(days=1)
        else:
            print("DEBUG: No se encontró hoja Fuel Oil (Standard)")

    except Exception as e:
        print(f"Error procesando Fuel Oil Standard: {e}")

    # 4. Descargar y Procesar Hoja "Base Pesada IFOS"
    eco_data_bpi = {}
    try:
        # Búsqueda flexible pero priorizando el nombre exacto si existe
        target_sheet = "Base pesada para IFOS"
        sheet_name_bpi = next((s for s in sheet_names if s.strip().lower() == target_sheet.lower()), None)
        
        # Fallback de búsqueda
        if not sheet_name_bpi:
             sheet_name_bpi = next((s for s in sheet_names if "IFOS" in s.upper() or ("BASE" in s.upper() and "PESADA" in s.upper())), None)
        
        if sheet_name_bpi:
            print(f"DEBUG: Hoja BPI encontrada: {sheet_name_bpi}")
            df_bpi = pd.read_excel(excel_file, sheet_name=sheet_name_bpi, header=None)
            
            col_precio_bpi = None
            
            # Barrer filas buscando fechas y detectar columna de precio al vuelo
            for r_idx, row in df_bpi.iterrows():
                # 1. Validar si Col 0 es fecha
                f_inicio_raw = row[0]
                if pd.isna(f_inicio_raw) or str(f_inicio_raw).strip() == "": continue
                
                # Optimización preliminar (longitud texto)
                if len(str(f_inicio_raw)) < 5: continue

                f_inicio = parse_spanish_date(f_inicio_raw)
                if not f_inicio: continue
                
                # 2. Parsear fecha fin (Col 1)
                f_fin_raw = row[1]
                hint = f_inicio.year if f_inicio else None
                f_fin = parse_spanish_date(f_fin_raw, year_hint=hint)
                if not f_fin: f_fin = f_inicio
                
                # 3. Detectar Columna Precio (Heurística: Primer numero > 500 en cols C, D, E...)
                val_bpi = 0.0
                
                if col_precio_bpi is None:
                    # Buscar en columnas 2 a 6
                    for c_candidate in range(2, 7):
                        if c_candidate >= len(row): break
                        try:
                            val_test = row.iloc[c_candidate]
                            if isinstance(val_test, (int, float)):
                                v_float = float(val_test)
                            else:
                                s = str(val_test).strip().replace('.', '').replace(',', '.')
                                v_float = float(s)
                            
                            # Filtro de cordura: Precio BPI suele ser ~2000+. 
                            # Evitar coger indices o porcentajes pequeños.
                            if v_float > 500: 
                                col_precio_bpi = c_candidate
                                val_bpi = v_float
                                break
                        except: pass
                else:
                    # Usar columna ya conocida
                    try:
                        v = row.iloc[col_precio_bpi]
                        if isinstance(v, (int, float)): 
                            val_bpi = float(v)
                        else:
                            s = str(v).strip().replace('.', '').replace(',', '.')
                            val_bpi = float(s)
                    except: val_bpi = 0.0
                
                # Guardar rango
                if val_bpi > 0:
                    curr = f_inicio
                    while curr <= f_fin:
                         if (curr - f_inicio).days > 120: break 
                         eco_data_bpi[curr] = val_bpi
                         curr += timedelta(days=1)
            
            if not eco_data_bpi:
                 print("DEBUG: Hoja BPI leida pero vacia tras heurística.")

        else:
            print("DEBUG: No se encontró hoja Base Pesada IFOS")

    except Exception as e:
        print(f"Error procesando Base Pesada IFOS: {e}")


    # 5. Consolidar Datos
    processed = 0
    
    # Determinar fecha límite
    dates_f04 = list(eco_data_f04.keys())
    dates_fo = list(eco_data_fo.keys())
    dates_bpi = list(eco_data_bpi.keys())
    
    all_dates = dates_f04 + dates_fo + dates_bpi
    
    last_eco_date = max(all_dates) if all_dates else today
    final_end_date = min(today, last_eco_date)
    
    delta = (final_end_date - start_date).days
    
    # Iteramos solo hasta donde tenemos datos reales o hasta hoy
    for i in range(delta + 1):
        current_date = start_date + timedelta(days=i)
        date_ts = pd.Timestamp(current_date)
        
        # Valores por defecto para prevenir saltos
        brent_val = 0.0
        trm_val = 0.0
        
        # Yahoo Finance (Brent) y TRM (Map)
        try:
            # Brent: Estrategia Carry-Forward
            found_brent_today = None
            if not brent_df.empty:
                try:
                    if date_ts in brent_df.index:
                        val = brent_df.loc[date_ts]
                    else:
                        subset = brent_df.loc[brent_df.index.normalize() == date_ts]
                        if not subset.empty:
                            val = subset.iloc[0]
                        else:
                            val = None
                            
                    if val is not None:
                        if isinstance(val, (pd.Series, pd.DataFrame)):
                             found_brent_today = float(val.iloc[0]) if hasattr(val, 'iloc') else float(val)
                        else:
                             found_brent_today = float(val)
                except: pass

            if found_brent_today is not None and found_brent_today > 0:
                latest_brent = found_brent_today
                brent_val = found_brent_today
            else:
                # Si no hay dato exacto (ej. fin de semana), mantener el ultimo conocido
                # PERO validar si el gap es muy grande
                brent_val = latest_brent
                print(f"DEBUG: Brent {current_date} -> {brent_val} (Carry-Forward)")
            
            # TRM: Estrategia Carry-Forward
            found_trm_today = trm_map.get(current_date, 0.0)
            if found_trm_today > 0:
                latest_trm = found_trm_today
            
            trm_val = latest_trm
            if trm_val == 0.0: trm_val = 4000.0
            
        except Exception as e:
            print(f"Error asignando valores mercado: {e}")
            trm_val = 4000.0

        # Datos Ecopetrol (F04)
        f04_data = eco_data_f04.get(current_date)
        
        # Variables persistentes para el bucle (inicializar fuera del loop si se quisiera estricto)
        # Pero aqui usamos last_known si falla
        
        if f04_data:
            f04_base_cop = f04_data['base']       
            f04_imp_cop = f04_data['impuestos']
            
            # Actualizar ultimos conocidos
            last_known_f04_base = f04_base_cop
            last_known_f04_imp = f04_imp_cop
        else:
            # Carry-Forward: Usar ultimo conocido si existe (llenar huecos 14-19 Ene)
            if 'last_known_f04_base' in locals() and last_known_f04_base > 0:
                 f04_base_cop = last_known_f04_base
                 f04_imp_cop = last_known_f04_imp
            else:
                 f04_base_cop = 0.0
                 f04_imp_cop = 0.0

        # Cálculos F04
        f04_total_cop = f04_base_cop + f04_imp_cop
        
        conversion_rate = trm_val if trm_val > 0 else 4000.0
        f04_base_usd = f04_base_cop / conversion_rate
        f04_total_usd = f04_total_cop / conversion_rate
        
        # FUEL OIL
        fo_val = eco_data_fo.get(current_date, 0.0)
        
        # BPI (Base Pesada IFOS)
        bpi_cop_kg = eco_data_bpi.get(current_date, 0.0)
        
        # Calculos Derivados BPI
        bpi_usd_kg = bpi_cop_kg / conversion_rate
        bpi_usd_mt = bpi_usd_kg * 1000.0
        bpi_usd_bll = bpi_usd_mt / 6.3 # Factor aproximado estándar

        # CALCULOS DE DIFERENCIAL (PREMIUM)
        # Segun instruccion FINAL: Producto - Brent 
        
        diff_f04_base = (f04_base_usd - brent_val) if brent_val > 0 else 0.0
        diff_f04_total = (f04_total_usd - brent_val) if brent_val > 0 else 0.0
        diff_fo = (fo_val - brent_val) if (brent_val > 0 and fo_val > 0) else 0.0 
        diff_bpi = (bpi_usd_bll - brent_val) if (brent_val > 0 and bpi_usd_bll > 0) else 0.0

        # Guardar en BD
        record = HistorialCombustibles.query.get(current_date)
        if not record:
            record = HistorialCombustibles(fecha=current_date)
            db.session.add(record)
        
        record.trm = trm_val
        record.brent = brent_val
        
        record.f04_base_cop = f04_base_cop 
        record.f04_impuesto_cop = f04_imp_cop
        record.f04_total_cop = f04_total_cop
        record.f04_base_usd = f04_base_usd
        record.f04_total_usd = f04_total_usd
        
        record.fuel_oil_usd = fo_val
        
        record.bpi_cop_kg = bpi_cop_kg
        record.bpi_usd_kg = bpi_usd_kg
        record.bpi_usd_mt = bpi_usd_mt
        record.bpi_usd_bll = bpi_usd_bll
        
        # Guardar Diferenciales
        record.diff_f04_base = diff_f04_base
        record.diff_f04_total = diff_f04_total
        record.diff_fuel_oil = diff_fo
        record.diff_bpi = diff_bpi
        
        processed += 1

    db.session.commit()
    flash(f"Actualización completada. {processed} registros procesados.", "success")
    return redirect(url_for('pricing_bp.index'))

# --- GASOIL PREMIUM ROUTES ---

@pricing_bp.route('/gasoil-premium', methods=['GET'])
def gasoil_index():
    from pricing.models import HistorialGasoil
    records = HistorialGasoil.query.order_by(HistorialGasoil.fecha.desc()).all()
    
    # 1. Calcular TRM Promedio Mensual (basado en registros)
    trm_sums = {}
    trm_counts = {}
    
    for r in records:
        if r.trm and r.trm > 0:
            key = (r.fecha.year, r.fecha.month)
            trm_sums[key] = trm_sums.get(key, 0) + r.trm
            trm_counts[key] = trm_counts.get(key, 0) + 1
            
    trm_avgs = {k: trm_sums[k]/trm_counts[k] for k in trm_sums}
    
    # 2. Enriquecer registros con "Premium COP" (Que en F04 son Precios Base convertidos)
    # Formula: (Precio USD/Bbl / 42.0) * TRM_Mensual
    for r in records:
        trm_mes = trm_avgs.get((r.fecha.year, r.fecha.month), r.trm or 0)
        r.trm_mensual_used = trm_mes
        
        # Helper interno
        def to_cop_gal_monthly(usd_bbl_val):
            if not usd_bbl_val: return 0.0
            # USD/Bbl -> USD/Gal -> COP/Gal
            # (Val / 42) * TRM Promedio Mensual
            return (usd_bbl_val / 42.0) * trm_mes
            
        # Usamos los PRECIOS ABSOLUTOS (NO los diferenciales/spreads) para coincidir con F04
        r.premium_cop_eco = to_cop_gal_monthly(r.diesel_eco_usd_bll)
        r.premium_cop_gasoil = to_cop_gal_monthly(r.gasoil_usd_bll)
        r.premium_cop_gran_cons_sin_iva = to_cop_gal_monthly(r.gran_cons_usd_bll)
        r.premium_cop_gran_cons_con_iva = to_cop_gal_monthly(r.gran_cons_total_usd)

    return render_template('pricing/gasoil_premium.html', records=records)

    


@pricing_bp.route('/gasoil-premium/reset', methods=['POST'])
def reset_gasoil():
    from extensions import db
    from pricing.models import HistorialGasoil
    try:
        num_deleted = db.session.query(HistorialGasoil).delete()
        db.session.commit()
        flash(f"Historial Gasoil eliminado correctamente ({num_deleted} registros).", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error eliminando historial Gasoil: {e}", "danger")
    return redirect(url_for('pricing_bp.gasoil_index'))

@pricing_bp.route('/gasoil-premium/update', methods=['POST'])
def update_gasoil():
    from extensions import db
    from pricing.models import HistorialGasoil
    from sqlalchemy import or_

    # Optimización: Buscar última fecha registrada
    try:
        latest_record = HistorialGasoil.query.order_by(HistorialGasoil.fecha.desc()).first()
    except:
        latest_record = None # Tabla podria no existir aun si no se corrio migracion

    start_date = date(2025, 1, 1)
    if latest_record:
        start_date = latest_record.fecha + timedelta(days=1)
    
    today = date.today()
    
    # Verificar si ya está actualizado
    if start_date > today:
        flash("La base de datos Gasoil ya está actualizada hasta hoy.", "info")
        return redirect(url_for('pricing_bp.gasoil_index'))

    # 1. BRENT (Reutilizamos lógica de F04, simplificada aquí)
    brent_df = pd.DataFrame()
    latest_brent = latest_record.brent if (latest_record and latest_record.brent) else 75.0
    
    # Intentar Yahoo Finance para Brent (BZ=F)
    try:
        print(f"Intentando Yahoo Finance para Brent desde {start_date}...")
        # Descargar solo desde la última fecha registrada
        brent_df_yf = yf.download("BZ=F", start=start_date.strftime('%Y-%m-%d'), progress=False)
        if not brent_df_yf.empty:
            # Limpieza MultiIndex
            if isinstance(brent_df_yf.columns, pd.MultiIndex):
                try:
                    if 'Close' in brent_df_yf.columns.get_level_values(0):
                         brent_df_yf = brent_df_yf.xs('Close', level=0, axis=1)
                    elif 'Adj Close' in brent_df_yf.columns.get_level_values(0):
                         brent_df_yf = brent_df_yf.xs('Adj Close', level=0, axis=1)
                    else:
                         brent_df_yf.columns = [c[0] for c in brent_df_yf.columns]
                except: pass
            
            # Asegurar serie
            if isinstance(brent_df_yf, pd.DataFrame):
                 val_series = brent_df_yf.iloc[:, 0]
            else:
                 val_series = brent_df_yf
            
            brent_df = pd.DataFrame({'brent': val_series})
            if brent_df.index.tz is not None:
                 brent_df.index = brent_df.index.tz_localize(None)
            
            latest_valid = brent_df['brent'].last_valid_index()
            if latest_valid:
                 latest_brent = float(brent_df.loc[latest_valid, 'brent'])
        else:
            print("⚠ Yahoo Brent vacío")
    except Exception as e:
        print(f"Error Yahoo Brent: {e}")

    # 2. TRM (Datos.gov.co)
    trm_map = {}
    latest_trm = 4000.0
    try:
        # Buscar desde un poco antes por si hay gaps
        fetch_start = start_date - timedelta(days=3)
        f_str = fetch_start.strftime('%Y-%m-%d')
        print(f"Descargando TRM desde {fetch_start}...")
        url_trm = f"https://www.datos.gov.co/resource/32sa-8pi3.json?$where=vigenciadesde >= '{f_str}T00:00:00.000'"
        resp_trm = requests.get(url_trm, timeout=30)
        if resp_trm.status_code == 200:
            data_trm = resp_trm.json()
            for item in data_trm:
                f_desde_str = item.get('vigenciadesde')
                f_hasta_str = item.get('vigenciahasta')
                val = float(item.get('valor', 0))
                if f_desde_str and f_hasta_str:
                    d_desde = datetime.strptime(f_desde_str[:10], '%Y-%m-%d').date()
                    d_hasta = datetime.strptime(f_hasta_str[:10], '%Y-%m-%d').date()
                    curr_trm = d_desde
                    while curr_trm <= d_hasta:
                        trm_map[curr_trm] = val
                        curr_trm += timedelta(days=1)
                    if d_hasta >= fetch_start: latest_trm = val
    except Exception as e:
        print(f"Error TRM: {e}")

    # 3. GASOIL (Yahoo Finance: LGO=F - ICE Gasoil Futures)
    gasoil_df = pd.DataFrame()
    # Default Gasoil Price ~700 USD/MT
    latest_gasoil = latest_record.gasoil_price if (latest_record and latest_record.gasoil_price) else 700.0
    
    try:
        print(f"Intentando Yahoo Finance para Gasoil desde {start_date}...")
        # Primero intentamos LGO=F (ICE Gasoil)
        gasoil_df_yf = yf.download("LGO=F", start=start_date.strftime('%Y-%m-%d'), progress=False)
        
        # Si LGO=F falla o está vacío, intentamos HO=F (Heating Oil) como proxy
        source_used = "LGO"
        if gasoil_df_yf.empty:
            print("⚠ Yahoo LGO=F vacío/falló. Intentando HO=F (Heating Oil) como proxy...")
            gasoil_df_yf = yf.download("HO=F", start=start_date.strftime('%Y-%m-%d'), progress=False)
            source_used = "HO"

        if not gasoil_df_yf.empty:
            if isinstance(gasoil_df_yf.columns, pd.MultiIndex):
                try:
                    if 'Close' in gasoil_df_yf.columns.get_level_values(0):
                         gasoil_df_yf = gasoil_df_yf.xs('Close', level=0, axis=1)
                    elif 'Adj Close' in gasoil_df_yf.columns.get_level_values(0):
                         gasoil_df_yf = gasoil_df_yf.xs('Adj Close', level=0, axis=1)
                    else:
                         gasoil_df_yf.columns = [c[0] for c in gasoil_df_yf.columns]
                except: pass
            
            if isinstance(gasoil_df_yf, pd.DataFrame):
                val_series = gasoil_df_yf.iloc[:, 0]
            else:
                val_series = gasoil_df_yf
            
            # Si usamos Heating Oil (USD/Gal), convertir a USD/MT aproximado para mantener consistencia
            # 1 Bbl = 42 Gal
            # 1 MT Gasoil ~ 7.4 Bbl
            # => USD/MT = (USD/Gal * 42) * 7.4
            if source_used == "HO":
                 val_series = val_series * 42 * 7.4
            
            gasoil_df = pd.DataFrame({'gasoil': val_series})
            if gasoil_df.index.tz is not None:
                 gasoil_df.index = gasoil_df.index.tz_localize(None)

            latest_valid_g = gasoil_df['gasoil'].last_valid_index()
            if latest_valid_g:
                 latest_gasoil = float(gasoil_df.loc[latest_valid_g, 'gasoil'])
        else:
            print("⚠ Yahoo Gasoil (LGO y HO) vacíos")
    except Exception as e:
        print(f"Error Yahoo Gasoil: {e}")


    # 3. GASOIL (Yahoo Finance)
    # ... (Existing Gasoil logic remains above) ...

    # 4. DIESEL ECOPETROL (Diesel Marino - Nueva URL)
    # URL provided by user: PME-V-DIESELMARINO_15.xls
    ECOPETROL_URL = "https://www.ecopetrol.com.co/wps/wcm/connect/07bb0dc0-7c62-4ef2-88d1-5e0379530ce8/PME-V-DIESELMARINO_15.xls?MOD=AJPERES&attachment=true&id=1588803550108"
    
    eco_map = {} # date -> price_cop_gl
    
    try:
        print("Descargando archivo Ecopetrol Diesel Marino...")
        resp_eco = requests.get(ECOPETROL_URL, verify=False, timeout=60)
        if resp_eco.status_code == 200:
            try:
                xl = pd.ExcelFile(io.BytesIO(resp_eco.content))
                target_sheet = None
                for s in xl.sheet_names:
                    if "cartagena" in s.lower(): # Match Cartagena (with or without 'a')
                        target_sheet = s
                        break
                
                if target_sheet:
                    print(f"Hoja encontrada: {target_sheet}")
                    # Parsear hoja
                    df_eco = xl.parse(target_sheet, header=None)
                    
                    for index, row in df_eco.iterrows():
                        try:
                            # Intento 1: Bloque Izquierdo (Cols 0, 1, 6)
                            date_found = False
                            price_found = 0.0
                            
                            s_d = row[0]
                            e_d = row[1]
                            p_val = row[6]
                            
                            if isinstance(s_d, (datetime, pd.Timestamp)) and isinstance(e_d, (datetime, pd.Timestamp)):
                                if isinstance(p_val, (int, float)) and not pd.isna(p_val):
                                    date_found = True
                                    price_found = float(p_val)
                                    start_final = s_d
                                    end_final = e_d

                            # Intento 2: Bloque Derecho (Cols 8, 9, 15) - Si Bloque Izq falló o está vacío
                            if not date_found:
                                try:
                                    s_d2 = row[8]
                                    e_d2 = row[9]
                                    # Probar col 15 (o 14 si 15 falla)
                                    p_val2 = row[15] if (len(row) > 15 and not pd.isna(row[15])) else row[14]
                                    
                                    if isinstance(s_d2, (datetime, pd.Timestamp)) and isinstance(e_d2, (datetime, pd.Timestamp)):
                                        if isinstance(p_val2, (int, float)) and not pd.isna(p_val2):
                                            date_found = True
                                            price_found = float(p_val2)
                                            start_final = s_d2
                                            end_final = e_d2
                                            # Debug print only occasionally or for first find
                                            # print(f"DEBUG: Found Right Block Data: {s_d2} | {price_found}")
                                except: pass
                            
                            if date_found:
                                # Deteccion de Unidad y Conversion
                                # Si precio > 1000 => Probablemente COP/Gal (Historico)
                                # Si precio < 500 => Probablemente USD/Bbl (Internacional)
                                
                                final_cop_gl = 0.0
                                
                                if price_found > 1000:
                                    final_cop_gl = price_found
                                else:
                                    # Asumimos USD/Bbl. Convertir a COP/Gal
                                    # Necesitamos TRM del dia. Usamos trm_map o latest
                                    
                                    curr_date = start_final.date() if isinstance(start_final, datetime) else start_final
                                    trm_for_conv = trm_map.get(curr_date, latest_trm)
                                    
                                    if trm_for_conv is None or trm_for_conv == 0:
                                        trm_for_conv = 3800.0 # Fallback safety
                                    
                                    # USD/Bbl -> USD/Gal = USD/Bbl / 42
                                    # USD/Gal -> COP/Gal = USD/Gal * TRM
                                    final_cop_gl = (price_found / 42.0) * trm_for_conv
                                    # print(f"DEBUG: Converted {price_found} USD/Bbl to {final_cop_gl} COP/GL (TRM: {trm_for_conv})")

                                # Llenar rango
                                curr = start_final.date() if isinstance(start_final, datetime) else start_final
                                fin = end_final.date() if isinstance(end_final, datetime) else end_final
                                
                                if fin >= date(2024, 1, 1):
                                    while curr <= fin:
                                        eco_map[curr] = final_cop_gl
                                        curr += timedelta(days=1)


                        except:
                            continue
                else:
                    print("No se encontró hoja Cartagena")
            except Exception as e_parse:
               print(f"Error parseando Excel Eco: {e_parse}")
        else:
            print(f"Error descarga Ecopetrol: {resp_eco.status_code}")
    except Exception as e:
        print(f"Error request Ecopetrol: {e}") 

    # 5. Consolidar y Guardar
    # ... (rest of logic) ...


    # 5. Consolidar y Guardar
    # (Existing consolidation loop needs to be updated to include eco_map) ...
    
    delta = (today - start_date).days
    count_new = 0
    
    for i in range(delta + 1):
        current_date = start_date + timedelta(days=i)
        date_ts = pd.Timestamp(current_date)
        
        # --- Fetch Values ---
        # Brent, TRM, Gasoil (Existing logic)
        
        # Brent
        brent_val = latest_brent
        try:
            if not brent_df.empty:
                if date_ts in brent_df.index:
                    val = brent_df.loc[date_ts]
                    brent_val = float(val.iloc[0] if isinstance(val, (pd.Series, pd.DataFrame)) else val)
                else:
                    # ffill
                    idx_loc = brent_df.index.searchsorted(date_ts, side='right') - 1
                    if idx_loc >= 0:
                        val = brent_df.iloc[idx_loc]
                        brent_val = float(val.iloc[0] if isinstance(val, (pd.Series, pd.DataFrame)) else val)
            if brent_val > 0: latest_brent = brent_val
        except: pass

        # TRM
        trm_val = trm_map.get(current_date, latest_trm)
        if trm_val > 0: latest_trm = trm_val
        
        # Gasoil
        gasoil_val_mt = latest_gasoil
        try:
            if not gasoil_df.empty:
                if date_ts in gasoil_df.index:
                    val = gasoil_df.loc[date_ts]
                    gasoil_val_mt = float(val.iloc[0] if isinstance(val, (pd.Series, pd.DataFrame)) else val)
                else:
                    idx_loc = gasoil_df.index.searchsorted(date_ts, side='right') - 1
                    if idx_loc >= 0:
                        val = gasoil_df.iloc[idx_loc]
                        gasoil_val_mt = float(val.iloc[0] if isinstance(val, (pd.Series, pd.DataFrame)) else val)
            if gasoil_val_mt > 0: latest_gasoil = gasoil_val_mt
        except: pass
        
        # Diesel Ecopetrol (ALC)
        eco_cop_gl = eco_map.get(current_date, 0.0)
        # Si falta dato hoy, usar ultimo conocido?
        if eco_cop_gl == 0 and i > 0:
             # Look back logic or just keep 0 if unknown
             pass

        # Calculos
        gasoil_bll = gasoil_val_mt / 7.4 if gasoil_val_mt > 0 else 0.0 # From MT to BLL
        premium = (gasoil_bll - brent_val) if (brent_val > 0 and gasoil_bll > 0) else 0.0
        
        # Diesel Eco Conversions
        eco_usd_gl = eco_cop_gl / trm_val if (trm_val and trm_val > 0) else 0.0
        eco_usd_bll = eco_usd_gl * 42.0

        # Guardar
        try:
            record = HistorialGasoil.query.get(current_date)
            if not record:
                record = HistorialGasoil(fecha=current_date)
                db.session.add(record)
            
            record.trm = trm_val
            record.brent = brent_val
            record.gasoil_price = gasoil_val_mt
            record.gasoil_usd_bll = gasoil_bll
            record.gasoil_premium = premium  # This is Gasoil - Brent
            record.premium_gasoil = premium  # Explicit alias for consistency
            
            # Ecopetrol Data
            record.diesel_eco_cop_gl = eco_cop_gl
            record.diesel_eco_usd_gl = eco_usd_gl
            record.diesel_eco_usd_bll = eco_usd_bll
            record.premium_eco = (eco_usd_bll - brent_val) if (brent_val > 0 and eco_usd_bll > 0) else 0.0

            # Gran Consumidor Premiums (Recalculate if GC data exists)
            # Gran Cons data might have been loaded manually, so we check if it exists
            if record.gran_cons_usd_bll and record.gran_cons_usd_bll > 0 and brent_val > 0:
                record.premium_gran_cons_sin_iva = record.gran_cons_usd_bll - brent_val
            
            if record.gran_cons_total_usd and record.gran_cons_total_usd > 0 and brent_val > 0:
                record.premium_gran_cons_con_iva = record.gran_cons_total_usd - brent_val
            record.diesel_eco_cop_gl = eco_cop_gl
            record.diesel_eco_usd_gl = eco_usd_gl
            record.diesel_eco_usd_bll = eco_usd_bll
            
            count_new += 1
        except Exception as e:
            print(f"Error guardando {current_date}: {e}")

    try:
        db.session.commit()
        if count_new > 0:
            flash(f"✅ Se actualizaron {count_new} registros de Gasoil (desde {start_date.strftime('%d/%m/%Y')} hasta {today.strftime('%d/%m/%Y')}).", "success")
        else:
            flash("✅ La base de datos ya está actualizada. No hay nuevos registros.", "info")
    except Exception as e:
        db.session.rollback()
        flash(f"Error guardando en BD: {e}", "danger")

    return redirect(url_for('pricing_bp.gasoil_index'))


@pricing_bp.route('/gasoil-premium/upload-gran-consumidor', methods=['POST'])
def upload_gran_consumidor():
    from pricing.models import HistorialGasoil
    from extensions import db
    
    try:
        # Check if File or Manual
        if 'file' in request.files and request.files['file'].filename != '':
            # --- FILE UPLOAD LOGIC ---
            file = request.files['file']
            filename = file.filename
            
            if filename.endswith('.csv'):
                df = pd.read_csv(file)
            elif filename.endswith(('.xls', '.xlsx')):
                df = pd.read_excel(file)
            else:
                flash("Formato de archivo no soportado. Use CSV o Excel.", "danger")
                return redirect(url_for('pricing_bp.gasoil_index'))
            
            # Expected columns: 'Fecha', 'Precio', 'IVA' (Optional)
            # Map common names
            df.columns = df.columns.str.lower()
            
            # Find date column
            date_col = next((c for c in df.columns if 'fecha' in c or 'date' in c), None)
            price_col = next((c for c in df.columns if 'precio' in c or 'cop/gl' in c or 'valor' in c), None)
            iva_col = next((c for c in df.columns if 'iva' in c or 'impuesto' in c), None)
            
            if not date_col or not price_col:
                flash("El archivo debe tener al menos columnas 'Fecha' y 'Precio' (o COP/GL).", "danger")
                return redirect(url_for('pricing_bp.gasoil_index'))

            count = 0
            for _, row in df.iterrows():
                try:
                    fecha_val = row[date_col]
                    if pd.isna(fecha_val): continue
                    
                    if isinstance(fecha_val, (pd.Timestamp, datetime)):
                        fecha_row = fecha_val.date()
                    else:
                        fecha_row = pd.to_datetime(fecha_val).date()

                    price_cop = float(row[price_col]) if pd.notnull(row[price_col]) else 0.0
                    iva_cop = float(row[iva_col]) if (iva_col and pd.notnull(row[iva_col])) else 0.0
                    
                    if price_cop > 0:
                        process_gran_consumidor_update(fecha_row, price_cop, iva_cop)
                        count += 1
                except Exception as e:
                    print(f"Error processing row: {e}")
                    continue
            
            flash(f"Carga Masiva Exitosa: {count} registros actualizados.", "success")

        else:
            # --- MANUAL RANGE LOGIC (supports multiple weeks) ---
            start_dates = request.form.getlist('start_date[]')
            end_dates = request.form.getlist('end_date[]')
            val_prods = request.form.getlist('val_prod[]')
            sobretasas = request.form.getlist('sobretasa[]')
            iva_prods = request.form.getlist('iva_prod[]')
            iva_mayors = request.form.getlist('iva_mayor[]')
            
            # Check if we got arrays (new multi-week form) or single values (fallback)
            if not start_dates:
                # Fallback to single value mode
                start_dates = [request.form.get('start_date')]
                end_dates = [request.form.get('end_date')]
                val_prods = [request.form.get('val_prod', 0)]
                sobretasas = [request.form.get('sobretasa', 0)]
                iva_prods = [request.form.get('iva_prod', 0)]
                iva_mayors = [request.form.get('iva_mayor', 0)]
            
            total_count = 0
            
            # Process each week entry
            for i in range(len(start_dates)):
                try:
                    start_date_str = start_dates[i]
                    end_date_str = end_dates[i]
                    
                    # Get values for this week
                    val_prod = float(val_prods[i]) if i < len(val_prods) and val_prods[i] else 0
                    sobretasa = float(sobretasas[i]) if i < len(sobretasas) and sobretasas[i] else 0
                    iva_prod = float(iva_prods[i]) if i < len(iva_prods) and iva_prods[i] else 0
                    iva_mayor = float(iva_mayors[i]) if i < len(iva_mayors) and iva_mayors[i] else 0
                    
                    # Calculate totals
                    price_cop = val_prod + sobretasa
                    iva_cop = iva_prod + iva_mayor
                    
                    if start_date_str and end_date_str and price_cop > 0:
                        s_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                        e_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                        
                        curr = s_date
                        while curr <= e_date:
                            process_gran_consumidor_update(curr, price_cop, iva_cop)
                            curr += timedelta(days=1)
                            total_count += 1
                except Exception as e:
                    print(f"Error processing week {i+1}: {e}")
                    continue
            
            if total_count > 0:
                flash(f"Actualización Manual Exitosa: {total_count} registros actualizados.", "success")
            else:
                flash("Datos inválidos. Verifique fechas y precios.", "warning")

    except Exception as e:
        flash(f"Error actualizando Gran Consumidor: {e}", "danger")
        print(f"Error GC Update: {e}")

    return redirect(url_for('pricing_bp.gasoil_index'))


def process_gran_consumidor_update(fecha_gl, price_cop, iva_cop):
    from pricing.models import HistorialGasoil
    from extensions import db
    
    record = HistorialGasoil.query.get(fecha_gl)
    if not record:
        record = HistorialGasoil(fecha=fecha_gl)
        db.session.add(record)
    
    total_cop = price_cop + iva_cop
    
    record.gran_cons_cop_gl = price_cop
    record.gran_cons_iva_cop = iva_cop
    record.gran_cons_total_cop = total_cop
    
    # Calculate USD if TRM exists
    trm_val = record.trm
    
    # TRM Safety Check
    if not trm_val or trm_val == 0:
        # Fallback or leave as 0? 
        # Ideally we should fetch TRM if missing, but for now we proceed.
        pass

    if trm_val and trm_val > 0:
        # USD/Gal = COP/Gal / TRM
        usd_gl = price_cop / trm_val
        usd_iva_gl = iva_cop / trm_val
        usd_total_gl = total_cop / trm_val
        
        # USD/Bbl = USD/Gal * 42
        record.gran_cons_usd_bll = usd_gl * 42.0
        record.gran_cons_iva_usd = usd_iva_gl * 42.0
        record.gran_cons_total_usd = usd_total_gl * 42.0
        
        # Calculate Premiums if Brent is available
        if record.brent and record.brent > 0:
            record.premium_gran_cons_sin_iva = record.gran_cons_usd_bll - record.brent
            record.premium_gran_cons_con_iva = record.gran_cons_total_usd - record.brent
    
    db.session.commit()

