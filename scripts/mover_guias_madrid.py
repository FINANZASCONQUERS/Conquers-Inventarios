#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Pasa a la sede MADRID los cargues de Madrid que se registraron en Cartagena
---------------------------------------------------------------------------
PROBLEMA:
    Antes de existir la Programación de Cargue Madrid, los despachos de la
    planta de Madrid se digitaban en la programación de Cartagena. Se
    reconocen por la guía física: el talonario de Madrid es 303700000 + folio
    (303700000016-0), el de Cartagena 303400000 + folio.

    Mientras sigan marcados CARTAGENA salen en la tabla, el reporte y la
    facturación de Cartagena, y no cuentan para el consecutivo de guías de
    Madrid.

QUÉ HACE:
    - Busca en programacion_cargue las filas de sede CARTAGENA cuya guía trae
      la serie 30370000 (incluye digitaciones con un cero de más, como
      3030370000010).
    - Las pasa a sede MADRID.
    - Pasa también a MADRID los pedidos (programacion_base) enlazados a ellas.
    - NO toca inventario_precintos: los sellos que haya enlazados se quedan en
      la bodega donde estaban. Moverlos cambiaría la marca de agua de las dos
      bodegas. Se listan para que se revisen.

SEGURIDAD:
    - Simula por defecto. Solo escribe con --apply.
    - Antes de escribir guarda un CSV con las filas que se van a mover.
    - Exige que exista la columna `sede` (la crea la app al arrancar con la
      versión que incluye Madrid: despliega primero, corre esto después).
    - No importa app.py: importarlo dispara db.create_all() contra la base a la
      que apunte DATABASE_URL.

USO (en la consola de Render o en local):
    # 1. simular y leer el plan
    python scripts/mover_guias_madrid.py

    # 2. aplicarlo
    python scripts/mover_guias_madrid.py --apply

    # otra base
    python scripts/mover_guias_madrid.py --database-url "postgresql://..."

    # dejar por fuera alguna fila que no es de Madrid
    python scripts/mover_guias_madrid.py --excluir 611,1430 --apply
"""

import sys
import os
import re
import csv
import argparse
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    sys.exit("Falta psycopg2. Instalalo con: pip install psycopg2-binary")

URL_POR_DEFECTO = 'postgresql://postgres:Sara_121128@localhost:5432/inventario_dev'

# Serie del talonario de Madrid sin el último cero, que a veces sobra o falta.
SERIE_MADRID = '30370000'


def enmascarar_url_bd(uri):
    return re.sub(r':([^:@]+)@', ':****@', uri) if uri else 'N/A'


def es_guia_madrid(numero_guia):
    return SERIE_MADRID in re.sub(r'\D', '', numero_guia or '')


def tiene_columna(cur, tabla, columna):
    cur.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """, (tabla, columna))
    return cur.fetchone() is not None


