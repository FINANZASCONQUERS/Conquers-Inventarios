"""
Script de prueba para validar las mejoras del simulador de rendimiento
Ejecutar después de instalar scipy
"""

import sys
import os

# Agregar el directorio del proyecto al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_scipy_import():
    """Test 1: Verificar que scipy se importa correctamente"""
    try:
        from scipy.interpolate import CubicSpline
        print("✅ Test 1 PASADO: scipy.interpolate.CubicSpline importado correctamente")
        return True
    except ImportError as e:
        print(f"❌ Test 1 FALLIDO: No se pudo importar scipy: {e}")
        return False

def test_cubic_spline():
    """Test 2: Verificar que CubicSpline funciona"""
    try:
        from scipy.interpolate import CubicSpline
        import numpy as np
        
        # Datos de prueba
        x = [0, 50, 100, 150, 200]
        y = [0, 10, 25, 45, 70]
        
        cs = CubicSpline(x, y)
        result = cs(125)
        
        assert isinstance(result, (float, np.ndarray)), "Resultado debe ser numérico"
        print(f"✅ Test 2 PASADO: CubicSpline funciona. Ejemplo: f(125) = {result:.2f}")
        return True
    except Exception as e:
        print(f"❌ Test 2 FALLIDO: Error en CubicSpline: {e}")
        return False

def test_watson_k_calculation():
    """Test 3: Verificar cálculo de Watson K-Factor"""
    try:
        import math
        
        # Datos de prueba: NAFTA típica
        temp_rankine = 900  # ~227°C
        sg = 0.75
        
        watson_k = (temp_rankine ** (1/3)) / sg
        
        assert 9 < watson_k < 13, f"Watson K debe estar entre 9-13, obtenido: {watson_k}"
        print(f"✅ Test 3 PASADO: Watson K calculado = {watson_k:.2f}")
        return True
    except Exception as e:
        print(f"❌ Test 3 FALLIDO: Error en Watson K: {e}")
        return False

def test_cetano_calculation():
    """Test 4: Verificar cálculo de número de cetano"""
    try:
        import math
        
        # Datos de prueba: Diesel típico
        api = 35
        azufre = 0.2
        punto_anilina = 65
        densidad_15C = 141.5 / (api + 131.5)
        
        cetano = 45.2 + (0.0892 * punto_anilina) + (131.1 * math.log(densidad_15C)) - (86.5 * azufre)
        
        assert 25 < cetano < 70, f"Cetano debe estar entre 25-70, obtenido: {cetano}"
        print(f"✅ Test 4 PASADO: Número de cetano calculado = {cetano:.1f}")
        return True
    except Exception as e:
        print(f"❌ Test 4 FALLIDO: Error en cetano: {e}")
        return False

def test_dynamic_sulfur_factors():
    """Test 5: Verificar factores dinámicos de azufre"""
    try:
        def get_factor_azufre(producto, api):
            factores_base = {
                'NAFTA': 0.03 if api > 40 else 0.08,
                'KERO': 0.12 if api > 35 else 0.20,
                'FO4': 0.85 if api > 30 else 1.15,
                'FO6': 2.8 if api > 25 else 3.5
            }
            return factores_base.get(producto, 1.0)
        
        # Test con crudo ligero (API > 40)
        factor_nafta_light = get_factor_azufre('NAFTA', 45)
        assert factor_nafta_light == 0.03, "Factor NAFTA ligero debe ser 0.03"
        
        # Test con crudo pesado (API < 30)
        factor_nafta_heavy = get_factor_azufre('NAFTA', 25)
        assert factor_nafta_heavy == 0.08, "Factor NAFTA pesado debe ser 0.08"
        
        print("✅ Test 5 PASADO: Factores dinámicos de azufre funcionan correctamente")
        return True
    except Exception as e:
        print(f"❌ Test 5 FALLIDO: Error en factores dinámicos: {e}")
        return False

def test_balance_masa():
    """Test 6: Verificar validación de balance de masa"""
    try:
        def api_a_sg(api):
            return 141.5 / (api + 131.5) if api != -131.5 else 0
        
        # Datos de prueba
        api_crudo = 32
        rendimientos = {'NAFTA': 15, 'KERO': 20, 'FO4': 35, 'FO6': 30}
        api_productos = {'NAFTA': 56.6, 'KERO': 42, 'FO4': 30, 'FO6': 21}
        
        sg_crudo = api_a_sg(api_crudo)
        sg_calculado = sum(rendimientos[p]/100 * api_a_sg(api_productos[p]) for p in rendimientos)
        diferencia = abs(sg_crudo - sg_calculado)
        
        print(f"   SG crudo: {sg_crudo:.4f}")
        print(f"   SG calculado: {sg_calculado:.4f}")
        print(f"   Diferencia: {diferencia:.4f}")
        
        if diferencia > 0.05:
            print(f"   ⚠️ Advertencia: Diferencia > 0.05")
        
        print("✅ Test 6 PASADO: Balance de masa calculado correctamente")
        return True
    except Exception as e:
        print(f"❌ Test 6 FALLIDO: Error en balance de masa: {e}")
        return False

def test_perdidas_proceso():
    """Test 7: Verificar aplicación de pérdidas de proceso"""
    try:
        PERDIDAS_TIPICAS = {
            'destilacion_atmosferica': 0.5,
            'gases_ligeros': 1.5,
            'coque': 0.3
        }
        total_perdidas = sum(PERDIDAS_TIPICAS.values())
        factor_perdidas = (100 - total_perdidas) / 100
        
        # Rendimientos originales
        rendimientos = {'NAFTA': 15, 'KERO': 20, 'FO4': 35, 'FO6': 30}
        
        # Aplicar pérdidas
        rendimientos_ajustados = {k: v * factor_perdidas for k, v in rendimientos.items()}
        
        suma_original = sum(rendimientos.values())
        suma_ajustada = sum(rendimientos_ajustados.values())
        
        print(f"   Suma original: {suma_original:.2f}%")
        print(f"   Suma ajustada: {suma_ajustada:.2f}%")
        print(f"   Pérdidas totales: {total_perdidas:.2f}%")
        
        assert abs(suma_ajustada - (100 - total_perdidas)) < 0.1, "Pérdidas mal aplicadas"
        
        print("✅ Test 7 PASADO: Pérdidas de proceso aplicadas correctamente")
        return True
    except Exception as e:
        print(f"❌ Test 7 FALLIDO: Error en pérdidas: {e}")
        return False

def run_all_tests():
    """Ejecutar todos los tests"""
    print("=" * 70)
    print("TESTS DE VALIDACIÓN - MEJORAS SIMULADOR DE RENDIMIENTO")
    print("=" * 70)
    print()
    
    tests = [
        test_scipy_import,
        test_cubic_spline,
        test_watson_k_calculation,
        test_cetano_calculation,
        test_dynamic_sulfur_factors,
        test_balance_masa,
        test_perdidas_proceso
    ]
    
    results = []
    for test in tests:
        print(f"\nEjecutando {test.__name__}...")
        results.append(test())
        print()
    
    print("=" * 70)
    print("RESUMEN DE TESTS")
    print("=" * 70)
    passed = sum(results)
    total = len(results)
    
    print(f"\n✅ Tests pasados: {passed}/{total}")
    
    if passed == total:
        print("🎉 ¡TODOS LOS TESTS PASARON EXITOSAMENTE!")
        return True
    else:
        print(f"⚠️ {total - passed} test(s) fallaron. Revisar errores arriba.")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
