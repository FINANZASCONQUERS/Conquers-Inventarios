#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script de Migración y Unificación de Clientes y Productos (Auditable y Seguro)
----------------------------------------------------------------------------
Importa los diccionarios canónicos y funciones de normalización directamente desde app.py.

Modos de uso:
  1. python scripts/migrar_clientes_produccion.py
     (DRY-RUN / Solo lectura por defecto: Muestra el diff y conteos sin modificar la BD).
  
  2. python scripts/migrar_clientes_produccion.py --apply
     (APPLY: Pide confirmación explícita, genera backup CSV con tabla, columna, id, original, nuevo
      y aplica los cambios en una transacción atómica).

  3. python scripts/migrar_clientes_produccion.py --rollback backups/backup_unificacion_YYYYMMDD_HHMMSS.csv
     (ROLLBACK: Lee el archivo CSV de respaldo y restaura cada registro exactamente a su valor original).
"""

import sys
import os
import argparse
import csv
from datetime import datetime
from collections import Counter
import re

# Añadir el directorio raíz al path para importar app
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, BASE_DIR)

from app import (
    app,
    db,
    ProgramacionCargue,
    _normalizar_producto_cargue,
    _normalizar_cliente_cargue,
    _generar_clave_normalizada,
    DICCIONARIO_CANONICO_CLIENTES,
    DICCIONARIO_CANONICO_PRODUCTOS
)

try:
    from app import ProgramacionBase
    TIENE_PROGRAMACION_BASE = True
except ImportError:
    TIENE_PROGRAMACION_BASE = False


def enmascarar_url_bd(uri):
    """Oculta la contraseña en una URI de base de datos para impresión segura."""
    if not uri:
        return 'N/A'
    return re.sub(r':([^:@]+)@', ':****@', uri)


def ejecutar_rollback(ruta_csv, auto_confirmar=False):
    """Restaura los valores originales en base de datos leyendo un archivo CSV de respaldo."""
    if not os.path.exists(ruta_csv):
        print(f"[ERROR] El archivo de respaldo '{ruta_csv}' no existe.")
        return 1

    with app.app_context():
        db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
        print("=" * 80)
        print("  PROCESO DE ROLLBACK / RESTAURACIÓN DESDE BACKUP")
        print("=" * 80)
        print(f"Base de datos objetivo: {enmascarar_url_bd(db_uri)}")
        print(f"Archivo de respaldo:    {ruta_csv}")
        print("=" * 80)

        filas_rollback = []
        with open(ruta_csv, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                filas_rollback.append(row)

        if not filas_rollback:
            print("[AVISO] El archivo CSV no contiene registros a restaurar.")
            return 0

        print(f"\nSe encontraron {len(filas_rollback)} celdas para revertir a su valor original.")

        if not auto_confirmar:
            print("\n" + "!" * 80)
            print("ATENCIÓN: Vas a restaurar valores anteriores en la base de datos.")
            print("!" * 80)
            confirmacion = input("Escribe 'CONFIRMAR' para proceder con el rollback: ").strip()
            if confirmacion != 'CONFIRMAR':
                print("Rollback cancelado por el usuario.")
                return 1

        try:
            cargues_modificados = 0
            bases_modificadas = 0

            for fila in filas_rollback:
                tabla = fila['tabla']
                columna = fila['columna']
                id_reg = int(fila['id_registro'])
                val_orig = fila['valor_original']

                if tabla == 'programacion_cargue':
                    reg = db.session.get(ProgramacionCargue, id_reg)
                    if reg and hasattr(reg, columna):
                        setattr(reg, columna, val_orig)
                        cargues_modificados += 1

                elif tabla == 'programacion_base' and TIENE_PROGRAMACION_BASE:
                    reg = db.session.get(ProgramacionBase, id_reg)
                    if reg and hasattr(reg, columna):
                        setattr(reg, columna, val_orig)
                        bases_modificadas += 1

            db.session.commit()
            print("\n" + "=" * 80)
            print("[EXITO] ROLLBACK COMPLETADO CON EXITO")
            print(f"  * Registros restaurados en 'programacion_cargue': {cargues_modificados}")
            print(f"  * Registros restaurados en 'programacion_base':   {bases_modificadas}")
            print("=" * 80)
            return 0

        except Exception as e:
            db.session.rollback()
            print(f"\n[ERROR] Falló el rollback (se ejecutó rollback de transacción): {e}")
            return 1


def auditar_y_migrar(dry_run=True, auto_confirmar=False):
    with app.app_context():
        db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
        print("=" * 80)
        print("  MIGRACIÓN AUDITABLE DE CLIENTES Y PRODUCTOS")
        print("=" * 80)
        print(f"Base de datos objetivo: {enmascarar_url_bd(db_uri)}")
        print(f"Modo de ejecución:      {'[DRY-RUN - SOLO LECTURA]' if dry_run else '[APPLY - APLICAR CAMBIOS]'}")
        print("=" * 80)

        # 1. Analizar registros de ProgramacionCargue
        cargues = ProgramacionCargue.query.all()
        print(f"\nConsultando tabla 'programacion_cargue'... ({len(cargues)} registros encontrados)")

        # 2. Analizar registros de ProgramacionBase si existe
        bases = []
        if TIENE_PROGRAMACION_BASE:
            try:
                bases = ProgramacionBase.query.all()
                print(f"Consultando tabla 'programacion_base'... ({len(bases)} registros encontrados)")
            except Exception as e:
                print(f"Nota: No se pudo consultar 'programacion_base': {e}")

        # Listas para auditoría
        cambios_pendientes = []
        cambios_cli_resumen = Counter()
        cambios_prod_resumen = Counter()
        no_mapeados_cli = Counter()
        no_mapeados_prod = Counter()

        # Procesar cargues
        for r in cargues:
            # Cliente
            if r.cliente:
                cli_orig = str(r.cliente)
                cli_norm = _normalizar_cliente_cargue(cli_orig)
                clave_cli = _generar_clave_normalizada(cli_orig)
                if clave_cli not in DICCIONARIO_CANONICO_CLIENTES:
                    no_mapeados_cli[cli_orig] += 1
                if cli_norm and cli_orig != cli_norm:
                    cambios_pendientes.append({
                        'tabla': 'programacion_cargue',
                        'columna': 'cliente',
                        'id_registro': r.id,
                        'valor_original': cli_orig,
                        'valor_nuevo': cli_norm,
                        'fecha_registro': str(r.fecha_programacion) if hasattr(r, 'fecha_programacion') and r.fecha_programacion else '',
                        'numero_guia': str(r.numero_guia) if hasattr(r, 'numero_guia') and r.numero_guia else ''
                    })
                    cambios_cli_resumen[(cli_orig, cli_norm)] += 1

            # Producto
            if r.producto_a_cargar:
                prod_orig = str(r.producto_a_cargar)
                prod_norm = _normalizar_producto_cargue(prod_orig)
                clave_prod = _generar_clave_normalizada(prod_orig)
                if clave_prod not in DICCIONARIO_CANONICO_PRODUCTOS:
                    no_mapeados_prod[prod_orig] += 1
                if prod_norm and prod_orig != prod_norm:
                    cambios_pendientes.append({
                        'tabla': 'programacion_cargue',
                        'columna': 'producto_a_cargar',
                        'id_registro': r.id,
                        'valor_original': prod_orig,
                        'valor_nuevo': prod_norm,
                        'fecha_registro': str(r.fecha_programacion) if hasattr(r, 'fecha_programacion') and r.fecha_programacion else '',
                        'numero_guia': str(r.numero_guia) if hasattr(r, 'numero_guia') and r.numero_guia else ''
                    })
                    cambios_prod_resumen[(prod_orig, prod_norm)] += 1

        # Procesar base (usa columna 'producto', no 'producto_a_cargar')
        for r in bases:
            if hasattr(r, 'cliente') and r.cliente:
                cli_orig = str(r.cliente)
                cli_norm = _normalizar_cliente_cargue(cli_orig)
                clave_cli = _generar_clave_normalizada(cli_orig)
                if clave_cli not in DICCIONARIO_CANONICO_CLIENTES:
                    no_mapeados_cli[cli_orig] += 1
                if cli_norm and cli_orig != cli_norm:
                    cambios_pendientes.append({
                        'tabla': 'programacion_base',
                        'columna': 'cliente',
                        'id_registro': r.id,
                        'valor_original': cli_orig,
                        'valor_nuevo': cli_norm,
                        'fecha_registro': str(r.fecha_cargue) if hasattr(r, 'fecha_cargue') and r.fecha_cargue else '',
                        'numero_guia': 'N/A (Pedido Base)'
                    })
                    cambios_cli_resumen[(cli_orig, cli_norm)] += 1

            if hasattr(r, 'producto') and r.producto:
                prod_orig = str(r.producto)
                prod_norm = _normalizar_producto_cargue(prod_orig)
                clave_prod = _generar_clave_normalizada(prod_orig)
                if clave_prod not in DICCIONARIO_CANONICO_PRODUCTOS:
                    no_mapeados_prod[prod_orig] += 1
                if prod_norm and prod_orig != prod_norm:
                    cambios_pendientes.append({
                        'tabla': 'programacion_base',
                        'columna': 'producto',
                        'id_registro': r.id,
                        'valor_original': prod_orig,
                        'valor_nuevo': prod_norm,
                        'fecha_registro': str(r.fecha_cargue) if hasattr(r, 'fecha_cargue') and r.fecha_cargue else '',
                        'numero_guia': 'N/A (Pedido Base)'
                    })
                    cambios_prod_resumen[(prod_orig, prod_norm)] += 1

        # Mostrar Resumen de Cambios
        print("\n" + "-" * 80)
        print(f"RESUMEN DE TRANSFORMACIONES: {len(cambios_pendientes)} celdas a modificar")
        print("-" * 80)

        print(f"\n[PRODUCTOS] ({len(cambios_prod_resumen)} transformaciones distintas):")
        if cambios_prod_resumen:
            for (orig, nuevo), count in cambios_prod_resumen.most_common():
                print(f"  * '{orig}' -> '{nuevo}' ({count} registros)")
        else:
            print("  (Ningun producto requiere actualizacion)")

        print(f"\n[CLIENTES] ({len(cambios_cli_resumen)} transformaciones distintas):")
        if cambios_cli_resumen:
            for (orig, nuevo), count in cambios_cli_resumen.most_common():
                print(f"  * '{orig}' -> '{nuevo}' ({count} registros)")
        else:
            print("  (Ningun cliente requiere actualizacion)")

        # Mostrar valores no mapeados (para advertencia al usuario)
        if no_mapeados_cli or no_mapeados_prod:
            print("\n" + "=" * 80)
            print("ADVERTENCIA: Valores detectados que NO estan en el diccionario canonico:")
            print("=" * 80)
            if no_mapeados_prod:
                print("[Productos desconocidos]:")
                for val, cnt in no_mapeados_prod.most_common():
                    print(f"  - '{val}' ({cnt} registros) -> Se conserva tal cual en mayusculas")
            if no_mapeados_cli:
                print("[Clientes desconocidos]:")
                for val, cnt in no_mapeados_cli.most_common():
                    print(f"  - '{val}' ({cnt} registros) -> Se conserva tal cual en mayusculas")

        # Decisiones según modo
        if dry_run:
            print("\n" + "=" * 80)
            print("DRY-RUN FINALIZADO CON EXITO: 0 registros modificados en BD.")
            print("Para aplicar estos cambios reales en la BD, ejecuta:")
            print("  python scripts/migrar_clientes_produccion.py --apply")
            print("=" * 80)
            return 0

        if not cambios_pendientes:
            print("\nNo hay cambios pendientes por aplicar. La base de datos ya esta 100% normalizada.")
            return 0

        # MODO APPLY: Confirmación de Seguridad
        if not auto_confirmar:
            print("\n" + "!" * 80)
            print(f"ATENCIÓN: Vas a modificar {len(cambios_pendientes)} registros en la base de datos:")
            print(f"  {enmascarar_url_bd(db_uri)}")
            print("!" * 80)
            confirmacion = input("Escribe 'CONFIRMAR' para proceder con la actualizacion: ").strip()
            if confirmacion != 'CONFIRMAR':
                print("Operacion cancelada por el usuario. No se modifico la base de datos.")
                return 1

        # Generar CSV de Respaldo y Rollback
        os.makedirs(os.path.join(BASE_DIR, 'backups'), exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        csv_path = os.path.join(BASE_DIR, 'backups', f'backup_unificacion_{timestamp}.csv')

        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'tabla', 'columna', 'id_registro', 'valor_original', 'valor_nuevo', 'fecha_registro', 'numero_guia'
            ])
            writer.writeheader()
            writer.writerows(cambios_pendientes)

        print(f"\n[BACKUP AUDITABLE GENERADO] -> {csv_path}")

        # Aplicar actualizaciones en BD
        print("Aplicando actualizaciones en la base de datos...")
        try:
            # Actualizar cargues
            for r in cargues:
                if r.cliente:
                    r.cliente = _normalizar_cliente_cargue(r.cliente)
                if r.producto_a_cargar:
                    r.producto_a_cargar = _normalizar_producto_cargue(r.producto_a_cargar)

            # Actualizar bases
            for r in bases:
                if hasattr(r, 'cliente') and r.cliente:
                    r.cliente = _normalizar_cliente_cargue(r.cliente)
                if hasattr(r, 'producto') and r.producto:
                    r.producto = _normalizar_producto_cargue(r.producto)

            db.session.commit()
            print("\n" + "=" * 80)
            print("[EXITO] ACTUALIZACION EXITOSA Y CONFIRMADA EN BASE DE DATOS")
            print(f"Total de celdas actualizadas: {len(cambios_pendientes)}")
            print(f"Archivo de auditoria/rollback guardado en: {csv_path}")
            print("Para revertir estos cambios en caso de ser necesario, ejecuta:")
            print(f"  python scripts/migrar_clientes_produccion.py --rollback {csv_path}")
            print("=" * 80)
            return 0
        except Exception as err:
            db.session.rollback()
            print(f"\n[ERROR] ERROR APLICANDO CAMBIOS (Se hizo ROLLBACK automatico): {err}")
            return 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Migración y normalización de Clientes y Productos.")
    parser.add_argument('--apply', action='store_true', help="Aplica los cambios en la BD (requiere confirmación).")
    parser.add_argument('--yes', action='store_true', help="Salta la confirmación interactiva (para scripts automatizados).")
    parser.add_argument('--rollback', type=str, help="Ruta del archivo CSV de respaldo para revertir cambios.")
    args = parser.parse_args()

    if args.rollback:
        sys.exit(ejecutar_rollback(args.rollback, auto_confirmar=args.yes))
    else:
        es_dry_run = not args.apply
        sys.exit(auditar_y_migrar(dry_run=es_dry_run, auto_confirmar=args.yes))
