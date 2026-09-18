# -*- coding: utf-8 -*-
"""
Conversión por gravedad API para barcazas: Barriles @60°F -> Galones -> Toneladas.

Usa la tabla static/data/conversion_api.json (generada desde static/data/conversion_api.csv con
scripts/generar_conversion_api.py). Cada fila: [Grados API, Kg/Gal, Ton/Barril, Barriles/Ton].
Para valores de API entre dos filas se interpola linealmente. Si el API está vacío, es <= 0 o
queda fuera del rango de la tabla, no se calcula (se devuelve None) para no mostrar toneladas falsas.
"""
import bisect
import io
import json
import os

RUTA_TABLA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'data', 'conversion_api.json')
GALONES_POR_BARRIL = 42.0

_TABLA = None      # lista de filas [api, kg_gal, ton_bbl, bbl_ton] ordenada por api
_APIS = None       # lista de apis (para bisect)


def _cargar():
    global _TABLA, _APIS
    if _TABLA is not None:
        return
    try:
        with io.open(RUTA_TABLA, 'r', encoding='utf-8') as f:
            datos = json.load(f)
        filas = sorted((list(map(float, r)) for r in datos.get('filas', [])), key=lambda r: r[0])
    except Exception as e:
        print(f'[CONVERSION_API] No fue posible cargar {RUTA_TABLA}: {e}')
        filas = []
    _TABLA = filas
    _APIS = [r[0] for r in filas]


def _num(v):
    if v is None:
        return None
    s = str(v).strip().replace(',', '.')
    if s == '':
        return None
    try:
        return float(s)
    except ValueError:
        return None


def rango_api():
    """(api_min, api_max) cubiertos por la tabla, o (None, None) si no cargó."""
    _cargar()
    if not _TABLA:
        return (None, None)
    return (_TABLA[0][0], _TABLA[-1][0])


def factores_api(api):
    """
    Factores para un API dado: {'api', 'kg_gal', 'ton_bbl', 'bbl_ton'} o None.
    Interpola linealmente entre las filas de la tabla.
    """
    _cargar()
    a = _num(api)
    if a is None or a <= 0 or not _TABLA or a < _TABLA[0][0] or a > _TABLA[-1][0]:
        return None
    i = bisect.bisect_left(_APIS, a)
    f1 = _TABLA[i]
    if f1[0] == a or i == 0:
        return {'api': a, 'kg_gal': f1[1], 'ton_bbl': f1[2], 'bbl_ton': f1[3]}
    f0 = _TABLA[i - 1]
    t = (a - f0[0]) / (f1[0] - f0[0])
    ip = lambda k: f0[k] + (f1[k] - f0[k]) * t
    return {'api': a, 'kg_gal': ip(1), 'ton_bbl': ip(2), 'bbl_ton': ip(3)}


def bls_a_galones(bls):
    b = _num(bls)
    return (b or 0.0) * GALONES_POR_BARRIL if b is not None else 0.0


def bls_a_toneladas(bls, api):
    """Toneladas métricas a partir de barriles @60°F y API. None si el API no permite convertir."""
    b = _num(bls)
    f = factores_api(api)
    if b is None or f is None:
        return None
    return b * f['ton_bbl']


def enriquecer_tanque(t, clave_bls='BLS_60', clave_api='API'):
    """
    Agrega al dict del tanque: GALONES, KG_GAL, TON_BBL, TONELADAS (las tres últimas pueden ser None).
    Devuelve el mismo dict (mutado) para poder encadenar.
    """
    f = factores_api(t.get(clave_api))
    t['GALONES'] = bls_a_galones(t.get(clave_bls))
    t['KG_GAL'] = f['kg_gal'] if f else None
    t['TON_BBL'] = f['ton_bbl'] if f else None
    t['TONELADAS'] = bls_a_toneladas(t.get(clave_bls), t.get(clave_api))
    return t


def totales_conversion(lista_tanques, clave_bls='BLS_60', clave_api='API'):
    """Suma de galones y toneladas de una lista de tanques (tanques sin API válido no aportan toneladas)."""
    total_gal = 0.0
    total_ton = 0.0
    sin_api = 0
    for t in lista_tanques or []:
        total_gal += bls_a_galones(t.get(clave_bls))
        ton = bls_a_toneladas(t.get(clave_bls), t.get(clave_api))
        if ton is None:
            if (_num(t.get(clave_bls)) or 0) > 0:
                sin_api += 1
        else:
            total_ton += ton
    return {'total_gal': total_gal, 'total_ton': total_ton, 'tanques_sin_api': sin_api}
