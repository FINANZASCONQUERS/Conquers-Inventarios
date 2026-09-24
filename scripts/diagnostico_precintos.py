#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Diagnóstico del inventario de precintos (SOLO LECTURA)
------------------------------------------------------
PROBLEMA QUE INVESTIGA:
    Al anular un precinto, el sistema no entregó el siguiente del consecutivo
    sino números que ya se habían usado físicamente.

    La causa está en `_tomar_precintos_disponibles` (app.py:22922), que define
    el "siguiente" como MIN(numero) WHERE estado='DISPONIBLE' — no como
    MAX(usado) + 1. Cualquier número viejo que haya quedado marcado DISPONIBLE
    se va al frente de la cola y es lo primero que entrega una anulación
    (app.py:23450) o una asignación (app.py:23355).

    Tres cosas dejan números viejos en DISPONIBLE:
      1. Dar de alta el lote completo cuando el consecutivo ya iba avanzado
         (api_precintos_crear_lote, app.py:23258).
      2. Rangos escritos como texto en la programación ("004365 al 004370"):
         _auto_vincular_precintos_con_programacion (app.py:23049) solo marca
         USADO los números que aparecen literalmente, no los del medio.
      3. Editar a mano la celda de precintos de un cargue: todo sello USADO que
         ya no aparezca en el texto vuelve a DISPONIBLE
         (_sincronizar_precintos_manual, app.py:23005).

QUÉ HACE ESTE SCRIPT:
    Mide el daño. No corrige nada. Abre la transacción en READ ONLY para que
    no pueda escribir ni por accidente, y nunca importa app.py (importarlo
    dispara db.create_all() contra la base a la que apunte DATABASE_URL).

USO (PowerShell):
    # contra la base local de desarrollo (por defecto)
    python scripts/diagnostico_precintos.py

    # contra producción — la forma recomendada, sin dejar la URL en el entorno
    python scripts/diagnostico_precintos.py --database-url "postgresql://usuario:clave@host:5432/basedatos"

    # o tomándola de la variable de entorno, si ya está puesta
    $env:DATABASE_URL = "postgresql://usuario:clave@host:5432/basedatos"
    python scripts/diagnostico_precintos.py

    # sin escribir el CSV de detalle
    python scripts/diagnostico_precintos.py --sin-csv

SALIDA:
    Informe en consola + backups/diagnostico_precintos_<fecha>.csv con el
    detalle de cada número sospechoso, para revisarlo antes de sanear nada.
"""

import sys
import os
import re
import csv
import bisect
import argparse
from datetime import datetime
from collections import defaultdict

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, BASE_DIR)

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    sys.exit("Falta psycopg2. Instalalo con: pip install psycopg2-binary")

URL_POR_DEFECTO = 'postgresql://postgres:Sara_121128@localhost:5432/inventario_dev'

# Mismo filtro que usa _auto_vincular_precintos_con_programacion (app.py:23049).
MIN_DIGITOS_TEXTO = 4

# Los codigos se guardan con 6 digitos (_formatear_codigo_precinto, app.py:1632).
DIGITOS_CODIGO = 6

# "004365 al 004370" / "4365 a 4370" / "004365 hasta 004370".
# Ojo: un listado con guiones ("004365-004366") NO es un rango, es una lista.
RE_RANGO_TEXTO = re.compile(r'(\d{4,})\s*(?:al|hasta|a)\s+(\d{4,})', re.IGNORECASE)

# Un numero suelto marcado USADO muy por encima del bloque principal casi
# siempre es un error de digitacion, no el consecutivo real. Se descarta para
# calcular la marca de agua: si no, un solo dedazo mueve el corte miles de
# numeros y el saneamiento se lleva por delante el stock bueno.
VENTANA_DENSIDAD = 100
MINIMO_DENSIDAD = 3


# ---------------------------------------------------------------- utilidades

def enmascarar_url_bd(uri):
    return re.sub(r':([^:@]+)@', ':****@', uri) if uri else 'N/A'


def titulo(texto):
    print('\n' + '=' * 78)
    print(texto)
    print('=' * 78)


def miles(n):
    return '{:,}'.format(n).replace(',', '.')


def agrupar_en_rangos(numeros):
    """[1,2,3,7,8,20] -> [(1,3),(7,8),(20,20)]"""
    if not numeros:
        return []
    numeros = sorted(numeros)
    rangos = []
    inicio = anterior = numeros[0]
    for n in numeros[1:]:
        if n == anterior + 1:
            anterior = n
            continue
        rangos.append((inicio, anterior))
        inicio = anterior = n
    rangos.append((inicio, anterior))
    return rangos


def fmt_rango(a, b, digitos=6):
    ca, cb = str(a).zfill(digitos), str(b).zfill(digitos)
    cantidad = b - a + 1
    if cantidad == 1:
        return '{} (1 numero)'.format(ca)
    return '{} - {}  ({} numeros)'.format(ca, cb, miles(cantidad))


def numeros_del_texto(texto):
    """Réplica exacta de lo que ve _auto_vincular_precintos_con_programacion."""
    if not texto:
        return []
    return [int(n) for n in re.findall(r'\d+', texto) if len(n) >= MIN_DIGITOS_TEXTO]


def calcular_marca_agua(ocupados):
    """Hasta donde llego el consecutivo, ignorando numeros sueltos muy arriba.

    Devuelve (marca, atipicos). La marca es el mayor numero ocupado que tenga
    al menos MINIMO_DENSIDAD vecinos ocupados dentro de VENTANA_DENSIDAD hacia
    abajo. Todo lo que quede por encima se reporta como atipico en vez de
    aceptarse como consecutivo real.
    """
    if not ocupados:
        return None, []
    ocupados = sorted(ocupados)
    for i in range(len(ocupados) - 1, -1, -1):
        actual = ocupados[i]
        desde = bisect.bisect_left(ocupados, actual - VENTANA_DENSIDAD)
        if i - desde + 1 >= MINIMO_DENSIDAD:
            return actual, ocupados[i + 1:]
    return ocupados[-1], []


# ------------------------------------------------------------------ consultas

def _tiene_columna_sede(cur, tabla):
    cur.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = %s AND column_name = 'sede'
    """, (tabla,))
    return cur.fetchone() is not None


