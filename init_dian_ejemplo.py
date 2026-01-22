from app import app, db, VolumenPendienteDian
from datetime import date

with app.app_context():
    print("🔧 Inicializando valores DIAN de ejemplo...")
    
    try:
        hoy = date.today()
        
        # Buscar o crear registro de hoy
        volumen_dian = VolumenPendienteDian.query.filter_by(fecha=hoy).first()
        
        if not volumen_dian:
            # Crear nuevo con valores de ejemplo
            volumen_dian = VolumenPendienteDian(
                fecha=hoy,
                volumen_pendiente=5000.0,  # 5,000 BBL ya aprobados
                volumen_por_aprobar=3000.0,  # 3,000 BBL en trámite
                observacion="Valores iniciales de ejemplo",
                usuario_actualizacion="Sistema"
            )
            db.session.add(volumen_dian)
            print(f"✅ Registro DIAN creado para {hoy}")
            print(f"   - Ya Aprobado: 5,000.000 BBL")
            print(f"   - Por Aprobar: 3,000.000 BBL")
            print(f"   - TOTAL: 8,000.000 BBL")
        else:
            print(f"ℹ️  Registro DIAN ya existe para {hoy}")
            print(f"   - Ya Aprobado: {volumen_dian.volumen_pendiente:,.3f} BBL")
            print(f"   - Por Aprobar: {volumen_dian.volumen_por_aprobar:,.3f} BBL")
            print(f"   - TOTAL: {(volumen_dian.volumen_pendiente + volumen_dian.volumen_por_aprobar):,.3f} BBL")
        
        db.session.commit()
        print("\n✅ Listo! Recarga el dashboard para ver los cambios.")
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error: {e}")
