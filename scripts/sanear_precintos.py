#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Saneamiento del inventario de precintos: retira los huecos del consecutivo
--------------------------------------------------------------------------
PROBLEMA:
    Quedaron números marcados DISPONIBLE por debajo del consecutivo real. Son
    sellos que ya se gastaron físicamente, pero como el inventario los cree
    libres, `_tomar_precintos_disponibles` (app.py) los entrega primero: son
    los números más bajos, y la cola se ordena por número ascendente.

    En producción, al 2026-09-22, eran 19 números repartidos en 5 tramos entre
    004463 y 004698, con la marca de agua en 004708. El siguiente precinto que
    el sistema iba a entregar era 004463, usado el 2026-09-09.

QUÉ HACE:
    Pasa esos huecos a ANULADO con usuario_anulacion = 'Ajuste de inventario',
    que es el marcador que app.py ya usa para separar "sacado de circulación"
    de "sello roto" en el resumen (PRECINTOS_USUARIO_AJUSTE, app.py:1565). No
    los borra: quedan en la tabla con su motivo y su fecha, y se pueden
    reactivar desde la página si alguno sí estaba en bodega.

    No toca USADO ni ANULADO, ni nada por encima del corte.

SEGURIDAD:
    - Simula por defecto. Solo escribe con --apply.
    - Antes de escribir guarda un CSV con el estado previo de cada fila tocada.
    - Se planta si el corte parece envenenado: un solo número mal digitado muy
      por encima del bloque principal (p.ej. '0005000' leído como 005000)
      dispararía la marca de agua y el saneamiento se llevaría el stock bueno.
      Eso pasó en pruebas, por eso existe la comprobación.
    - No importa app.py: importarlo dispara db.create_all() contra la base a la
      que apunte DATABASE_URL.

USO (PowerShell):
    # 1. simular contra producción y leer el plan
    python scripts/sanear_precintos.py --database-url "postgresql://..."

    # 2. si el plan está bien, aplicarlo
    python scripts/sanear_precintos.py --database-url "postgresql://..." --apply

    # con un corte manual, cuando el consecutivo físico va más adelante
    python scripts/sanear_precintos.py --corte 4708 --apply

    # la bodega de Madrid (cada sede tiene su propio consecutivo)
    python scripts/sanear_precintos.py --sede MADRID

SEDES:
    Desde que existe Madrid, cada sede lleva su propia marca de agua. Todo se
    calcula y se aplica dentro de la sede de --sede (CARTAGENA por defecto).
    Con una marca global, los sellos que Madrid tiene en bodega por debajo del
    consecutivo de Cartagena se verían como huecos y se retirarían.