def cargar_datos(cur, sede='CARTAGENA'):
    """Todo se mide dentro de una sede: cada bodega tiene su propio consecutivo."""
    datos = {}

    if _tiene_columna_sede(cur, 'inventario_precintos'):
        f, fp = ' AND sede = %s', (sede,)
    elif sede == 'CARTAGENA':
        # Base anterior a Madrid: todo el inventario es de Cartagena.
        f, fp = '', ()
    else:
        sys.exit('\nEsta base no tiene la columna sede: no hay bodega de {}.'.format(sede))
    fc = ' AND sede = %s' if _tiene_columna_sede(cur, 'programacion_cargue') and fp else ''
    fcp = (sede,) if fc else ()

    cur.execute("""
        SELECT estado, COUNT(*) AS cantidad, MIN(numero) AS minimo, MAX(numero) AS maximo
        FROM inventario_precintos
        WHERE 1 = 1""" + f + """
        GROUP BY estado
        ORDER BY estado
    """, fp)
    datos['por_estado'] = cur.fetchall()

    cur.execute("""
        SELECT id, nombre, rango_inicial, rango_final, total_precintos,
               numero_digitos, es_historico, activo, fecha_ingreso, usuario_registro
        FROM lotes_precintos
        WHERE 1 = 1""" + (""" AND (sede = %s OR id IN (
            SELECT lote_id FROM inventario_precintos WHERE sede = %s))""" if fp else "") + """
        ORDER BY rango_inicial
    """, fp * 2)
    datos['lotes'] = cur.fetchall()

    # Marca de agua: hasta donde llego el consecutivo segun la base.
    cur.execute("""
        SELECT numero
        FROM inventario_precintos
        WHERE estado IN ('USADO', 'ANULADO')""" + f + """
        ORDER BY numero
    """, fp)
    ocupados = [f['numero'] for f in cur.fetchall()]
    datos['maximo_ocupado'] = ocupados[-1] if ocupados else None
    datos['marca_agua'], datos['atipicos'] = calcular_marca_agua(ocupados)

    # La cola actual: exactamente lo que entregaria la proxima anulacion.
    cur.execute("""
        SELECT numero, codigo, lote_id, origen
        FROM inventario_precintos
        WHERE estado = 'DISPONIBLE'""" + f + """
        ORDER BY numero ASC
        LIMIT 20
    """, fp)
    datos['cola'] = cur.fetchall()

    cur.execute("""
        SELECT numero, codigo, lote_id, origen, created_at
        FROM inventario_precintos
        WHERE estado = 'DISPONIBLE'""" + f + """
        ORDER BY numero ASC
    """, fp)
    datos['disponibles'] = cur.fetchall()

    cur.execute("""
        SELECT numero, codigo, estado, programacion_id, placa, numero_guia,
               cliente, fecha_uso, usuario_uso, motivo_anulacion,
               fecha_anulacion, usuario_anulacion, origen
        FROM inventario_precintos
        WHERE estado = 'ANULADO'""" + f + """
        ORDER BY fecha_anulacion DESC NULLS LAST, numero DESC
    """, fp)
    datos['anulados'] = cur.fetchall()

    cur.execute("""
        SELECT numero, codigo, programacion_id, placa, numero_guia, fecha_uso
        FROM inventario_precintos
        WHERE estado = 'USADO'""" + f + """
        ORDER BY numero
    """, fp)
    datos['usados'] = cur.fetchall()

    cur.execute("""
        SELECT id, placa, numero_guia, cliente, fecha_programacion, fecha_despacho,
               precintos, ultimo_editor
        FROM programacion_cargue
        WHERE precintos IS NOT NULL AND TRIM(precintos) <> ''""" + fc + """
        ORDER BY id
    """, fcp)
    datos['cargues'] = cur.fetchall()

    return datos


