#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Depura los números de guía repetidos en programacion_cargue
-----------------------------------------------------------
PROBLEMA:
    Un número de guía es un documento único, pero en programacion_cargue hay
    guías que aparecen en varias filas. Son de tres clases:

    1. COPIAS: la misma guía en filas que son el mismo despacho (misma sede,
       fecha, placa, producto y galones). Filas duplicadas por cargas repetidas.
       -> Se dejan en una sola fila. Antes de borrar las copias, lo que una copia
          tenga y la que se queda no (factura, factura SICOM, imagen de la guía,
          precintos...) se pasa a la que se queda, y los precintos del
          inventario, los pedidos y los ítems de facturación que apuntaban a una
          copia pasan a apuntar a la que se queda.

    2. CONFLICTOS: la misma guía en despachos DISTINTOS (otra placa, otra fecha).
       Alguien digitó mal un número. -> NO se tocan: se listan para corregirlos a
       mano con la guía física. (Las copias dentro de cada despacho sí se unen.)

    3. INCOMPLETAS: solo la serie ('3034', '303400000'...), sin el número.
       -> NO se tocan: se listan para completarlas.

    La comparación es por el número completo sin espacios y en mayúscula. El
    sufijo NO se descarta: 303400000456-0 y 303400000456-6 son guías distintas.

    Si al final no queda ninguna guía repetida, crea un índice único en la base
    para que no puedan volver a entrar (la app ya lo impide, el índice cierra
    también el caso de dos personas guardando al mismo tiempo).

SEGURIDAD:
    - Simula por defecto. Solo escribe con --apply.
    - Antes de escribir guarda un CSV con las filas completas que se borran.
    - Todo en una transacción: si algo falla no queda nada a medias.
    - No importa app.py: importarlo dispara db.create_all() contra la base a la
      que apunte DATABASE_URL.

USO (consola de Render o local):
    python scripts/depurar_guias_duplicadas.py              # simula y muestra el plan
    python scripts/depurar_guias_duplicadas.py --apply      # lo aplica
    python scripts/depurar_guias_duplicadas.py --detalle    # lista todas las copias, no solo el resumen
