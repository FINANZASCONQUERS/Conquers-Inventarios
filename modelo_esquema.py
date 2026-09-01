# -*- coding: utf-8 -*-
"""Esquema de los parametros del Modelo de Optimizacion LP.

Esto es lo que permite arrancar un escenario DESDE CERO sin que exista ningun
Excel: antes la estructura (que hojas, que columnas y en que orden) se leia del
archivo maestro, asi que sin el no se podia ni crear un escenario en blanco.

CUIDADO al editar los nombres: varios llevan espacios dobles o saltos de linea
y el modelo los usa literalmente (por ejemplo `Aluminum (Al)  mg/kg` con dos
espacios). Cambiar un nombre aqui sin cambiarlo en modelo_optimizacion_core.py
rompe el modelo en silencio.

Generado desde Parametros.xlsx; verificado columna a columna contra el archivo.
"""

import pandas as pd


# Valores economicos globales del escenario.
CLAVES_ECONOMICS = ['BRENT', 'TRM', 'DIESEL [COP/gal]']

# Hoja auxiliar: NO la lee el solver, alimenta la derivacion de precios.
HOJA_PRECIOS = '13.PRECIOS_VENTA'

# Las 12 hojas del modelo, en el orden en que se presentan.
HOJAS = [
    '1.NODOS',
    '2.FLUJOS',
    '3.COMPRAS',
    '4.RUTAS_TRANSPORTE',
    '5.CURVA_DESTILACION',
    '6.VENTAS',
    '7.COSTOS_REFINACION',
    '8.LIMITES_CALIDAD',
    '9.FLASH_RESTR',
    '10.CVC',
    '11.REL_CRUDO_MEZCLA',
    '12.COSTOS_OPERACIONALES',
]

