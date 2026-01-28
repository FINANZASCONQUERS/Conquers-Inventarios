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

class HistorialGasoil(db.Model):
    __tablename__ = 'historial_gasoil'

    fecha = db.Column(db.Date, primary_key=True)
    trm = db.Column(db.Float)
    brent = db.Column(db.Float)
    
    # Gasoil Yahoo
    gasoil_price = db.Column(db.Float)       # USD/MT (Usually quoted in MT in ICE) or USD/BLL? 
                                             # MEMO: ICE Gasoil is USD/Metric Tonne.
                                             # We might need to convert to BLL if comparing to Brent.
                                             # 1 MT approx 7.45 Bbl for Gasoil.

    # Calculated
    gasoil_usd_bll = db.Column(db.Float)     # Converted if needed
    gasoil_premium = db.Column(db.Float)     # Gasoil (USD/BLL) - Brent

    # Diesel Ecopetrol
    diesel_eco_cop_gl = db.Column(db.Float)
    diesel_eco_usd_gl = db.Column(db.Float)
    diesel_eco_usd_bll = db.Column(db.Float)

    # Gran Consumidor
    gran_cons_cop_gl = db.Column(db.Float)
    gran_cons_iva_cop = db.Column(db.Float)
    gran_cons_total_cop = db.Column(db.Float)
    
    gran_cons_usd_bll = db.Column(db.Float)
    gran_cons_iva_usd = db.Column(db.Float)
    gran_cons_total_usd = db.Column(db.Float)

    # PREMIUM (Diferenciales USD/Bbl)
    # Formula: Producto USD/BLL - Brent
    premium_eco = db.Column(db.Float)               # Ecopetrol - Brent
    premium_gasoil = db.Column(db.Float)            # Gasoil - Brent
    premium_gran_cons_sin_iva = db.Column(db.Float) # GC (Sin IVA) - Brent
    premium_gran_cons_con_iva = db.Column(db.Float) # GC (Con IVA) - Brent

    # PREMIUM COP (Diferenciales COP/Gal)
    # Formula: (Premium USD/Bbl / 42) * TRM_Mensual
    premium_cop_eco = db.Column(db.Float)
    premium_cop_gasoil = db.Column(db.Float)
    premium_cop_gran_cons_sin_iva = db.Column(db.Float)
    premium_cop_gran_cons_con_iva = db.Column(db.Float)
    
    # Store Monthly TRM used for consistency
    trm_mensual_used = db.Column(db.Float)

    # Placeholder for Ecopetrol Data (Future)
    ecopetrol_price = db.Column(db.Float)
    
    def __repr__(self):
        return f'<HistorialGasoil {self.fecha}>'
