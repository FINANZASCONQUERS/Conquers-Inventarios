#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Reparación del catálogo de clientes (tabla `clientes` + static/Clientes.json)
----------------------------------------------------------------------------
PROBLEMA 1 - Datos corruptos:
    Un script suelto insertó filas cuyos campos DIRECCION y CIUDAD_DEPARTAMENTO
    quedaron destruidos (se metió 'N°' entre cada carácter). Los NOMBRES
    sobrevivieron intactos. Como cargar_clientes() prioriza la BD y hace
    auto-sync BD -> Clientes.json, restaurar solo el archivo no sirve.

PROBLEMA 2 - Esquema que no admite sedes:
    La tabla arrastra un UNIQUE(nombre) que el modelo nunca declaró. Impide
    guardar dos sedes de la misma empresa, que las guías de transporte sí
    necesitan. Se reemplaza por UNIQUE(nombre, direccion, ciudad_departamento).

ESTRATEGIA: FUSIONAR, NUNCA REEMPLAZAR.
    El catálogo bueno se arma con la versión limpia de git + los clientes
    recuperados del historial. Pero las filas de la BD que NO estén corruptas y
    NO estén en ese catálogo se CONSERVAN: son clientes creados desde la página.
    Una fila corrupta que no se pueda emparejar con el catálogo también se
    conserva y se reporta, en vez de borrarse.

  Simulación (por defecto):  python scripts/reparar_catalogo_clientes.py
  Aplicar:                   python scripts/reparar_catalogo_clientes.py --apply