# Columnas de cada hoja, en orden. Las 'Unnamed: N' son columnas vacias que el
# Excel arrastra; se conservan para que el ancho de la hoja no cambie.
COLUMNAS = {
    HOJA_PRECIOS: [
        'CORRIENTE COMERCIAL',
        'AJUSTE VS BRENT (USD/BBL)',
        'PRECIO CALCULADO (USD/BBL)',
    ],
    '1.NODOS': [
        'NOMBRE DEL NODO',
        'TIPO DE NODO',
        'Comentarios',
        'Unnamed: 3',
        'Unnamed: 4',
        'Unnamed: 5',
        'Unnamed: 6',
        'TIPO DE NODO DEF',
        'DEFINICION',
        'Unnamed: 9',
        'AUX RELAX CONST FLASH',
    ],
    '2.FLUJOS': [
        'FLUJO',
        'TIPO DE FLUJO',
        'Comentarios',
        'Unnamed: 3',
        'Unnamed: 4',
        'Unnamed: 5',
        'TIPOS DE FLUJO def',
        'DEFINICION',
    ],
    '3.COMPRAS': [
        'CRUDO O PRODUCTO',
        'TIPO ',
        'ORIGEN',
        'Volumen Minimo a Compra (BPD)',
        'Volumen Disponible a Compra (BPD)',
        'Precio de Compra CALCULADO  (USD/BPD)',
        'Spread\n (Valor +/- al precio de BRENT) ',
        'Formula Precio Referencia',
        'CALIDAD API',
        'SPG',
        'DENSIDAD  (BBL/TONMETRICA)',
        '%AZUFRE',
        'Viscosidad Cst',
        'Iv50',
        'FLASH POINT C',
        'ACID NUMBER mg KOH/g',
        'Accelerated Total Sediment by Hot Filtration % m/m',
        'Micro Carbon Residue % m/m',
        'Water by Distillation % v/v',
        'Ash Content % m/m',
        'Vanadium (V) mg/kg',
        'Sodium (Na) mg/kg',
        'Aluminum (Al)  mg/kg',
        'Silicon (Si) mg/kg',
        'Aluminum plus Silicon mg/kg',
        'Calcium (Ca)  mg/kg',
        'Zinc (Zn)  mg/kg',
        'Phosphorus (P)   mg/kg',
    ],
    '4.RUTAS_TRANSPORTE': [
        'FLUJO',
        'CRUDO ORIGEN',
        'TIPO FLUJO',
        'ORIGEN',
        'TIPO DE NODO ORIGEN',
        'DESTINO',
        'TIPO DE NODO DESTINO',
        'CVC MEZCLA RESULANTE',
        'RUTA DE TRANSPORTE',
        'Costo de Transporte ',
        'Costo de transporte USD/BBL para modelo',
        'Relacion Area de Operacion Costo BLEND IFO?',
    ],
    '5.CURVA_DESTILACION': [
        'PRODUCTO',
        'CRUDO ORIGEN',
        'FRACCION %',
        'TOTAL (DEBE SER IGUAL A 1)',
        'CALIDAD API',
        'SPG',
        'DENSIDAD (BBL/TONMETRICA)',
        'AZUFRE %',
        'Viscosidad Cst',
        'Iv50',
        'ACID NUMBER mg KOH/g',
        'Accelerated Total Sediment by Hot Filtration % m/m',
        'Micro Carbon Residue % m/m',
        'Water by Distillation % v/v',
        'Ash Content % m/m',
        'Vanadium (V) mg/kg',
        'Sodium (Na) mg/kg',
        'Aluminum (Al)  mg/kg',
        'Silicon (Si) mg/kg',
        'Aluminum plus Silicon mg/kg',
        'Calcium (Ca)  mg/kg',
        'Zinc (Zn)  mg/kg',
        'Phosphorus (P)   mg/kg',
    ],
    '6.VENTAS': [
        'FLUJO',
        'CRUDO ORIGEN',
        'TIPO FLUJO',
        'PUNTO DE VENTA',
        'VALIDACION TIPO DE NODO VENTA',
        'VENTA DENSIDAD',
        'VENTA CVC',
        'ORIGEN BLEND',
        'Precio de venta (USD/BPD)',
        'Densidad (BBL/TONMetrica) Contractual',
        'Formula de Precio de venta',
        'Volumen Minimo a Venta (BPD)',
        'Volumen Maximo a Venta (Si aplica)  (BPD)',
        'CRUDO: DENSIDAD  (BBL/TONMETRICA)',
        'REFINADO: DENSIDAD  (BBL/TONMETRICA)',
        'RELACION  DCONTRAC/DENTREGA',
    ],
    '7.COSTOS_REFINACION': [
        'PLANTA REFINACION',
        'TIPO DE NODO',
        'Costo de refinacion (USD/BPD)',
        'Capacidad minima de Refinacion (BPD)',
        'Capacidad maxima de Refinacion (BPD)',
    ],
    '8.LIMITES_CALIDAD': [
        'MEZCLA',
        'CENTRO DE BLENDING',
        'VENTA DENSIDAD',
        'MINIMO CALIDAD API',
        'MAXIMO CALIDAD API',
        'MINIMO CALIDAD SPG',
        'MAXIMO CALIDAD SPG',
        'MINIMO CALIDAD AZUFRE',
        'MAXIMO CALIDAD AZUFRE',
        'MINIMO VISCOSIDAD',
        'MAXIMO VISCOSIDAD',
        'MINIMO V50',
        'MAXIMO V50',
        'MINIMO CALIDAD ACID NUMBER mg KOH/g',
        'MAXIMO CALIDAD ACID NUMBER mg KOH/g',
        'MINIMO CALIDAD  Accelerated Total Sediment by Hot Filtration % m/m',
        'MAXIMO CALIDAD Accelerated Total Sediment by Hot Filtration % m/m',
        'MINIMO CALIDAD  Micro Carbon Residue % m/m',
        'MAXIMO CALIDAD   Micro Carbon Residue % m/m',
        'MINIMO CALIDAD Water by Distillation % v/v',
        'MAXIMO CALIDAD Water by Distillation % v/v',
        'MINIMO CALIDAD  Ash Content % m/m',
        'MAXIMO CALIDAD  Ash Content % m/m',
        'MINIMO CALIDAD Vanadium (V) mg/kg',
        'MAXIMO CALIDAD Vanadium (V) mg/kg',
        'MINIMO CALIDAD Sodium (Na) mg/kg',
        'MAXIMO CALIDAD Sodium (Na) mg/kg',
        'MINIMO CALIDAD Aluminum (Al)  mg/kg',
        'MAXIMO CALIDAD Aluminum (Al) mg/kg',
        'MINIMO CALIDAD Silicon (Si) mg/kg',
        'MAXIMO CALIDAD Silicon (Si) mg/kg',
        'MINIMO CALIDAD Aluminum plus Silicon mg/kg',
        'MAXIMO CALIDAD Aluminum plus Silicon mg/kg',
        'MINIMO CALIDAD Calcium (Ca)  mg/kg',
        'MAXIMO CALIDAD Calcium (Ca)   mg/kg',
        'MINIMO CALIDAD Zinc (Zn)  mg/kg',
        'MAXIMO CALIDAD Zinc (Zn)  mg/kg',
        'MINIMO CALIDAD Phosphorus (P)   mg/kg',
        'MAXIMO CALIDAD Phosphorus (P)    mg/kg',
    ],
    '9.FLASH_RESTR': [
        'FLUJO',
        'TIPO FLUJO',
        'ORIGEN',
        'DESTINO',
        'MEZCLA A PERTENECER',
        'FLASH POINT C',
        'MINIMO REQUERIDO EN DESTINO',
        'BINARY COND',
        'RELAX RESTRICION?',
    ],
    '10.CVC': [
        'FLUJO',
        'CRUDO ORIGEN',
        'TIPO FLUJO',
        'MEZCLA A PERTENECER',
        'DESTINO',
        'FACTOR CVC',
    ],
    '11.REL_CRUDO_MEZCLA': [
        'FLUJO',
        'CRUDO ORIGEN',
        'TIPO FLUJO',
        'DESTINO',
        'BLEND DENSIDAD',
        'MEZCLA A PERTENECER',
    ],
    '12.COSTOS_OPERACIONALES': [
        'PUNTO DE BLENDING',
        'Almacenamiento (USD/BBL)',
        'Op. Portuaria (USD/BBL)',
        'Barcazas  (USD/BBL)',
        'Pusher (USD/BBL)',
        'Tasa Portuaria (USD/BBL)',
        'Costo Operacional (USD/BBL)',
        'Costo Operacion Refinados en Blend  (USD/BBL)',
    ],
}


