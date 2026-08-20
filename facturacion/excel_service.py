"""
Servicio de procesamiento de Excel para el módulo de Facturación de Despachos.
Soporta hojas físicas/digitales (001.FT.OP.ZF), encabezados dinámicos,
cruce inteligente y tolerante por número de guía con dígito de verificación (DV),
limpieza de textos 'N/A', vacíos o códigos especiales, filtrado por tipo de guía
y exportación de guías faltantes / no encontradas.
"""
import io
import re
import uuid
from datetime import date, datetime
import openpyxl
import pandas as pd
from sqlalchemy import func, or_, and_
from extensions import db
from facturacion.models import FacturacionImportBatch, FacturacionImportItem


MESES_MAP = {
    'ENERO': '01', 'FEBRERO': '02', 'MARZO': '03', 'ABRIL': '04',
    'MAYO': '05', 'JUNIO': '06', 'JULIO': '07', 'AGOSTO': '08',
    'SEPTIEMBRE': '09', 'SETIEMBRE': '09', 'OCTUBRE': '10', 'NOVIEMBRE': '11', 'DICIEMBRE': '12',
    'ENE': '01', 'FEB': '02', 'MAR': '03', 'ABR': '04', 'MAY': '05', 'JUN': '06',
    'JUL': '07', 'AGO': '08', 'SEP': '09', 'SET': '09', 'OCT': '10', 'NOV': '11', 'DIC': '12'
}


def limpiar_texto_factura(valor):
    """Limpia el número/código de factura manejando 'N/A', vacías o códigos como 'ALMACENAMIENTO'."""
    if valor is None or pd.isna(valor):
        return None
    texto = str(valor).strip()
    if not texto or texto.lower() in ('nan', 'none', 'null', 'nat', 'n/a', 'na', 'n/d', '-', 'vacio', 'vacío', 's/n'):
        return None
    if texto.endswith('.0') and texto[:-2].isdigit():
        texto = texto[:-2]
    # Limpiar textos comunes tipo 'ALMACENAMIENTO N/A'
    if texto.upper() in ('ALMACENAMIENTO N/A', 'ALMACENAMIENTO - NA', 'ALMACENAMIENTO - N/A'):
        return 'ALMACENAMIENTO'
    return texto


def limpiar_codigo_transporte(valor):
    """Limpia el código de transporte manejando 'N/A', vacías o formatos float."""
    if valor is None or pd.isna(valor):
        return None
    texto = str(valor).strip()
    if not texto or texto.lower() in ('nan', 'none', 'null', 'nat', 'n/a', 'na', 'n/d', '-', 'vacio', 'vacío', 's/n'):
        return None
    if texto.endswith('.0') and texto[:-2].isdigit():
        texto = texto[:-2]
    return texto.upper()


def normalizar_guia(valor, dv=None):
    """
    Limpia y normaliza el número de guía para cruces confiables.
    Si se proporciona dígito de verificación (dv), lo combina coherentemente.
    """
    if valor is None or pd.isna(valor):
        return None
    texto = str(valor).strip()
    if not texto or texto.lower() in ('nan', 'none', 'null', 'nat', 's/n', '-', 'vacio', 'vacío'):
        return None

    # Manejar floats de Excel como 303400000310.0 -> 303400000310
    if texto.endswith('.0') and texto[:-2].isdigit():
        texto = texto[:-2]

    # Quitar comillas o caracteres extra de los bordes
    texto = re.sub(r"^['\"]|['\"]$", '', texto).strip()

    # Si viene un DV explícito en otra columna
    if dv is not None and pd.notna(dv):
        dv_str = str(dv).strip()
        if dv_str.endswith('.0') and dv_str[:-2].isdigit():
            dv_str = dv_str[:-2]
        if dv_str and dv_str.lower() not in ('nan', 'none', 'null', 'n/a', 'na', 'n/d', '-') and not (f"-{dv_str}" in texto or f" {dv_str}" in texto):
            return f"{texto}-{dv_str}".upper()

    return texto.upper() if texto else None