# -------------------------------------------------------------------- bloques

def bloque_inventario(datos):
    titulo('1. ESTADO ACTUAL DEL INVENTARIO')
    total = 0
    print('  {:<14} {:>10}  {:>10}  {:>10}'.format('ESTADO', 'CANTIDAD', 'MINIMO', 'MAXIMO'))
    print('  ' + '-' * 50)
    for f in datos['por_estado']:
        total += f['cantidad']
        print('  {:<14} {:>10}  {:>10}  {:>10}'.format(
            f['estado'], miles(f['cantidad']),
            str(f['minimo']).zfill(6), str(f['maximo']).zfill(6)))
    print('  ' + '-' * 50)
    print('  {:<14} {:>10}'.format('TOTAL', miles(total)))

    print('\n  Lotes registrados:')
    if not datos['lotes']:
        print('    (ninguno)')
    for l in datos['lotes']:
        marca = ' [HISTORICO]' if l['es_historico'] else ''
        marca += '' if l['activo'] else ' [INACTIVO]'
        print('    #{:<4} {} - {}   {:>7} precintos   {}{}'.format(
            l['id'],
            str(l['rango_inicial']).zfill(6),
            str(l['rango_final']).zfill(6),
            miles(l['total_precintos'] or 0),
            l['nombre'] or '(sin nombre)',
            marca))


def bloque_cola(datos):
    titulo('2. LA COLA: QUE ENTREGARIA EL SISTEMA AHORA MISMO')
    marca = datos['marca_agua']
    print('  Marca de agua (hasta donde llego el consecutivo): {}'.format(
        str(marca).zfill(6) if marca else 'N/A'))

    atipicos = datos['atipicos']
    if atipicos:
        print('  Maximo bruto USADO/ANULADO............: {}'.format(
            str(datos['maximo_ocupado']).zfill(6)))
        print('  Se descartaron {} numero(s) atipicos al calcular la marca:'.format(
            len(atipicos)))
        print('    {}'.format(', '.join(str(n).zfill(6) for n in atipicos[:15])))
        print('  (quedan aislados, sin vecinos ocupados cerca -> ver bloque 5)')

    print('  Regla actual del codigo: MIN(numero) WHERE estado = DISPONIBLE')
    print('  (app.py:22928 - order_by(numero.asc()), NO "ultimo usado + 1")\n')

    if not datos['cola']:
        print('  No hay precintos DISPONIBLE. Stock agotado.')
        return

    print('  Los proximos 20 que entregaria una anulacion o asignacion:\n')
    peligrosos = 0
    for i, p in enumerate(datos['cola'], 1):
        bajo_marca = marca is not None and p['numero'] < marca
        if bajo_marca:
            peligrosos += 1
        senal = '  <-- POR DEBAJO DE LA MARCA DE AGUA' if bajo_marca else ''
        print('   {:>2}. {}{}'.format(i, p['codigo'], senal))

    print()
    if peligrosos:
        print('  >>> {} de los proximos 20 estan por debajo de la marca de agua.'.format(peligrosos))
        print('  >>> Son numeros que el consecutivo ya paso. Al entregarlos, el')
        print('  >>> sistema repite precintos ya usados. ESTO ES EL BUG.')
    else:
        print('  OK: la cola arranca por encima de la marca de agua.')


