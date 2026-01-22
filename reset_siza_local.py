from app import app, db
from app import PedidoSiza, InventarioSizaDiario, VolumenPendienteDian, HistorialAprobacionDian, RecargaSiza, ConsumoSiza, MovimientoDian

with app.app_context():
    print("🗑️  Iniciando limpieza TOTAL de SIZA (Local)...")
    
    try:
        # 1. Borrar Historiales detallados
        num_movs = db.session.query(MovimientoDian).delete()
        print(f"- Historial Movimientos DIAN borrado ({num_movs} registros).")
        
        num_hist = db.session.query(HistorialAprobacionDian).delete()
        print(f"- Historial Aprobaciones borrado ({num_hist} registros).")
        
        num_ped = db.session.query(PedidoSiza).delete()
        print(f"- Todos los Pedidos borrados ({num_ped} registros).")
        
        num_rec = db.session.query(RecargaSiza).delete()
        print(f"- Historial Recargas borrado ({num_rec} registros).")
        
        num_con = db.session.query(ConsumoSiza).delete()
        print(f"- Historial Consumos borrado ({num_con} registros).")
        
        # 2. Reiniciar Saldos a Cero
        num_inv = db.session.query(InventarioSizaDiario).delete()
        print(f"- Inventarios Diarios y Acumulados (Agua/Merma) reiniciados ({num_inv} registros).")
        
        num_vol = db.session.query(VolumenPendienteDian).delete()
        print(f"- Control y Saldos DIAN reiniciados ({num_vol} registros).")
        
        # Confirmar cambios
        db.session.commit()
        print("\n✅ ¡BASE DE DATOS SIZA REINICIADA EXITOSAMENTE!")
        print("   Nota: Los productos (catálogo) se han conservado.")
        
    except Exception as e:
        db.session.rollback()
        print(f"\n❌ Error durante la limpieza: {e}")
