from app import app, db, HistorialAprobacionDian

with app.app_context():
    print("Creando tabla historial_aprobacion_dian...")
    try:
        db.create_all()
        print("✅ Tabla creada correctamente.")
    except Exception as e:
        print(f"❌ Error: {str(e)}")
