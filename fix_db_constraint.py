from app import app, db
from sqlalchemy import text

if __name__ == "__main__":
    with app.app_context():
        try:
            print("Attempting to drop unique constraint on clientes.nombre...")
            # Try common constraint names for unique(nombre)
            # PostgreSQL default naming: tablename_column_key
            constraints = ['clientes_nombre_key', 'unique_client_name'] 
            
            for c in constraints:
                try:
                    db.session.execute(text(f"ALTER TABLE clientes DROP CONSTRAINT IF EXISTS {c}"))
                    print(f"Executed drop for {c}")
                except Exception as ex:
                    print(f"Could not drop {c}: {ex}")
            
            db.session.commit()
            print("Database constraints update finished.")
        except Exception as e:
            print(f"General Error: {e}")
            db.session.rollback()