def bloque_huecos(datos):
    titulo('3. HUECOS: DISPONIBLES POR DEBAJO DE LA MARCA DE AGUA')
    marca = datos['marca_agua']
    if marca is None:
        print('  No hay ningun precinto USADO ni ANULADO. Nada que comparar.')
        return []

    huecos = [p for p in datos['disponibles'] if p['numero'] < marca]
    if not huecos:
        print('  Ninguno. Todos los DISPONIBLE estan por encima de {}.'.format(
            str(marca).zfill(6)))
        return []

    rangos = agrupar_en_rangos([p['numero'] for p in huecos])
    print('  {} numeros marcados DISPONIBLE que el consecutivo ya dejo atras.'.format(
        miles(len(huecos))))
    print('  Agrupados en {} rango(s) contiguo(s):\n'.format(len(rangos)))
    for a, b in rangos[:40]:
        print('    {}'.format(fmt_rango(a, b)))
    if len(rangos) > 40:
        print('    ... y {} rango(s) mas (ver el CSV).'.format(len(rangos) - 40))

    print('\n  >>> Estos son los que hay que sacar de circulacion.')
    return huecos


def bloque_usados_sin_marcar(datos):
    titulo('4. PRECINTOS ESCRITOS EN UN CARGUE PERO AUN MARCADOS DISPONIBLE')
    disponibles = {p['numero'] for p in datos['disponibles']}
    encontrados = {}

    for c in datos['cargues']:
        for n in numeros_del_texto(c['precintos']):
            if n in disponibles:
                encontrados.setdefault(n, []).append(c)

    if not encontrados:
        print('  Ninguno. La auto-vinculacion cerro todo lo que estaba escrito.')
        return {}

    print('  {} numero(s) aparecen en la celda de precintos de un cargue y sin'.format(
        miles(len(encontrados))))
    print('  embargo el inventario los cree libres. Ya se usaron fisicamente.\n')
    for n in sorted(encontrados)[:30]:
        c = encontrados[n][0]
        print('    {}  <- cargue #{} placa {} guia {}'.format(
            str(n).zfill(6), c['id'], c['placa'] or '?', c['numero_guia'] or '?'))
    if len(encontrados) > 30:
        print('    ... y {} mas (ver el CSV).'.format(len(encontrados) - 30))
    return encontrados


def bloque_codigos_mal_escritos(datos):
    titulo('5. CODIGOS MAL ESCRITOS EN LA CELDA DE PRECINTOS')
    por_cargue = []
    total_tokens = 0
    for c in datos['cargues']:
        malos = []
        for token in re.findall(r'\d+', c['precintos'] or ''):
            if len(token) == DIGITOS_CODIGO:
                continue
            if len(token) < MIN_DIGITOS_TEXTO:
                efecto = 'ignorado -> el sello queda DISPONIBLE'
            else:
                efecto = 'se lee como {}'.format(str(int(token)).zfill(DIGITOS_CODIGO))
            malos.append((token, efecto))
        if malos:
            por_cargue.append((c, malos))
            total_tokens += len(malos)

    if not por_cargue:
        print('  Ninguno. Todos los codigos tienen {} digitos.'.format(DIGITOS_CODIGO))
        return []

    print('  Los codigos se guardan con {} digitos, pero la auto-vinculacion'.format(
        DIGITOS_CODIGO))
    print('  (app.py:23049) acepta cualquier corrida de {}+ digitos sin validar'.format(
        MIN_DIGITOS_TEXTO))
    print('  longitud. Un dedazo consume un numero que no corresponde, y eso')
    print('  distorsiona la marca de agua (ver los atipicos del bloque 2).\n')
    print('  {} token(s) mal escritos en {} cargue(s):\n'.format(
        miles(total_tokens), miles(len(por_cargue))))
    for c, malos in por_cargue[:20]:
        print('    cargue #{:<6} placa {:<10} "{}"'.format(
            c['id'], c['placa'] or '?', c['precintos']))
        for token, efecto in malos:
            print('       "{}" ({} digitos) -> {}'.format(token, len(token), efecto))
    if len(por_cargue) > 20:
        print('    ... y {} cargue(s) mas.'.format(len(por_cargue) - 20))
    return por_cargue


