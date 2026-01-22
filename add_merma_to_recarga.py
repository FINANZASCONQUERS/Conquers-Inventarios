from app import app, db

with app.app_context():
    print("🔧 Agregando columna volumen_merma a recargas_siza...")
    
    try:
        with db.engine.connect() as conn:
            # Agregar columna si no existe (nombre correcto: recargas_siza)
            conn.execute(db.text("""
                ALTER TABLE recargas_siza 
                ADD COLUMN IF NOT EXISTS volumen_merma FLOAT DEFAULT 0.0
            """))
            conn.commit()
        
        print("✅ Columna volumen_merma agregada exitosamente a recargas_siza")
        print("   Ahora cada recarga registrará su merma individual")
        
    except Exception as e:
        print(f"❌ Error: {e}")