Ver primero scripts/diagnostico_precintos.py, que mide sin tocar nada.
"""

import sys
import os
import re
import csv
import bisect
import argparse
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, BASE_DIR)

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    sys.exit("Falta psycopg2. Instalalo con: pip install psycopg2-binary")

URL_POR_DEFECTO = 'postgresql://postgres:Sara_121128@localhost:5432/inventario_dev'

# Mismo marcador que usa el resumen de app.py para no contarlos como merma.
USUARIO_AJUSTE = 'Ajuste de inventario'
MOTIVO_DEFECTO = 'Retirado por ajuste: numero anterior al consecutivo vigente'
SEDES = ('CARTAGENA', 'MADRID')

# Igual que en el diagnostico: un ocupado aislado muy arriba es un dedazo.
VENTANA_DENSIDAD = 100
MINIMO_DENSIDAD = 3


def enmascarar_url_bd(uri):
    return re.sub(r':([^:@]+)@', ':****@', uri) if uri else 'N/A'


def miles(n):
    return '{:,}'.format(n).replace(',', '.')


def codigo(n):
    return str(n).zfill(6)


def agrupar_en_rangos(numeros):
    if not numeros:
        return []
    numeros = sorted(numeros)
    rangos, inicio, anterior = [], numeros[0], numeros[0]
    for n in numeros[1:]:
        if n == anterior + 1:
            anterior = n
            continue
        rangos.append((inicio, anterior))
        inicio = anterior = n
    rangos.append((inicio, anterior))
    return rangos


def calcular_marca_agua(ocupados):
    """(marca, atipicos) — ver scripts/diagnostico_precintos.py."""
    if not ocupados:
        return None, []
    ocupados = sorted(ocupados)
    for i in range(len(ocupados) - 1, -1, -1):
        actual = ocupados[i]
        desde = bisect.bisect_left(ocupados, actual - VENTANA_DENSIDAD)
        if i - desde + 1 >= MINIMO_DENSIDAD:
            return actual, ocupados[i + 1:]
    return ocupados[-1], []


def main():
    ap = argparse.ArgumentParser(
        description='Retira del stock los precintos anteriores al consecutivo vigente.')
    ap.add_argument('--database-url', default=None,
                    help='URL de la base. Por defecto $DATABASE_URL o la local de desarrollo.')
    ap.add_argument('--apply', action='store_true',
                    help='Aplica los cambios. Sin esto solo simula.')
    ap.add_argument('--corte', type=int, default=None,
                    help='Numero de corte manual. Se retira todo DISPONIBLE menor a este. '
                         'Por defecto se usa la marca de agua calculada.')
    ap.add_argument('--motivo', default=MOTIVO_DEFECTO, help='Motivo que queda registrado.')
    ap.add_argument('--forzar', action='store_true',
                    help='Ignora la comprobacion de corte envenenado. Usar solo si ya lo revisaste.')
    ap.add_argument('--sede', default='CARTAGENA', type=str.upper, choices=SEDES,
                    help='Bodega a sanear. Cada sede tiene su propio consecutivo.')
    args = ap.parse_args()

    url = args.database_url or os.environ.get('DATABASE_URL') or URL_POR_DEFECTO

    print('=' * 78)
    print('SANEAMIENTO DE PRECINTOS  -  {}'.format(
        'APLICANDO CAMBIOS' if args.apply else 'SIMULACION (no escribe nada)'))
    print('=' * 78)
    print('  Base de datos: {}'.format(enmascarar_url_bd(url)))
    print('  Sede.........: {}'.format(args.sede))
    print('  Fecha........: {}'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

    conexion = psycopg2.connect(url)
    conexion.autocommit = False
    cur = conexion.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'inventario_precintos' AND column_name = 'sede'
        """)
        if cur.fetchone():
            filtro_sede, params_sede = ' AND sede = %s', (args.sede,)
        elif args.sede == 'CARTAGENA':
            # Base anterior a Madrid: todo el inventario es de Cartagena.
            filtro_sede, params_sede = '', ()
        else:
            sys.exit('\nEsta base no tiene la columna sede: no hay bodega de {}.'.format(args.sede))

        cur.execute("""
            SELECT numero FROM inventario_precintos
            WHERE estado IN ('USADO', 'ANULADO')""" + filtro_sede + """ ORDER BY numero
        """, params_sede)
        ocupados = [f['numero'] for f in cur.fetchall()]
        if not ocupados:
            sys.exit('\nNo hay precintos USADO ni ANULADO. Nada que sanear.')

        marca, atipicos = calcular_marca_agua(ocupados)
        corte = args.corte if args.corte is not None else marca

        print('\n  Marca de agua calculada .... {}'.format(codigo(marca)))
        print('  Maximo bruto ocupado ....... {}'.format(codigo(max(ocupados))))
        print('  Corte que se aplicara ...... {}{}'.format(
            codigo(corte), '  (manual)' if args.corte is not None else ''))

        if atipicos:
            print('\n  AVISO: {} numero(s) marcados USADO/ANULADO quedan aislados muy'.format(
                len(atipicos)))
            print('  por encima del bloque principal. Casi siempre son dedazos:')
            print('    {}'.format(', '.join(codigo(n) for n in atipicos[:15])))
            if args.corte is None and not args.forzar:
                print('\n  Se usa la marca por densidad ({}), no el maximo bruto ({}),'.format(
                    codigo(marca), codigo(max(ocupados))))
                print('  justo para que un dedazo no se lleve por delante el stock bueno.')

        cur.execute("""
            SELECT id, numero, codigo, estado, lote_id, origen, programacion_id,
                   placa, numero_guia, cliente, fecha_uso, usuario_uso
            FROM inventario_precintos
            WHERE estado = 'DISPONIBLE' AND numero < %s""" + filtro_sede + """
            ORDER BY numero
        """, (corte,) + params_sede)
        huecos = cur.fetchall()

        cur.execute("SELECT COUNT(*) AS n FROM inventario_precintos WHERE estado = 'DISPONIBLE'"
                    + filtro_sede, params_sede)
        total_disponible = cur.fetchone()['n']

        if not huecos:
            print('\n  No hay nada que sanear: ningun DISPONIBLE por debajo de {}.'.format(
                codigo(corte)))
            conexion.rollback()
            return

        rangos = agrupar_en_rangos([h['numero'] for h in huecos])
        print('\n  A RETIRAR: {} precinto(s) en {} tramo(s)'.format(
            miles(len(huecos)), len(rangos)))
        for a, b in rangos[:40]:
            print('    {}{}  ({} numero{})'.format(
                codigo(a), '' if a == b else ' - ' + codigo(b),
                b - a + 1, '' if a == b else 's'))
        if len(rangos) > 40:
            print('    ... y {} tramo(s) mas.'.format(len(rangos) - 40))

        quedan = total_disponible - len(huecos)
        print('\n  DISPONIBLE ahora ........... {}'.format(miles(total_disponible)))
        print('  Se retiran ................. {}'.format(miles(len(huecos))))
        print('  Stock real que queda ....... {}'.format(miles(quedan)))

        # El desastre a evitar: un corte envenenado que se lleve casi todo.
        if quedan == 0 or (total_disponible and len(huecos) / total_disponible > 0.5):
            print('\n  ' + '!' * 70)
            print('  ALTO: el saneamiento se llevaria mas de la mitad del stock.')
            print('  Eso casi siempre significa que el corte esta mal (un numero')
            print('  mal digitado disparo la marca de agua), no que el stock este malo.')
            print('  Revisa con scripts/diagnostico_precintos.py y, si de verdad es')
            print('  correcto, vuelve a correr con --forzar.')
            print('  ' + '!' * 70)
            if not args.forzar:
                conexion.rollback()
                sys.exit(1)

        if not args.apply:
            print('\n  SIMULACION: no se escribio nada.')
            print('  Para aplicarlo, repite el comando agregando --apply')
            conexion.rollback()
            return

        respaldo = os.path.join(
            BASE_DIR, 'backups',
            'saneamiento_precintos_{}.csv'.format(datetime.now().strftime('%Y%m%d_%H%M%S')))
        os.makedirs(os.path.dirname(respaldo), exist_ok=True)
        with open(respaldo, 'w', newline='', encoding='utf-8-sig') as fh:
            w = csv.DictWriter(fh, fieldnames=list(huecos[0].keys()))
            w.writeheader()
            for h in huecos:
                w.writerow(dict(h))
        print('\n  Respaldo del estado previo: {}'.format(respaldo))

        cur.execute("""
            UPDATE inventario_precintos
            SET estado = 'ANULADO',
                motivo_anulacion = %s,
                fecha_anulacion = NOW(),
                usuario_anulacion = %s
            WHERE id = ANY(%s)
        """, (args.motivo, USUARIO_AJUSTE, [h['id'] for h in huecos]))
        tocados = cur.rowcount
        conexion.commit()

        print('  {} precinto(s) retirados del stock.'.format(miles(tocados)))

        cur.execute("""
            SELECT codigo FROM inventario_precintos
            WHERE estado = 'DISPONIBLE' AND numero > %s""" + filtro_sede + """
            ORDER BY numero ASC LIMIT 1
        """, (corte,) + params_sede)
        siguiente = cur.fetchone()
        print('  El siguiente precinto a entregar es ahora: {}'.format(
            siguiente['codigo'] if siguiente else '(sin stock)'))

    except Exception as e:
        conexion.rollback()
        raise SystemExit('\nSe revirtio todo por un error: {}'.format(e))
    finally:
        conexion.close()

    print()


if __name__ == '__main__':
    main()