def bloque_rangos_texto(datos):
    titulo('6. RANGOS ESCRITOS COMO TEXTO ("004365 al 004370")')
    disponibles = {p['numero'] for p in datos['disponibles']}
    hallazgos = []

    for c in datos['cargues']:
        for m in RE_RANGO_TEXTO.finditer(c['precintos'] or ''):
            a, b = int(m.group(1)), int(m.group(2))
            if not (0 < b - a < 100):
                continue
            medio = [n for n in range(a + 1, b) if n in disponibles]
            if medio:
                hallazgos.append((c, m.group(0).strip(), a, b, medio))

    if not hallazgos:
        print('  Ninguno. Nadie escribio rangos con "al"/"a"/"hasta".')
        return []

    print('  La auto-vinculacion (app.py:23049) solo marca los numeros que')
    print('  aparecen literalmente. Los del medio quedan libres para siempre.\n')
    for c, texto, a, b, medio in hallazgos[:20]:
        print('    cargue #{} placa {}: "{}"'.format(c['id'], c['placa'] or '?', texto))
        print('       -> quedaron DISPONIBLE: {}'.format(
            ', '.join(str(n).zfill(6) for n in medio[:10])
            + (' ...' if len(medio) > 10 else '')))
    if len(hallazgos) > 20:
        print('    ... y {} caso(s) mas.'.format(len(hallazgos) - 20))
    return hallazgos


def bloque_repetidos(datos):
    titulo('7. NUMEROS REPETIDOS EN DOS O MAS CARGUES (dano ya ocurrido)')
    apariciones = defaultdict(list)
    for c in datos['cargues']:
        for n in set(numeros_del_texto(c['precintos'])):
            apariciones[n].append(c)

    repetidos = {n: filas for n, filas in apariciones.items() if len(filas) > 1}
    if not repetidos:
        print('  Ninguno. Ningun numero esta escrito en dos cargues distintos.')
        return {}

    def fecha_cargue(c):
        return c['fecha_despacho'] or c['fecha_programacion']

    def mas_reciente(n):
        fechas = [fecha_cargue(c) for c in repetidos[n] if fecha_cargue(c)]
        return max(fechas) if fechas else None

    # Mismo sello, misma placa y misma guia = la fila de cargue esta duplicada,
    # no hubo reasignacion del precinto. Solo cuenta como dano real cuando el
    # sello aparece en dos viajes distintos.
    reales, duplicados = {}, {}
    for n, filas in repetidos.items():
        viajes = {((c['placa'] or '').strip().upper(),
                   (c['numero_guia'] or '').strip()) for c in filas}
        (reales if len(viajes) > 1 else duplicados)[n] = filas

    print('  {} numero(s) figuran en mas de un cargue:'.format(miles(len(repetidos))))
    print('    - {} en DOS VIAJES DISTINTOS  <- dano real'.format(miles(len(reales))))
    print('    - {} en filas duplicadas (misma placa y guia) <- solo datos repetidos'.format(
        miles(len(duplicados))))

    if not reales:
        print('\n  Ningun sello se fue a dos viajes distintos. Lo repetido son')
        print('  filas de cargue duplicadas, que es otro problema aparte.')
        return repetidos

    orden = sorted(reales,
                   key=lambda n: (mas_reciente(n) is not None, mas_reciente(n), n),
                   reverse=True)
    print('\n  Sellos que se fueron a dos viajes distintos (mas reciente primero):\n')
    for n in orden[:25]:
        print('    {}:'.format(str(n).zfill(6)))
        for c in sorted(reales[n], key=lambda x: fecha_cargue(x) or datetime.min.date(),
                        reverse=True):
            print('       #{:<6} placa {:<10} guia {:<18} {}'.format(
                c['id'], c['placa'] or '?', c['numero_guia'] or '?',
                fecha_cargue(c) or '?'))
    if len(reales) > 25:
        print('    ... y {} mas (ver el CSV).'.format(len(reales) - 25))
    return repetidos


