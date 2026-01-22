from extensions import db

class HistorialCombustibles(db.Model):
    __tablename__ = 'historial_combustibles'

    fecha = db.Column(db.Date, primary_key=True)
    trm = db.Column(db.Float)
    brent = db.Column(db.Float)
    
    # F04
    f04_base_cop = db.Column(db.Float)       # COP/BLL
    f04_impuesto_cop = db.Column(db.Float)   # IVA+IMPU(COP)/BLL
    f04_total_cop = db.Column(db.Float)      # TOTAL COP/BLL
    f04_base_usd = db.Column(db.Float)       # USD/BLL
    f04_total_usd = db.Column(db.Float)      # TOTAL USD/BLL (Final)

    # FUEL OIL (Columna suelta en la imagen)
    fuel_oil_usd = db.Column(db.Float)       # FUEL OIL

    # BPI
    bpi_cop_kg = db.Column(db.Float)         # COP/KG
    bpi_usd_kg = db.Column(db.Float)         # USD/KG
    bpi_usd_mt = db.Column(db.Float)         # USD/MT
    bpi_usd_bll = db.Column(db.Float)        # USD/BLL

    # PREMIUM (Diferenciales vs Brent)
    # Formula: Producto USD/BLL - Brent
    diff_f04_base = db.Column(db.Float)
    diff_f04_total = db.Column(db.Float)
    diff_fuel_oil = db.Column(db.Float)
    diff_bpi = db.Column(db.Float)

    def __repr__(self):
        return f'<HistorialCombustibles {self.fecha}>'
