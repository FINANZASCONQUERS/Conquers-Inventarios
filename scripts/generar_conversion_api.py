# -*- coding: utf-8 -*-
"""
Genera los archivos de la tabla de conversión por gravedad API a partir del CSV fuente.

Fuente:   static/data/conversion_api.csv   (Grados API;Kg/Gal;Ton/Barril;Barriles/Ton — separador ';' y decimales ',')
Salidas:  static/data/conversion_api.json  (lo lee conversion_api.py en el backend)
          static/js/conversion_api.js      (lo usan las planillas y reportes de barcazas en el navegador)

Uso:  python scripts/generar_conversion_api.py [ruta_csv]
"""
import csv
import io
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_DEFAULT = os.path.join(RAIZ, 'static', 'data', 'conversion_api.csv')
JSON_OUT = os.path.join(RAIZ, 'static', 'data', 'conversion_api.json')
JS_OUT = os.path.join(RAIZ, 'static', 'js', 'conversion_api.js')


def _num(txt):
    return float(str(txt).strip().replace(',', '.'))


def leer_csv(ruta):
    filas = []
    with io.open(ruta, 'r', encoding='utf-8-sig', newline='') as f:
        lector = csv.reader(f, delimiter=';')
        encabezado = next(lector)
        for fila in lector:
            if not fila or not str(fila[0]).strip():
                continue
            api, kg_gal, ton_bbl, bbl_ton = (_num(x) for x in fila[:4])
            filas.append([round(api, 1), kg_gal, ton_bbl, bbl_ton])
    filas.sort(key=lambda r: r[0])
    return encabezado, filas


def main():
    ruta = sys.argv[1] if len(sys.argv) > 1 else CSV_DEFAULT
    encabezado, filas = leer_csv(ruta)
    if not filas:
        print('El CSV no tiene filas de datos'); sys.exit(1)

    datos = {
        'fuente': os.path.basename(ruta),
        'columnas': ['api', 'kg_gal', 'ton_bbl', 'bbl_ton'],
        'encabezado_original': encabezado,
        'api_min': filas[0][0],
        'api_max': filas[-1][0],
        'galones_por_barril': 42,
        'filas': filas,
    }
    os.makedirs(os.path.dirname(JSON_OUT), exist_ok=True)
    with io.open(JSON_OUT, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(datos, f, ensure_ascii=False, separators=(',', ':'))

    # JS: mismo contenido, expuesto como window.ConversionAPI
    filas_js = ',\n'.join('  [%s,%s,%s,%s]' % tuple(repr(v) for v in r) for r in filas)
    js = (
        "// Archivo GENERADO por scripts/generar_conversion_api.py a partir de static/data/conversion_api.csv. No editar a mano.\n"
        "// Tabla: [Grados API, Kg/Gal, Ton/Barril, Barriles/Ton]\n"
        "(function (global) {\n"
        "  'use strict';\n"
        "  const TABLA = [\n" + filas_js + "\n  ];\n"
        "  const GAL_POR_BBL = 42;\n"
        "  const API_MIN = TABLA[0][0], API_MAX = TABLA[TABLA.length - 1][0];\n"
        "\n"
        "  function _num(v) {\n"
        "    if (v === null || v === undefined) return NaN;\n"
        "    const n = parseFloat(String(v).trim().replace(',', '.'));\n"
        "    return Number.isFinite(n) ? n : NaN;\n"
        "  }\n"
        "\n"
        "  // Factores para un API dado (interpolación lineal entre filas). null si API vacío, <= 0 o fuera de rango.\n"
        "  function factores(api) {\n"
        "    const a = _num(api);\n"
        "    if (!Number.isFinite(a) || a <= 0 || a < API_MIN || a > API_MAX) return null;\n"
        "    let lo = 0, hi = TABLA.length - 1;\n"
        "    while (lo < hi) {\n"
        "      const mid = (lo + hi) >> 1;\n"
        "      if (TABLA[mid][0] < a) lo = mid + 1; else hi = mid;\n"
        "    }\n"
        "    const f1 = TABLA[lo];\n"
        "    if (f1[0] === a || lo === 0) return { api: a, kg_gal: f1[1], ton_bbl: f1[2], bbl_ton: f1[3] };\n"
        "    const f0 = TABLA[lo - 1];\n"
        "    const t = (a - f0[0]) / (f1[0] - f0[0]);\n"
        "    const ip = (i) => f0[i] + (f1[i] - f0[i]) * t;\n"
        "    return { api: a, kg_gal: ip(1), ton_bbl: ip(2), bbl_ton: ip(3) };\n"
        "  }\n"
        "\n"
        "  function galones(bls) { const b = _num(bls); return Number.isFinite(b) ? b * GAL_POR_BBL : 0; }\n"
        "  function toneladas(bls, api) {\n"
        "    const b = _num(bls); const f = factores(api);\n"
        "    if (!Number.isFinite(b) || !f) return null;\n"
        "    return b * f.ton_bbl;\n"
        "  }\n"
        "  function kilogramos(bls, api) { const t = toneladas(bls, api); return t === null ? null : t * 1000; }\n"
        "\n"
        "  global.ConversionAPI = { TABLA, GAL_POR_BBL, API_MIN, API_MAX, factores, galones, toneladas, kilogramos };\n"
        "})(window);\n"
    )
    os.makedirs(os.path.dirname(JS_OUT), exist_ok=True)
    with io.open(JS_OUT, 'w', encoding='utf-8', newline='\n') as f:
        f.write(js)

    print('Filas: %d | API %s a %s' % (len(filas), filas[0][0], filas[-1][0]))
    print('JSON:', JSON_OUT)
    print('JS:  ', JS_OUT)


if __name__ == '__main__':
    main()