"""

import sys
import os
import re
import csv
import argparse
from collections import defaultdict
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    sys.exit("Falta psycopg2. Instalalo con: pip install psycopg2-binary")

URL_POR_DEFECTO = 'postgresql://postgres:Sara_121128@localhost:5432/inventario_dev'

# Igual que GUIA_SOLO_SERIE en app.py.
GUIA_SOLO_SERIE = {'3034', '3037', '303400000', '303700000'}

# Lo que identifica un despacho. El cliente no entra: hay copias del mismo
# despacho con el cliente escrito distinto ('ISM INGENIERIA' / 'INGENIERIAS').
CLAVE_DESPACHO = ('sede', 'fecha_programacion', 'placa', 'producto_a_cargar', 'galones')

# Datos que se rescatan de una copia si a la fila que se queda le faltan.
CAMPOS_A_RESCATAR = (
    'factura', 'factura_sicom', 'fecha_factura', 'mes_facturado', 'codigo_transporte',
    'imagen_guia', 'precintos', 'fecha_despacho', 'placa', 'tanque', 'nombre_conductor',
    'cedula_conductor', 'celular_conductor', 'empresa_transportadora', 'cliente', 'destino',
    'temperatura', 'api_obs', 'api_corregido', 'barriles', 'galones', 'hora_llegada_estimada',
    'refineria_completado_en', 'tipo_guia',
)

NOMBRE_INDICE = 'ux_programacion_cargue_numero_guia'


def enmascarar_url_bd(uri):
    return re.sub(r':([^:@]+)@', ':****@', uri) if uri else 'N/A'


def normalizar_guia(valor):
    return re.sub(r'\s+', '', str(valor or '')).upper()


def normalizar_texto(valor):
    return re.sub(r'\s+', ' ', str(valor or '')).strip().upper()


def vacio(valor):
    return valor is None or (isinstance(valor, str) and valor.strip() == '')


def mismo_despacho(a, b):
    """Iguales en la clave; un dato vacío en una de las dos no las separa."""
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


def agrupar_despachos(filas):
    """Separa las filas de una misma guía en despachos (grupos de copias)."""
    despachos = []
    for f in filas:
        for d in despachos:
            if all(mismo_despacho(f, otra) for otra in d):
                d.append(f)
                break
        else:
            despachos.append([f])
    return despachos


def tabla_existe(cur, tabla):
    cur.execute("SELECT to_regclass(%s) IS NOT NULL AS existe", (tabla,))
    return cur.fetchone()['existe']


def main():
    ap = argparse.ArgumentParser(description='Une las filas con número de guía repetido.')
    ap.add_argument('--database-url', default=None,
                    help='URL de la base. Por defecto $DATABASE_URL o la local de desarrollo.')
    ap.add_argument('--apply', action='store_true', help='Aplica los cambios. Sin esto solo simula.')
    ap.add_argument('--detalle', action='store_true', help='Lista cada guía con copias.')
    args = ap.parse_args()

    url = args.database_url or os.environ.get('DATABASE_URL') or URL_POR_DEFECTO

    print('=' * 78)
    print('DEPURAR NUMEROS DE GUIA REPETIDOS  -  {}'.format(
        'APLICANDO CAMBIOS' if args.apply else 'SIMULACION (no escribe nada)'))
    print('=' * 78)
    print('  Base de datos: {}'.format(enmascarar_url_bd(url)))
    print('  Fecha........: {}'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

    conexion = psycopg2.connect(url)
    conexion.autocommit = False
    cur = conexion.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute("""SELECT column_name FROM information_schema.columns
                       WHERE table_name = 'programacion_cargue'""")
        columnas = {r['column_name'] for r in cur.fetchall()}
        tiene_sede = 'sede' in columnas
        rescatables = [c for c in CAMPOS_A_RESCATAR if c in columnas]

        cur.execute("""
            SELECT * FROM programacion_cargue
            WHERE numero_guia IS NOT NULL AND TRIM(numero_guia) <> ''
            ORDER BY id
            FOR UPDATE
        """)
        filas = cur.fetchall()
        if not tiene_sede:
            for f in filas:
                f['sede'] = 'CARTAGENA'

        # Enlaces: cuántos precintos y pedidos cuelgan de cada fila.
        precintos_por_fila = {}
        if tabla_existe(cur, 'inventario_precintos'):
            cur.execute("""SELECT programacion_id AS id, COUNT(*) AS n FROM inventario_precintos
                           WHERE programacion_id IS NOT NULL GROUP BY programacion_id""")
            precintos_por_fila = {r['id']: r['n'] for r in cur.fetchall()}
        pedidos_por_fila = {}
        if tabla_existe(cur, 'programacion_base'):
            cur.execute("""SELECT programacion_cargue_id AS id, COUNT(*) AS n FROM programacion_base
                           WHERE programacion_cargue_id IS NOT NULL GROUP BY programacion_cargue_id""")
            pedidos_por_fila = {r['id']: r['n'] for r in cur.fetchall()}

        por_guia = defaultdict(list)
        for f in filas:
            por_guia[normalizar_guia(f['numero_guia'])].append(f)
        repetidas = {g: v for g, v in por_guia.items() if len(v) > 1}

        def puntaje(f):
            """La fila que se queda: la más enlazada, luego la más completa, luego la última editada."""
            enlaces = precintos_por_fila.get(f['id'], 0) + 10 * pedidos_por_fila.get(f['id'], 0)
            completos = sum(1 for c in rescatables if not vacio(f.get(c)))
            editada = f.get('fecha_actualizacion') or datetime.min
            return (enlaces, completos, editada, -f['id'])

        plan = []            # (guia, se_queda, [copias], {campo: valor rescatado}, diferencias)
        conflictos = []      # (guia, [despachos])
        incompletas = []     # (guia, [despachos])
        for guia, filas_guia in sorted(repetidas.items()):
            despachos = agrupar_despachos(filas_guia)
            for d in despachos:
                if len(d) < 2:
                    continue
                d = sorted(d, key=puntaje, reverse=True)
                queda, copias = d[0], d[1:]
                rescate, diferencias = {}, {}
                for c in rescatables:
                    if vacio(queda.get(c)):
                        valor = next((x[c] for x in copias if not vacio(x.get(c))), None)
                        if valor is not None:
                            rescate[c] = valor
                    else:
                        otros = {normalizar_texto(x[c]) for x in copias if not vacio(x.get(c))}
                        otros.discard(normalizar_texto(queda[c]))
                        if otros and c != 'imagen_guia':
                            diferencias[c] = (queda[c], sorted(otros))
                plan.append((guia, queda, copias, rescate, diferencias))
            if guia in GUIA_SOLO_SERIE:
                incompletas.append((guia, despachos))
            elif len(despachos) > 1:
                conflictos.append((guia, despachos))

        filas_a_borrar = [c for (_, _, copias, _, _) in plan for c in copias]
        print('\n  Filas con número de guía ........... {:,}'.format(len(filas)))
        print('  Números de guía repetidos .......... {:,}'.format(len(repetidas)))
        print('  Copias del mismo despacho a unir ... {:,} filas se borran, {:,} se quedan'.format(
            len(filas_a_borrar), len(plan)))
        print('  Guías en despachos DISTINTOS ....... {:,}  (corregir a mano)'.format(len(conflictos)))
        print('  Guías incompletas (solo la serie) .. {:,}  (completar a mano)'.format(
            sum(len(d) for _, d in incompletas)))

        con_rescate = [p for p in plan if p[3]]
        con_diferencias = [p for p in plan if p[4]]
        print('\n  Uniones que rescatan datos de una copia: {:,}'.format(len(con_rescate)))
        print('  Uniones donde las copias tenían datos distintos (queda el de la fila elegida): {:,}'.format(
            len(con_diferencias)))
        for guia, queda, copias, _, dif in con_diferencias[:15]:
            print('    {}  se queda id {}:'.format(guia, queda['id']))
            for c, (valor, otros) in dif.items():
                print('        {}: "{}"  (copias: {})'.format(c, valor, ' | '.join(otros)))
        if len(con_diferencias) > 15:
            print('    ... y {} más (en el CSV de respaldo quedan todas las copias).'.format(len(con_diferencias) - 15))

        if args.detalle:
            print('\n  DETALLE DE UNIONES')
            for guia, queda, copias, rescate, _ in plan:
                print('    {}  queda id {}  borra {}{}'.format(
                    guia, queda['id'], ', '.join(str(c['id']) for c in copias),
                    ('  rescata ' + ', '.join(rescate)) if rescate else ''))

        def mostrar(titulo, grupos):
            if not grupos:
                return
            print('\n  ' + titulo)
            for guia, despachos in grupos:
                print('    {}'.format(guia))
                for d in despachos:
                    f = d[0]
                    print('        id {:>5}  {}  {}  placa {:<7}  {:>10} gal  {}{}'.format(
                        f['id'], f.get('sede') or '', f['fecha_programacion'] or '', f['placa'] or '-',
                        '{:,.0f}'.format(f['galones']) if f['galones'] is not None else '-',
                        (f['cliente'] or '')[:30], '  (+{} copia(s))'.format(len(d) - 1) if len(d) > 1 else ''))

        mostrar('GUIAS USADAS EN DESPACHOS DISTINTOS (buscar la guía física y corregir el número):', conflictos)
        mostrar('GUIAS INCOMPLETAS (escribir el número completo):', incompletas)

        if not args.apply:
            print('\n  SIMULACION: no se escribio nada.')
            print('  Para aplicarlo, repite el comando agregando --apply')
            conexion.rollback()
            return

        if filas_a_borrar:
            respaldo = os.path.join(
                BASE_DIR, 'backups',
                'depurar_guias_duplicadas_{}.csv'.format(datetime.now().strftime('%Y%m%d_%H%M%S')))
            os.makedirs(os.path.dirname(respaldo), exist_ok=True)
            destino_de = {c['id']: queda['id'] for (_, queda, copias, _, _) in plan for c in copias}
            with open(respaldo, 'w', newline='', encoding='utf-8-sig') as fh:
                campos = ['unida_en_id'] + list(filas_a_borrar[0].keys())
                w = csv.DictWriter(fh, fieldnames=campos)
                w.writeheader()
                for f in filas_a_borrar:
                    fila = dict(f)
                    fila['unida_en_id'] = destino_de[f['id']]
                    w.writerow(fila)
            print('\n  Respaldo de las filas borradas: {}'.format(respaldo))

            hay_items_fact = tabla_existe(cur, 'facturacion_import_items')
            hay_locks = tabla_existe(cur, 'programacion_cargue_locks')
            for guia, queda, copias, rescate, _ in plan:
                ids_copias = [c['id'] for c in copias]
                if rescate:
                    sets = ', '.join('{} = %s'.format(c) for c in rescate)
                    cur.execute('UPDATE programacion_cargue SET {} WHERE id = %s'.format(sets),
                                list(rescate.values()) + [queda['id']])
                cur.execute("UPDATE inventario_precintos SET programacion_id = %s WHERE programacion_id = ANY(%s)",
                            (queda['id'], ids_copias))
                cur.execute("""UPDATE programacion_base SET programacion_cargue_id = %s
                               WHERE programacion_cargue_id = ANY(%s)""", (queda['id'], ids_copias))
                if hay_items_fact:
                    cur.execute("""UPDATE facturacion_import_items SET programacion_id = %s
                                   WHERE programacion_id = ANY(%s)""", (queda['id'], ids_copias))
                if hay_locks:
                    cur.execute("DELETE FROM programacion_cargue_locks WHERE registro_id = ANY(%s)", (ids_copias,))
                cur.execute("DELETE FROM programacion_cargue WHERE id = ANY(%s)", (ids_copias,))
            print('  {:,} copias unidas en {:,} filas.'.format(len(filas_a_borrar), len(plan)))

        # ¿Quedó alguna guía repetida? Si no, índice único.
        cur.execute("""
            SELECT UPPER(REPLACE(TRIM(numero_guia), ' ', '')) AS g, COUNT(*) AS n
            FROM programacion_cargue
            WHERE numero_guia IS NOT NULL AND TRIM(numero_guia) <> ''
            GROUP BY 1 HAVING COUNT(*) > 1
        """)
        quedan = cur.fetchall()
        if quedan:
            print('\n  Quedan {} número(s) de guía repetidos (conflictos e incompletas).'.format(len(quedan)))
            print('  Cuando los corrijas, vuelve a correr el script con --apply y creará el índice único.')
        else:
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS {} ON programacion_cargue
                (UPPER(REPLACE(TRIM(numero_guia), ' ', '')))
                WHERE numero_guia IS NOT NULL AND TRIM(numero_guia) <> ''
            """.format(NOMBRE_INDICE))
            print('\n  No quedan guías repetidas: índice único {} creado.'.format(NOMBRE_INDICE))

        conexion.commit()

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
