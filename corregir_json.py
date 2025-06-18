import json
import os

# Asegúrate de que el nombre del archivo y la ruta sean correctos
# Esto asume que tu script está en la misma carpeta que la carpeta 'static'
nombre_archivo = os.path.join('static', 'Conductores.json')

print(f"--- Iniciando corrección para el archivo: {nombre_archivo} ---")

try:
    # 1. Leer el archivo JSON original
    with open(nombre_archivo, 'r', encoding='utf-8') as f:
        lista_conductores = json.load(f)

    conductores_corregidos = 0
    # 2. Recorrer cada conductor en la lista
    for conductor in lista_conductores:
        # Comprobar si la clave 'CEDULA' existe y si su valor es un número
        if 'CEDULA' in conductor and isinstance(conductor['CEDULA'], int):
            # Convertir el número a texto (string)
            conductor['CEDULA'] = str(conductor['CEDULA'])
            conductores_corregidos += 1

    # 3. Guardar la lista completamente corregida en el mismo archivo
    with open(nombre_archivo, 'w', encoding='utf-8') as f:
        json.dump(lista_conductores, f, ensure_ascii=False, indent=4)

    print(f"✅ ¡Listo! Se corrigieron {conductores_corregidos} cédulas.")
    print("Ahora tu archivo 'Conductores.json' tiene todas las cédulas como texto (con comillas).")

except FileNotFoundError:
    print(f"❌ ERROR: No se encontró el archivo en la ruta '{nombre_archivo}'. Asegúrate de que la ruta sea correcta.")
except Exception as e:
    print(f"❌ Ocurrió un error inesperado: {e}")