def hojas_vacias(incluir_precios=False):
    """Las 12 hojas con sus columnas y sin ninguna fila.

    Con `incluir_precios` agrega tambien la hoja auxiliar de precios de venta.
    """
    nombres = list(HOJAS) + ([HOJA_PRECIOS] if incluir_precios else [])
    return {h: pd.DataFrame(columns=list(COLUMNAS[h])) for h in nombres}


def payload_vacio(economics=None):
    """Un escenario en blanco listo para capturar, sin depender de ningun Excel.

    Devuelve la misma estructura que `modelo_parametros_builder.escenario_vacio`:
    {'economics': {...}, 'sheets': {hoja: {'columns', 'editable', 'rows'}}}
    """
    from modelo_parametros_builder import columnas_editables

    econ = {k: None for k in CLAVES_ECONOMICS}
    if economics:
        econ.update({k: v for k, v in economics.items() if k in econ})

    sheets = {}
    for h in list(HOJAS) + [HOJA_PRECIOS]:
        cols = list(COLUMNAS[h])
        sheets[h] = {
            'columns': cols,
            'editable': columnas_editables(h, cols),
            'rows': [],
        }
    return {'economics': econ, 'sheets': sheets}


def verificar_contra_excel(excel_path):
    """Compara el esquema con un Excel real. Devuelve la lista de diferencias."""
    difs = []
    for h in HOJAS:
        reales = [str(c) for c in pd.read_excel(excel_path, sheet_name=h).columns]
        if reales != list(COLUMNAS[h]):
            faltan = [c for c in reales if c not in COLUMNAS[h]]
            sobran = [c for c in COLUMNAS[h] if c not in reales]
            difs.append({'hoja': h, 'faltan_en_esquema': faltan,
                         'sobran_en_esquema': sobran,
                         'mismo_orden': reales == list(COLUMNAS[h])})
    return difs
