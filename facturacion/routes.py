"""
Rutas y API del módulo de Facturación de Despachos.
"""
import io
from datetime import date, datetime
from functools import wraps
import pandas as pd
from flask import (
    Blueprint, Response, current_app, jsonify, redirect,
    render_template, request, session, url_for
)
from werkzeug.routing import BuildError
from sqlalchemy import or_, and_, func

from extensions import db
from facturacion.models import FacturacionImportBatch, FacturacionImportItem
from facturacion.excel_service import procesar_excel_dry_run, confirmar_lote_importacion, normalizar_fecha, normalizar_mes_facturado


facturacion_bp = Blueprint('facturacion_bp', __name__)


def _es_peticion_api():
    return request.path.startswith('/api/') or request.headers.get('Accept') == 'application/json' or request.is_json


def _no_autenticado():
    if _es_peticion_api():
        return jsonify(success=False, message='Sesión requerida.'), 401
    try:
        return redirect(url_for('login', next=request.url))
    except Exception:
        return redirect('/login')


def _sin_permiso():
    if _es_peticion_api():
        return jsonify(success=False, message='No tienes permisos para acceder a Facturación.'), 403
    try:
        from flask import flash
        flash("No tienes los permisos necesarios para acceder a Facturación.", "danger")
        return redirect(url_for('home_global'))
    except Exception:
        return redirect('/inicio-global') if not _es_peticion_api() else (jsonify(success=False, message='No tienes permisos.'), 403)