def bloque_anulaciones(datos):
    titulo('8. ANULACIONES Y EL REEMPLAZO QUE ENTREGO CADA UNA')
    anulados = [a for a in datos['anulados']
                if a['usuario_anulacion'] != 'Ajuste de inventario']
    if not anulados:
        print('  No hay anulaciones registradas (fuera de ajustes de inventario).')
        return

    marca = datos['marca_agua']
    usados_por_prog = defaultdict(list)
    for u in datos['usados']:
        if u['programacion_id']:
            usados_por_prog[u['programacion_id']].append(u)

    cargues_por_id = {c['id']: c for c in datos['cargues']}

    print('  Para cada precinto anulado, que numero entro en su lugar.')
    print('  El reemplazo sale de _tomar_precintos_disponibles(1) (app.py:23450).\n')

    for a in anulados[:25]:
        fecha = a['fecha_anulacion'].strftime('%Y-%m-%d %H:%M') if a['fecha_anulacion'] else '?'
        print('    {} anulado el {} por {}'.format(
            a['codigo'], fecha, a['usuario_anulacion'] or '?'))
        print('       motivo: {}'.format(a['motivo_anulacion'] or '(sin motivo)'))

        prog = a['programacion_id']
        if not prog:
            print('       cargue: (ninguno) -- no se genero reemplazo')
            print()
            continue

        c = cargues_por_id.get(prog)
        print('       cargue: #{} placa {} guia {}'.format(
            prog, (c['placa'] if c else None) or '?', (c['numero_guia'] if c else None) or '?'))
        if c:
            print('       celda precintos hoy: {}'.format(c['precintos']))

        # El reemplazo es el sello USADO de ese cargue que no estaba antes.
        candidatos = sorted(usados_por_prog.get(prog, []), key=lambda u: u['numero'])
        if candidatos:
            print('       sellos USADO en ese cargue: {}'.format(
                ', '.join(u['codigo'] for u in candidatos)))
            sospechosos = [u for u in candidatos
                           if marca is not None and u['numero'] < a['numero']]
            if sospechosos:
                print('       >>> REEMPLAZO HACIA ATRAS: {}'.format(
                    ', '.join(u['codigo'] for u in sospechosos)))
                print('       >>> son menores que el anulado {}. El sistema retrocedio.'.format(
                    a['codigo']))
        print()

    if len(anulados) > 25:
        print('    ... y {} anulacion(es) mas.'.format(len(anulados) - 25))


def bloque_veredicto(datos, huecos, sin_marcar):
    titulo('9. VEREDICTO')
    marca = datos['marca_agua']
    disponibles = len(datos['disponibles'])
    sanos = [p for p in datos['disponibles'] if marca is None or p['numero'] > marca]

    print('  Marca de agua actual .................. {}'.format(
        str(marca).zfill(6) if marca else 'N/A'))
    print('  DISPONIBLE en total ................... {}'.format(miles(disponibles)))
    print('  DISPONIBLE por debajo de la marca ..... {}   <- a sanear'.format(miles(len(huecos))))
    print('  DISPONIBLE por encima (stock real) .... {}'.format(miles(len(sanos))))
    print('  Escritos en un cargue pero libres ..... {}'.format(miles(len(sin_marcar))))

    if sanos:
        print('\n  Si se sanea, el siguiente precinto pasaria a ser: {}'.format(
            sanos[0]['codigo']))
    if huecos:
        print('\n  Sin sanear, el siguiente precinto es: {}  (ya gastado)'.format(
            datos['cola'][0]['codigo'] if datos['cola'] else '?'))

    print('\n  NOTA: la marca de agua se calcula sobre lo que la BASE sabe. Si el')
    print('  consecutivo fisico en bodega va mas adelante que MAX(usado), el corte')
    print('  real del saneamiento es ese numero fisico, no este. Confirmalo antes')
    print('  de corregir nada.')


# ------------------------------------------------------------------------ csv

