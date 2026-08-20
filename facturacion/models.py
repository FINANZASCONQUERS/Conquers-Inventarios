"""
Modelos y migración de esquema para el módulo de Facturación de Despachos.
"""
from datetime import datetime
from extensions import db
from sqlalchemy import inspect, text


class FacturacionImportBatch(db.Model):
    """Lote de importación para el flujo de dos fases (Dry-Run / Confirmación)."""
    __tablename__ = 'facturacion_import_batches'

    id = db.Column(db.Integer, primary_key=True)
    batch_uuid = db.Column(db.String(36), unique=True, nullable=False, index=True)
    archivo_nombre = db.Column(db.String(255), nullable=True)
    usuario = db.Column(db.String(120), nullable=True)
    total_filas = db.Column(db.Integer, default=0)
    cruces_exactos = db.Column(db.Integer, default=0)
    sobrescrituras = db.Column(db.Integer, default=0)
    no_encontrados = db.Column(db.Integer, default=0)
    ambiguos = db.Column(db.Integer, default=0)
    estado = db.Column(db.String(20), default='PREVIEW')  # 'PREVIEW', 'CONFIRMADO', 'CANCELADO'
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_confirmacion = db.Column(db.DateTime, nullable=True)

    items = db.relationship('FacturacionImportItem', backref='batch', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'batch_uuid': self.batch_uuid,
            'archivo_nombre': self.archivo_nombre,
            'usuario': self.usuario,
            'total_filas': self.total_filas,
            'cruces_exactos': self.cruces_exactos,
            'sobrescrituras': self.sobrescrituras,
            'no_encontrados': self.no_encontrados,
            'ambiguos': self.ambiguos,
            'estado': self.estado,
            'fecha_creacion': self.fecha_creacion.isoformat() if self.fecha_creacion else None,
            'fecha_confirmacion': self.fecha_confirmacion.isoformat() if self.fecha_confirmacion else None
        }


class FacturacionImportItem(db.Model):
    """Detalle de cada fila procesada dentro de un lote de importación."""
    __tablename__ = 'facturacion_import_items'

    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey('facturacion_import_batches.id', ondelete='CASCADE'), nullable=False, index=True)
    hoja = db.Column(db.String(100), nullable=True)
    fila_excel = db.Column(db.Integer, nullable=True)
    numero_guia = db.Column(db.String(100), nullable=True, index=True)

    factura_nueva = db.Column(db.String(100), nullable=True)
    fecha_factura_nueva = db.Column(db.Date, nullable=True)
    mes_facturado_nuevo = db.Column(db.String(20), nullable=True)
    codigo_transporte_nuevo = db.Column(db.String(100), nullable=True)

    programacion_id = db.Column(db.Integer, nullable=True)
    factura_anterior = db.Column(db.String(100), nullable=True)
    fecha_factura_anterior = db.Column(db.Date, nullable=True)
    mes_facturado_anterior = db.Column(db.String(20), nullable=True)
    codigo_transporte_anterior = db.Column(db.String(100), nullable=True)

    # Tipo de cruce: 'EXACTO', 'SOBRESCRITURA', 'NO_ENCONTRADO', 'AMBIGUO'
    tipo_cruce = db.Column(db.String(30), nullable=False)
    observacion = db.Column(db.String(255), nullable=True)
    aplicado = db.Column(db.Boolean, default=False)

    def to_dict(self):
        return {
            'id': self.id,
            'hoja': self.hoja,
            'fila_excel': self.fila_excel,
            'numero_guia': self.numero_guia,
            'factura_nueva': self.factura_nueva,
            'fecha_factura_nueva': self.fecha_factura_nueva.isoformat() if self.fecha_factura_nueva else None,
            'mes_facturado_nuevo': self.mes_facturado_nuevo,
            'codigo_transporte_nuevo': self.codigo_transporte_nuevo,
            'programacion_id': self.programacion_id,
            'factura_anterior': self.factura_anterior,
            'fecha_factura_anterior': self.fecha_factura_anterior.isoformat() if self.fecha_factura_anterior else None,
            'mes_facturado_anterior': self.mes_facturado_anterior,
            'codigo_transporte_anterior': self.codigo_transporte_anterior,
            'tipo_cruce': self.tipo_cruce,
            'observacion': self.observacion,
            'aplicado': self.aplicado
        }


def _ensure_facturacion_schema(app=None):
    """Asegura que las columnas e índices de facturación existan en `programacion_cargue` y crea tablas de lotes."""
    from flask import current_app
    app_to_use = app or current_app

    def _ejecutar():
        insp = inspect(db.engine)
        tables = insp.get_table_names()

        # 1. Crear tablas de lotes de importación si no existen
        if 'facturacion_import_batches' not in tables:
            FacturacionImportBatch.__table__.create(db.engine)
            print("[INIT FACTURACION] Tabla facturacion_import_batches creada.")
        if 'facturacion_import_items' not in tables:
            FacturacionImportItem.__table__.create(db.engine)
            print("[INIT FACTURACION] Tabla facturacion_import_items creada.")

        # 2. Verificar columnas en `programacion_cargue`
        if 'programacion_cargue' in tables:
            cols = [c['name'] for c in insp.get_columns('programacion_cargue')]
            dialect = db.engine.dialect.name

            date_type = 'DATE'
            str20_type = 'VARCHAR(20)'
            str100_type = 'VARCHAR(100)'

            with db.engine.begin() as conn:
                if 'fecha_factura' not in cols:
                    conn.execute(text(f"ALTER TABLE programacion_cargue ADD COLUMN fecha_factura {date_type}"))
                    print("[INIT FACTURACION] Columna fecha_factura añadida a programacion_cargue.")
                if 'mes_facturado' not in cols:
                    conn.execute(text(f"ALTER TABLE programacion_cargue ADD COLUMN mes_facturado {str20_type}"))
                    print("[INIT FACTURACION] Columna mes_facturado añadida a programacion_cargue.")
                if 'codigo_transporte' not in cols:
                    conn.execute(text(f"ALTER TABLE programacion_cargue ADD COLUMN codigo_transporte {str100_type}"))
                    print("[INIT FACTURACION] Columna codigo_transporte añadida a programacion_cargue.")

                # Índice sobre numero_guia si no existe
                try:
                    indexes = [ix['name'] for ix in insp.get_indexes('programacion_cargue')]
                    if 'ix_programacion_cargue_numero_guia' not in indexes and 'ix_prog_cargue_numero_guia' not in indexes:
                        conn.execute(text("CREATE INDEX ix_prog_cargue_numero_guia ON programacion_cargue (numero_guia)"))
                        print("[INIT FACTURACION] Índice en numero_guia creado para programacion_cargue.")
                except Exception as ex:
                    print("[INIT FACTURACION] Nota sobre índice en numero_guia:", ex)

    if app_to_use:
        with app_to_use.app_context():
            _ejecutar()
    else:
        _ejecutar()