def extraer_claves_guia(valor, dv=None):
    """
    Genera un conjunto de variantes canónicas para matching tolerante de números de guía:
    - 1. Texto exacto en mayúsculas (ej: '303400000350-6')
    - 2. Con DV adjunto si viene en columna separada
    - 3. Solo alfanumérico (ej: '3034000003506')
    - 4. Base sin sufijo de dígito de verificación (ej: '303400000350-6' -> '303400000350', '303400000351 0' -> '303400000351')
    """
    if valor is None or pd.isna(valor):
        return []
    texto = str(valor).strip()
    if not texto or texto.lower() in ('nan', 'none', 'null', 'nat', 's/n', '-', 'vacio', 'vacío'):
        return []

    if texto.endswith('.0') and texto[:-2].isdigit():
        texto = texto[:-2]

    texto = re.sub(r"^['\"]|['\"]$", '', texto).strip().upper()
    claves = set()
    claves.add(texto)

    # Solo caracteres alfanuméricos
    solo_alfanum = re.sub(r'[^0-9A-Z]', '', texto)
    if solo_alfanum:
        claves.add(solo_alfanum)

    # Si tiene patrón BASE-DV o BASE DV (ej: 303400000350-6 o 303400000351 0)
    m_dv = re.match(r'^([0-9A-Z]+)[-/\s]+([0-9A-Z]{1,2})$', texto)
    if m_dv:
        base, dig_v = m_dv.group(1), m_dv.group(2)
        claves.add(base)
        claves.add(f"{base}-{dig_v}")
        claves.add(f"{base} {dig_v}")
        claves.add(f"{base}{dig_v}")

    # Si viene un DV explícito
    if dv is not None and pd.notna(dv):
        dv_str = str(dv).strip()
        if dv_str.endswith('.0') and dv_str[:-2].isdigit():
            dv_str = dv_str[:-2]
        if dv_str and dv_str.lower() not in ('nan', 'none', 'null', 'n/a', 'na', 'n/d', '-'):
            claves.add(f"{texto}-{dv_str}")
            claves.add(f"{texto} {dv_str}")
            claves.add(f"{texto}{dv_str}")
            if solo_alfanum:
                claves.add(f"{solo_alfanum}{dv_str}")

    return [c for c in claves if c]


def normalizar_fecha(valor):
    """Convierte diferentes formatos de fecha de Excel o strings a datetime.date."""
    if valor is None or pd.isna(valor):
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    if not texto or texto.lower() in ('nan', 'none', 'null', 'nat', 'n/a', 'na', 'n/d', '-', 's/n', 'vacio', 'vacío'):
        return None

    # Probar formatos comunes directamente
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%Y-%m-%d %H:%M:%S'):
        try:
            val_limpio = texto.split()[0] if (' ' in texto and fmt != '%Y-%m-%d %H:%M:%S') else texto
            return datetime.strptime(val_limpio, fmt).date()
        except ValueError:
            pass

    try:
        dayfirst = not bool(re.match(r'^\d{4}', texto))
        dt = pd.to_datetime(texto, errors='coerce', dayfirst=dayfirst)
        if pd.notna(dt):
            return dt.date()
    except Exception:
        pass
    return None


MESES_NUM_A_TEXTO = {
    1: 'ENERO', 2: 'FEBRERO', 3: 'MARZO', 4: 'ABRIL',
    5: 'MAYO', 6: 'JUNIO', 7: 'JULIO', 8: 'AGOSTO',
    9: 'SEPTIEMBRE', 10: 'OCTUBRE', 11: 'NOVIEMBRE', 12: 'DICIEMBRE'
}


def normalizar_mes_facturado(mes_raw, fecha_factura=None):
    """Devuelve el nombre textual del mes (ej: 'AGOSTO') a partir de texto, código YYYY-MM o fecha."""
    if mes_raw is not None and pd.notna(mes_raw):
        texto = str(mes_raw).strip().upper()
        if texto and texto.lower() not in ('nan', 'none', 'null', 'nat', 'n/a', 'na', 'n/d', '-', 's/n', 'vacio', 'vacío'):
            # Si contiene el nombre textual directo del mes
            for nombre_mes in ('SEPTIEMBRE', 'SETIEMBRE', 'NOVIEMBRE', 'DICIEMBRE', 'FEBRERO', 'OCTUBRE', 'AGOSTO', 'ENERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO', 'JULIO'):
                if nombre_mes in texto:
                    return 'SEPTIEMBRE' if nombre_mes == 'SETIEMBRE' else nombre_mes

            # Si es YYYY-MM o YYYY/MM
            m_iso = re.match(r'^\d{4}[-/](\d{1,2})$', texto)
            if m_iso:
                m_num = int(m_iso.group(1))
                if 1 <= m_num <= 12:
                    return MESES_NUM_A_TEXTO[m_num]

            # Si es MM-YYYY
            m_inv = re.match(r'^(\d{1,2})[-/]\d{4}$', texto)
            if m_inv:
                m_num = int(m_inv.group(1))
                if 1 <= m_num <= 12:
                    return MESES_NUM_A_TEXTO[m_num]

            # Si es abreviatura
            for abrev, cod in MESES_MAP.items():
                if abrev in texto:
                    m_num = int(cod)
                    return MESES_NUM_A_TEXTO[m_num]

            return texto

    if fecha_factura and isinstance(fecha_factura, (date, datetime)):
        return MESES_NUM_A_TEXTO.get(fecha_factura.month, 'AGOSTO')

    return None


