#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Reporte de números de guía (SOLO LECTURA)
-----------------------------------------
Muestra, por sede:

    1. GUÍAS REPETIDAS: el mismo número en más de un cargue. Se distingue si
       son copias del mismo despacho (las une scripts/depurar_guias_duplicadas.py)
       o despachos distintos con el mismo número (hay que corregirlos a mano con
       la guía física).

    2. DESPACHADOS SIN NÚMERO DE GUÍA: cargues DESPACHADOS (o con fecha de
       despacho) cuya guía está vacía o tiene solo la serie ('3034',
       '303400000'...). A esos hay que escribirles el número.

No modifica nada: abre la conexión en modo de solo lectura.

USO (consola de Render o local):
    python scripts/reporte_guias.py                         # Cartagena
    python scripts/reporte_guias.py --sede MADRID
    python scripts/reporte_guias.py --sede TODAS
    python scripts/reporte_guias.py --desde 2026-01-01      # solo despachos desde esa fecha
    python scripts/reporte_guias.py --csv reporte.csv       # además guarda las listas en CSV
"""

import sys
import os
import re
import csv
import argparse
from collections import defaultdict
from datetime import datetime, date

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    sys.exit("Falta psycopg2. Instalalo con: pip install psycopg2-binary")

URL_POR_DEFECTO = 'postgresql://postgres:Sara_121128@localhost:5432/inventario_dev'
GUIA_SOLO_SERIE = {'3034', '3037', '303400000', '303700000'}
CLAVE_DESPACHO = ('fecha_programacion', 'placa', 'producto_a_cargar', 'galones')


def enmascarar_url_bd(uri):
    return re.sub(r':([^:@]+)@', ':****@', uri) if uri else 'N/A'


def normalizar_guia(valor):
    return re.sub(r'\s+', '', str(valor or '')).upper()


def normalizar_texto(valor):
    return re.sub(r'\s+', ' ', str(valor or '')).strip().upper()


def vacio(valor):
    return valor is None or (isinstance(valor, str) and valor.strip() == '')


def mismo_despacho(a, b):
    for campo in CLAVE_DESPACHO:
        va, vb = a.get(campo), b.get(campo)
        if vacio(va) or vacio(vb):
            continue
        if campo == 'galones':
            if abs(float(va) - float(vb)) > 0.5:
                return False
        elif normalizar_texto(va) != normalizar_texto(vb):
            return False
    return True


def fmt_fila(f):
    gal = '{:,.0f}'.format(f['galones']) if f.get('galones') is not None else '-'
    return 'id {:>5}  {}  despacho {}  placa {:<7} {:>8} gal  {:<11} {}'.format(
        f['id'], f['fecha_programacion'] or 'sin fecha', f['fecha_despacho'] or '-',
        f['placa'] or '-', gal, (f['estado'] or '')[:11], (f['cliente'] or '')[:34])


def main():
    ap = argparse.ArgumentParser(description='Reporte de guías repetidas y despachos sin guía (solo lectura).')
    ap.add_argument('--database-url', default=None,
                    help='URL de la base. Por defecto $DATABASE_URL o la local de desarrollo.')
    ap.add_argument('--sede', default='CARTAGENA', type=str.upper, choices=('CARTAGENA', 'MADRID', 'TODAS'))
    ap.add_argument('--desde', default=None, help='Solo cargues con fecha de programación desde AAAA-MM-DD.')
    ap.add_argument('--csv', default=None, help='Guarda las dos listas en este archivo CSV.')
    args = ap.parse_args()

    url = args.database_url or os.environ.get('DATABASE_URL') or URL_POR_DEFECTO
    desde = date.fromisoformat(args.desde) if args.desde else None

    print('=' * 90)
    print('REPORTE DE GUIAS  -  SOLO LECTURA, NO MODIFICA NADA')
    print('=' * 90)
    print('  Base de datos: {}'.format(enmascarar_url_bd(url)))
    print('  Sede.........: {}{}'.format(args.sede, '  · desde {}'.format(desde) if desde else ''))
    print('  Fecha........: {}'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

    conexion = psycopg2.connect(url)
    conexion.set_session(readonly=True, autocommit=False)
    cur = conexion.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""SELECT 1 FROM information_schema.columns
                       WHERE table_name = 'programacion_cargue' AND column_name = 'sede'""")
        tiene_sede = cur.fetchone() is not None
        cur.execute("""
            SELECT id, {sede} AS sede, numero_guia, tipo_guia, fecha_programacion, fecha_despacho,
                   placa, cliente, producto_a_cargar, galones, estado
            FROM programacion_cargue ORDER BY fecha_programacion, id
        """.format(sede='sede' if tiene_sede else "'CARTAGENA'"))
        filas = cur.fetchall()
    finally:
        conexion.rollback()
        conexion.close()

    if args.sede != 'TODAS':
        filas = [f for f in filas if (f['sede'] or 'CARTAGENA') == args.sede]
    if desde:
        filas = [f for f in filas if f['fecha_programacion'] and f['fecha_programacion'] >= desde]

    # 1. Guías repetidas
    por_guia = defaultdict(list)
    for f in filas:
        g = normalizar_guia(f['numero_guia'])
        if g and g not in GUIA_SOLO_SERIE:
            por_guia[g].append(f)
    repetidas = {g: v for g, v in por_guia.items() if len(v) > 1}
    solo_copias, conflictos = [], []
    for g, v in sorted(repetidas.items()):
        despachos = []
        for f in v:
            for d in despachos:
                if all(mismo_despacho(f, o) for o in d):
                    d.append(f)
                    break
            else:
                despachos.append([f])
        (conflictos if len(despachos) > 1 else solo_copias).append((g, despachos))

    # 2. Despachados sin guía (vacía o solo la serie)
    def despachado(f):
        return (f['estado'] or '').strip().upper() == 'DESPACHADO' or f['fecha_despacho'] is not None
    sin_guia_filas = [f for f in filas if despachado(f) and
                      (vacio(f['numero_guia']) or normalizar_guia(f['numero_guia']) in GUIA_SOLO_SERIE)]
    # Una línea por despacho: las filas duplicadas (misma fecha, placa, producto,
    # galones y cliente) se muestran juntas para no pedir la misma guía dos veces.
    grupos_sin_guia = []
    for f in sin_guia_filas:
        for g in grupos_sin_guia:
            o = g[0]
            if mismo_despacho(f, o) and normalizar_texto(f['cliente']) == normalizar_texto(o['cliente']):
                g.append(f)
                break
        else:
            grupos_sin_guia.append([f])
    sin_guia = [g[0] for g in grupos_sin_guia]
    copias_sin_guia = {g[0]['id']: [x['id'] for x in g[1:]] for g in grupos_sin_guia}

    print('\n  Cargues revisados .......................... {:,}'.format(len(filas)))
    print('  Guías repetidas ............................ {:,}'.format(len(repetidas)))
    print('     copias del mismo despacho (se unen solas)  {:,}'.format(len(solo_copias)))
    print('     MISMA GUÍA EN DESPACHOS DISTINTOS ........ {:,}  <- corregir a mano'.format(len(conflictos)))
    print('  DESPACHADOS SIN NÚMERO DE GUÍA ............. {:,}  <- escribirles el número'.format(len(sin_guia)))
    if len(sin_guia_filas) > len(sin_guia):
        print('     (son {:,} filas: {:,} son copias repetidas del mismo despacho)'.format(
            len(sin_guia_filas), len(sin_guia_filas) - len(sin_guia)))

    if conflictos:
        print('\n' + '-' * 90)
        print('  MISMA GUÍA EN DESPACHOS DISTINTOS (buscar la guía física y corregir el número del que no es)')
        print('-' * 90)
        for g, despachos in conflictos:
            print('  {}'.format(g))
            for d in despachos:
                print('      {}{}'.format(fmt_fila(d[0]), '  (+{} copia)'.format(len(d) - 1) if len(d) > 1 else ''))

    if sin_guia:
        print('\n' + '-' * 90)
        print('  DESPACHADOS SIN NÚMERO DE GUÍA')
        print('-' * 90)
        por_mes = defaultdict(list)
        for f in sin_guia:
            mes = f['fecha_programacion'].strftime('%Y-%m') if f['fecha_programacion'] else 'sin fecha'
            por_mes[mes].append(f)
        for mes in sorted(por_mes):
            print('  {}  ({} despacho(s))'.format(mes, len(por_mes[mes])))
            for f in por_mes[mes]:
                actual = normalizar_guia(f['numero_guia'])
                copias = copias_sin_guia.get(f['id']) or []
                print('      {}{}{}'.format(fmt_fila(f), '  guía: "{}"'.format(actual) if actual else '',
                                            '  (copias: id {})'.format(', '.join(map(str, copias))) if copias else ''))

    if solo_copias:
        print('\n  Además hay {:,} guías con copias del mismo despacho: las une '
              'scripts/depurar_guias_duplicadas.py --apply.'.format(len(solo_copias)))

    if args.csv:
        with open(args.csv, 'w', newline='', encoding='utf-8-sig') as fh:
            w = csv.writer(fh)
            w.writerow(['problema', 'numero_guia', 'id', 'sede', 'fecha_programacion', 'fecha_despacho',
                        'placa', 'cliente', 'producto', 'galones', 'estado'])
            for g, despachos in conflictos:
                for d in despachos:
                    for f in d:
                        w.writerow(['MISMA GUIA EN DESPACHOS DISTINTOS', g, f['id'], f['sede'], f['fecha_programacion'],
                                    f['fecha_despacho'], f['placa'], f['cliente'], f['producto_a_cargar'],
                                    f['galones'], f['estado']])
            for f in sin_guia_filas:
                w.writerow(['DESPACHADO SIN GUIA', normalizar_guia(f['numero_guia']), f['id'], f['sede'],
                            f['fecha_programacion'], f['fecha_despacho'], f['placa'], f['cliente'],
                            f['producto_a_cargar'], f['galones'], f['estado']])
        print('\n  CSV guardado en: {}'.format(os.path.abspath(args.csv)))
    print()


if __name__ == '__main__':
    main()
