from flask import Blueprint, render_template, request, flash, redirect, url_for
from datetime import date, datetime, timedelta
import pandas as pd
import yfinance as yf
import requests
from io import BytesIO

# Definicion del Blueprint
pricing_bp = Blueprint('pricing_bp', __name__, template_folder='templates')

@pricing_bp.route('/pricing', methods=['GET'])
def index():
    from pricing.models import HistorialCombustibles
    records = HistorialCombustibles.query.order_by(HistorialCombustibles.fecha.desc()).all()
    return render_template('pricing/f04_premium.html', records=records)

@pricing_bp.route('/pricing/update', methods=['POST'])
def update_prices():
    from extensions import db
    from pricing.models import HistorialCombustibles
    
    # Optimización: Buscar última fecha registrada
    latest_record = HistorialCombustibles.query.order_by(HistorialCombustibles.fecha.desc()).first()
    
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
            
            max_retries = 3
            attempts = 0
            success = False
            fetch_start = start_date - timedelta(days=7)
            
            while attempts < max_retries and not success:
                attempts += 1
                try:
                    ticker = yf.Ticker("BZ=F")
                    brent_df_yf = ticker.history(start=fetch_start, interval="1d")
                    
                    if brent_df_yf.empty:
                        brent_df_yf = yf.download("BZ=F", start=fetch_start, progress=False, timeout=10)
                    
                    if not brent_df_yf.empty:
                        success = True
                        
                        # Fix MultiIndex
                        if isinstance(brent_df_yf.columns, pd.MultiIndex):
                            try:
                                brent_df_yf = brent_df_yf.xs('Close', level=0, axis=1)
                            except:
                                brent_df_yf.columns = [c[0] for c in brent_df_yf.columns]
                        
                        last_valid_idx = brent_df_yf.last_valid_index()
                        if last_valid_idx:
                            val = brent_df_yf.loc[last_valid_idx]
                            if isinstance(val, pd.Series): val = val.iloc[0]
                            latest_brent = float(val)
                            
                            # Convertir a formato estándar
                            brent_df = pd.DataFrame({'brent': brent_df_yf.iloc[:, 0]})
                            print(f"✓ Yahoo: Último Brent = {latest_brent} ({last_valid_idx.date()})")
                    else:
                        raise ValueError("Yahoo data empty")
                        
                except Exception as e_retry:
                    print(f"✗ Yahoo intento {attempts}/{max_retries}: {e_retry}")
                    if attempts < max_retries:
                        time.sleep(random.uniform(1.0, 3.0))
            
            if not success:
                raise ValueError("Yahoo failed all retries")
                
        except Exception as e_yahoo:
            print(f"✗ Yahoo Finance falló: {e_yahoo}")
            print(f"⚠ Usando último valor conocido de BD: {latest_brent}")
    
    # FUENTE 3: Si todo falla, brent_df queda vacío y se usa latest_brent de BD


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
                 
                 # CRITERIO DE ACEPTACIÓN: Ambas deben ser fechas válidas
                 # MEJORA: Validar Año Incorrecto (Ecopetrol a veces deja 2025 en 2026)
                 
                 # Si la fecha parseada es 2025 pero estamos en 2026, y es Enero/Febrero, asumir error de año en Excel
                 current_real_year = datetime.now().year
                 if d_inicio and d_inicio.year == (current_real_year - 1):
                      # Heurística: Si la fecha es de este año o el anterior, corregir al actual
                      # Solo corregir si el mes coincide con la ventana actual de actualización (Enero)
                      if d_inicio.month == datetime.now().month or d_inicio.month == (datetime.now().month - 1):
                           d_inicio = d_inicio.replace(year=current_real_year)
                           print(f"DEBUG: Corrigiendo año {current_real_year-1} -> {current_real_year} para {d_inicio}")
                           
                           # CRÍTICO: Si corregimos d_inicio, también debemos corregir d_fin si tiene el año viejo
                           # o si por consecuencia d_fin quedó menor que d_inicio.
                           if d_fin:
                               # Si d_fin tiene el mismo año viejo, actualizarlo
                               if d_fin.year == (current_real_year - 1):
                                   d_fin = d_fin.replace(year=current_real_year)
                                   print(f"DEBUG: Corrigiendo año fin -> {d_fin}")
                               
                               # Si aun así d_fin es menor (ej. cambio de año en rango), forzar consistencia
                               if d_fin < d_inicio:
                                   # Intentar mover d_fin al año siguiente si parece ser un rango que cruza año (Dic->Ene)
                                   # pero como estamos corrigiendo "2025" a "2026", es probable que simplemente necesite ser >=
                                   if d_fin.year < d_inicio.year:
                                        d_fin = d_fin.replace(year=d_inicio.year)                 
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
            
            brent_val = latest_brent
            
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
        
        if not f04_data:
            f04_base_cop = 0.0
            f04_imp_cop = 0.0
        else:
            f04_base_cop = f04_data['base']       
            f04_imp_cop = f04_data['impuestos']   

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