def _buscar_columna(nombres_disponibles, candidatos):
    """Encuentra la columna en el DataFrame comparando de forma flexible."""
    cols_norm = {re.sub(r'[^A-Z0-9]', '', str(c).upper()): c for c in nombres_disponibles}
    for cand in candidatos:
        cand_norm = re.sub(r'[^A-Z0-9]', '', cand.upper())
        if cand_norm in cols_norm:
            return cols_norm[cand_norm]
    return None


def _detectar_tabla_en_hoja(archivo_bytes, hoja_nombre):
    """
    Lee las primeras filas de una hoja de Excel para detectar
    dónde empieza la cabecera real buscando la columna 'GUIA'.
    """
    try:
        df_preview = pd.read_excel(
            archivo_bytes,
            sheet_name=hoja_nombre,
            header=None,
            nrows=25,
            engine='openpyxl'
        )
    except Exception:
        archivo_bytes.seek(0)
        df_preview = pd.read_excel(
            archivo_bytes,
            sheet_name=hoja_nombre,
            header=None,
            nrows=25
        )

    fila_header = None
    for r_idx, row in df_preview.iterrows():
        row_vals = [str(val).upper().strip() for val in row.values if pd.notna(val)]
        for v in row_vals:
            if re.search(r'\b(GUIA|GUÍA|NRO GUIA|NUMERO GUIA|GUIA DESPACHO)\b', v):
                fila_header = r_idx
                break
        if fila_header is not None:
            break

    if fila_header is None:
        fila_header = 0

    archivo_bytes.seek(0)
    try:
        df = pd.read_excel(
            archivo_bytes,
            sheet_name=hoja_nombre,
            header=fila_header,
            engine='openpyxl'
        )
    except Exception:
        archivo_bytes.seek(0)
        df = pd.read_excel(
            archivo_bytes,
            sheet_name=hoja_nombre,
            header=fila_header
        )

    return df, fila_header + 1


