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
    
    # Si ya estamos al día, validamos y salimos para no procesar nada
    if start_date > today:
       flash("La base de datos ya está actualizada hasta hoy. No se encontraron días nuevos.", "info")
       return redirect(url_for('pricing_bp.index'))

    ECOPETROL_URL = "https://www.ecopetrol.com.co/wps/wcm/connect/94bf0826-889a-4937-a6c0-668e35b1ea55/PME-VPRECIOSCRUDOSYFUELOILPARAIFOS-15.xls?MOD=AJPERES&attachment=true&id=1589474858686"
    
    # 1. BRENT (Yahoo Finance)
    brent_df = pd.DataFrame()
    latest_brent = 0.0
    try:
        # Descargar historial reciente (Desde un poco antes para coger ultimo val si hoy es nulo)
        fetch_start = start_date - timedelta(days=7)
        brent_df = yf.download("BZ=F", start=fetch_start, progress=False)
        # Fix MultiIndex de Yahoo (Price, Ticker) -> 'Close'
        if isinstance(brent_df.columns, pd.MultiIndex):
            try:
                brent_df = brent_df.xs('Close', level=0, axis=1) # O accede directo si es diferente
            except:
                # Si falla, intentar aplanar
                brent_df.columns = [c[0] for c in brent_df.columns]
        
        # Obtener ultimo valor conocido real
        if not brent_df.empty:
            # Asumiendo columna 'BZ=F' o similar si se aplanó
            # Busco la primera columna que tenga datos
            last_valid_idx = brent_df.last_valid_index()
            if last_valid_idx:
                 val = brent_df.loc[last_valid_idx]
                 # Si es serie (varias cols), tomar la primera
                 if isinstance(val, pd.Series): val = val.iloc[0]
                 latest_brent = float(val)
                 print(f"Ultimo Brent Real: {latest_brent} ({last_valid_idx})")

    except Exception as e:
        print(f"Error Yahoo Brent: {e}")

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
        
        # Mapa de meses español
        meses = {
            'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6,
            'julio': 7, 'agosto': 8, 'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12
        }

        def parse_spanish_date(date_val, year_hint=None):
            # Si ya es un objeto fecha, devolverlo
            if isinstance(date_val, (pd.Timestamp, datetime, date)):
                return date_val.date() if hasattr(date_val, 'date') else date_val
            
            # Si es string
            date_str = str(date_val).strip()
            
            # Intento 1: Formato pandas default (YYYY-MM-DD...)
            try:
                ts = pd.to_datetime(date_str, errors='raise')
                return ts.date()
            except:
                pass

            # Intento 2: Parseo manual Español "martes, 6 de enero..." (y casos sucios "2025sujeto")
            try:
                # Pre-limpieza de basura específica observada
                s_clean = date_str.lower()
                s_clean = s_clean.replace('sujeto', ' sujeto ') # Separa "2025sujeto"
                s_clean = s_clean.replace('hasta', ' ')
                
                parts = s_clean.replace(',', '').replace('.', '').replace('del', '').replace('de', '').split()
                day, month, year = None, None, None
                
                for part in parts:
                    if part.isdigit():
                        val = int(part)
                        if val > 31: year = val
                        else: 
                            if not day: day = val
                            else: year = val # Si aparece otro num puede ser año
                    elif part in meses:
                        month = meses[part]
                
                # Inferencia: Si tenemos día y mes pero falta año, usar hint
                if day and month and not year and year_hint:
                    year = int(year_hint)

                if day and month and year:
                    return date(year, month, day)
            except:
                pass
                
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
                 if not d_inicio: 
                     continue 
                 if not d_fin: d_fin = d_inicio 
                 
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
                 
                 val_ingreso = get_val(3)
                 val_iva = get_val(4)
                 val_carbono = get_val(5)
                 
                 # 4. Transformaciones (Expandir fechas)
                 val_carbono_bll = val_carbono * 42.0 # GLN a BLL
                 
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
            
            if start_row_fo is not None:
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