def escribir_csv(ruta, datos, huecos, sin_marcar, repetidos):
    marca = datos['marca_agua']
    por_numero = {}

    for p in huecos:
        por_numero[p['numero']] = {
            'numero': p['numero'],
            'codigo': p['codigo'],
            'estado_bd': 'DISPONIBLE',
            'lote_id': p['lote_id'],
            'origen': p['origen'],
            'bajo_marca_agua': 'SI',
            'escrito_en_cargue': '',
            'cargues': '',
            'veces_en_cargues': 0,
            'diagnostico': 'Disponible por debajo de la marca de agua',
        }

    for n, filas in sin_marcar.items():
        fila = por_numero.setdefault(n, {
            'numero': n,
            'codigo': str(n).zfill(6),
            'estado_bd': 'DISPONIBLE',
            'lote_id': '',
            'origen': '',
            'bajo_marca_agua': 'SI' if (marca and n < marca) else 'NO',
            'escrito_en_cargue': '',
            'cargues': '',
            'veces_en_cargues': 0,
            'diagnostico': '',
        })
        fila['escrito_en_cargue'] = 'SI'
        fila['cargues'] = ' | '.join(
            '#{} {} {}'.format(c['id'], c['placa'] or '?', c['numero_guia'] or '?')
            for c in filas)
        fila['veces_en_cargues'] = len(filas)
        fila['diagnostico'] = 'Usado fisicamente pero el inventario lo cree libre'

    for n, filas in repetidos.items():
        fila = por_numero.setdefault(n, {
            'numero': n,
            'codigo': str(n).zfill(6),
            'estado_bd': '',
            'lote_id': '',
            'origen': '',
            'bajo_marca_agua': 'SI' if (marca and n < marca) else 'NO',
            'escrito_en_cargue': 'SI',
            'cargues': '',
            'veces_en_cargues': 0,
            'diagnostico': '',
        })
        fila['cargues'] = ' | '.join(
            '#{} {} {}'.format(c['id'], c['placa'] or '?', c['numero_guia'] or '?')
            for c in filas)
        fila['veces_en_cargues'] = len(filas)
        viajes = {((c['placa'] or '').strip().upper(),
                   (c['numero_guia'] or '').strip()) for c in filas}
        if len(viajes) > 1:
            fila['diagnostico'] = 'REASIGNADO: el sello se fue a {} viajes distintos'.format(
                len(viajes))
        else:
            fila['diagnostico'] = 'Fila de cargue duplicada ({} filas, mismo viaje)'.format(
                len(filas))

    columnas = ['numero', 'codigo', 'estado_bd', 'lote_id', 'origen',
                'bajo_marca_agua', 'escrito_en_cargue', 'veces_en_cargues',
                'cargues', 'diagnostico']

    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.DictWriter(fh, fieldnames=columnas)
        w.writeheader()
        for n in sorted(por_numero):
            w.writerow(por_numero[n])
    return len(por_numero)


# ----------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        description='Diagnostico de solo lectura del inventario de precintos.')
    ap.add_argument('--database-url', default=None,
                    help='URL de la base. Por defecto toma $DATABASE_URL o la local de desarrollo.')
    ap.add_argument('--sin-csv', action='store_true', help='No escribir el CSV de detalle.')
    ap.add_argument('--sede', default='CARTAGENA', type=str.upper, choices=('CARTAGENA', 'MADRID'),
                    help='Bodega a diagnosticar. Cada sede tiene su propio consecutivo.')
    args = ap.parse_args()

    url = args.database_url or os.environ.get('DATABASE_URL') or URL_POR_DEFECTO

    print('=' * 78)
    print('DIAGNOSTICO DE PRECINTOS  -  SOLO LECTURA, NO MODIFICA NADA')
    print('=' * 78)
    print('  Base de datos: {}'.format(enmascarar_url_bd(url)))
    print('  Sede.........: {}'.format(args.sede))
    print('  Fecha........: {}'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

    conexion = None
    try:
        conexion = psycopg2.connect(url)
        conexion.set_session(readonly=True, autocommit=False)
        cur = conexion.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        datos = cargar_datos(cur, args.sede)
    except psycopg2.Error as e:
        sys.exit('\nNo se pudo consultar la base: {}'.format(e))
    finally:
        if conexion is not None:
            conexion.rollback()
            conexion.close()

    bloque_inventario(datos)
    bloque_cola(datos)
    huecos = bloque_huecos(datos)
    sin_marcar = bloque_usados_sin_marcar(datos)
    bloque_codigos_mal_escritos(datos)
    bloque_rangos_texto(datos)
    repetidos = bloque_repetidos(datos)
    bloque_anulaciones(datos)
    bloque_veredicto(datos, huecos, sin_marcar)

    if not args.sin_csv and (huecos or sin_marcar or repetidos):
        nombre = 'diagnostico_precintos_{}.csv'.format(datetime.now().strftime('%Y%m%d_%H%M%S'))
        ruta = os.path.join(BASE_DIR, 'backups', nombre)
        total = escribir_csv(ruta, datos, huecos, sin_marcar, repetidos)
        titulo('CSV DE DETALLE')
        print('  {} fila(s) escritas en:'.format(miles(total)))
        print('  {}'.format(ruta))

    print()


if __name__ == '__main__':
    main()