def procesar_excel_dry_run(
    archivo_stream_o_bytes,
    filename,
    usuario_nombre,
    ProgramacionCargueModel,
    hoja_seleccionada='TODAS',
    tipo_guia_filtro='TODAS'
):
    """
    Ejecuta la Fase 1 (Dry-Run): analiza el Excel, cruza contra ProgramacionCargue
    permitiendo seleccionar la hoja y el tipo de guía (Física / Digital).
    """
    if isinstance(archivo_stream_o_bytes, (bytes, bytearray)):
        bio = io.BytesIO(archivo_stream_o_bytes)
    else:
        bio = io.BytesIO(archivo_stream_o_bytes.read())

    # Obtener todas las hojas del archivo Excel
    xl = pd.ExcelFile(bio, engine='openpyxl')
    hojas_disponibles = xl.sheet_names

    # Identificar exactamente las 2 hojas operativas oficiales
    hojas_fisicas = [h for h in hojas_disponibles if '001.FT.OP.ZF - FISICAS' in h.upper() or ('001.FT.OP.ZF' in h.upper() and 'FISIC' in h.upper()) or 'FISICA' in h.upper() or 'FÍSICA' in h.upper()]
    hojas_digitales = [h for h in hojas_disponibles if '001.FT.OP.ZF - DIGITALES' in h.upper() or ('001.FT.OP.ZF' in h.upper() and 'DIGIT' in h.upper()) or 'DIGITAL' in h.upper()]

    hoja_sel_norm = str(hoja_seleccionada).upper().strip()
    if hoja_sel_norm in ('FISICAS', 'FISICA'):
        hojas_a_procesar = hojas_fisicas
    elif hoja_sel_norm in ('DIGITALES', 'DIGITAL'):
        hojas_a_procesar = hojas_digitales
    elif hoja_sel_norm != 'TODAS' and hoja_seleccionada in hojas_disponibles:
        hojas_a_procesar = [hoja_seleccionada]
    else:
        # Modo 'TODAS': Procesar exclusivamente las 2 hojas operativas (FISICAS + DIGITALES) e ignorar el resto
        hojas_a_procesar = list(dict.fromkeys(hojas_fisicas + hojas_digitales))
        if not hojas_a_procesar:
            # Fallback en caso de variación menor en los nombres
            hojas_a_procesar = [h for h in hojas_disponibles if '001.FT.OP.ZF' in h.upper()]
        if not hojas_a_procesar:
            hojas_a_procesar = hojas_disponibles

    # Construir consulta a la base de datos: solo despachos de Agosto 2026 en adelante
    fecha_corte_agosto = date(2026, 8, 1)
    query_prog = ProgramacionCargueModel.query.filter(
        ProgramacionCargueModel.numero_guia.isnot(None),
        ProgramacionCargueModel.numero_guia != '',
        or_(
            ProgramacionCargueModel.fecha_despacho >= fecha_corte_agosto,
            and_(
                ProgramacionCargueModel.fecha_despacho.is_(None),
                ProgramacionCargueModel.fecha_programacion >= fecha_corte_agosto
            )
        )
    )

    # Filtrar por tipo de guía si el usuario lo especificó
    tipo_filtro_norm = str(tipo_guia_filtro).upper().strip()
    if tipo_filtro_norm in ('FISICAS', 'FISICA'):
        query_prog = query_prog.filter(
            or_(
                func.lower(ProgramacionCargueModel.tipo_guia).like('%fis%'),
                func.lower(ProgramacionCargueModel.tipo_guia).like('%fís%'),
                ProgramacionCargueModel.tipo_guia.is_(None)
            )
        )
    elif tipo_filtro_norm in ('DIGITALES', 'DIGITAL'):
        query_prog = query_prog.filter(
            func.lower(ProgramacionCargueModel.tipo_guia).like('%dig%')
        )

    registros_prog = query_prog.all()

    # Indexar registros de base de datos con índice tolerante multiclave
    guia_a_prog = {}
    for r in registros_prog:
        claves_r = extraer_claves_guia(r.numero_guia)
        for k in claves_r:
            guia_a_prog.setdefault(k, []).append(r)

    batch = FacturacionImportBatch(
        batch_uuid=str(uuid.uuid4()),
        archivo_nombre=filename,
        usuario=usuario_nombre,
        estado='PREVIEW'
    )
    db.session.add(batch)
    db.session.flush()

    total_filas = 0
    cruces_exactos = 0
    sobrescrituras = 0
    no_encontrados = 0
    ambiguos = 0

    items_a_guardar = []

    for hoja in hojas_a_procesar:
        bio.seek(0)
        try:
            df, fila_inicio = _detectar_tabla_en_hoja(bio, hoja)
        except Exception:
            continue

        if df.empty:
            continue

        cols = list(df.columns)
        col_guia = _buscar_columna(cols, ['GUIA', 'GUÍA', 'NUMERO GUIA', 'N° GUIA', 'NRO GUIA', 'GUIA DESPACHO', 'CONSECUTIVO GUIA'])
        if not col_guia:
            continue

        col_dv = _buscar_columna(cols, ['DV', 'D.V', 'DIGITO', 'DIGITO VERIFICACION', 'DIGITO VERIFICADOR'])
        col_factura = _buscar_columna(cols, [
            'FACTURA', 'N° FACTURA', 'NUMERO FACTURA', 'NRO FACTURA', 'FACTURA N°',
            'NO FACTURA', 'NUMERO DE FACTURA', 'CONTROL CONSECUTIVO DS', 'CONSECUTIVO DS',
            'CONTROL CONSECUTIVO', 'CONSECUTIVO', 'NUMERO FACT', 'FACTURA ELECTRONICA'
        ])
        col_fecha_fac = _buscar_columna(cols, ['FECHA FACTURA', 'FECHA DE FACTURA', 'FECHA FAC', 'FECHA FACTURACION', 'FECHA'])
        col_fecha_cargue = _buscar_columna(cols, ['FECHA CARGUE', 'FECHA DE CARGUE', 'FECHA DESPACHO', 'FECHA PROGRAMACION', 'FECHA_CARGUE', 'FECHA'])
        col_mes = _buscar_columna(cols, ['MES FACTURADO', 'MES FACTURA', 'MES'])
        col_trans = _buscar_columna(cols, [
            'CODIGO TRANSPORTE', 'CÓDIGO TRANSPORTE', 'COD TRANSPORTE', 'CODIGO DE TRANSPORTE',
            'CODIGO_TRANSPORTE', 'COD_TRANS', 'CODIGO FLETE', 'COD FLETE'
        ])

        for idx, row in df.iterrows():
            fila_num = fila_inicio + idx + 1

            guia_raw = row.get(col_guia)
            dv_raw = row.get(col_dv) if col_dv else None

            guia_val = normalizar_guia(guia_raw, dv=dv_raw)
            if not guia_val:
                continue

            factura_val = limpiar_texto_factura(row.get(col_factura)) if col_factura else None
            fecha_fac_val = normalizar_fecha(row.get(col_fecha_fac)) if col_fecha_fac else None
            fecha_cargue_val = normalizar_fecha(row.get(col_fecha_cargue)) if col_fecha_cargue else None
            mes_fac_val = normalizar_mes_facturado(row.get(col_mes), fecha_fac_val) if col_mes else (
                fecha_fac_val.strftime('%Y-%m') if fecha_fac_val else None
            )
            trans_val = limpiar_codigo_transporte(row.get(col_trans)) if col_trans else None

            # Búsqueda tolerante por todas las claves posibles
            claves_busqueda = set(extraer_claves_guia(guia_raw, dv=dv_raw))
            if guia_val:
                claves_busqueda.update(extraer_claves_guia(guia_val))

            coincidencias_dict = {}
            for k in claves_busqueda:
                for rec in guia_a_prog.get(k, []):
                    coincidencias_dict[rec.id] = rec

            prog_coincidencias = list(coincidencias_dict.values())

            if not prog_coincidencias:
                # Omitir registros históricos del archivo Excel que pertenezcan a meses previos a Agosto 2026
                es_historico_previo = False
                if fecha_fac_val and fecha_fac_val < fecha_corte_agosto:
                    es_historico_previo = True
                elif fecha_cargue_val and fecha_cargue_val < fecha_corte_agosto:
                    es_historico_previo = True
                elif mes_fac_val and any(mes_fac_val.startswith(f"2026-0{m}") for m in range(1, 8)):
                    es_historico_previo = True

                if es_historico_previo:
                    continue

                tipo_cruce = 'NO_ENCONTRADO'
                obs = f"Guía '{guia_val}' no encontrada en la tabla de despachos activos de Agosto."
                no_encontrados += 1
                prog_id = None
                fac_ant = None
                ffac_ant = None
                mfac_ant = None
                trans_ant = None
            elif len(prog_coincidencias) > 1:
                tipo_cruce = 'AMBIGUO'
                obs = f"Guía coincide con {len(prog_coincidencias)} despachos activos de Agosto."
                ambiguos += 1
                prog_rec = prog_coincidencias[0]
                prog_id = prog_rec.id
                fac_ant = prog_rec.factura
                ffac_ant = getattr(prog_rec, 'fecha_factura', None)
                mfac_ant = getattr(prog_rec, 'mes_facturado', None)
                trans_ant = getattr(prog_rec, 'codigo_transporte', None)
            else:
                prog_rec = prog_coincidencias[0]
                prog_id = prog_rec.id
                fac_ant = prog_rec.factura
                ffac_ant = getattr(prog_rec, 'fecha_factura', None)
                mfac_ant = getattr(prog_rec, 'mes_facturado', None)
                trans_ant = getattr(prog_rec, 'codigo_transporte', None)

                if fac_ant and factura_val and fac_ant.strip().upper() != factura_val.strip().upper():
                    tipo_cruce = 'SOBRESCRITURA'
                    obs = f"Sobrescribe factura anterior '{fac_ant}' por '{factura_val}'."
                    sobrescrituras += 1
                else:
                    tipo_cruce = 'EXACTO'
                    obs = f"Cruce exitoso con Guía '{prog_rec.numero_guia}' ({prog_rec.cliente or 'Sin cliente'})."
                    cruces_exactos += 1

            total_filas += 1

            item = FacturacionImportItem(
                batch_id=batch.id,
                hoja=hoja,
                fila_excel=fila_num,
                numero_guia=guia_val,
                factura_nueva=factura_val,
                fecha_factura_nueva=fecha_fac_val,
                mes_facturado_nuevo=mes_fac_val,
                codigo_transporte_nuevo=trans_val,
                programacion_id=prog_id,
                factura_anterior=fac_ant,
                fecha_factura_anterior=ffac_ant,
                mes_facturado_anterior=mfac_ant,
                codigo_transporte_anterior=trans_ant,
                tipo_cruce=tipo_cruce,
                observacion=obs,
                aplicado=False
            )
            items_a_guardar.append(item)

    batch.total_filas = len(items_a_guardar)
    batch.cruces_exactos = cruces_exactos
    batch.sobrescrituras = sobrescrituras
    batch.no_encontrados = no_encontrados
    batch.ambiguos = ambiguos

    db.session.bulk_save_objects(items_a_guardar)
    db.session.commit()

    return {
        'batch': batch.to_dict(),
        'hojas_disponibles': hojas_disponibles,
        'hojas_procesadas': hojas_a_procesar,
        'resumen': {
            'total_filas': batch.total_filas,
            'cruces_exactos': cruces_exactos,
            'sobrescrituras': sobrescrituras,
            'no_encontrados': no_encontrados,
            'ambiguos': ambiguos
        },
        'items': [i.to_dict() for i in items_a_guardar]
    }


