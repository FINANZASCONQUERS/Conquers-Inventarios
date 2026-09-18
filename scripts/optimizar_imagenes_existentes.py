#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de Mantenimiento: Optimización y Compresión de Imágenes Existentes

Este script recorre la carpeta de guías (GUIDES_DIR) y comprime todas las imágenes
(JPG, PNG, WEBP) que pesen más de 800 KB, reduciendo su peso hasta en un 90%
sin alterar los nombres de archivo ni romper los enlaces de la base de datos.

Modo de uso:
  1. Modo Simulación (por defecto, no toca nada, solo informa el ahorro estimado):
     python scripts/optimizar_imagenes_existentes.py

  2. Modo Real (aplica la optimización y sobreescribe los archivos pesados):
     python scripts/optimizar_imagenes_existentes.py --apply
"""

import os
import sys
import argparse
from io import BytesIO
from PIL import Image, ImageOps

# Intentar obtener la ruta de guías configurada en la aplicación
def obtener_directorio_guias(directorio_custom=None):
    if directorio_custom:
        return os.path.abspath(directorio_custom)

    try:
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
        from app import app
        return app.config.get('GUIDES_DIR') or os.path.join(os.path.dirname(__file__), '..', 'guias')
    except Exception:
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'guias'))

def formatear_tamano(bytes_cant):
    for unidad in ['B', 'KB', 'MB', 'GB']:
        if bytes_cant < 1024.0:
            return f"{bytes_cant:.2f} {unidad}"
        bytes_cant /= 1024.0
    return f"{bytes_cant:.2f} TB"

def optimizar_imagen(ruta_archivo, max_dim=2048, quality=82):
    """
    Lee una imagen, aplica rotación EXIF y comprime en memoria.
    Retorna los bytes optimizados si se redujo el peso, o None.
    """
    try:
        _, ext = os.path.splitext(ruta_archivo)
        ext_lower = ext.lower()
        is_jpeg = ext_lower in ('.jpg', '.jpeg')
        save_format = 'JPEG' if is_jpeg else ('PNG' if ext_lower == '.png' else 'WEBP')

        with Image.open(ruta_archivo) as im:
            # 1. Corregir orientación si fue tomada con celular
            im = ImageOps.exif_transpose(im)

            # 2. Convertir a RGB si es JPEG y tiene transparencia
            if im.mode in ('RGBA', 'P', 'LA') and is_jpeg:
                im = im.convert('RGB')

            # 3. Redimensionar si supera la dimensión máxima
            if im.width > max_dim or im.height > max_dim:
                im.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

            # 4. Guardar en buffer en memoria para comparar tamaños
            buffer = BytesIO()
            if save_format in ('JPEG', 'WEBP'):
                im.save(buffer, format=save_format, quality=quality, optimize=True)
            else:
                im.save(buffer, format=save_format, optimize=True)

            nuevo_contenido = buffer.getvalue()
            return nuevo_contenido
    except Exception as e:
        print(f"   [!] Error procesando {os.path.basename(ruta_archivo)}: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Optimizador de imágenes existentes en el almacenamiento de guías.")
    parser.add_argument('--apply', action='store_true', help="Aplica los cambios reales. Si no se especifica, corre en modo simulación (dry-run).")
    parser.add_argument('--dir', type=str, default=None, help="Ruta personalizada del directorio de guías.")
    parser.add_argument('--min-kb', type=int, default=800, help="Tamaño mínimo en KB para considerar optimizar un archivo (por defecto 800 KB).")
    parser.add_argument('--max-dim', type=int, default=2048, help="Dimensión máxima en píxeles (ancho o alto, por defecto 2048px).")
    parser.add_argument('--quality', type=int, default=82, help="Calidad de compresión JPEG (1-95, por defecto 82).")
    args = parser.parse_args()

    carpeta_guias = obtener_directorio_guias(args.dir)
    modo_simulacion = not args.apply

    print("=" * 70)
    print("  OPTIMIZADOR DE IMÁGENES EXISTENTES - CONQUERS")
    print("=" * 70)
    print(f"Directorio analizado : {carpeta_guias}")
    print(f"Modo de ejecución    : {'[SIMULACIÓN] (No se modificará ningún archivo)' if modo_simulacion else '[REAL] (Se optimizarán los archivos en disco)'}")
    print(f"Umbral mínimo        : {args.min_kb} KB")
    print(f"Resolución máxima    : {args.max_dim}px (Full HD+)")
    print(f"Calidad JPEG         : {args.quality}%")
    print("=" * 70)

    if not os.path.exists(carpeta_guias):
        print(f"[ERROR] El directorio {carpeta_guias} no existe.")
        return

    extensiones_validas = {'.jpg', '.jpeg', '.png', '.webp'}
    total_archivos_escaneados = 0
    imagenes_pesadas_encontradas = 0
    imagenes_optimizadas = 0
    bytes_originales_totales = 0
    bytes_optimizados_totales = 0

    archivos_a_procesar = []

    for root, _, files in os.walk(carpeta_guias):
        for f in files:
            total_archivos_escaneados += 1
            _, ext = os.path.splitext(f)
            if ext.lower() in extensiones_validas:
                ruta_completa = os.path.join(root, f)
                try:
                    peso = os.path.getsize(ruta_completa)
                    if peso >= args.min_kb * 1024:
                        archivos_a_procesar.append((ruta_completa, peso))
                except Exception:
                    pass

    print(f"Total de archivos escaneados en disco: {total_archivos_escaneados}")
    print(f"Imágenes que superan {args.min_kb} KB     : {len(archivos_a_procesar)}")
    print("-" * 70)

    if not archivos_a_procesar:
        print("[OK] No se encontraron imágenes pesadas que requieran optimización.")
        print("     Todos tus archivos existentes ya son livianos.")
        print("=" * 70)
        return

    for ruta, peso_original in archivos_a_procesar:
        nombre_rel = os.path.relpath(ruta, carpeta_guias)
        imagenes_pesadas_encontradas += 1
        bytes_originales_totales += peso_original

        contenido_optimizado = optimizar_imagen(ruta, max_dim=args.max_dim, quality=args.quality)
        if contenido_optimizado and len(contenido_optimizado) < peso_original:
            peso_nuevo = len(contenido_optimizado)
            ahorro = peso_original - peso_nuevo
            porcentaje_ahorro = (ahorro / peso_original) * 100

            bytes_optimizados_totales += peso_nuevo
            imagenes_optimizadas += 1

            if not modo_simulacion:
                with open(ruta, 'wb') as f_out:
                    f_out.write(contenido_optimizado)
                estado = "[OPTIMIZADO]"
            else:
                estado = "[SIMULADO]"

            print(f"{estado} {nombre_rel}")
            print(f"   -> Antes: {formatear_tamano(peso_original)} | Ahora: {formatear_tamano(peso_nuevo)} (Ahorro: -{porcentaje_ahorro:.1f}%)")
        else:
            bytes_optimizados_totales += peso_original
            print(f"[SIN CAMBIOS] {nombre_rel} (Ya está optimizado)")

    ahorro_total_bytes = bytes_originales_totales - bytes_optimizados_totales
    ahorro_porcentaje = (ahorro_total_bytes / bytes_originales_totales * 100) if bytes_originales_totales > 0 else 0

    print("=" * 70)
    print("  RESUMEN FINAL")
    print("=" * 70)
    print(f"Imágenes candidatas evaluadas : {imagenes_pesadas_encontradas}")
    print(f"Imágenes optimizables         : {imagenes_optimizadas}")
    print(f"Peso total original           : {formatear_tamano(bytes_originales_totales)}")
    print(f"Peso total tras optimización  : {formatear_tamano(bytes_optimizados_totales)}")
    print(f"Espacio total ahorrado        : {formatear_tamano(ahorro_total_bytes)} (-{ahorro_porcentaje:.1f}%)")

    if modo_simulacion:
        print("\n* NOTA: Este informe fue una SIMULACIÓN. Ningún archivo fue modificado.")
        print("  Para aplicar estos cambios reales en disco, ejecuta:")
        print("  python scripts/optimizar_imagenes_existentes.py --apply")
    else:
        print("\n* ÉXITO: Todos los archivos fueron optimizados y sobreescritos con éxito.")
        print("  El espacio en disco ha sido liberado.")
    print("=" * 70)

if __name__ == '__main__':
    main()