def main():
    ap = argparse.ArgumentParser(
        description='Pasa a sede MADRID los cargues con guía de la serie 3037.')
    ap.add_argument('--database-url', default=None,
                    help='URL de la base. Por defecto $DATABASE_URL o la local de desarrollo.')
    ap.add_argument('--apply', action='store_true', help='Aplica los cambios. Sin esto solo simula.')
    ap.add_argument('--excluir', default='',
                    help='IDs de programacion_cargue que NO se deben mover, separados por coma.')
    args = ap.parse_args()

    url = args.database_url or os.environ.get('DATABASE_URL') or URL_POR_DEFECTO
    excluir = {int(x) for x in re.findall(r'\d+', args.excluir)}

    print('=' * 78)
    print('MOVER GUIAS DE MADRID A LA SEDE MADRID  -  {}'.format(
        'APLICANDO CAMBIOS' if args.apply else 'SIMULACION (no escribe nada)'))
    print('=' * 78)
    print('  Base de datos: {}'.format(enmascarar_url_bd(url)))
    print('  Fecha........: {}'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

    conexion = psycopg2.connect(url)
    conexion.autocommit = False
    cur = conexion.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        if not tiene_columna(cur, 'programacion_cargue', 'sede'):
            sys.exit('\nLa tabla programacion_cargue no tiene la columna sede. Despliega primero '
                     'la versión de la app con Madrid (la crea al arrancar) y vuelve a correr esto.')

        cur.execute("""
            SELECT id, fecha_programacion, fecha_despacho, numero_guia, tipo_guia,
                   producto_a_cargar, cliente, placa, estado, precintos
            FROM programacion_cargue
            WHERE sede = 'CARTAGENA' AND numero_guia LIKE '%%3037%%'
            ORDER BY fecha_programacion, id
            FOR UPDATE
        """)
        candidatas = [f for f in cur.fetchall() if es_guia_madrid(f['numero_guia'])]
        excluidas = [f for f in candidatas if f['id'] in excluir]
        mover = [f for f in candidatas if f['id'] not in excluir]

        if not mover:
            print('\n  No hay cargues con guía de Madrid marcados como Cartagena. Nada que hacer.')
            conexion.rollback()
            return

        print('\n  CARGUES A PASAR A MADRID: {}'.format(len(mover)))
        print('  {:>6}  {:<10}  {:<16}  {:<8}  {:<11}  {}'.format(
            'ID', 'FECHA', 'GUIA', 'PLACA', 'ESTADO', 'PRODUCTO'))
        for f in mover:
            print('  {:>6}  {:<10}  {:<16}  {:<8}  {:<11}  {}'.format(
                f['id'], str(f['fecha_programacion'] or ''), f['numero_guia'] or '',
                f['placa'] or '', f['estado'] or '', (f['producto_a_cargar'] or '')[:28]))
        if excluidas:
            print('\n  Excluidas por --excluir: {}'.format(', '.join(str(f['id']) for f in excluidas)))

        ids = [f['id'] for f in mover]

        pedidos = []
        if tiene_columna(cur, 'programacion_base', 'sede'):
            cur.execute("""
                SELECT id, programacion_cargue_id, cliente, producto, sede
                FROM programacion_base
                WHERE programacion_cargue_id = ANY(%s) AND sede <> 'MADRID'
            """, (ids,))
            pedidos = cur.fetchall()
        print('\n  Pedidos enlazados que también pasan a Madrid: {}'.format(len(pedidos)))

        cur.execute("""
            SELECT numero, codigo, estado, programacion_id, sede
            FROM inventario_precintos
            WHERE programacion_id = ANY(%s)
            ORDER BY numero
        """, (ids,))
        sellos = cur.fetchall()
        if sellos:
            print('\n  AVISO: {} sello(s) del inventario están enlazados a estos cargues.'.format(len(sellos)))
            print('  Se quedan en su bodega actual (no se mueven):')
            for s in sellos[:20]:
                print('    {}  {}  bodega {}  cargue {}'.format(
                    s['codigo'], s['estado'], s['sede'], s['programacion_id']))
            if len(sellos) > 20:
                print('    ... y {} más.'.format(len(sellos) - 20))
        else:
            print('  Sellos del inventario enlazados: 0 (los precintos escritos en esas filas no'
                  ' son del inventario de Cartagena).')

        if not args.apply:
            print('\n  SIMULACION: no se escribio nada.')
            print('  Para aplicarlo, repite el comando agregando --apply')
            conexion.rollback()
            return

        respaldo = os.path.join(
            BASE_DIR, 'backups',
            'mover_guias_madrid_{}.csv'.format(datetime.now().strftime('%Y%m%d_%H%M%S')))
        os.makedirs(os.path.dirname(respaldo), exist_ok=True)
        with open(respaldo, 'w', newline='', encoding='utf-8-sig') as fh:
            w = csv.DictWriter(fh, fieldnames=['tabla', 'id', 'sede_anterior', 'numero_guia', 'placa', 'fecha'])
            w.writeheader()
            for f in mover:
                w.writerow({'tabla': 'programacion_cargue', 'id': f['id'], 'sede_anterior': 'CARTAGENA',
                            'numero_guia': f['numero_guia'], 'placa': f['placa'],
                            'fecha': f['fecha_programacion']})
            for p in pedidos:
                w.writerow({'tabla': 'programacion_base', 'id': p['id'], 'sede_anterior': p['sede'],
                            'numero_guia': '', 'placa': '', 'fecha': ''})
        print('\n  Respaldo: {}'.format(respaldo))

        cur.execute("UPDATE programacion_cargue SET sede = 'MADRID' WHERE id = ANY(%s)", (ids,))
        movidos = cur.rowcount
        if pedidos:
            cur.execute("UPDATE programacion_base SET sede = 'MADRID' WHERE id = ANY(%s)",
                        ([p['id'] for p in pedidos],))
        conexion.commit()
        print('  {} cargue(s) y {} pedido(s) pasados a MADRID.'.format(movidos, len(pedidos)))
        print('  Para devolverlos, usa los IDs del respaldo con sede CARTAGENA.')

    except SystemExit:
        conexion.rollback()
        raise
    except Exception as e:
        conexion.rollback()
        raise SystemExit('\nSe revirtio todo por un error: {}'.format(e))
    finally:
        conexion.close()

    print()


if __name__ == '__main__':
    main()
