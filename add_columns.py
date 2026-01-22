from app import app, db
from sqlalchemy import text

def add_columns():
    with app.app_context():
        # List of columns to add
        columns = [
            "diff_f04_base",
            "diff_f04_total",
            "diff_fuel_oil",
            "diff_bpi"
        ]
        
        with db.engine.connect() as conn:
            for col in columns:
                try:
                    # check if column exists first to avoid error (optional but safer)
                    # For postgres, simple ALTER TABLE ADD COLUMN IF NOT EXISTS is best if version supports it (9.6+)
                    # Assuming standard postgres
                    sql = text(f"ALTER TABLE historial_combustibles ADD COLUMN IF NOT EXISTS {col} DOUBLE PRECISION")
                    conn.execute(sql)
                    print(f"Added column: {col}")
                except Exception as e:
                    print(f"Error adding {col}: {e}")
            
            conn.commit()
            print("Migration finished.")

if __name__ == "__main__":
    add_columns()
