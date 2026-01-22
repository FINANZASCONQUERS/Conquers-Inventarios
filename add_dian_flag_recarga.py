from app import app, db

with app.app_context():
    print("🔧 Agregando columna descontado_dian a recargas_siza...")
    
    try:
        with db.engine.connect() as conn:
            # Agregar columna para rastrear si se descontó de DIAN
            conn.execute(db.text("""
                ALTER TABLE recargas_siza 
                ADD COLUMN IF NOT EXISTS descontado_dian BOOLEAN DEFAULT FALSE
            """))
            conn.commit()
        
        print("✅ Columna descontado_dian agregada exitosamente")
        
    except Exception as e:
        print(f"❌ Error: {e}")
