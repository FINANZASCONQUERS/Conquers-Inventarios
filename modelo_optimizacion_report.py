# -*- coding: utf-8 -*-
import io
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import pandas as pd

def generar_informe_excel(nombre_escenario: str, resultados: dict, excel_path_param: str = None) -> bytes:
    """
    Generates a professional corporate Excel report using openpyxl based on optimization results.
    
    Parameters:
        nombre_escenario (str): Name of the scenario (e.g. 'Escenario Base Mayo').
        resultados (dict): Dict of results returned by modelo_optimizacion_core.ejecutar_modelo.
        excel_path_param (str): Optional path to the parameters file to fetch Brent, TRM, etc.
    """
    # 1. Fetch economic parameters
    brent = 0.0
    trm = 0.0
    pct_fin = 0.0
    prem_exp = 0.0
    
    if excel_path_param:
        try:
            # Read from the uploaded Excel file to keep exact parameter numbers
            xls_vals = pd.ExcelFile(excel_path_param)
            if 'ECONOMICOS' in xls_vals.sheet_names:
                df_econ = pd.read_excel(xls_vals, sheet_name='ECONOMICOS')
                # Find Brent, TRM, etc.
                idx_col = next((c for c in df_econ.columns if str(c).strip().upper() in ("INDEX", "INDICE", "VARIABLE", "NOMBRE")), None)
                val_col = next((c for c in df_econ.columns if str(c).strip().upper() in ("VALUE", "VALOR", "VAL")), None)
                
                if idx_col and val_col:
                    m_brent = df_econ[idx_col].astype(str).str.upper().str.strip() == "BRENT"
                    if m_brent.any():
                        brent = float(df_econ.loc[m_brent, val_col].iloc[0])
                    
                    m_trm = df_econ[idx_col].astype(str).str.upper().str.strip() == "TRM"
                    if m_trm.any():
                        try:
                            # Parse string cop values if necessary
                            raw_trm = df_econ.loc[m_trm, val_col].iloc[0]
                            trm = float(str(raw_trm).replace('$','').replace('.','').replace(',','.').replace(' ','').strip())
                        except:
                            trm = 0.0
                            
                # Try getting B4 (% Fin) and B7 (Prem Exp)
                wb = openpyxl.load_workbook(excel_path_param, data_only=True)
                if 'ECONOMICOS' in wb.sheetnames:
                    ws_ec = wb['ECONOMICOS']
                    pct_fin = ws_ec['B4'].value or 0.0
                    prem_exp = ws_ec['B7'].value or 0.0
                    if isinstance(pct_fin, str):
                        pct_fin = float(pct_fin.replace('%','').strip()) / 100.0
                    if isinstance(prem_exp, str):
                        prem_exp = float(prem_exp.replace('$','').replace(',','').strip())
        except Exception as e:
            print(f"Error loading parameters for report: {e}")
            
    # Calculate margins
    utilidad = resultados.get('utilidad_total', 0.0)
    vol_ventas = resultados.get('vol_ventas_total', 0.0)
    vol_compras = resultados.get('vol_compras_total', 0.0)
    margen_neto = (utilidad / vol_ventas) if vol_ventas > 0 else 0.0
    status = resultados.get('status', 'OPTIMAL')
    
    # 2. Initialize Workbook
    wb = Workbook()
    
    # Setup styles
    font_family = "Segoe UI"
    
    font_title = Font(name=font_family, size=16, bold=True, color="1E3A5F")
    font_subtitle = Font(name=font_family, size=11, italic=True, color="555555")
    font_section = Font(name=font_family, size=12, bold=True, color="1E3A5F")
    font_header = Font(name=font_family, size=10, bold=True, color="FFFFFF")
    font_data = Font(name=font_family, size=10)
    font_total = Font(name=font_family, size=10, bold=True, color="10B981")
    font_kpi_label = Font(name=font_family, size=9, bold=True, color="475569")
    font_kpi_value = Font(name=font_family, size=10, bold=True, color="0F172A")
    
    fill_header = PatternFill(start_color="1E3A5F", end_color="1E3A5F", fill_type="solid")
    fill_kpi = PatternFill(start_color="F0F4F8", end_color="F0F4F8", fill_type="solid")
    fill_total = PatternFill(start_color="E6F4EA", end_color="E6F4EA", fill_type="solid")
    
    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )
    
    total_border = Border(
        top=Side(style='thin', color='10B981'),
        bottom=Side(style='double', color='10B981')
    )
    
    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")
    
    # ================= Sheet 1: Resumen Ejecutivo =================
    ws = wb.active
    ws.title = "Resumen Ejecutivo"
    ws.views.sheetView[0].showGridLines = True
    
    # Titles
    ws["A1"] = "INFORME EJECUTIVO DE OPTIMIZACIÓN"
    ws["A1"].font = font_title
    
    ws["A2"] = f"Escenario: {nombre_escenario}"
    ws["A2"].font = font_subtitle
    
    ws["A3"] = f"Fecha de reporte: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
    ws["A3"].font = Font(name=font_family, size=9, color="777777")
    
    # 3. Write Economic block in F1:G8
    kpis = [
        ("BRENT (USD/BBL)", brent, "$#,##0.00"),
        ("TRM (COP/USD)", trm, "$#,##0.00"),
        ("Costo Financiación %", pct_fin, "0.0%"),
        ("Premium Export (USD)", prem_exp, "$#,##0.00"),
        ("Utilidad Total (USD/Día)", utilidad, "$#,##0.00"),
        ("Vol. Compras (BPD)", vol_compras, "#,##0.00"),
        ("Vol. Ventas (BPD)", vol_ventas, "#,##0.00"),
        ("Margen Neto (USD/BBL)", margen_neto, "$#,##0.00")
    ]
    
    for idx, (label, val, fmt) in enumerate(kpis):
        row = idx + 1
        ws.cell(row=row, column=6, value=label).font = font_kpi_label
        ws.cell(row=row, column=6).fill = fill_kpi
        ws.cell(row=row, column=6).alignment = align_left
        ws.cell(row=row, column=6).border = thin_border
        
        c_val = ws.cell(row=row, column=7, value=val)
        c_val.font = font_kpi_value
        c_val.fill = fill_kpi
        c_val.alignment = align_right
        c_val.number_format = fmt
        c_val.border = thin_border
        
    # Table Header at row 11
    ws.cell(row=10, column=1, value="MATRIZ DE OPERACIONES OPTIMIZADAS").font = font_section
    
    headers = [
        "Tipo", "Producto/Corriente", "Origen / Planta", "Destino / Pto Venta",
        "Volumen Optimizado (BPD)", "Precio/Tarifa Unit. (USD)", "Valor Bruto (USD/Día)",
        "Tarifa Transporte (USD/BBL)", "Costo Transporte (USD/Día)", "Financiación Unit.",
        "Costo Financiación (USD/Día)", "Costo Total Neto (USD/Día)"
    ]
    
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=11, column=col_idx, value=h)
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = align_center
        cell.border = thin_border
        ws.row_dimensions[11].height = 25
        
    # Data aggregation
    rows_data = []
    
    # Gather Compras
    for item in resultados.get('compras', []):
        vol = item.get('Volumen Comprado BPD', 0.0)
        price = item.get('Precio Compra USD/BBL', 0.0)
        tot = item.get('Costo Total USD', 0.0)
        rows_data.append({
            'type': 'Compra',
            'name': item.get('Crudo o Producto', ''),
            'src': item.get('Origen', ''),
            'dst': 'CZF',
            'vol': vol,
            'rate': price,
            'gross': tot,
            'trans_rate': 0.0,
            'trans_tot': 0.0,
            'fin_rate': pct_fin,
            'fin_tot': tot * pct_fin,
            'net': tot + (tot * pct_fin)
        })
        
    # Gather Ventas
    for item in resultados.get('ventas', []):
        vol = item.get('Volumen Vendido BPD', 0.0)
        price = item.get('Precio Venta USD/BBL', 0.0)
        tot = item.get('Costo Total USD', 0.0) # wait, in ventas list this is income
        rows_data.append({
            'type': 'Venta',
            'name': item.get('Corriente Venta', ''),
            'src': item.get('Punto de Venta', ''), # or origin
            'dst': item.get('Punto de Venta', ''),
            'vol': vol,
            'rate': price,
            'gross': tot,
            'trans_rate': 0.0,
            'trans_tot': 0.0,
            'fin_rate': 0.0,
            'fin_tot': 0.0,
            'net': tot
        })
        
    start_row = 12
    current_row = start_row
    
    for r in rows_data:
        ws.cell(row=current_row, column=1, value=r['type']).alignment = align_center
        ws.cell(row=current_row, column=2, value=r['name']).alignment = align_left
        ws.cell(row=current_row, column=3, value=r['src']).alignment = align_left
        ws.cell(row=current_row, column=4, value=r['dst']).alignment = align_left
        
        ws.cell(row=current_row, column=5, value=r['vol']).number_format = "#,##0.00"
        ws.cell(row=current_row, column=6, value=r['rate']).number_format = "$#,##0.00"
        ws.cell(row=current_row, column=7, value=r['gross']).number_format = "$#,##0.00"
        ws.cell(row=current_row, column=8, value=r['trans_rate']).number_format = "$#,##0.00"
        ws.cell(row=current_row, column=9, value=r['trans_tot']).number_format = "$#,##0.00"
        ws.cell(row=current_row, column=10, value=r['fin_rate']).number_format = "0.0%"
        ws.cell(row=current_row, column=11, value=r['fin_tot']).number_format = "$#,##0.00"
        ws.cell(row=current_row, column=12, value=r['net']).number_format = "$#,##0.00"
        
        # Apply font, borders and right alignment for numeric columns
        for c in range(1, 13):
            cell = ws.cell(row=current_row, column=c)
            cell.font = font_data
            cell.border = thin_border
            if c >= 5:
                cell.alignment = align_right
                
        ws.row_dimensions[current_row].height = 20
        current_row += 1
        
    # Totals Row
    ws.cell(row=current_row, column=1, value="TOTALES").font = font_total
    ws.cell(row=current_row, column=1).alignment = align_center
    ws.cell(row=current_row, column=1).fill = fill_total
    ws.cell(row=current_row, column=1).border = total_border
    
    for c in range(2, 5):
        cell = ws.cell(row=current_row, column=c, value="")
        cell.fill = fill_total
        cell.border = total_border
        
    # Formulas for totals
    vol_col_letter = get_column_letter(5)
    gross_col_letter = get_column_letter(7)
    trans_col_letter = get_column_letter(9)
    fin_col_letter = get_column_letter(11)
    net_col_letter = get_column_letter(12)
    
    total_cells = [
        (5, f"=SUM({vol_col_letter}{start_row}:{vol_col_letter}{current_row-1})", "#,##0.00"),
        (6, "", ""),
        (7, f"=SUM({gross_col_letter}{start_row}:{gross_col_letter}{current_row-1})", "$#,##0.00"),
        (8, "", ""),
        (9, f"=SUM({trans_col_letter}{start_row}:{trans_col_letter}{current_row-1})", "$#,##0.00"),
        (10, "", ""),
        (11, f"=SUM({fin_col_letter}{start_row}:{fin_col_letter}{current_row-1})", "$#,##0.00"),
        (12, f"=SUM({net_col_letter}{start_row}:{net_col_letter}{current_row-1})", "$#,##0.00")
    ]
    
    for col, formula, fmt in total_cells:
        cell = ws.cell(row=current_row, column=col)
        cell.fill = fill_total
        cell.border = total_border
        cell.font = font_total
        cell.alignment = align_right
        if formula:
            cell.value = formula
            cell.number_format = fmt
            
    ws.row_dimensions[current_row].height = 22
    
    # Auto-adjust column widths for Sheet 1
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        # Avoid title at A1 and scenario at A2 causing massive column width
        for cell in col:
            if cell.row in [1, 2, 3]:
                continue
            val_str = str(cell.value or '')
            if cell.number_format and ('$' in cell.number_format or '%' in cell.number_format):
                val_str += "   " # Add padding for formatting symbols
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)
        
    # ================= Sheet 2: Detalle Compras =================
    ws_c = wb.create_sheet(title="Compras")
    ws_c.views.sheetView[0].showGridLines = True
    
    ws_c["A1"] = "DETALLE DE COMPRAS OPTIMIZADAS"
    ws_c["A1"].font = font_section
    
    c_headers = ["Crudo / Producto", "Origen", "Volumen Comprado (BPD)", "Precio Compra (USD/BBL)", "Costo Total (USD/Día)"]
    for col_idx, h in enumerate(c_headers, 1):
        cell = ws_c.cell(row=3, column=col_idx, value=h)
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = align_center
        cell.border = thin_border
    ws_c.row_dimensions[3].height = 24
    
    c_row = 4
    for item in resultados.get('compras', []):
        ws_c.cell(row=c_row, column=1, value=item.get('Crudo o Producto', '')).alignment = align_left
        ws_c.cell(row=c_row, column=2, value=item.get('Origen', '')).alignment = align_left
        ws_c.cell(row=c_row, column=3, value=item.get('Volumen Comprado BPD', 0.0)).number_format = "#,##0.00"
        ws_c.cell(row=c_row, column=4, value=item.get('Precio Compra USD/BBL', 0.0)).number_format = "$#,##0.00"
        ws_c.cell(row=c_row, column=5, value=item.get('Costo Total USD', 0.0)).number_format = "$#,##0.00"
        
        for col in range(1, 6):
            cell = ws_c.cell(row=c_row, column=col)
            cell.font = font_data
            cell.border = thin_border
            if col >= 3:
                cell.alignment = align_right
        ws_c.row_dimensions[c_row].height = 20
        c_row += 1
        
    # Total Compras Row
    ws_c.cell(row=c_row, column=1, value="TOTALES").font = font_total
    ws_c.cell(row=c_row, column=1).alignment = align_center
    ws_c.cell(row=c_row, column=1).fill = fill_total
    ws_c.cell(row=c_row, column=1).border = total_border
    ws_c.cell(row=c_row, column=2, value="").fill = fill_total
    ws_c.cell(row=c_row, column=2).border = total_border
    
    ws_c.cell(row=c_row, column=3, value=f"=SUM(C4:C{c_row-1})").number_format = "#,##0.00"
    ws_c.cell(row=c_row, column=5, value=f"=SUM(E4:E{c_row-1})").number_format = "$#,##0.00"
    
    for c in range(3, 6):
        cell = ws_c.cell(row=c_row, column=c)
        cell.fill = fill_total
        cell.border = total_border
        cell.font = font_total
        cell.alignment = align_right
    ws_c.row_dimensions[c_row].height = 22
    
    # Auto-adjust column widths
    for col in ws_c.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.row == 1: continue
            max_len = max(max_len, len(str(cell.value or '')))
        ws_c.column_dimensions[col_letter].width = max(max_len + 4, 15)
        
    # ================= Sheet 3: Detalle Ventas =================
    ws_v = wb.create_sheet(title="Ventas")
    ws_v.views.sheetView[0].showGridLines = True
    
    ws_v["A1"] = "DETALLE DE VENTAS OPTIMIZADAS"
    ws_v["A1"].font = font_section
    
    v_headers = ["Corriente de Venta", "Punto de Venta", "Volumen Vendido (BPD)", "Precio Venta (USD/BBL)", "Ingreso Total (USD/Día)", "Crudo de Origen"]
    for col_idx, h in enumerate(v_headers, 1):
        cell = ws_v.cell(row=3, column=col_idx, value=h)
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = align_center
        cell.border = thin_border
    ws_v.row_dimensions[3].height = 24
    
    v_row = 4
    for item in resultados.get('ventas', []):
        ws_v.cell(row=v_row, column=1, value=item.get('Corriente Venta', '')).alignment = align_left
        ws_v.cell(row=v_row, column=2, value=item.get('Punto de Venta', '')).alignment = align_left
        ws_v.cell(row=v_row, column=3, value=item.get('Volumen Vendido BPD', 0.0)).number_format = "#,##0.00"
        ws_v.cell(row=v_row, column=4, value=item.get('Precio Venta USD/BBL', 0.0)).number_format = "$#,##0.00"
        ws_v.cell(row=v_row, column=5, value=item.get('Costo Total USD', 0.0)).number_format = "$#,##0.00"
        ws_v.cell(row=v_row, column=6, value=item.get('Crudo Origen', '')).alignment = align_left
        
        for col in range(1, 7):
            cell = ws_v.cell(row=v_row, column=col)
            cell.font = font_data
            cell.border = thin_border
            if col in [3, 4, 5]:
                cell.alignment = align_right
        ws_v.row_dimensions[v_row].height = 20
        v_row += 1
        
    # Total Ventas Row
    ws_v.cell(row=v_row, column=1, value="TOTALES").font = font_total
    ws_v.cell(row=v_row, column=1).alignment = align_center
    ws_v.cell(row=v_row, column=1).fill = fill_total
    ws_v.cell(row=v_row, column=1).border = total_border
    for c in [2, 6]:
        ws_v.cell(row=v_row, column=c, value="").fill = fill_total
        ws_v.cell(row=v_row, column=c).border = total_border
        
    ws_v.cell(row=v_row, column=3, value=f"=SUM(C4:C{v_row-1})").number_format = "#,##0.00"
    ws_v.cell(row=v_row, column=5, value=f"=SUM(E4:E{v_row-1})").number_format = "$#,##0.00"
    
    for c in range(3, 6):
        cell = ws_v.cell(row=v_row, column=c)
        cell.fill = fill_total
        cell.border = total_border
        cell.font = font_total
        cell.alignment = align_right
    ws_v.row_dimensions[v_row].height = 22
    
    # Auto-adjust column widths
    for col in ws_v.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.row == 1: continue
            max_len = max(max_len, len(str(cell.value or '')))
        ws_v.column_dimensions[col_letter].width = max(max_len + 4, 15)
        
    # ================= Sheet 4: Transporte =================
    ws_t = wb.create_sheet(title="Transporte")
    ws_t.views.sheetView[0].showGridLines = True
    
    ws_t["A1"] = "DETALLE DE TRANSPORTE Y RUTAS LOGÍSTICAS"
    ws_t["A1"].font = font_section
    
    t_headers = ["Flujo/Item", "Origen", "Destino", "Ruta de Transporte", "Volumen (BPD)", "Tarifa (USD/BBL)", "Costo Total (USD/Día)"]
    for col_idx, h in enumerate(t_headers, 1):
        cell = ws_t.cell(row=3, column=col_idx, value=h)
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = align_center
        cell.border = thin_border
    ws_t.row_dimensions[3].height = 24
    
    t_row = 4
    for item in resultados.get('transporte', []):
        ws_t.cell(row=t_row, column=1, value=item.get('Flujo', '')).alignment = align_left
        ws_t.cell(row=t_row, column=2, value=item.get('Origen', '')).alignment = align_left
        ws_t.cell(row=t_row, column=3, value=item.get('Destino', '')).alignment = align_left
        ws_t.cell(row=t_row, column=4, value=item.get('Ruta', '')).alignment = align_left
        ws_t.cell(row=t_row, column=5, value=item.get('Volumen Transportado BPD', 0.0)).number_format = "#,##0.00"
        ws_t.cell(row=t_row, column=6, value=item.get('Costo de transporte USD/BBL', 0.0)).number_format = "$#,##0.00"
        ws_t.cell(row=t_row, column=7, value=item.get('Costo Total USD', 0.0)).number_format = "$#,##0.00"
        
        for col in range(1, 8):
            cell = ws_t.cell(row=t_row, column=col)
            cell.font = font_data
            cell.border = thin_border
            if col in [5, 6, 7]:
                cell.alignment = align_right
        ws_t.row_dimensions[t_row].height = 20
        t_row += 1
        
    # Total Transporte Row
    ws_t.cell(row=t_row, column=1, value="TOTALES").font = font_total
    ws_t.cell(row=t_row, column=1).alignment = align_center
    ws_t.cell(row=t_row, column=1).fill = fill_total
    ws_t.cell(row=t_row, column=1).border = total_border
    for c in range(2, 5):
        ws_t.cell(row=t_row, column=c, value="").fill = fill_total
        ws_t.cell(row=t_row, column=c).border = total_border
        
    ws_t.cell(row=t_row, column=5, value=f"=SUM(E4:E{t_row-1})").number_format = "#,##0.00"
    ws_t.cell(row=t_row, column=7, value=f"=SUM(G4:G{t_row-1})").number_format = "$#,##0.00"
    
    for c in [5, 7]:
        cell = ws_t.cell(row=t_row, column=c)
        cell.fill = fill_total
        cell.border = total_border
        cell.font = font_total
        cell.alignment = align_right
    ws_t.row_dimensions[t_row].height = 22
    
    # Auto-adjust column widths
    for col in ws_t.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.row == 1: continue
            max_len = max(max_len, len(str(cell.value or '')))
        ws_t.column_dimensions[col_letter].width = max(max_len + 4, 15)
        
    # ================= Sheet 5: Blending & Propiedades =================
    ws_b = wb.create_sheet(title="Blending & Calidades")
    ws_b.views.sheetView[0].showGridLines = True
    
    ws_b["A1"] = "CALIDADES Y PROPIEDADES EN CENTROS DE BLENDING"
    ws_b["A1"].font = font_section
    
    b_headers = [
        "Mezcla", "Centro de Blending", "Volumen (BPD)", "API", "% Azufre", 
        "Viscosidad Cst", "Acid Number (mg KOH/g)", "Sedimentos (%)", "Residuo Carbón (%)", "Agua (%)"
    ]
    for col_idx, h in enumerate(b_headers, 1):
        cell = ws_b.cell(row=3, column=col_idx, value=h)
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = align_center
        cell.border = thin_border
    ws_b.row_dimensions[3].height = 24
    
    b_row = 4
    for item in resultados.get('blending', []):
        ws_b.cell(row=b_row, column=1, value=item.get('Mezcla', '')).alignment = align_left
        ws_b.cell(row=b_row, column=2, value=item.get('Centro de Blending', '')).alignment = align_left
        ws_b.cell(row=b_row, column=3, value=item.get('Volumen BPD', 0.0)).number_format = "#,##0.00"
        ws_b.cell(row=b_row, column=4, value=item.get('API', 0.0)).number_format = "0.00"
        ws_b.cell(row=b_row, column=5, value=item.get('%AZUFRE', 0.0)).number_format = "0.00%"
        ws_b.cell(row=b_row, column=6, value=item.get('Viscosidad Cst', 0.0)).number_format = "0.00"
        ws_b.cell(row=b_row, column=7, value=item.get('ACID NUMBER mg KOH/g', 0.0)).number_format = "0.00"
        ws_b.cell(row=b_row, column=8, value=item.get('Accelerated Total Sediment by Hot Filtration % m/m', 0.0)).number_format = "0.00%"
        ws_b.cell(row=b_row, column=9, value=item.get('Micro Carbon Residue % m/m', 0.0)).number_format = "0.00%"
        ws_b.cell(row=b_row, column=10, value=item.get('Water by Distillation % v/v', 0.0)).number_format = "0.00%"
        
        for col in range(1, 11):
            cell = ws_b.cell(row=b_row, column=col)
            cell.font = font_data
            cell.border = thin_border
            if col >= 3:
                cell.alignment = align_right
        ws_b.row_dimensions[b_row].height = 20
        b_row += 1
        
    # Auto-adjust column widths
    for col in ws_b.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.row == 1: continue
            max_len = max(max_len, len(str(cell.value or '')))
        ws_b.column_dimensions[col_letter].width = max(max_len + 4, 15)
        
    # ================= Save to memory and return bytes =================
    output_bytes = io.BytesIO()
    wb.save(output_bytes)
    output_bytes.seek(0)
    return output_bytes.read()
