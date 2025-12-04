#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script para verificar la estructura de la tabla registros_calidad
"""

from app import db, app
from sqlalchemy import text

def verificar_estructura():
    """Verifica las columnas de la tabla registros_calidad"""
    with app.app_context():
        try:
            with db.engine.connect() as conn:
                result = conn.execute(text(
                    "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'registros_calidad' ORDER BY ordinal_position;"
                ))
                print("\n📋 Estructura de la tabla 'registros_calidad':")
                print("-" * 50)
                for row in result:
                    print(f"  • {row[0]:<20} ({row[1]})")
                print("-" * 50)
        except Exception as e:
            print(f"✗ Error al consultar estructura: {e}")

if __name__ == "__main__":
    verificar_estructura()