def login_requerido(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'email' not in session:
            return _no_autenticado()
        return f(*args, **kwargs)
    return wrapper


def permiso_facturacion_requerido(f):
    """Permite lectura en Facturación a Administradores o usuarios con área 'facturacion' / 'contabilidad'."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'email' not in session:
            return _no_autenticado()

        if session.get('rol') == 'admin':
            return f(*args, **kwargs)

        areas = [str(a).strip().lower() for a in session.get('area', [])]
        if 'facturacion' in areas or 'contabilidad' in areas:
            return f(*args, **kwargs)

        return _sin_permiso()
    return wrapper


def permiso_facturacion_edicion_requerido(f):
    """Exige rol de editor o admin para modificar datos o confirmar importaciones."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'email' not in session:
            return _no_autenticado()

        if session.get('rol') == 'admin':
            return f(*args, **kwargs)

        areas = [str(a).strip().lower() for a in session.get('area', [])]
        if ('facturacion' in areas or 'contabilidad' in areas) and session.get('rol') == 'editor':
            return f(*args, **kwargs)

        if _es_peticion_api():
            return jsonify(success=False, message='No tienes permisos de edición en Facturación (solo lectura).'), 403
        return _sin_permiso()
    return wrapper


def permiso_importacion_requerido(f):
    """Permite importar archivos exclusivamente al rol Admin y a Juan Diego Ayala."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'email' not in session:
            return _no_autenticado()

        email = str(session.get('email', '')).strip().lower()
        rol = str(session.get('rol', '')).strip().lower()

        es_admin_o_autorizado = (rol == 'admin') or (email in [
            'numbers@conquerstrading.com',
            'oci@conquerstrading.com',
            'carlos.baron@conquerstrading.com',
            'logistics.inventory@conquerstrading.com'
        ])

        if es_admin_o_autorizado:
            return f(*args, **kwargs)

        if _es_peticion_api():
            return jsonify(success=False, message='Acceso denegado: Solo el Administrador y Juan Diego pueden importar archivos de Excel.'), 403
        return _sin_permiso()
    return wrapper


def _get_programacion_model():
    """Obtiene dinámicamente el modelo ProgramacionCargue de db.Model o SQLAlchemy registry."""
    # 1. En SQLAlchemy 2 / Flask-SQLAlchemy 3+
    try:
        if hasattr(db.Model, 'registry') and hasattr(db.Model.registry, 'mappers'):
            for mapper in db.Model.registry.mappers:
                if mapper.class_.__name__ == 'ProgramacionCargue' or getattr(mapper.class_, '__tablename__', None) == 'programacion_cargue':
                    return mapper.class_
    except Exception:
        pass

    # 2. En Flask-SQLAlchemy clásico (_decl_class_registry)
    try:
        registry = getattr(db.Model, '_decl_class_registry', {})
        if 'ProgramacionCargue' in registry:
            return registry['ProgramacionCargue']
        for c in registry.values():
            if hasattr(c, '__tablename__') and c.__tablename__ == 'programacion_cargue':
                return c
    except Exception:
        pass

    # 3. Fallback import directo
    try:
        from app import ProgramacionCargue
        return ProgramacionCargue
    except Exception:
        pass

    raise RuntimeError("No se encontró el modelo ProgramacionCargue.")


# --- Rutas de Vista ---

@facturacion_bp.route('/facturacion-despachos')
@login_requerido
@permiso_facturacion_requerido
def facturacion_despachos():
    """Página principal del módulo de Facturación de Despachos."""
    areas = [str(a).strip().lower() for a in session.get('area', [])]
    email = str(session.get('email', '')).strip().lower()
    rol = str(session.get('rol', '')).strip().lower()

    puede_editar = (rol == 'admin') or (('facturacion' in areas or 'contabilidad' in areas) and rol == 'editor')
    puede_importar = (rol == 'admin') or (email in [
        'numbers@conquerstrading.com',
        'oci@conquerstrading.com',
        'carlos.baron@conquerstrading.com',
        'logistics.inventory@conquerstrading.com'
    ])

    return render_template(
        'facturacion_despachos.html',
        nombre=session.get('nombre'),
        email=session.get('email'),
        rol=session.get('rol'),
        puede_editar=puede_editar,
        puede_importar=puede_importar
    )


# --- APIs ---

@facturacion_bp.route('/api/facturacion/despachos', methods=['GET'])
@login_requerido
@permiso_facturacion_requerido
def listar_despachos_facturacion():
    """Devuelve listado paginado de despachos con soporte de filtros y KPIs."""
    ProgramacionCargue = _get_programacion_model()

    # Filtro dinámico por mes (predeterminado: vacio/TODOS = todos los meses desde agosto 2026)
    mes_filtro = request.args.get('mes', '').strip()
    nombre_mes_label = "TODOS LOS MESES"

    if mes_filtro and mes_filtro.upper() != 'TODOS':
        try:
            partes = mes_filtro.split('-')
            año = int(partes[0])
            mes_num = int(partes[1])
            import calendar
            _, ultimo_dia = calendar.monthrange(año, mes_num)
            inicio_mes = date(año, mes_num, 1)
            fin_mes = date(año, mes_num, ultimo_dia)

            nombres_meses = ["", "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]
            nombre_mes_label = f"{nombres_meses[mes_num]} {año}"

            query = ProgramacionCargue.query.filter(
                or_(
                    func.upper(ProgramacionCargue.estado) == 'DESPACHADO',
                    ProgramacionCargue.fecha_despacho.isnot(None)
                ),
                or_(
                    and_(ProgramacionCargue.fecha_despacho >= inicio_mes, ProgramacionCargue.fecha_despacho <= fin_mes),
                    and_(
                        ProgramacionCargue.fecha_despacho.is_(None),
                        ProgramacionCargue.fecha_programacion >= inicio_mes,
                        ProgramacionCargue.fecha_programacion <= fin_mes
                    )
                )
            )
        except Exception:
            inicio_mes = date(2026, 8, 1)
            query = ProgramacionCargue.query.filter(
                or_(
                    func.upper(ProgramacionCargue.estado) == 'DESPACHADO',
                    ProgramacionCargue.fecha_despacho.isnot(None)
                ),
                or_(
                    ProgramacionCargue.fecha_despacho >= inicio_mes,
                    and_(
                        ProgramacionCargue.fecha_despacho.is_(None),
                        ProgramacionCargue.fecha_programacion >= inicio_mes
                    )
                )
            )
    else:
        nombre_mes_label = "TODOS LOS MESES"
        inicio_mes = date(2026, 8, 1)
        query = ProgramacionCargue.query.filter(
            or_(
                func.upper(ProgramacionCargue.estado) == 'DESPACHADO',
                ProgramacionCargue.fecha_despacho.isnot(None)
            ),
            or_(
                ProgramacionCargue.fecha_despacho >= inicio_mes,
                and_(
                    ProgramacionCargue.fecha_despacho.is_(None),
                    ProgramacionCargue.fecha_programacion >= inicio_mes
                )
            )
        )

    # Filtro por estado de facturación: 'FACTURADO', 'PENDIENTE', 'TODOS'
    estado_fac = request.args.get('estado_facturacion', 'TODOS').upper().strip()
    if estado_fac == 'FACTURADO':
        query = query.filter(
            ProgramacionCargue.factura.isnot(None),
            ProgramacionCargue.factura != ''
        )
    elif estado_fac == 'PENDIENTE':
        query = query.filter(
            or_(
                ProgramacionCargue.factura.is_(None),
                ProgramacionCargue.factura == ''
            )
        )

    # Filtro por cliente
    cliente = request.args.get('cliente')
    if cliente:
        query = query.filter(ProgramacionCargue.cliente.ilike(f"%{cliente.strip()}%"))

    # Filtro por producto
    producto = request.args.get('producto')
    if producto:
        query = query.filter(ProgramacionCargue.producto_a_cargar.ilike(f"%{producto.strip()}%"))

    # Búsqueda libre general (Guía, Factura, Cliente, Placa, Ciudad/Destino, Producto, Transportadora, Cód. Transporte, Mes Facturado)
    q = request.args.get('q')
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                ProgramacionCargue.numero_guia.ilike(term),
                ProgramacionCargue.factura.ilike(term),
                ProgramacionCargue.cliente.ilike(term),
                ProgramacionCargue.placa.ilike(term),
                ProgramacionCargue.destino.ilike(term),
                ProgramacionCargue.producto_a_cargar.ilike(term),
                ProgramacionCargue.empresa_transportadora.ilike(term),
                ProgramacionCargue.codigo_transporte.ilike(term),
                ProgramacionCargue.mes_facturado.ilike(term)
            )
        )

    # Calcular KPIs globales sobre la consulta filtrada (responde a producto, cliente, ciudad, transportadora, etc.)
    total_registros = query.count()

    # Facturados vs Pendientes
    facturados_count = query.filter(ProgramacionCargue.factura.isnot(None), ProgramacionCargue.factura != '').count()
    pendientes_count = total_registros - facturados_count

    # Galones y Barriles totales y facturados
    try:
        sum_gal_total = query.with_entities(func.sum(ProgramacionCargue.galones)).scalar() or 0.0
        sum_gal_fact = query.filter(ProgramacionCargue.factura.isnot(None), ProgramacionCargue.factura != '').with_entities(func.sum(ProgramacionCargue.galones)).scalar() or 0.0
        sum_bbl_total = query.with_entities(func.sum(ProgramacionCargue.barriles)).scalar() or 0.0
        sum_bbl_fact = query.filter(ProgramacionCargue.factura.isnot(None), ProgramacionCargue.factura != '').with_entities(func.sum(ProgramacionCargue.barriles)).scalar() or 0.0
    except Exception:
        sum_gal_total = 0.0
        sum_gal_fact = 0.0
        sum_bbl_total = 0.0
        sum_bbl_fact = 0.0

    # Obtener dinámicamente los meses reales que existen en la base de datos a partir de Agosto 2026
    meses_set = set()
    nombres_meses_es = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

    try:
        fechas_db = db.session.query(
            func.coalesce(ProgramacionCargue.fecha_despacho, ProgramacionCargue.fecha_programacion)
        ).filter(
            func.coalesce(ProgramacionCargue.fecha_despacho, ProgramacionCargue.fecha_programacion) >= date(2026, 8, 1)
        ).distinct().all()

        for (f_val,) in fechas_db:
            if f_val:
                try:
                    cod = f_val.strftime('%Y-%m')
                    nom = f"{nombres_meses_es[f_val.month]} {f_val.year}"
                    meses_set.add((cod, nom, f_val.year, f_val.month))
                except Exception:
                    pass

        meses_fac_db = db.session.query(ProgramacionCargue.mes_facturado).filter(
            ProgramacionCargue.mes_facturado.isnot(None),
            ProgramacionCargue.mes_facturado != ''
        ).distinct().all()

        for (mf,) in meses_fac_db:
            if mf and re.match(r'^\d{4}-\d{2}$', str(mf).strip()):
                try:
                    y, m = map(int, str(mf).strip().split('-'))
                    if y >= 2026 and (y > 2026 or m >= 8):
                        nom = f"{nombres_meses_es[m]} {y}"
                        meses_set.add((str(mf).strip(), nom, y, m))
                except Exception:
                    pass
    except Exception:
        pass

    if not meses_set:
        meses_set.add(('2026-08', 'Agosto 2026', 2026, 8))

    meses_disponibles = [
        {'codigo': cod, 'nombre': nom}
        for cod, nom, y, m in sorted(meses_set, key=lambda x: (x[2], x[3]), reverse=True)
    ]

    # Paginación
    try:
        page = max(1, int(request.args.get('page', 1)))
        per_page = max(10, min(int(request.args.get('per_page', 50)), 200))
    except (TypeError, ValueError):
        page = 1
        per_page = 50

    # Ordenamiento predeterminado: de más nuevo a más viejo (DESC)
    fecha_col = func.coalesce(ProgramacionCargue.fecha_despacho, ProgramacionCargue.fecha_programacion)
    order_by_criteria = [fecha_col.desc(), ProgramacionCargue.id.desc()]

    pages = max(1, (total_registros + per_page - 1) // per_page)
    registros = query.order_by(*order_by_criteria).offset((page - 1) * per_page).limit(per_page).all()

    items = []
    for r in registros:
        esta_facturado = bool(r.factura and r.factura.strip())
        mes_fac_val = getattr(r, 'mes_facturado', None)
        mes_fac_display = normalizar_mes_facturado(mes_fac_val, getattr(r, 'fecha_factura', None)) if (mes_fac_val or getattr(r, 'fecha_factura', None)) else (mes_fac_val or '')

        items.append({
            'id': r.id,
            'producto': r.producto_a_cargar,
            'cliente': r.cliente,
            'ciudad': r.destino,
            'galones': r.galones,
            'barriles': r.barriles,
            'api_corregido': r.api_corregido,
            'fecha_despacho': r.fecha_despacho.isoformat() if r.fecha_despacho else (r.fecha_programacion.isoformat() if r.fecha_programacion else None),
            'numero_guia': r.numero_guia,
            'placa': r.placa,
            'empresa_transportadora': r.empresa_transportadora,
            # Campos de Facturación
            'factura': r.factura,
            'fecha_factura': r.fecha_factura.isoformat() if getattr(r, 'fecha_factura', None) else None,
            'mes_facturado': mes_fac_display,
            'codigo_transporte': getattr(r, 'codigo_transporte', None),
            'estado_facturacion': 'FACTURADO' if esta_facturado else 'PENDIENTE',
            'ultimo_editor': r.ultimo_editor,
            'fecha_actualizacion': r.fecha_actualizacion.isoformat() if r.fecha_actualizacion else None
        })

    return jsonify(
        success=True,
        data=items,
        total=total_registros,
        page=page,
        per_page=per_page,
        pages=pages,
        mes_seleccionado=mes_filtro,
        meses_disponibles=meses_disponibles,
        kpis={
            'total_vehiculos': total_registros,
            'total_despachos': total_registros,
            'barriles_totales': round(float(sum_bbl_total), 2),
            'galones_totales': round(float(sum_gal_total), 2),
            'pendientes': pendientes_count,
            'facturados': facturados_count,
            'galones_facturados': round(float(sum_gal_fact), 2),
            'barriles_facturados': round(float(sum_bbl_fact), 2),
            'porcentaje_facturado': round((facturados_count / total_registros * 100), 1) if total_registros > 0 else 0
        }
    )


@facturacion_bp.route('/api/facturacion/despachos/<int:id>', methods=['PUT'])
@login_requerido
@permiso_facturacion_edicion_requerido
def actualizar_facturacion_despacho(id):
    """Actualiza en línea los 4 campos de facturación para un despacho específico."""
    ProgramacionCargue = _get_programacion_model()
    registro = ProgramacionCargue.query.get_or_404(id)
    data = request.get_json() or {}

    try:
        if 'factura' in data:
            val_fac = data.get('factura')
            registro.factura = str(val_fac).strip().upper() if val_fac not in (None, '') else None

        if 'fecha_factura' in data:
            registro.fecha_factura = normalizar_fecha(data.get('fecha_factura'))
            if 'mes_facturado' not in data and registro.fecha_factura and not getattr(registro, 'mes_facturado', None):
                registro.mes_facturado = normalizar_mes_facturado(None, registro.fecha_factura)

        if 'mes_facturado' in data:
            val_mes = data.get('mes_facturado')
            registro.mes_facturado = normalizar_mes_facturado(val_mes, getattr(registro, 'fecha_factura', None)) if val_mes else None

        if 'codigo_transporte' in data:
            val_tr = data.get('codigo_transporte')
            registro.codigo_transporte = str(val_tr).strip().upper() if val_tr not in (None, '') else None

        registro.ultimo_editor = session.get('nombre', 'Sistema')
        registro.fecha_actualizacion = datetime.utcnow()

        db.session.commit()

        esta_facturado = bool(registro.factura and registro.factura.strip())
        mes_fac_out = normalizar_mes_facturado(getattr(registro, 'mes_facturado', None), getattr(registro, 'fecha_factura', None))

        return jsonify(
            success=True,
            message="Datos de facturación actualizados.",
            registro={
                'id': registro.id,
                'factura': registro.factura,
                'fecha_factura': registro.fecha_factura.isoformat() if getattr(registro, 'fecha_factura', None) else None,
                'mes_facturado': mes_fac_out,
                'codigo_transporte': getattr(registro, 'codigo_transporte', None),
                'estado_facturacion': 'FACTURADO' if esta_facturado else 'PENDIENTE',
                'ultimo_editor': registro.ultimo_editor,
                'fecha_actualizacion': registro.fecha_actualizacion.isoformat() if registro.fecha_actualizacion else None
            }
        )
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, message=f"Error actualizando registro: {str(e)}"), 500


@facturacion_bp.route('/api/facturacion/importar/dry-run', methods=['POST'])
@login_requerido
@permiso_importacion_requerido
def importar_excel_dry_run():
    """Fase 1: Recibe el Excel de control de despachos y genera una previsualización de cruces sin aplicar cambios."""
    if 'archivo_excel' not in request.files:
        return jsonify(success=False, message="Debes adjuntar un archivo Excel (.xlsx)."), 400

    archivo = request.files['archivo_excel']
    if not archivo.filename.endswith(('.xlsx', '.xls')):
        return jsonify(success=False, message="Formato no admitido. Usa un archivo .xlsx de Excel."), 400

    modo_importacion = request.form.get('modo_importacion', 'TODAS').strip().upper()
    hoja_seleccionada = request.form.get('hoja_seleccionada', modo_importacion).strip()
    tipo_guia_filtro = request.form.get('tipo_guia_filtro', modo_importacion).strip()

    ProgramacionCargue = _get_programacion_model()

    try:
        resultado = procesar_excel_dry_run(
            archivo_stream_o_bytes=archivo.stream,
            filename=archivo.filename,
            usuario_nombre=session.get('nombre', 'Usuario'),
            ProgramacionCargueModel=ProgramacionCargue,
            hoja_seleccionada=hoja_seleccionada,
            tipo_guia_filtro=tipo_guia_filtro
        )

        return jsonify(
            success=True,
            batch=resultado['batch'],
            hojas_disponibles=resultado.get('hojas_disponibles', []),
            hojas_procesadas=resultado.get('hojas_procesadas', []),
            items=resultado['items'],
            resumen=resultado['resumen']
        )
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Error en importación de Excel Dry-Run")
        return jsonify(success=False, message=f"Error procesando el archivo: {str(e)}"), 500


@facturacion_bp.route('/api/facturacion/importar/confirmar', methods=['POST'])
@login_requerido
@permiso_importacion_requerido
def confirmar_importacion():
    """Fase 2: Aplica los cambios del lote validado en la base de datos."""
    data = request.get_json() or {}
    batch_uuid = data.get('batch_uuid')
    aplicar_sobrescrituras = bool(data.get('aplicar_sobrescrituras', True))

    if not batch_uuid:
        return jsonify(success=False, message="Identificador de lote requerido."), 400

    ProgramacionCargue = _get_programacion_model()

    try:
        actualizados = confirmar_lote_importacion(
            batch_uuid=batch_uuid,
            usuario_nombre=session.get('nombre', 'Usuario'),
            ProgramacionCargueModel=ProgramacionCargue,
            aplicar_sobrescrituras=aplicar_sobrescrituras
        )

        return jsonify(
            success=True,
            message=f"Se actualizaron {actualizados} registro(s) de despachos con los datos de facturación.",
            actualizados=actualizados
        )
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, message=f"Error al confirmar lote: {str(e)}"), 500


@facturacion_bp.route('/api/facturacion/importar/exportar-no-encontrados/<batch_uuid>', methods=['GET'])
@login_requerido
@permiso_importacion_requerido
def exportar_no_encontrados_lote(batch_uuid):
    """Permite descargar un archivo Excel con todas las guías del archivo que no se encontraron en el sistema."""
    from facturacion.excel_service import generar_excel_no_encontrados
    try:
        buf = generar_excel_no_encontrados(batch_uuid)
        return send_file(
            buf,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f"Guias_No_Encontradas_{batch_uuid[:8]}.xlsx"
        )
    except Exception as e:
        return jsonify(success=False, message=f"Error generando reporte de guías faltantes: {str(e)}"), 404


@facturacion_bp.route('/api/facturacion/exportar', methods=['GET'])
@login_requerido
@permiso_facturacion_requerido
def exportar_facturacion_excel():
    """Exporta la lista actual filtrada a un archivo Excel descargable."""
    ProgramacionCargue = _get_programacion_model()

    # Filtro dinámico por mes (predeterminado: '2026-08' = Agosto 2026)
    mes_filtro = request.args.get('mes', '2026-08').strip()

    if mes_filtro and mes_filtro.upper() != 'TODOS':
        try:
            partes = mes_filtro.split('-')
            año = int(partes[0])
            mes_num = int(partes[1])
            import calendar
            _, ultimo_dia = calendar.monthrange(año, mes_num)
            inicio_mes = date(año, mes_num, 1)
            fin_mes = date(año, mes_num, ultimo_dia)

            query = ProgramacionCargue.query.filter(
                or_(
                    func.upper(ProgramacionCargue.estado) == 'DESPACHADO',
                    ProgramacionCargue.fecha_despacho.isnot(None)
                ),
                or_(
                    and_(ProgramacionCargue.fecha_despacho >= inicio_mes, ProgramacionCargue.fecha_despacho <= fin_mes),
                    and_(
                        ProgramacionCargue.fecha_despacho.is_(None),
                        ProgramacionCargue.fecha_programacion >= inicio_mes,
                        ProgramacionCargue.fecha_programacion <= fin_mes
                    )
                )
            )
        except Exception:
            inicio_mes = date(2026, 8, 1)
            query = ProgramacionCargue.query.filter(
                or_(
                    func.upper(ProgramacionCargue.estado) == 'DESPACHADO',
                    ProgramacionCargue.fecha_despacho.isnot(None)
                ),
                or_(
                    ProgramacionCargue.fecha_despacho >= inicio_mes,
                    and_(
                        ProgramacionCargue.fecha_despacho.is_(None),
                        ProgramacionCargue.fecha_programacion >= inicio_mes
                    )
                )
            )
    else:
        inicio_mes = date(2026, 8, 1)
        query = ProgramacionCargue.query.filter(
            or_(
                func.upper(ProgramacionCargue.estado) == 'DESPACHADO',
                ProgramacionCargue.fecha_despacho.isnot(None)
            ),
            or_(
                ProgramacionCargue.fecha_despacho >= inicio_mes,
                and_(
                    ProgramacionCargue.fecha_despacho.is_(None),
                    ProgramacionCargue.fecha_programacion >= inicio_mes
                )
            )
        )

    estado_fac = request.args.get('estado_facturacion', 'TODOS').upper().strip()
    if estado_fac == 'FACTURADO':
        query = query.filter(ProgramacionCargue.factura.isnot(None), ProgramacionCargue.factura != '')
    elif estado_fac == 'PENDIENTE':
        query = query.filter(or_(ProgramacionCargue.factura.is_(None), ProgramacionCargue.factura == ''))

    mes_fac = request.args.get('mes_facturado')
    if mes_fac:
        query = query.filter(ProgramacionCargue.mes_facturado == mes_fac.strip())

    q = request.args.get('q')
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                ProgramacionCargue.numero_guia.ilike(term),
                ProgramacionCargue.factura.ilike(term),
                ProgramacionCargue.cliente.ilike(term),
                ProgramacionCargue.placa.ilike(term)
            )
        )

    fecha_col = func.coalesce(ProgramacionCargue.fecha_despacho, ProgramacionCargue.fecha_programacion)
    registros = query.order_by(fecha_col.desc(), ProgramacionCargue.id.desc()).all()

    filas = []
    for r in registros:
        filas.append({
            'ID': r.id,
            'Producto': r.producto_a_cargar,
            'Cliente': r.cliente,
            'Ciudad Destino': r.destino,
            'Galones': r.galones,
            'Barriles': r.barriles,
            'API Corregido': r.api_corregido,
            'Fecha Despacho': r.fecha_despacho.strftime('%Y-%m-%d') if r.fecha_despacho else (r.fecha_programacion.strftime('%Y-%m-%d') if r.fecha_programacion else ''),
            'Número Guía': r.numero_guia,
            'Placa': r.placa,
            'Transportadora': r.empresa_transportadora,
            'N° Factura': r.factura or '',
            'Fecha Factura': r.fecha_factura.strftime('%Y-%m-%d') if getattr(r, 'fecha_factura', None) else '',
            'Mes Facturado': getattr(r, 'mes_facturado', '') or '',
            'Código Transporte': getattr(r, 'codigo_transporte', '') or '',
            'Estado': 'FACTURADO' if (r.factura and r.factura.strip()) else 'PENDIENTE',
            'Último Editor': r.ultimo_editor or ''
        })

    df = pd.DataFrame(filas)
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Facturacion_Despachos')
        ws = writer.sheets['Facturacion_Despachos']
        # Ajuste simple de ancho de columnas
        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = col[0].column_letter
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    out.seek(0)
    nombre_archivo = f"Facturacion_Despachos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(
        out.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{nombre_archivo}"'}
    )