NOTA: no toca precintos ni programación. Solo el catálogo de clientes.
"""

import sys
import os
import json
import csv
import re
import argparse
import subprocess
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, BASE_DIR)

from sqlalchemy import text  # noqa: E402
from app import app, db, Cliente, cargar_clientes  # noqa: E402

RUTA_JSON = os.path.join(BASE_DIR, 'static', 'Clientes.json')
CONSTRAINT_VIEJO = 'clientes_nombre_key'
CONSTRAINT_NUEVO = 'uq_cliente_sede'

# Única errata corregida sobre los nombres legales del catálogo.
CORRECCIONES_NOMBRE = {
    'ALMA ENERGY INVESMENTS SAS': 'ALMA ENERGY INVESTMENTS SAS',
}

# Clientes que existieron en commits anteriores y desaparecieron del catálogo.
# Confirmados uno por uno con el usuario. ('HOLIS' se descartó: era de prueba.)
CLIENTES_RECUPERADOS = [
    {
        'NOMBRE_CLIENTE': 'PINTURAS EVERY',
        'DIRECCION': 'KM 1,8 VIA MADRID SUBACHOQUE',
        'CIUDAD_DEPARTAMENTO': 'MADRID-CUNDINAMARCA',
    },
    {
        'NOMBRE_CLIENTE': 'C.I. OCTANO INDUSTRIAL',
        'DIRECCION': 'SOCIEDAD PORTUARIA DEL DIQUE ZONA FRANCA KM 13 VIA MAMONAL',
        'CIUDAD_DEPARTAMENTO': 'CARTAGENA-BOLIVAR',
    },
    {
        'NOMBRE_CLIENTE': 'DISOLVAN Y CIA S.A.S',
        'DIRECCION': 'ZONA FRANCA INDUSTRIAL MAMONAL, KM 13 VIA PASACABALLOS',
        'CIUDAD_DEPARTAMENTO': 'CARTAGENA-BOLIVAR',
    },
]

# El script de unificación renombró clientes en la tabla. Este mapa permite
# reconocer que una fila corrupta llamada 'ISM' es la misma empresa que
# 'ISM INGENIERIA...' del catálogo legal, y por lo tanto es reparable.
# Las guías son documentos legales: el catálogo conserva la razón social completa.
ALIAS_UNIFICACION = {
    'COMBUSTIBLES JUANCHITO SAS': 'COMBUSTIBLES JUANCHITOS S.A.S',
    'COMERCIALIZADORA INDUSTRIAL LIUTEX SAS': 'LIUTEX',
    'DIAMOND SUPPLIES & LOGISTICS SAS': 'DIAMOND SUPPLIES & LOGISTICAS S.A.S',
    'EWAY FUEL LLC - EXPORTACION': 'EWAY FUEL LLC',
    'ISM': 'ISM INGENIERIA SERVICIO MONTAJE ESTACIONES DE SERVICIO SA',
    'SOLVENTES QUIMICOS DE COLOMBIA SAS': 'SOLVENTES QUIMICOS S.A.S',
}


def enmascarar_url_bd(uri):
    return re.sub(r':([^:@]+)@', ':****@', uri) if uri else 'N/A'


def clave(texto):
    return re.sub(r'[^A-Z0-9]', '', (texto or '').upper())


def esta_corrupto(direccion, ciudad):
    """Detecta el patrón de corrupción: 'N°' insertado entre cada carácter."""
    texto = (direccion or '') + (ciudad or '')
    return 'N°N' in texto or texto.count('N°') > 5


def construir_catalogo_bueno():
    """Catálogo limpio = versión de git + errata corregida + recuperados."""
    salida = subprocess.run(
        ['git', 'show', 'HEAD:static/Clientes.json'],
        cwd=BASE_DIR, capture_output=True, text=True, encoding='utf-8'
    )
    if salida.returncode != 0:
        raise RuntimeError(f"No se pudo leer la versión limpia desde git: {salida.stderr}")

    catalogo = []
    for c in json.loads(salida.stdout):
        nombre = CORRECCIONES_NOMBRE.get(c['NOMBRE_CLIENTE'], c['NOMBRE_CLIENTE'])
        catalogo.append({
            'NOMBRE_CLIENTE': nombre,
            'DIRECCION': c['DIRECCION'],
            'CIUDAD_DEPARTAMENTO': c['CIUDAD_DEPARTAMENTO'],
        })

    existentes = {(clave(c['NOMBRE_CLIENTE']), clave(c['DIRECCION'])) for c in catalogo}
    for c in CLIENTES_RECUPERADOS:
        if (clave(c['NOMBRE_CLIENTE']), clave(c['DIRECCION'])) not in existentes:
            catalogo.append(dict(c))
    return catalogo


def constraints_actuales():
    filas = db.session.execute(text("""
        SELECT con.conname FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        WHERE rel.relname = 'clientes' AND con.contype = 'u'
    """)).fetchall()
    return {f[0] for f in filas}


def clasificar_filas_bd(filas, catalogo):
    """Separa las filas actuales en: reparables, conservables y huérfanas."""
    nombres_catalogo = {clave(c['NOMBRE_CLIENTE']) for c in catalogo}
    claves_catalogo = {(clave(c['NOMBRE_CLIENTE']), clave(c['DIRECCION'])) for c in catalogo}

    reparables, conservar, huerfanas = [], [], []
    for f in filas:
        corrupta = esta_corrupto(f.direccion, f.ciudad_departamento)
        nombre_legal = ALIAS_UNIFICACION.get(f.nombre, f.nombre)
        cubierta = clave(nombre_legal) in nombres_catalogo

        if corrupta and cubierta:
            reparables.append(f)
        elif corrupta:
            huerfanas.append(f)          # corrupta y sin equivalente: NO se borra
        elif (clave(f.nombre), clave(f.direccion)) in claves_catalogo:
            reparables.append(f)         # ya está en el catálogo, se reescribe igual
        else:
            conservar.append(f)          # cliente creado desde la página: se respeta
    return reparables, conservar, huerfanas


def reparar(dry_run=True):
    with app.app_context():
        print("=" * 78)
        print("  REPARACIÓN DEL CATÁLOGO DE CLIENTES")
        print("=" * 78)
        print(f"Base de datos objetivo: {enmascarar_url_bd(app.config.get('SQLALCHEMY_DATABASE_URI'))}")
        print(f"Modo de ejecución:      {'[DRY-RUN - SOLO LECTURA]' if dry_run else '[APPLY - APLICAR CAMBIOS]'}")
        print("=" * 78)

        filas = Cliente.query.order_by(Cliente.id.asc()).all()
        catalogo = construir_catalogo_bueno()
        uniques = constraints_actuales()
        reparables, conservar, huerfanas = clasificar_filas_bd(filas, catalogo)

        corruptas = [f for f in filas if esta_corrupto(f.direccion, f.ciudad_departamento)]
        try:
            en_disco = json.load(open(RUTA_JSON, encoding='utf-8'))
        except Exception:
            en_disco = []

        print(f"\nTabla 'clientes' actual : {len(filas)} filas ({len(corruptas)} corruptas)")
        print(f"Clientes.json en disco  : {len(en_disco)} registros")
        print(f"Catálogo bueno a aplicar: {len(catalogo)} registros "
              f"(git HEAD + 1 errata + {len(CLIENTES_RECUPERADOS)} recuperados)")
        print(f"UNIQUE en la tabla      : {', '.join(sorted(uniques)) or '(ninguno)'}")

        print(f"\n{'-' * 78}")
        print("CLASIFICACIÓN DE LAS FILAS ACTUALES")
        print(f"{'-' * 78}")
        print(f"  Reparables (se reponen del catálogo) : {len(reparables)}")
        print(f"  Se CONSERVAN (creadas desde la web)  : {len(conservar)}")
        for f in conservar:
            print(f"      * {f.nombre} | {f.direccion} | {f.ciudad_departamento}")
        print(f"  Huérfanas (corruptas sin equivalente): {len(huerfanas)}")
        for f in huerfanas:
            print(f"      * id={f.id} {f.nombre}  <- NO se borra, requiere arreglo manual")

        total_final = len(catalogo) + len(conservar) + len(huerfanas)
        from collections import Counter
        repetidos = {n: k for n, k in
                     Counter(c['NOMBRE_CLIENTE'] for c in catalogo).items() if k > 1}

        print(f"\n{'-' * 78}")
        print("PLAN")
        print(f"{'-' * 78}")
        paso = 1
        if CONSTRAINT_VIEJO in uniques:
            print(f"  {paso}. Eliminar UNIQUE '{CONSTRAINT_VIEJO}' (impide guardar sedes)"); paso += 1
        if CONSTRAINT_NUEVO not in uniques:
            print(f"  {paso}. Crear UNIQUE '{CONSTRAINT_NUEVO}' (nombre + direccion + ciudad)"); paso += 1
        print(f"  {paso}. Dejar la tabla con {total_final} filas "
              f"({len(catalogo)} del catálogo + {len(conservar)} conservadas + {len(huerfanas)} huérfanas)"); paso += 1
        print(f"  {paso}. Reescribir Clientes.json y verificar el auto-sync")

        if repetidos:
            print("\n  Sedes múltiples que quedan soportadas:")
            for n, k in sorted(repetidos.items()):
                print(f"    * {n}: {k} sedes")

        if dry_run:
            print("\n" + "=" * 78)
            print("DRY-RUN: no se modificó nada.")
            print("Para aplicar:  python scripts/reparar_catalogo_clientes.py --apply")
            print("=" * 78)
            return 0

        # ---------- 1. Respaldo ----------
        os.makedirs(os.path.join(BASE_DIR, 'backups'), exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        ruta_bk = os.path.join(BASE_DIR, 'backups', f'backup_tabla_clientes_{ts}.csv')
        with open(ruta_bk, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['id', 'nombre', 'direccion', 'ciudad_departamento'])
            for c in filas:
                w.writerow([c.id, c.nombre, c.direccion, c.ciudad_departamento])
        print(f"\n[1/4] Respaldo de las {len(filas)} filas -> {os.path.basename(ruta_bk)}")

        # ---------- 2. Esquema ----------
        try:
            db.session.execute(text(
                f'ALTER TABLE clientes DROP CONSTRAINT IF EXISTS {CONSTRAINT_VIEJO}'))
            if CONSTRAINT_NUEVO not in uniques:
                db.session.execute(text(
                    f'ALTER TABLE clientes ADD CONSTRAINT {CONSTRAINT_NUEVO} '
                    f'UNIQUE (nombre, direccion, ciudad_departamento)'))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"\n[ERROR] Falló el cambio de constraints (ROLLBACK): {e}")
            return 1
        print(f"[2/4] Esquema corregido: UNIQUE ahora es {', '.join(sorted(constraints_actuales()))}")

        # ---------- 3. Datos: borrar SOLO las reparables, sembrar el catálogo ----------
        try:
            for f in reparables:
                db.session.delete(f)
            db.session.flush()

            presentes = {
                (clave(f.nombre), clave(f.direccion), clave(f.ciudad_departamento))
                for f in (conservar + huerfanas)
            }
            for c in catalogo:
                k = (clave(c['NOMBRE_CLIENTE']), clave(c['DIRECCION']),
                     clave(c['CIUDAD_DEPARTAMENTO']))
                if k in presentes:
                    continue
                presentes.add(k)
                db.session.add(Cliente(
                    nombre=c['NOMBRE_CLIENTE'],
                    direccion=c['DIRECCION'],
                    ciudad_departamento=c['CIUDAD_DEPARTAMENTO']
                ))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"\n[ERROR] Falló la reconstrucción de datos (ROLLBACK): {e}")
            return 1
        print(f"[3/4] Tabla 'clientes' reconstruida: {Cliente.query.count()} filas "
              f"({len(conservar)} conservadas, {len(huerfanas)} huérfanas intactas)")

        # ---------- 4. Archivo + verificación ----------
        resultado = cargar_clientes()   # lee de BD y reescribe el archivo
        final = json.load(open(RUTA_JSON, encoding='utf-8'))
        corr_mem = sum(1 for c in resultado
                       if esta_corrupto(c.get('DIRECCION'), c.get('CIUDAD_DEPARTAMENTO')))
        corr_final = sum(1 for c in final
                         if esta_corrupto(c.get('DIRECCION'), c.get('CIUDAD_DEPARTAMENTO')))
        print("[4/4] Verificación del auto-sync BD -> archivo:")
        print(f"        cargar_clientes()      -> {len(resultado)} clientes, {corr_mem} corruptos")
        print(f"        Clientes.json en disco -> {len(final)} registros, {corr_final} corruptos")

        nombres_final = [c['NOMBRE_CLIENTE'] for c in final]
        sedes_ok = all(nombres_final.count(n) >= k for n, k in repetidos.items())
        recuperados_ok = all(
            any(clave(c['NOMBRE_CLIENTE']) == clave(r['NOMBRE_CLIENTE'])
                and clave(c['DIRECCION']) == clave(r['DIRECCION']) for c in final)
            for r in CLIENTES_RECUPERADOS
        )
        conservados_ok = all(
            any(clave(c['NOMBRE_CLIENTE']) == clave(f.nombre)
                and clave(c['DIRECCION']) == clave(f.direccion) for c in final)
            for f in conservar
        )
        print(f"        sedes múltiples preservadas -> {'SI' if sedes_ok else 'NO'}")
        print(f"        clientes recuperados presentes -> {'SI' if recuperados_ok else 'NO'}")
        print(f"        clientes de la web conservados -> {'SI' if conservados_ok else 'NO'}")

        ok = (corr_mem == 0 and corr_final == 0 and sedes_ok
              and recuperados_ok and conservados_ok)
        print("\n" + "=" * 78)
        if ok:
            print("[EXITO] Catálogo reparado y verificado.")
            print("  - Direcciones y ciudades legibles")
            print("  - Sedes múltiples soportadas por el esquema")
            print("  - Clientes recuperados del historial presentes")
            print("  - Ningún cliente creado desde la web se perdió")
            print("  - El auto-sync ya no corrompe el archivo")
            if huerfanas:
                print(f"\n  PENDIENTE: {len(huerfanas)} fila(s) corrupta(s) sin equivalente en el")
                print("  catálogo quedaron intactas. Corrígelas a mano desde Editar Cliente.")
            print(f"\nRespaldo de lo anterior: {os.path.basename(ruta_bk)}")
        else:
            print("[ATENCION] La verificación no pasó limpia. Revisar antes de usar.")
        print("=" * 78)
        return 0 if ok else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Repara el catálogo de clientes (esquema + datos).")
    parser.add_argument('--apply', action='store_true',
                        help="Aplica la reparación. Sin este flag solo simula.")
    args = parser.parse_args()
    sys.exit(reparar(dry_run=not args.apply))