def generar_excel_no_encontrados(batch_uuid):
    """Genera un archivo Excel descargable con todos los registros NO_ENCONTRADO de un lote."""
    batch = FacturacionImportBatch.query.filter_by(batch_uuid=batch_uuid).first()
    if not batch:
        raise ValueError("Lote no encontrado.")

    items = FacturacionImportItem.query.filter_by(
        batch_id=batch.id,
        tipo_cruce='NO_ENCONTRADO'
    ).order_by(FacturacionImportItem.fila_excel.asc()).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Guias_Faltantes'

    headers = [
        'Hoja Excel', 'Fila Excel', 'N° Guía', 'N° Factura',
        'Fecha Factura', 'Mes Facturado', 'Cód. Transporte', 'Detalle / Estado'
    ]
    ws.append(headers)

    for item in items:
        ws.append([
            item.hoja,
            item.fila_excel,
            item.numero_guia,
            item.factura_nueva or 'Sin Factura',
            item.fecha_factura_nueva.isoformat() if item.fecha_factura_nueva else '-',
            item.mes_facturado_nuevo or '-',
            item.codigo_transporte_nuevo or '-',
            item.observacion
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def confirmar_lote_importacion(batch_uuid, usuario_nombre, ProgramacionCargueModel, aplicar_sobrescrituras=True):
    """
    Ejecuta la Fase 2: Aplica los cambios validados en la base de datos
    dentro de una sola transacción atómica.
    """
    batch = FacturacionImportBatch.query.filter_by(batch_uuid=batch_uuid).first()
    if not batch:
        raise ValueError("Lote de importación no encontrado.")

    if batch.estado == 'CONFIRMADO':
        raise ValueError("Este lote ya fue confirmado previamente.")

    tipos_permitidos = ['EXACTO']
    if aplicar_sobrescrituras:
        tipos_permitidos.append('SOBRESCRITURA')

    items = FacturacionImportItem.query.filter(
        FacturacionImportItem.batch_id == batch.id,
        FacturacionImportItem.tipo_cruce.in_(tipos_permitidos),
        FacturacionImportItem.programacion_id.isnot(None),
        FacturacionImportItem.aplicado.is_(False)
    ).all()

    prog_ids = [i.programacion_id for i in items if i.programacion_id]
    registros_prog = {r.id: r for r in ProgramacionCargueModel.query.filter(ProgramacionCargueModel.id.in_(prog_ids)).all()}

    actualizados = 0
    ahora = datetime.utcnow()

    for item in items:
        reg = registros_prog.get(item.programacion_id)
        if not reg:
            continue

        modificado = False
        if item.factura_nueva:
            reg.factura = item.factura_nueva
            modificado = True

        if item.fecha_factura_nueva:
            reg.fecha_factura = item.fecha_factura_nueva
            modificado = True

        if item.mes_facturado_nuevo:
            reg.mes_facturado = item.mes_facturado_nuevo
            modificado = True

        if item.codigo_transporte_nuevo:
            reg.codigo_transporte = item.codigo_transporte_nuevo
            modificado = True

        if modificado:
            reg.ultimo_editor = usuario_nombre
            reg.fecha_actualizacion = ahora
            item.aplicado = True
            actualizados += 1

    batch.estado = 'CONFIRMADO'
    batch.fecha_confirmacion = ahora
    batch.usuario = usuario_nombre

    db.session.commit()
    return actualizados
