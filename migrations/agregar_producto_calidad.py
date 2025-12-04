#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script para agregar la columna 'producto' a la tabla registros_calidad
"""

from app import db, app
from sqlalchemy import text

def agregar_columna_producto():
    """Agrega la columna producto a registros_calidad si no existe"""
    with app.app_context():
        try:
            # Usar text() para la consulta SQL
            with db.engine.connect() as conn:
                conn.execute(text(
                    "ALTER TABLE registros_calidad ADD COLUMN IF NOT EXISTS producto VARCHAR(50);"
                ))
                conn.commit()
            print("✓ Columna 'producto' agregada exitosamente a registros_calidad")
        except Exception as e:
            print(f"✗ Error al agregar columna: {e}")
            print("   La columna puede ya existir o hay un error en la base de datos")

if __name__ == "__main__":
    agregar_columna_producto()
