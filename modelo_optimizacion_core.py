# -*- coding: utf-8 -*-
from pulp import *
import pandas as pd
import openpyxl
import numpy as np
import math
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)
openpyxl.reader.excel.warnings.simplefilter(action='ignore')

def sanitize_nans(obj):
    import math
    if isinstance(obj, dict):
        return {k: sanitize_nans(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [sanitize_nans(x) for x in obj]
    else:
        try:
            import numpy as np
            if isinstance(obj, (np.floating, np.integer)):
                if np.isnan(obj) or np.isinf(obj):
                    return None
                return obj.item()
        except ImportError:
            pass

        try:
            val = float(obj)
            if math.isnan(val) or math.isinf(val):
                return None
            if isinstance(obj, float) and not isinstance(obj, bool):
                return val
        except (ValueError, TypeError):
            pass
            
        return obj

def ejecutar_modelo(excel_path: str) -> dict:
    """Runs the linear programming model and returns KPIs and tables of results."""
    
    'Parte 1: Importacion de datos'
    
    
    '____________________________________________________________________________________________________________________________________________'
    
    'CREACION DE SETS UNIDIMENSIONALES ARRAY DE 1 ENTRADA NODOS FLUJOS Y MEDIOS DE TRASNPORTE'
    
    
    #Indexar vectores de nodos
    nodos = pd.read_excel(excel_path,sheet_name='1.NODOS')
    nodosb = nodos[['NOMBRE DEL NODO','TIPO DE NODO']]
    
    nodos_origen= nodosb[(nodosb['TIPO DE NODO'] == "ORIGEN") ]
    nodos_origen.set_index(['NOMBRE DEL NODO'],inplace=True)
    
    nodos_blend= nodosb[(nodosb['TIPO DE NODO'] == "PUNTO DE BLENDING") ]
    nodos_blend.set_index(['NOMBRE DEL NODO'],inplace=True)
    
    nodos_ref= nodosb[(nodosb['TIPO DE NODO'] == "PLANTA REFINACION") ]
    nodos_ref.set_index(['NOMBRE DEL NODO'],inplace=True)
    
    nodos_venta= nodosb[(nodosb['TIPO DE NODO'] == "PUNTO VENTA") ]
    nodos_venta.set_index(['NOMBRE DEL NODO'],inplace=True)
    
    nodos_est= nodosb[(nodosb['TIPO DE NODO'] == "ESTACION") ]
    nodos_est.set_index(['NOMBRE DEL NODO'],inplace=True)
    
    flujos = pd.read_excel(excel_path,sheet_name='2.FLUJOS')
    flujosb =  flujos[['FLUJO','TIPO DE FLUJO']]
    
    flujo_compras= flujosb[(flujosb['TIPO DE FLUJO'] == "CRUDO")  + (flujosb['TIPO DE FLUJO'] == "PRODUCTO COMPRADO")]
    flujo_compras.set_index(['FLUJO'],inplace=True)
    
    flujo_ref= flujosb[(flujosb['TIPO DE FLUJO'] == "PRODUCTO REFINADO")]
    flujo_ref.set_index(['FLUJO'],inplace=True)
    
    flujo_mezcla= flujosb[(flujosb['TIPO DE FLUJO'] == "MEZCLA A VENTA")]
    flujo_mezcla.set_index(['FLUJO'],inplace=True)
    
    vector = pd.read_excel(excel_path,sheet_name='4.RUTAS_TRANSPORTE', usecols="I")
    #vectortt  = vector[['RUTA DE TRANSPORTE']]
    vectort= vector.drop_duplicates('RUTA DE TRANSPORTE')
    vectort.set_index('RUTA DE TRANSPORTE', inplace=True)
     
    '____________________________________________________________________________________________________________________________________________'
    
    'CREACION DE SETS DE COMPRAS crudo o producto i en el origen c'
    
    
    #Indexa y crea la tupla: Crudo o producto comprado i en el centro c
    Compras = pd.read_excel(excel_path,sheet_name='3.COMPRAS',index_col=[0,2])
    
    
    Compras1 = pd.read_excel(excel_path,sheet_name='3.COMPRAS',index_col=[0])
    Compras1 
    
    '____________________________________________________________________________________________________________________________________________'
    
    'CREACION DE SETS de Transporte para crudos y productos comprados'
    Rutasbase = pd.read_excel(excel_path,sheet_name='4.RUTAS_TRANSPORTE')
    Rutasbase
    
    #SETTranspi_c_b_t SETTransp Sets Crudo o producto comprado i que viaja del origen c al centro de blending b en el medio de transporte t.
    SETTranspi_c_b_t= Rutasbase[(Rutasbase['TIPO DE NODO ORIGEN'] == "ORIGEN") & (Rutasbase['TIPO DE NODO DESTINO'] == "PUNTO DE BLENDING") ]
    SETTranspi_c_b_t.set_index(['FLUJO', 'ORIGEN','DESTINO', 'RUTA DE TRANSPORTE'], inplace=True)
    
    #SETTranspi_c_z_t SETTransp Sets Crudo o producto comprado i que viaja del origen c al punto de venta z en el medio de transporte t.
    SETTranspi_c_z_t= Rutasbase[(Rutasbase['TIPO DE NODO ORIGEN'] == "ORIGEN") & (Rutasbase['TIPO DE NODO DESTINO'] == "PUNTO VENTA") ]
    SETTranspi_c_z_t.set_index(['FLUJO', 'ORIGEN','DESTINO', 'RUTA DE TRANSPORTE'], inplace=True)
    
    #SETTranspi_c_r_t SETTransp Sets Crudo o producto comprado i que viaja del origen c a la planta de Refinacion r en el medio de transporte t.
    SETTranspi_c_r_t= Rutasbase[(Rutasbase['TIPO DE NODO ORIGEN'] == "ORIGEN") & (Rutasbase['TIPO DE NODO DESTINO'] == "PLANTA REFINACION") ]
    SETTranspi_c_r_t.set_index(['FLUJO', 'ORIGEN','DESTINO', 'RUTA DE TRANSPORTE'], inplace=True)
    
    #SETTranspi_c_d_t SETTransp Sets Crudo o producto comprado i que viaja del origen c a la estacion de paso/trasnbordo d en el medio de transporte t.
    SETTranspi_c_d_t= Rutasbase[(Rutasbase['TIPO DE NODO ORIGEN'] == "ORIGEN") & (Rutasbase['TIPO DE NODO DESTINO'] == "ESTACION") ]
    SETTranspi_c_d_t.set_index(['FLUJO', 'ORIGEN','DESTINO', 'RUTA DE TRANSPORTE'], inplace=True)
    
    #SETTranspi_d_z_t SETTransp Sets Crudo o producto comprado i que viaja de la estacion de paso d al punto de venta z en el medio de transporte t.
    SETTranspi_d_z_t= Rutasbase[(Rutasbase['TIPO DE NODO ORIGEN'] == "ESTACION") & (Rutasbase['TIPO DE NODO DESTINO'] == "PUNTO VENTA") ]
    SETTranspi_d_z_t.set_index(['FLUJO', 'ORIGEN','DESTINO', 'RUTA DE TRANSPORTE'], inplace=True)
    
    #SETTranspi_d_r_t SETTransp Sets Crudo o producto comprado i que viaja de la estacion de paso d al planta de Refinacion r en el medio de transporte t.
    SETTranspi_d_r_t= Rutasbase[(Rutasbase['TIPO DE NODO ORIGEN'] == "ESTACION") & (Rutasbase['TIPO DE NODO DESTINO'] == "PLANTA REFINACION") ]
    SETTranspi_d_r_t.set_index(['FLUJO', 'ORIGEN','DESTINO', 'RUTA DE TRANSPORTE'], inplace=True)
    
    #SETTranspi_d_d_t SETTransp Sets Crudo o producto comprado i que viaja de la estacion de paso d al centro de blend b en el medio de transporte t.
    SETTranspi_d_b_t= Rutasbase[(Rutasbase['TIPO DE NODO ORIGEN'] == "ESTACION") & (Rutasbase['TIPO DE NODO DESTINO'] == "PUNTO DE BLENDING") ]
    SETTranspi_d_b_t.set_index(['FLUJO', 'ORIGEN','DESTINO', 'RUTA DE TRANSPORTE'], inplace=True)
    
    'SETTransps de Transporte para mezclas producidas'
    
    #SETTranspm_b_z_t SETTransp Sets Mezcla producidad m que viaja de la estacion de blend b al punto de venta z en el medio de transporte t.
    SETTranspm_b_z_t= Rutasbase[(Rutasbase['TIPO DE NODO ORIGEN'] == "PUNTO DE BLENDING") & (Rutasbase['TIPO DE NODO DESTINO'] == "PUNTO VENTA")  ]
    SETTranspm_b_z_t.set_index(['FLUJO', 'ORIGEN','DESTINO', 'RUTA DE TRANSPORTE'], inplace=True)
    
    'SETTransps de Transporte para productos refinados'
    
    #SETTranspp_i_r_z_t SETTransp Sets Crudo o producto refinado p obtenido del crudo i en la refineria r que viaja al punto de venta z en el medio de transporte t.
    SETTranspp_i_r_z_t= Rutasbase[(Rutasbase['TIPO FLUJO'] == "PRODUCTO REFINADO") & (Rutasbase['TIPO DE NODO ORIGEN'] == "PLANTA REFINACION") & (Rutasbase['TIPO DE NODO DESTINO'] == "PUNTO VENTA") ]
    SETTranspp_i_r_z_t.set_index(['FLUJO', 'CRUDO ORIGEN','ORIGEN','DESTINO', 'RUTA DE TRANSPORTE'], inplace=True)
    
    #SETTranspp_i_r_b_t SETTransp Sets Crudo o producto refinado p obtenido del crudo i en la refineria r que viaja al centro de blending b en el medio de transporte t.
    SETTranspp_i_r_b_t= Rutasbase[(Rutasbase['TIPO FLUJO'] == "PRODUCTO REFINADO") & (Rutasbase['TIPO DE NODO ORIGEN'] == "PLANTA REFINACION") & (Rutasbase['TIPO DE NODO DESTINO'] == "PUNTO DE BLENDING") ]
    SETTranspp_i_r_b_t.set_index(['FLUJO', 'CRUDO ORIGEN','ORIGEN','DESTINO', 'RUTA DE TRANSPORTE'], inplace=True)

    # Variantes logisticas por primer tramo de transporte para compras (CRUDO/PRODUCTO COMPRADO)
    compra_routes_by_ic = defaultdict(list)
    for i, c, b, t in SETTranspi_c_b_t.index:
        compra_routes_by_ic[(i, c)].append(('PUNTO DE BLENDING', str(b), str(t), 'c_b'))
    for i, c, z, t in SETTranspi_c_z_t.index:
        compra_routes_by_ic[(i, c)].append(('PUNTO VENTA', str(z), str(t), 'c_z'))
    for i, c, r, t in SETTranspi_c_r_t.index:
        compra_routes_by_ic[(i, c)].append(('PLANTA REFINACION', str(r), str(t), 'c_r'))
    for i, c, d, t in SETTranspi_c_d_t.index:
        compra_routes_by_ic[(i, c)].append(('ESTACION', str(d), str(t), 'c_d'))

    compra_variants_by_ic = {}
    compra_variant_meta = {}
    for i, c in Compras.index:
        route_options = compra_routes_by_ic.get((i, c), [])
        if not route_options:
            variant_id = 'V001'
            compra_variants_by_ic[(i, c)] = [variant_id]
            compra_variant_meta[(i, c, variant_id)] = {
                'variant_id': variant_id,
                'leg_kind': 'none',
                'destino_tipo': 'SIN RUTA',
                'destino_inicial': 'SIN RUTA',
                'ruta_inicial': 'SIN RUTA',
                'etiqueta_variacion': 'SIN RUTA'
            }
            continue

        route_options = sorted(route_options, key=lambda x: (x[0], x[1], x[2]))
        variants = []
        for pos, (dest_tipo, dest_name, route_name, leg_kind) in enumerate(route_options, start=1):
            variant_id = f"V{pos:03d}"
            variants.append(variant_id)
            compra_variant_meta[(i, c, variant_id)] = {
                'variant_id': variant_id,
                'leg_kind': leg_kind,
                'destino_tipo': dest_tipo,
                'destino_inicial': dest_name,
                'ruta_inicial': route_name,
                'etiqueta_variacion': f"{dest_name} | {route_name}"
            }
        compra_variants_by_ic[(i, c)] = variants

    compra_variant_index = [
        (i, c, v)
        for (i, c), variants in compra_variants_by_ic.items()
        for v in variants
    ]
    
    
    '____________________________________________________________________________________________________________________________________________'
    
    'SETS de Pertenencia de Crudo-PuntodeBlending-Mezcla'
    RELA = pd.read_excel(excel_path,sheet_name='11.REL_CRUDO_MEZCLA')
    
    SETCrudoBlend_i_b = RELA[(RELA['TIPO FLUJO'] == "CRUDO") + (RELA['TIPO FLUJO'] == "PRODUCTO COMPRADO")]
    SETCrudoBlend_i_b.set_index(['FLUJO','DESTINO'], inplace=True)
    
    SETCrudoBlendMezcla_i_b_m = RELA[(RELA['TIPO FLUJO'] == "CRUDO") + (RELA['TIPO FLUJO'] == "PRODUCTO COMPRADO")]
    SETCrudoBlendMezcla_i_b_m.set_index(['FLUJO','DESTINO','MEZCLA A PERTENECER'], inplace=True)
    
    
    SUBSET_DENS_CrudoBlendMezcla_i_b_m =  RELA [ (RELA['TIPO FLUJO'] == "CRUDO") + (RELA['TIPO FLUJO'] == "PRODUCTO COMPRADO")  & (RELA['BLEND DENSIDAD'] == "DEN")]
    SUBSET_DENS_CrudoBlendMezcla_i_b_m.set_index(['FLUJO', 'DESTINO', 'MEZCLA A PERTENECER'], inplace=True)
    
    '____________________________________________________________________________________________________________________________________________'
    
    'SETS de Pertenencia de ProductoRefinado-PuntodeBlending-Mezcla'
    
    SETRefiBlendp_i_b = RELA[(RELA['TIPO FLUJO'] == "PRODUCTO REFINADO") ]
    SETRefiBlendp_i_b.set_index(['FLUJO', 'CRUDO ORIGEN','DESTINO'], inplace=True)
    
    SETRefiBlendMezclap_i_b_m = RELA[(RELA['TIPO FLUJO'] == "PRODUCTO REFINADO") ]
    SETRefiBlendMezclap_i_b_m.set_index(['FLUJO',  'CRUDO ORIGEN','DESTINO','MEZCLA A PERTENECER'], inplace=True)
     
    SUBSET_DENS_RefiBlendMezclap_i_b_m =  RELA[(RELA['TIPO FLUJO'] == "PRODUCTO REFINADO") & (RELA['BLEND DENSIDAD'] == "DEN")]
    SUBSET_DENS_RefiBlendMezclap_i_b_m.set_index(['FLUJO', 'CRUDO ORIGEN','DESTINO', 'MEZCLA A PERTENECER'], inplace=True)
     
    '_____________ __________________________________________________________________________________________________________________________________'
    
    'Creacion SET  de productos refinados creados en plantas de refinacion ESPECIAL ELIMINACION DE DUPLICADOS'
    #TuplaProdRefp_i_r. TuplaProdRef Sets Crudo o producto refinado p obtenido del crudo i en la refineria r 
    TuplaProdRefp_i_r= Rutasbase[(Rutasbase['TIPO FLUJO'] == "PRODUCTO REFINADO") & (Rutasbase['TIPO DE NODO ORIGEN'] == "PLANTA REFINACION") & (Rutasbase['TIPO DE NODO ORIGEN'] == "PLANTA REFINACION") ]
    #Creacion de tupla eliminando los duplicados ya que provienen de la matriz de rutas
    SETProdRefp_i_r= TuplaProdRefp_i_r.drop_duplicates(subset=['FLUJO', 'CRUDO ORIGEN','ORIGEN'])
    SETProdRefp_i_r.set_index(['FLUJO', 'CRUDO ORIGEN','ORIGEN'], inplace=True)
    
    
    '____________________________________________________________________________________________________________________________________________'
    
    '   CREACION DE SETS DE VENTAS'
    
    Ventas = pd.read_excel(excel_path,sheet_name='6.VENTAS')
    Ventas
    
    
    'SET de venta directa  para productos refinados que no se mezclan'
    
    #SETVentap_i_z SETVenta Sets Crudo o producto refinado p obtenido del crudo i vendido en el punto de venta z
    SETVentap_i_z= Ventas[(Ventas['TIPO FLUJO'] == "PRODUCTO REFINADO") ]
    SETVentap_i_z.set_index(['FLUJO', 'CRUDO ORIGEN','PUNTO DE VENTA'], inplace=True)
    
    'SET de venta directa para crudos que no se mezclan'
    
    #SETVentai_z SETVenta Sets  del crudo i vendido en el punto de venta z
    SETVentai_z= Ventas[(Ventas['TIPO FLUJO'] == "CRUDO") ]
    SETVentai_z.set_index(['FLUJO','PUNTO DE VENTA'], inplace=True)
    
    'SET de ventas GENERAL/GLOBAL para mezclas producidas'
    
    #SUBSETVentaNormalm_z SETVenta Sets  de la mezcla m vendido en el punto de venta z
    SETVentaGlobalm_z= Ventas[(Ventas['TIPO FLUJO'] == "MEZCLA A VENTA")]
    SETVentaGlobalm_z.set_index(['FLUJO','PUNTO DE VENTA'], inplace=True)
    
    #SUBSETVentaNormalm_z SETVenta Sets  de la mezcla m vendido en el punto de venta z
    SUBSETVentaNormalm_z= Ventas[(Ventas['TIPO FLUJO'] == "MEZCLA A VENTA") & (Ventas['VENTA DENSIDAD'] == "N") & (Ventas['VENTA CVC'] == "N") ]
    SUBSETVentaNormalm_z.set_index(['FLUJO','PUNTO DE VENTA'], inplace=True)
    
    #SUBSETVentaNormalm_z SETVenta Sets  de la mezcla m vendido en el punto de venta z
    SUBSETVentaDENm_b= Ventas[(Ventas['TIPO FLUJO'] == "MEZCLA A VENTA") & (Ventas['VENTA DENSIDAD'] == "DEN") & (Ventas['VENTA CVC'] == "N") ]
    SUBSETVentaDENm_b.set_index(['FLUJO','ORIGEN BLEND'], inplace=True)
    
    '____________________________________________________________________________________________________________________________________________'
    
    '   CREACION DE SETS DE BLENDS'
    
    
    'SET GLOBAL DE  Blend m producido en centro blending b'
    SETBlendGlobalm_b= pd.read_excel(excel_path,sheet_name='8.LIMITES_CALIDAD')
    SETBlendGlobalm_b.set_index(['MEZCLA' , 'CENTRO DE BLENDING'], inplace=True)
    
    
    Blends= pd.read_excel(excel_path,sheet_name='8.LIMITES_CALIDAD')
    SUBSET_DENS_BlendGlobalm_b = Blends[(Blends['VENTA DENSIDAD'] == "DEN")]
    SUBSET_DENS_BlendGlobalm_b.set_index(['MEZCLA' , 'CENTRO DE BLENDING'], inplace=True)
    
    
    '____________________________________________________________________________________________________________________________________________'
    
    ' LECTURA DE PARAMETROS'
    #Indexa y crea la tupla: Mezcla producida m en el centro de blend b
    LimitesCALIDADES = pd.read_excel(excel_path,sheet_name='8.LIMITES_CALIDAD',index_col=[0,1])
    LimitesCALIDADES
    
    
    #Indexa sobre la tupla: Producto  refinado p del crudo i
    CurvaDestilacion= pd.read_excel(excel_path,sheet_name='5.CURVA_DESTILACION',index_col=[0,1])
    #Indexa y crea  la tupla: planta de refinacion r
    CostosRef= pd.read_excel(excel_path,sheet_name='7.COSTOS_REFINACION',index_col=[0])
    CostosOPERA= pd.read_excel(excel_path,sheet_name='12.COSTOS_OPERACIONALES',index_col=[0])
    
    '________'
    ' SET DE FLASH POINT'
    SETCRUDOBLENDFLASHi_b= pd.read_excel(excel_path,sheet_name='9.FLASH_RESTR',index_col=[0,3])
    
    '__________________________________________________________________________'
    
    '    CREACION SETS PARA CVC '
    
    ' SET DE CVC PARA CRUDOS'
    datacvc= pd.read_excel(excel_path,sheet_name='10.CVC')
    SETCVCCRUDOi_b_m= datacvc[(datacvc['TIPO FLUJO'] == "CRUDO") + (datacvc['TIPO FLUJO'] == "PRODUCTO COMPRADO") ]
    SETCVCCRUDOi_b_m.set_index(['FLUJO','DESTINO','MEZCLA A PERTENECER'], inplace=True)
    
    ' SET DE CVC PARA REFINADOS'
    
    SETCVCREFIp_i_b_m= datacvc[ (datacvc['TIPO FLUJO'] == "PRODUCTO REFINADO") ]
    SETCVCREFIp_i_b_m.set_index(['FLUJO', 'CRUDO ORIGEN','DESTINO','MEZCLA A PERTENECER'], inplace=True)
    
    ' SET DE CVC PARA mezcla en blend'
    
    SUBSETCVCmezclab_m= datacvc.drop_duplicates(['DESTINO','MEZCLA A PERTENECER'])
    SUBSETCVCmezclab_m.set_index(['MEZCLA A PERTENECER','DESTINO'], inplace=True)
    
    ' SET DE CVC PARA mezcla en PUNTO DE VENTA'
    
    SUBSETVentaCVCm_z= Ventas[(Ventas['TIPO FLUJO'] == "MEZCLA A VENTA") & (Ventas['VENTA CVC'] == "CVC") ]
    SUBSETVentaCVCm_z.set_index(['FLUJO','PUNTO DE VENTA'], inplace=True)
    
    ' SET DE CVC PARA mezcla CVC en TRANSPORTE PUNTO DE VENTA' 
    
    SUBSETTransCVCpm_b_z_t= Rutasbase[(Rutasbase['TIPO DE NODO ORIGEN'] == "PUNTO DE BLENDING") & (Rutasbase['TIPO DE NODO DESTINO'] == "PUNTO VENTA") & (Rutasbase['CVC MEZCLA RESULANTE'] == "CVC")   ]
    SUBSETTransCVCpm_b_z_t.set_index(['FLUJO', 'ORIGEN','DESTINO', 'RUTA DE TRANSPORTE'], inplace=True)
     
    
    'SET de costo especial de refinados con destino  punto de blending en misma area geografica, ehjemplo cartagena' 
    
    SUBSETTransREFIOPp_i_r_b_t= Rutasbase[ (Rutasbase['Relacion Area de Operacion Costo BLEND IFO?'] == "SI")   ]
    SUBSETTransREFIOPp_i_r_b_t.set_index(['FLUJO', 'CRUDO ORIGEN','ORIGEN','DESTINO', 'RUTA DE TRANSPORTE'], inplace=True)
    
    'SET de costo REGULAR de refinados con destino  punto de blending en misma area geografica, ehjemplo cartagena' 
    
    SUBSETTransREFIREGOPp_i_r_b_t= Rutasbase[ (Rutasbase['Relacion Area de Operacion Costo BLEND IFO?'] == "NO")   ]
    SUBSETTransREFIREGOPp_i_r_b_t.set_index(['FLUJO', 'CRUDO ORIGEN','ORIGEN','DESTINO', 'RUTA DE TRANSPORTE'], inplace=True)
    
    
    '_______________________________________________________________________________________________________________________________________________'
    
    #display(SETTranspi_c_b_t)
    #display(SETTranspp_i_r_z_t)
    #display(SUBSETVentaNormalm_z)
    #display(SETVentap_i_z)
    #display(SETProdRefp_i_r)
    #display(LimitesCALIDADES)
    #display(Compras) 
    
    'PART2: Crear variables de decision'
    '_______________________________________________________________________________________________________________________________________________'
    
    
    'Variable Funcion Objetivo'
    # Variable funcion objetivo
    Utilidad = pulp.LpProblem("Utilidad",LpMaximize)
    
    
    '_____________________________________________________________________________________________________'
    
    '  Variables de Compras'
    
    'Variable Ci,c Volumen de crudo o producto comprado i en el campo u origen c'
    Ci_c = pulp.LpVariable.dicts("Comprai,c",
                                         ((i, c) for i, c in Compras.index), 0, cat='Continuous'
                                         )

    # Variable Ci,c,v Volumen de compra desagregado por variante logistica (primer tramo)
    Ci_c_v = pulp.LpVariable.dicts("Comprai,c,v",
                                         ((i, c, v) for i, c, v in compra_variant_index), 0, cat='Continuous'
                                         )
    #display(Ci_c)
    #print(len(Ci_c))
    
    
    '_____________________________________________________________________________________________________________'
    '  Variables de transporte de crudos y productos comprados, mezclas y refinados  '
    
    'Variable Vi,c,b,t Volumen de crudo o producto comprado i, transportado desde el campo u origen c al centro de blend b en la ruta de transporte t'
    Vi_c_b_t = pulp.LpVariable.dicts("Volumeni,c,b,t",
                                         ((i, c, b, t) for i, c, b, t in SETTranspi_c_b_t.index), 0, cat='Continuous'
                                         )
    #display(Vi_c_b_t)
    #print(len(Vi_c_b_t))
    
    'Variable Vi,c,z,t Volumen de crudo o producto comprado i, transportado desde el campo u origen c al punto de venta z en la ruta de transporte t'
    Vi_c_z_t = pulp.LpVariable.dicts("Volumeni,c,z,t",
                                         ((i, c, z, t) for i, c, z, t in SETTranspi_c_z_t.index), 0, cat='Continuous'
                                         )
    #display(Vi_c_z_t)
    #print(len(Vi_c_z_t))
    
    'Variable Vi,c,d,t Volumen de crudo o producto comprado i, transportado desde el campo u origen c a la estacion de paso d en la ruta de transporte t'
    Vi_c_d_t = pulp.LpVariable.dicts("Volumeni,c,d,t",
                                         ((i, c, d, t) for i, c, d, t in SETTranspi_c_d_t.index), 0, cat='Continuous'
                                         )
    #display(Vi_c_d_t)
    #print(len(Vi_c_d_t))
    
    'Variable Vi,c,r,t Volumen de crudo o producto comprado i, transportado desde el campo u origen c a la planta de refinacion r en la ruta de transporte t'
    Vi_c_r_t = pulp.LpVariable.dicts("Volumeni,c,r,t",
                                         ((i, c, r, t) for i, c, r, t in SETTranspi_c_r_t.index), 0, cat='Continuous'
                                         )
    #display(Vi_c_r_t)
    #print(len(Vi_c_r_t))
    
    'Variable Vi,d,z,t Volumen de crudo o producto comprado i, transportado desde la estacion de paso d al punto de venta z  en la ruta de transporte t'
    Vi_d_z_t = pulp.LpVariable.dicts("Volumeni,d,z,t",
                                         ((i, d, z, t) for i, d, z, t in SETTranspi_d_z_t.index), 0, cat='Continuous'
                                         )
    #display(Vi_d_z_t)
    #print(len(Vi_d_z_t))
    
    'Variable Vi,d,b,t Volumen de crudo o producto comprado i, transportado desde la estacion de paso d a la estacion de blending b  en la ruta de transporte t'
    Vi_d_b_t = pulp.LpVariable.dicts("Volumeni,d,b,t",
                                         ((i, d, b, t) for i, d, b, t in SETTranspi_d_b_t.index), 0, cat='Continuous'
                                         )
    #display(Vi_d_b_t)
    #print(len(Vi_d_b_t))
    
    'Variable Vi,d,r,t Volumen de crudo o producto comprado i, transportado desde la estacion de paso d a la refineria r  en la ruta de transporte t'
    Vi_d_r_t = pulp.LpVariable.dicts("Volumeni,d,r,t",
                                         ((i, d, r, t) for i, d, r, t in SETTranspi_d_r_t.index), 0, cat='Continuous'
                                         )
    #display(Vi_d_r_t)
    #print(len(Vi_d_r_t))
    
    
    'Variable Mm,b,z,t Volumen de mezcla producida m, transportado desde la estacion de blending b al punto de venta z en la ruta de transporte t'
    Mm_b_z_t = pulp.LpVariable.dicts("VolMezclam,b,z,t",
                                         ((m, b, z, t) for m, b, z, t in SETTranspm_b_z_t.index), 0, cat='Continuous'
                                         )
    #display(Mm_b_z_t)
    #print(len(Mm_b_z_t))
    
    'Variable Pp,i,r,z,t Volumen del producto refinado p destilado del crudo i en la planta de refinacion r transportado hacia el punto de venta z usando el medio de transporte t'
    Pp_i_r_z_t = pulp.LpVariable.dicts("VolPTp,i,r,z,t",
                                         ((p, i, r, z, t) for p, i, r, z, t in SETTranspp_i_r_z_t.index), 0, cat='Continuous'
                                         )
    #display(Pp_i_r_z_t)
    #print(len(Pp_i_r_z_t))
    
    'Variable Pp,i,r,b,t Volumen del producto refinado p destilado del crudo i en la planta de refinacion r transportado hacia el punto de blending b usando el medio de transporte t'
    Pp_i_r_b_t = pulp.LpVariable.dicts("VolPTp,i,r,b,t",
                                         ((p, i, r, b, t) for p, i, r, b, t in SETTranspp_i_r_b_t.index), 0, cat='Continuous'
                                         )
    #display(Pp_i_r_b_t)
    #print(len(Pp_i_r_b_t))
    '___________________________________________________________________________________________________'
    
    '  Variables de Pertenencia crudos en centros de blend y a mezclas  '
    
    'Variable VEi,b Volumen de crudo i total en el punto de blending b'
    Vi_b = pulp.LpVariable.dicts("VolCrudoBlendi,b",
                                         ((i, b) for i, b in SETCrudoBlend_i_b.index), 0, cat='Continuous'
                                         )
    
    'Variable VEi,b,M Volumen de crudo i total en el punto de blending b'
    Vi_b_m = pulp.LpVariable.dicts("VolCrudoBlendMezclai,b,m",
                                         ((i, b, m) for i, b, m in SETCrudoBlendMezcla_i_b_m .index), 0, cat='Continuous'
                                         )
    
    '___________________________________________________________________________________________________'
    
    '  Variables de Pertenencia REFINADOS en centros de blend y a mezclas  '
    
    'Variable PEi,b Volumen de crudo i total en el punto de blending b'
    Pp_i_b = pulp.LpVariable.dicts("VolRefiBlendi,b",
                                         ((p, i, b) for p, i, b in SETRefiBlendp_i_b.index), 0, cat='Continuous'
                                         )
    
    'Variable VEi,b,M Volumen de crudo i total en el punto de blending b'
    Pp_i_b_m = pulp.LpVariable.dicts("VolRefiBlMzi,b,m",
                                         ((p, i, b, m) for p, i, b, m in SETRefiBlendMezclap_i_b_m.index), 0, cat='Continuous'
                                         )
    
    '___________________________________________________________________________________________________'
    
    '  Variables de creacion de mezclas  '
    
    'Variable Mm,b Volumen de mezcla producida m en el punto de blending b'
    Mm_b = pulp.LpVariable.dicts("VolumenMezclam,b",
                                         ((m, b) for m, b in SETBlendGlobalm_b.index), 0, cat='Continuous'
                                         )
    #display(Mm_b)
    #print(len(Mm_b))
    
    '___________________________________________________________________________________________________'
    
    '  Variables de VENTAS '
    
    
    'Variable Mm,z Volumen de mezcla producida m vendida en el punto de venta z'
    Mm_z = pulp.LpVariable.dicts("VolumenMezclam,z",
                                         ((m, z) for m, z in SETVentaGlobalm_z.index), 0, cat='Continuous'
                                         )
    #display(Mm_z)
    #print(len(Mm_z))
    
    'Variable CVi,c Volumen de crudo i vendido directamente sin mezcla en el punto de venta z '
    CVi_z = pulp.LpVariable.dicts("CrudoVentai,z",
                                         ((i, z) for i, z in SETVentai_z.index), 0, cat='Continuous'
                                         )
    #display(CVi_z)
    #print(len(CVi_z))
    
    'Variable Pp,i,z Volumen del producto refinado p destilado del crudo i vendido directamente en el punto de venta z'
    Pp_i_z = pulp.LpVariable.dicts("VolumenProductop,i,z",
                                         ((p, i, z) for p, i, z in SETVentap_i_z.index), 0, cat='Continuous'
                                         )
    #display(Pp_i_z)
    #print(len(Pp_i_z))
    
    
    '_____________________________________________________________________________________________________'
    
    '  Variables de Volumenes de Productos refinados'
    
    'Variable Pp,i,r Volumen del producto refinado p destilado del crudo i en la planta de refinacion r'
    Pp_i_r = pulp.LpVariable.dicts("VolumenProductop,i,r",
                                         ((p, i, r) for p, i, r in SETProdRefp_i_r.index), 0, cat='Continuous'
                                         )
    #display(Pp_i_r)
    #print(len(Pp_i_r)) 
    
    
    'Variable Pr Throughput total de una refineria r'
    Pr = pulp.LpVariable.dicts("VoltotalRefineriar",
                                         ((r) for r in CostosRef.index), 0, cat='Continuous'
                                         )
    #display(Pr)
    #print(len(Pr))
    
    'Variable Vb Volumen total operado en Nodo de blending solo crudos'
    Vb = pulp.LpVariable.dicts("Voltotalnodob",
                                         ((b) for b in CostosOPERA.index), 0, cat='Continuous'
                                         )
    #display(Vb)
    #print(len(Vb))
    
    'Variable Vb Volumen total operado en Nodo de blending solo refinados ESPECIAL'
    Pb = pulp.LpVariable.dicts("VoltotalREFInodob",
                                         ((b) for b in CostosOPERA.index), 0, cat='Continuous'
                                         )
    
    
    'Variable Vb Volumen total operado en Nodo de blending solo refinados NORMAL'
    PNORMALb = pulp.LpVariable.dicts("VoltotalREFINORMALnodob",
                                         ((b) for b in CostosOPERA.index), 0, cat='Continuous'
                                         )
    
    '_____________________________________________________________________________________________________'
    
    '  Variables de VCVC'
    
    'Variable CVC del crudo i en blend b en mezcla m'
    VCVCi_b_m = pulp.LpVariable.dicts("VolCVCcrudo",
                                         ((i,b,m) for i,b,m in SETCVCCRUDOi_b_m.index), 0, cat='Continuous'
                                         )
    
    'Variable CVC del Refinado p del crudo  i en blend b en mezcla m'
    PCVCp_i_b_m = pulp.LpVariable.dicts("VolCVCrefi",
                                         ((p,i,b,m) for p,i,b,m in SETCVCREFIp_i_b_m.index), 0, cat='Continuous'
                                         )
    
    'Variable Mm,b Volumen de CVC mezcla producida m en el punto de blending b'
    MCVCm_b = pulp.LpVariable.dicts("VolumenCVCMezclam,b",
                                         ((m, b) for m, b in SUBSETCVCmezclab_m.index), 0, cat='Continuous'
                                         )
    
    'Variable Mm,z Volumen CVC de mezcla producida m vendida en el punto de venta z'
    MCVCm_z = pulp.LpVariable.dicts("VolVENTACVCMezclam,z",
                                         ((m, z) for m, z in SUBSETVentaCVCm_z.index), 0, cat='Continuous'
                                         )
    
    'Variable Mm,b,z,t Volumen de mezcla  CVC producida m, transportado desde la estacion de blending b al punto de venta z en la ruta de transporte t'
    MCVCm_b_z_t = pulp.LpVariable.dicts("VolTRANSCVCm,b,z,t",
                                         ((m, b, z, t) for m, b, z, t in SUBSETTransCVCpm_b_z_t.index), 0, cat='Continuous'
                                         )
    
    
    
    'PART3: Definicion funcion Objetivo'
    '_______________________________________________________________________________________________________________________________________________'
    
    'Utilidad= Ingreso por venta de crudos directo + productos refinados + mezclas Menos Egresos por Compras de crudo, costos de transporte y Costos de refinacion'
    Utilidad +=  pulp.lpSum(
        [Mm_z[(m, z)] * SUBSETVentaNormalm_z.loc[(m, z), 'Precio de venta (USD/BPD)'] for m, z in SUBSETVentaNormalm_z.index]
        + [MCVCm_z[(m, z)] * SUBSETVentaCVCm_z.loc[(m, z), 'Precio de venta (USD/BPD)'] for m, z in SUBSETVentaCVCm_z.index]
        + [Pp_i_z[(p, i, z)] * SETVentap_i_z.loc[(p, i, z), 'Precio de venta (USD/BPD)'] * SETVentap_i_z.loc[(p, i, z), 'RELACION  DCONTRAC/DENTREGA'] for p, i, z in SETVentap_i_z.index]
        + [CVi_z[(i, z)] * SETVentai_z.loc[(i, z), 'Precio de venta (USD/BPD)'] * SETVentai_z.loc[(i, z), 'RELACION  DCONTRAC/DENTREGA'] for i, z in SETVentai_z.index]
        + [(-1)*Ci_c[(i, c)] * Compras.loc[(i, c), 'Precio de Compra CALCULADO  (USD/BPD)'] for i, c in Compras.index]
        + [(-1)*Vi_c_b_t[(i, c, b, t)] * SETTranspi_c_b_t.loc[(i, c, b, t), 'Costo de transporte USD/BBL para modelo'] for i, c, b, t in SETTranspi_c_b_t.index]
        + [(-1)*Vi_c_z_t[(i, c, z, t)] * SETTranspi_c_z_t.loc[(i, c, z, t), 'Costo de transporte USD/BBL para modelo'] for i, c, z, t in SETTranspi_c_z_t.index]
        + [(-1)*Vi_c_d_t[(i, c, d, t)] * SETTranspi_c_d_t.loc[(i, c, d, t), 'Costo de transporte USD/BBL para modelo'] for i, c, d, t in SETTranspi_c_d_t.index]
        + [(-1)*Vi_c_r_t[(i, c, r, t)] * SETTranspi_c_r_t.loc[(i, c, r, t), 'Costo de transporte USD/BBL para modelo'] for i, c, r, t in SETTranspi_c_r_t.index]
        + [(-1)*Pp_i_r_z_t[(p, i, r, z, t)] * SETTranspp_i_r_z_t.loc[(p, i, r, z, t), 'Costo de transporte USD/BBL para modelo'] for p, i, r, z, t in SETTranspp_i_r_z_t.index]
        + [(-1)*Pp_i_r_b_t[(p, i, r, b, t)] * SETTranspp_i_r_b_t.loc[(p, i, r, b, t), 'Costo de transporte USD/BBL para modelo'] for p, i, r, b, t in SETTranspp_i_r_b_t.index]
        + [(-1)*Vi_d_z_t[(i, d, z, t)] * SETTranspi_d_z_t.loc[(i, d, z, t), 'Costo de transporte USD/BBL para modelo'] for i, d, z, t in SETTranspi_d_z_t.index]
        + [(-1)*Vi_d_b_t[(i, d, b, t)] * SETTranspi_d_b_t.loc[(i, d, b, t), 'Costo de transporte USD/BBL para modelo'] for i, d, b, t in SETTranspi_d_b_t.index]
        + [(-1)*Vi_d_r_t[(i, d, r, t)] * SETTranspi_d_r_t.loc[(i, d, r, t), 'Costo de transporte USD/BBL para modelo'] for i, d, r, t in SETTranspi_d_r_t.index]
        + [(-1)*Mm_b_z_t[(m, b, z, t)] * SETTranspm_b_z_t.loc[(m, b, z, t), 'Costo de transporte USD/BBL para modelo'] for m, b, z, t in SETTranspm_b_z_t.index]
        + [(-1)*Pr[r] * CostosRef.loc[r,'Costo de refinacion (USD/BPD)'] for r in CostosRef.index]
        + [(-1)*Vb[b] * CostosOPERA.loc[(b),'Costo Operacional (USD/BBL)'] for b in CostosOPERA.index]
        + [(-1)*PNORMALb[b] * CostosOPERA.loc[(b),'Costo Operacional (USD/BBL)'] for b in CostosOPERA.index]
        + [(-1)*Pb[b] * CostosOPERA.loc[(b),'Costo Operacion Refinados en Blend  (USD/BBL)'] for b in CostosOPERA.index ]
        ) + pulp.lpSum( SUBSETVentaDENm_b.loc[(m,b),'Precio de venta (USD/BPD)'] * SUBSETVentaDENm_b.loc[(m,b),'Densidad (BBL/TONMetrica) Contractual'] * pulp.lpSum(  [Vi_b_m [(i, b, m)] * (1/ Compras1.loc[(i), 'DENSIDAD  (BBL/TONMETRICA)']) for i in flujo_compras.index if (i,b,m) in SUBSET_DENS_CrudoBlendMezcla_i_b_m.index] + [Pp_i_b_m [(p, i, b, m)] *  (1/ CurvaDestilacion.loc[(p,i), 'DENSIDAD (BBL/TONMETRICA)'] ) for p in flujo_ref.index for i in flujo_compras.index if (p, i, b, m) in SUBSET_DENS_RefiBlendMezclap_i_b_m.index]) for  m, b in  SUBSETVentaDENm_b.index)
     
    
    'PART4: Deficion de Restricciones'
    '_______________________________________________________________________________________________________________________________________________'
    
    ' RESTRICCIONES DE OFERTA Y DEMANDA '

    'i-aux) Desagregacion de compras por variantes logisticas del primer tramo'
    for i, c in Compras.index:
        variants = compra_variants_by_ic.get((i, c), [])
        if not variants:
            continue

        Utilidad += (Ci_c[(i, c)] == pulp.lpSum(Ci_c_v[(i, c, v)] for v in variants))

        for v in variants:
            meta = compra_variant_meta.get((i, c, v), {})
            leg_kind = meta.get('leg_kind')
            destino = meta.get('destino_inicial')
            ruta = meta.get('ruta_inicial')

            if leg_kind == 'c_b' and (i, c, destino, ruta) in SETTranspi_c_b_t.index:
                Utilidad += (Ci_c_v[(i, c, v)] == Vi_c_b_t[(i, c, destino, ruta)])
            elif leg_kind == 'c_z' and (i, c, destino, ruta) in SETTranspi_c_z_t.index:
                Utilidad += (Ci_c_v[(i, c, v)] == Vi_c_z_t[(i, c, destino, ruta)])
            elif leg_kind == 'c_r' and (i, c, destino, ruta) in SETTranspi_c_r_t.index:
                Utilidad += (Ci_c_v[(i, c, v)] == Vi_c_r_t[(i, c, destino, ruta)])
            elif leg_kind == 'c_d' and (i, c, destino, ruta) in SETTranspi_c_d_t.index:
                Utilidad += (Ci_c_v[(i, c, v)] == Vi_c_d_t[(i, c, destino, ruta)])
            else:
                Utilidad += (Ci_c_v[(i, c, v)] == 0)
    
    'i)  Oferta de produccion disponible, no se compre mas del volumen disponible'
    for i, c in Compras.index:
        Maxdisponible = Compras.loc[(i,c),'Volumen Disponible a Compra (BPD)'] 
        Mindisponible = Compras.loc[(i,c),'Volumen Minimo a Compra (BPD)'] 
        Utilidad += ( Ci_c[(i, c)] <= Maxdisponible )
        Utilidad += ( Ci_c[(i, c)] >= Mindisponible )
       # Utilidad += ( Ci_c[('CARRIZALES', 'CAMPO CARRIZALES')] >= 2 )
        
    'ii) Demanda. No se vende mas del limite comercial segunda parte para blend Espcieal formula densidad'
    for m, z in SETVentaGlobalm_z.index:
        Maxdisponibled = SETVentaGlobalm_z.loc[(m,z),'Volumen Maximo a Venta (Si aplica)  (BPD)']
        Utilidad += ( Mm_z[(m, z)] <= Maxdisponibled )
        
    'iii) Demanda de productos refinados a venta. Limite maximo de venta'
    for p, i, z  in SETVentap_i_z.index: 
        Maxdisponibler = SETVentap_i_z.loc[(p, i, z),'Volumen Maximo a Venta (Si aplica)  (BPD)'] 
        Utilidad += ( Pp_i_z[(p, i, z)]  <= Maxdisponibler )      
        
    'iv) Demanda de crudo vendido en punto z'
    for i, z in SETVentai_z.index:
        Utilidad += ( CVi_z[(i, z)] <= SETVentai_z.loc[(i,z),'Volumen Maximo a Venta (Si aplica)  (BPD)']  )  
        
    '_______________________________________________________________________________________________________________________________________________'
    
    ' RESTRICCIONES DE BALANCE NODOS DE ORIGEN Y NODOS DE TRANSBORDO '
        
    'v) Balance en Origen. Todo lo que se compra en un campo u origen sale a venta,blend,refinacion o paso, no se almacena'
    for i, c in Compras.index:
        RHS1 = pulp.lpSum( [Vi_c_b_t[(i, c, b, t)] for b in nodos_blend.index for t in vectort.index if  (i, c, b, t) in SETTranspi_c_b_t.index] 
                         + [Vi_c_z_t[(i, c, z, t)] for z in nodos_venta.index for t in vectort.index if  (i, c, z, t) in SETTranspi_c_z_t.index] 
                         + [Vi_c_r_t[(i, c, r, t)] for r in nodos_ref.index for t in vectort.index if  (i, c, r, t) in SETTranspi_c_r_t.index]  
                         + [Vi_c_d_t[(i, c, d, t)] for d in nodos_est.index for t in vectort.index if  (i, c, d, t) in SETTranspi_c_d_t.index] 
                         )
        Utilidad += ( Ci_c[(i, c)] == RHS1 )
        
        
    ' vi) Balance en nodos de transbordo o estaciones de paso'  
    for  i in flujo_compras.index:
     for d in nodos_est.index:
      # if (i, c, d, t) in SETTranspi_c_d_t.index:
         RHS21 = pulp.lpSum( [Vi_d_z_t[(i, d, z, t)]  for z in nodos_venta.index for t in vectort.index if  (i, d, z, t) in SETTranspi_d_z_t.index] 
                          +  [Vi_d_b_t[(i, d, b, t)]  for b in nodos_blend.index for t in vectort.index if  (i, d, b, t) in SETTranspi_d_b_t.index]
                          +  [Vi_d_r_t[(i, d, r, t)]  for r in nodos_ref.index for t in vectort.index if  (i, d, r, t) in SETTranspi_d_r_t.index]
                          )
         Utilidad += ( pulp.lpSum( [Vi_c_d_t[(i, c, d, t)]  for c in nodos_origen.index for t in vectort.index if  (i, c, d, t) in SETTranspi_c_d_t.index] )  == RHS21 )
    
    '_______________________________________________________________________________________________________________________________________________'
    
    ' RESTRICCIONES DE PERTENENCIA DE CRUDOS A UN BLEND '
    
    ' vii) Calculo total de entradas de crudos a un punto de blend '  
    for i, b in SETCrudoBlend_i_b.index:
       RHS31 = pulp.lpSum( [Vi_c_b_t[(i, c, b, t)]  for c in nodos_origen.index  for t in vectort.index if  (i, c, b, t) in SETTranspi_c_b_t.index]
                         + [Vi_d_b_t[(i, d, b, t)] for d in nodos_est.index  for t in vectort.index if  (i, d, b, t) in SETTranspi_d_b_t.index]
                         )
       Utilidad += ( Vi_b[(i, b)] == RHS31 )   
    
    ' viii) Calculo total de entradas de crudos a un punto de blend por mezcla '  
    for i, b in SETCrudoBlend_i_b.index:
       RHS40 = pulp.lpSum( [Vi_b_m[(i, b, m )]  for m in flujo_mezcla.index  if  (i, b, m ) in SETCrudoBlendMezcla_i_b_m.index]
                           )
       Utilidad += ( Vi_b[(i, b)] == RHS40 )      
    
    '_______________________________________________________________________________________________________________________________________________'
    
    ' RESTRICCIONES DE PERTENENCIA DE REFINADOS A UN BLEND '
    
    'ix) Calculo total de entradas de Refinados a un punto de blend '   
     
    for p, i, b in SETRefiBlendp_i_b.index:
       RHS32 = pulp.lpSum( [Pp_i_r_b_t[(p, i, r, b, t)]  for r in nodos_ref.index  for t in vectort.index if  (p, i, r, b, t) in SETTranspp_i_r_b_t.index]
                          )
       Utilidad += ( Pp_i_b [(p, i, b)] == RHS32 )  
    
    'x) Calculo total de entradas de Refinados a un punto de blend por mezcla '   
     
    for p, i, b in SETRefiBlendp_i_b.index:
       RHS32 = pulp.lpSum( [Pp_i_b_m [(p, i, b, m)]  for m in flujo_mezcla.index  if  (p, i, b, m) in SETRefiBlendMezclap_i_b_m.index]
                          )
       Utilidad += ( Pp_i_b [(p, i, b)] == RHS32 )  
       
    '_______________________________________________________________________________________________________________________________________________'   
    
    '  RESTRICCION DE CREACION DE MEZCLA '
      
    
    'xi) Balance de creacion de mezcla: Calcula El volumen de una mezcla producida es la suma de crudos/productos + refinados'  
    for m, b in SETBlendGlobalm_b.index:
       RHS3 = pulp.lpSum( [Vi_b_m[(i, b, m )] for i in flujo_compras.index  if  (i, b, m ) in SETCrudoBlendMezcla_i_b_m.index]
                        + [Pp_i_b_m [(p, i, b, m)] for p in flujo_ref.index for i in flujo_compras.index if  (p, i, b, m) in SETRefiBlendMezclap_i_b_m.index]
                         )
       Utilidad += ( Mm_b[(m, b)] == RHS3 ) 
       
    '_______________________________________________________________________________________________________________________________________________'   
     
    '  RESTRICCIONES DE TRANSPORTE Y VENTA DE MEZCLA '  
       
    'xii) Toda Mezcla Producida  es transportado'
    for m, b in SETBlendGlobalm_b.index:
        RHS4 = pulp.lpSum( [Mm_b_z_t[(m, b, z, t)] for z in nodos_venta.index for t in vectort.index if  (m, b, z, t) in SETTranspm_b_z_t.index]
                          )
        Utilidad += ( Mm_b[(m, b)] == RHS4 ) 
    
        
    'xiii) Todo lo transporatado se vende '
    for m, z in SETVentaGlobalm_z.index:
        RHS5 = pulp.lpSum( [Mm_b_z_t[(m, b, z, t)] for b in nodos_blend.index for t in vectort.index if  (m, b, z, t) in SETTranspm_b_z_t.index]
                          )
        Utilidad += ( Mm_z[(m, z)]== RHS5 ) 
    
    
        
    '   Restricciones de refinacion'
    '_________________________________________________________________'    
        
    'xiv) Creacion de las fracciones  Calculo de cada producto refinado por crudo segun curva de destilacion'
    for p, i, r  in SETProdRefp_i_r.index: 
        RHS6 = pulp.lpSum( [Vi_c_r_t[(i, c, r, t)]  for c in nodos_origen.index for t in vectort.index if  (i, c, r, t) in SETTranspi_c_r_t.index] 
                          + [Vi_d_r_t[(i, d, r, t)] for d in nodos_est.index for t in vectort.index if  (i, d, r, t) in SETTranspi_d_r_t.index]
                          )
        Utilidad += ( Pp_i_r[(p, i, r)] == CurvaDestilacion.loc[(p, i), 'FRACCION %'] * RHS6 )
    
    'xv) Aseguramiento balance por cada crudo producido, Sumatoria de TODOS los productos refinados suman el total de cada crudo entrante '
    for  i in flujo_compras.index:
     for r in CostosRef.index: 
        if (p, i, r) in SETProdRefp_i_r.index:
            RHS7 = pulp.lpSum( [Vi_c_r_t[(i, c, r, t)]  for c in nodos_origen.index for t in vectort.index if  (i, c, r, t) in SETTranspi_c_r_t.index] 
                          + [Vi_d_r_t[(i, d, r, t)] for d in nodos_est.index for t in vectort.index if  (i, d, r, t) in SETTranspi_d_r_t.index]
                          )
            Utilidad += (  pulp.lpSum( [Pp_i_r[(p, i, r)] for p in flujo_ref.index if (p, i, r) in SETProdRefp_i_r.index ] ) == RHS7)
    
    'xvi) Calculo del throughput de una refineria r'
    for r in CostosRef.index:
       Utilidad += ( Pr[r] ==  pulp.lpSum( Pp_i_r[(p, i, r)] for p in flujo_ref.index for i in flujo_compras.index if (p, i, r) in SETProdRefp_i_r.index ) )
    
    
    'xvii) Limite capacidad maxima de una refineria r'
    for r in CostosRef.index:
       Utilidad += ( Pr[r] <= CostosRef.loc[r,'Capacidad maxima de Refinacion (BPD)']  )
       Utilidad += ( Pr[r] >= CostosRef.loc[r,'Capacidad minima de Refinacion (BPD)']  )
       
    'xviii) NO EXISTE '
    
    'xix)Todo lo producido en refineria r se transporta a venta o a un centro de mezcla'
    for p, i, r  in SETProdRefp_i_r.index: 
        RHS8 = pulp.lpSum( [Pp_i_r_z_t[(p, i, r, z, t)]  for z in nodos_venta.index for t in vectort.index if  (p, i, r, z, t) in SETTranspp_i_r_z_t.index]
                          +[Pp_i_r_b_t[(p, i, r, b, t)]  for b in nodos_blend.index for t in vectort.index if  (p, i, r, b, t) in SETTranspp_i_r_b_t.index]
                          )
        Utilidad += ( Pp_i_r[(p, i, r)] == RHS8 )
        
    'xx) Balance de calculo de de producto refinado en centro de venta'
    for p, i, z  in SETVentap_i_z.index:    
         Utilidad += ( Pp_i_z[(p, i, z)] ==  pulp.lpSum( [Pp_i_r_z_t[(p, i, r, z, t)]  for r in nodos_ref.index for t in vectort.index if  (p, i, r, z, t) in SETTranspp_i_r_z_t.index] ) )
    
    
    '________________________________________________________________________________________________________________________________'   
    
    
    ' CALCULO DE CRUDOS VENDIDOS EN PUNTO DE VENTA '
    'xxi) Calculo de Crudo vendido en un punto de venta z'
    for i, z in SETVentai_z.index:
        RHS2 = pulp.lpSum( [Vi_c_z_t[(i, c, z, t)]  for c in nodos_origen.index for t in vectort.index if  (i, c, z, t) in SETTranspi_c_z_t.index] 
                         + [Vi_d_z_t[(i, d, z, t)]  for d in nodos_est.index for t in vectort.index if  (i, d, z, t) in SETTranspi_d_z_t.index] 
                         )
        Utilidad += ( CVi_z[(i, z)]  == RHS2 )
        
    '________________________________________________________________________________________________________________________________'   
    
    ' RESTRICCIONES DE CALCULO DE CALIDADES API , AZUFRE , DENSIDAD OBJETIVO'
    
    'xxii) Aseguramiento Calidad API limite inferior y Limite superior para cada mezcla en la estacion de blending b'   
    
    for m, b in SETBlendGlobalm_b.index:
        RHS9 =  pulp.lpSum( [Vi_b_m[(i, b, m)] * Compras1.loc[(i),'SPG'] for i in flujo_compras.index  if (i, b, m)   in SETCrudoBlendMezcla_i_b_m.index]
                          +  [Pp_i_b_m[(p, i, b, m)]  * CurvaDestilacion.loc[(p,i),'SPG'] for p, i in CurvaDestilacion.index  if (p, i, b, m)  in SETRefiBlendMezclap_i_b_m.index]
                          )
                                                                       
        Utilidad += ( RHS9 <= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MAXIMO CALIDAD SPG'] )            
        Utilidad += ( RHS9 >= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MINIMO CALIDAD SPG'] ) 
        
    
    'xxiii) Aseguramiento Calidad AZUFRE limite inferior y Limite superior para cada mezcla en la estacion de bleding b'   
    for m, b in SETBlendGlobalm_b.index:
        RHS10 =   pulp.lpSum( [Vi_b_m[(i, b, m)] * Compras1.loc[(i),'%AZUFRE'] for i in flujo_compras.index  if (i, b, m)   in SETCrudoBlendMezcla_i_b_m.index]
                            +  [Pp_i_b_m[(p, i, b, m)]  * CurvaDestilacion.loc[(p,i),'AZUFRE %'] for p, i in CurvaDestilacion.index  if (p, i, b, m)  in SETRefiBlendMezclap_i_b_m.index]
                            )
         
        Utilidad += ( RHS10 <= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MAXIMO CALIDAD AZUFRE'] )            
        Utilidad += ( RHS10 >= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MINIMO CALIDAD AZUFRE'] )  
    
    'xxii) Aseguramiento Indice V50  limite inferior y Limite superior para cada mezcla en la estacion de blending b'   
    
    for m, b in SETBlendGlobalm_b.index:
        RHS90 =  pulp.lpSum( [Vi_b_m[(i, b, m)] * Compras1.loc[(i),'Iv50'] * Compras1.loc[(i),'SPG'] for i in flujo_compras.index  if (i, b, m)   in SETCrudoBlendMezcla_i_b_m.index]
                          +  [Pp_i_b_m[(p, i, b, m)]  * CurvaDestilacion.loc[(p,i),'Iv50'] * CurvaDestilacion.loc[(p,i),'SPG']  for p, i in CurvaDestilacion.index  if (p, i, b, m)  in SETRefiBlendMezclap_i_b_m.index]
                          )
        
        AUX_SPGXVOL =  pulp.lpSum( [Vi_b_m[(i, b, m)] * Compras1.loc[(i),'SPG'] for i in flujo_compras.index  if (i, b, m)   in SETCrudoBlendMezcla_i_b_m.index]
                          +  [Pp_i_b_m[(p, i, b, m)]  * CurvaDestilacion.loc[(p,i),'SPG']  for p, i in CurvaDestilacion.index  if (p, i, b, m)  in SETRefiBlendMezclap_i_b_m.index]
                          )
                                                                       
        Utilidad += ( RHS90 <= AUX_SPGXVOL * LimitesCALIDADES.loc [(m ,b) , 'MAXIMO V50'] )            
        Utilidad += ( RHS90 >= AUX_SPGXVOL * LimitesCALIDADES.loc [(m ,b) , 'MINIMO V50'] )     
        
    'xxiii) Aseguramiento Calidad ACID NUMBER limite inferior y Limite superior para cada mezcla en la estacion de bleding b'   
    for m, b in SETBlendGlobalm_b.index:
        RHS101 =   pulp.lpSum( [Vi_b_m[(i, b, m)] * Compras1.loc[(i),'ACID NUMBER mg KOH/g'] for i in flujo_compras.index  if (i, b, m)   in SETCrudoBlendMezcla_i_b_m.index]
                            +  [Pp_i_b_m[(p, i, b, m)]  * CurvaDestilacion.loc[(p,i),'ACID NUMBER mg KOH/g'] for p, i in CurvaDestilacion.index  if (p, i, b, m)  in SETRefiBlendMezclap_i_b_m.index]
                            )
         
        Utilidad += ( RHS101 <= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MAXIMO CALIDAD ACID NUMBER mg KOH/g'] )            
        Utilidad += ( RHS101 >= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MINIMO CALIDAD ACID NUMBER mg KOH/g'] )  
    
    'xxiv) Aseguramiento Calidad  Accelerated Total Sediment limite inferior y Limite superior para cada mezcla en la estacion de bleding b'   
    for m, b in SETBlendGlobalm_b.index:
        RHS102 =   pulp.lpSum( [Vi_b_m[(i, b, m)] * Compras1.loc[(i),'Accelerated Total Sediment by Hot Filtration % m/m'] for i in flujo_compras.index  if (i, b, m)   in SETCrudoBlendMezcla_i_b_m.index]
                            +  [Pp_i_b_m[(p, i, b, m)]  * CurvaDestilacion.loc[(p,i),'Accelerated Total Sediment by Hot Filtration % m/m'] for p, i in CurvaDestilacion.index  if (p, i, b, m)  in SETRefiBlendMezclap_i_b_m.index]
                            )
         
        Utilidad += ( RHS102 <= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MAXIMO CALIDAD Accelerated Total Sediment by Hot Filtration % m/m'] )            
        Utilidad += ( RHS102 >= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MINIMO CALIDAD  Accelerated Total Sediment by Hot Filtration % m/m'] )      
    
    'xxv) Aseguramiento Calidad   Micro Carbon Residue % m/m  limite inferior y Limite superior para cada mezcla en la estacion de bleding b'   
    for m, b in SETBlendGlobalm_b.index:
        RHS103 =   pulp.lpSum( [Vi_b_m[(i, b, m)] * Compras1.loc[(i),'Micro Carbon Residue % m/m'] for i in flujo_compras.index  if (i, b, m)   in SETCrudoBlendMezcla_i_b_m.index]
                            +  [Pp_i_b_m[(p, i, b, m)]  * CurvaDestilacion.loc[(p,i),'Micro Carbon Residue % m/m'] for p, i in CurvaDestilacion.index  if (p, i, b, m)  in SETRefiBlendMezclap_i_b_m.index]
                            )
         
        Utilidad += ( RHS103 <= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MAXIMO CALIDAD   Micro Carbon Residue % m/m'] )            
        Utilidad += ( RHS103 >= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MINIMO CALIDAD  Micro Carbon Residue % m/m'] )      
    
    'xxvi) Aseguramiento Calidad   Water by Distillation % v/v  limite inferior y Limite superior para cada mezcla en la estacion de bleding b'   
    for m, b in SETBlendGlobalm_b.index:
        RHS104 =   pulp.lpSum( [Vi_b_m[(i, b, m)] * Compras1.loc[(i),'Water by Distillation % v/v'] for i in flujo_compras.index  if (i, b, m)   in SETCrudoBlendMezcla_i_b_m.index]
                            +  [Pp_i_b_m[(p, i, b, m)]  * CurvaDestilacion.loc[(p,i),'Water by Distillation % v/v'] for p, i in CurvaDestilacion.index  if (p, i, b, m)  in SETRefiBlendMezclap_i_b_m.index]
                            )
         
        Utilidad += ( RHS104 <= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MAXIMO CALIDAD Water by Distillation % v/v'] )            
        Utilidad += ( RHS104 >= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MINIMO CALIDAD Water by Distillation % v/v'] )      
     
    'xxvii) Aseguramiento Calidad   Ash Content % m/m  limite inferior y Limite superior para cada mezcla en la estacion de bleding b'   
    for m, b in SETBlendGlobalm_b.index:
        RHS105 =   pulp.lpSum( [Vi_b_m[(i, b, m)] * Compras1.loc[(i),'Ash Content % m/m'] for i in flujo_compras.index  if (i, b, m)   in SETCrudoBlendMezcla_i_b_m.index]
                            +  [Pp_i_b_m[(p, i, b, m)]  * CurvaDestilacion.loc[(p,i),'Ash Content % m/m'] for p, i in CurvaDestilacion.index  if (p, i, b, m)  in SETRefiBlendMezclap_i_b_m.index]
                            )
         
        Utilidad += ( RHS105 <= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MAXIMO CALIDAD  Ash Content % m/m'] )            
        Utilidad += ( RHS105 >= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MINIMO CALIDAD  Ash Content % m/m'] )      
    
    'xxviii) Aseguramiento Calidad   Vanadium (V) mg/kg  limite inferior y Limite superior para cada mezcla en la estacion de bleding b'   
    for m, b in SETBlendGlobalm_b.index:
        RHS106 =   pulp.lpSum( [Vi_b_m[(i, b, m)] * Compras1.loc[(i),'Vanadium (V) mg/kg'] for i in flujo_compras.index  if (i, b, m)   in SETCrudoBlendMezcla_i_b_m.index]
                            +  [Pp_i_b_m[(p, i, b, m)]  * CurvaDestilacion.loc[(p,i),'Vanadium (V) mg/kg'] for p, i in CurvaDestilacion.index  if (p, i, b, m)  in SETRefiBlendMezclap_i_b_m.index]
                            )
         
        Utilidad += ( RHS106 <= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MAXIMO CALIDAD Vanadium (V) mg/kg'] )            
        Utilidad += ( RHS106 >= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MINIMO CALIDAD Vanadium (V) mg/kg'] )      
    
    'xxix) Aseguramiento Calidad   Sodium (Na) mg/kg  limite inferior y Limite superior para cada mezcla en la estacion de bleding b'   
    for m, b in SETBlendGlobalm_b.index:
        RHS107 =   pulp.lpSum( [Vi_b_m[(i, b, m)] * Compras1.loc[(i),'Sodium (Na) mg/kg'] for i in flujo_compras.index  if (i, b, m)   in SETCrudoBlendMezcla_i_b_m.index]
                            +  [Pp_i_b_m[(p, i, b, m)]  * CurvaDestilacion.loc[(p,i),'Sodium (Na) mg/kg'] for p, i in CurvaDestilacion.index  if (p, i, b, m)  in SETRefiBlendMezclap_i_b_m.index]
                            )
         
        Utilidad += ( RHS107 <= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MAXIMO CALIDAD Sodium (Na) mg/kg'] )            
        Utilidad += ( RHS107 >= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MINIMO CALIDAD Sodium (Na) mg/kg'] )  
    
    'xxxi) Aseguramiento Calidad   Aluminum (Al)  mg/kg  limite inferior y Limite superior para cada mezcla en la estacion de bleding b'   
    for m, b in SETBlendGlobalm_b.index:
        RHS108 =   pulp.lpSum( [Vi_b_m[(i, b, m)] * Compras1.loc[(i),'Aluminum (Al)  mg/kg'] for i in flujo_compras.index  if (i, b, m)   in SETCrudoBlendMezcla_i_b_m.index]
                            +  [Pp_i_b_m[(p, i, b, m)]  * CurvaDestilacion.loc[(p,i),'Aluminum (Al)  mg/kg'] for p, i in CurvaDestilacion.index  if (p, i, b, m)  in SETRefiBlendMezclap_i_b_m.index]
                            )
         
        Utilidad += ( RHS108 <= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MAXIMO CALIDAD Aluminum (Al) mg/kg'] )            
        Utilidad += ( RHS108 >= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MINIMO CALIDAD Aluminum (Al)  mg/kg'] )  
    
    'xxxii) Aseguramiento Calidad   Silicon (Si) mg/kg  limite inferior y Limite superior para cada mezcla en la estacion de bleding b'   
    for m, b in SETBlendGlobalm_b.index:
        RHS109 =   pulp.lpSum( [Vi_b_m[(i, b, m)] * Compras1.loc[(i),'Silicon (Si) mg/kg'] for i in flujo_compras.index  if (i, b, m)   in SETCrudoBlendMezcla_i_b_m.index]
                            +  [Pp_i_b_m[(p, i, b, m)]  * CurvaDestilacion.loc[(p,i),'Silicon (Si) mg/kg'] for p, i in CurvaDestilacion.index  if (p, i, b, m)  in SETRefiBlendMezclap_i_b_m.index]
                            )
         
        Utilidad += ( RHS109 <= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MAXIMO CALIDAD Silicon (Si) mg/kg'] )            
        Utilidad += ( RHS109 >= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MINIMO CALIDAD Silicon (Si) mg/kg'] )  
    
    'xxxiii) Aseguramiento Calidad   Aluminum plus Silicon mg/kg limite inferior y Limite superior para cada mezcla en la estacion de bleding b'   
    for m, b in SETBlendGlobalm_b.index:
        RHS110 =   pulp.lpSum( [Vi_b_m[(i, b, m)] * Compras1.loc[(i),'Aluminum plus Silicon mg/kg'] for i in flujo_compras.index  if (i, b, m)   in SETCrudoBlendMezcla_i_b_m.index]
                            +  [Pp_i_b_m[(p, i, b, m)]  * CurvaDestilacion.loc[(p,i),'Aluminum plus Silicon mg/kg'] for p, i in CurvaDestilacion.index  if (p, i, b, m)  in SETRefiBlendMezclap_i_b_m.index]
                            )
         
        Utilidad += ( RHS110 <= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MAXIMO CALIDAD Aluminum plus Silicon mg/kg'] )            
        Utilidad += ( RHS110 >= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MINIMO CALIDAD Aluminum plus Silicon mg/kg'] )  
    
    'xxxiv) Aseguramiento Calidad   Calcium (Ca)  mg/kg  limite inferior y Limite superior para cada mezcla en la estacion de bleding b'   
    for m, b in SETBlendGlobalm_b.index:
        RHS111 =   pulp.lpSum( [Vi_b_m[(i, b, m)] * Compras1.loc[(i),'Calcium (Ca)  mg/kg'] for i in flujo_compras.index  if (i, b, m)   in SETCrudoBlendMezcla_i_b_m.index]
                            +  [Pp_i_b_m[(p, i, b, m)]  * CurvaDestilacion.loc[(p,i),'Calcium (Ca)  mg/kg'] for p, i in CurvaDestilacion.index  if (p, i, b, m)  in SETRefiBlendMezclap_i_b_m.index]
                            )
         
        Utilidad += ( RHS111 <= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MAXIMO CALIDAD Calcium (Ca)   mg/kg'] )            
        Utilidad += ( RHS111 >= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MINIMO CALIDAD Calcium (Ca)  mg/kg'] )  
    
    'xxxv) Aseguramiento Calidad   Zinc (Zn)  mg/kg  limite inferior y Limite superior para cada mezcla en la estacion de bleding b'   
    for m, b in SETBlendGlobalm_b.index:
        RHS112 =   pulp.lpSum( [Vi_b_m[(i, b, m)] * Compras1.loc[(i),'Zinc (Zn)  mg/kg'] for i in flujo_compras.index  if (i, b, m)   in SETCrudoBlendMezcla_i_b_m.index]
                            +  [Pp_i_b_m[(p, i, b, m)]  * CurvaDestilacion.loc[(p,i),'Zinc (Zn)  mg/kg'] for p, i in CurvaDestilacion.index  if (p, i, b, m)  in SETRefiBlendMezclap_i_b_m.index]
                            )
         
        Utilidad += ( RHS112 <= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MAXIMO CALIDAD Zinc (Zn)  mg/kg'] )            
        Utilidad += ( RHS112 >= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MINIMO CALIDAD Zinc (Zn)  mg/kg'] )  
    
    'xxxvi) Aseguramiento Calidad   Phosphorus (P)   mg/kg  limite inferior y Limite superior para cada mezcla en la estacion de bleding b'   
    for m, b in SETBlendGlobalm_b.index:
        RHS113 =   pulp.lpSum( [Vi_b_m[(i, b, m)] * Compras1.loc[(i),'Phosphorus (P)   mg/kg'] for i in flujo_compras.index  if (i, b, m)   in SETCrudoBlendMezcla_i_b_m.index]
                            +  [Pp_i_b_m[(p, i, b, m)]  * CurvaDestilacion.loc[(p,i),'Phosphorus (P)   mg/kg'] for p, i in CurvaDestilacion.index  if (p, i, b, m)  in SETRefiBlendMezclap_i_b_m.index]
                            )
         
        Utilidad += ( RHS113 <= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MAXIMO CALIDAD Phosphorus (P)    mg/kg'] )            
        Utilidad += ( RHS113 >= Mm_b[(m, b)] * LimitesCALIDADES.loc [(m ,b) , 'MINIMO CALIDAD Phosphorus (P)   mg/kg'] )         
    
    
    
        
    #'xxiv) Asrguramiento densidad entregada <=  denisdad contractual '  
    #for m, b in SUBSET_DENS_BlendGlobalm_b.index:
    #   RHS33 = pulp.lpSum( [Vi_b_m[(i, b, m)] * Compras1.loc[(i), 'DENSIDAD  (BBL/TONMETRICA)']  for i in flujo_compras.index  if  (i, b, m) in SUBSET_DENS_CrudoBlendMezcla_i_b_m.index ]  
    #                      + [Pp_i_b_m[(p, i, b, m)]  * CurvaDestilacion.loc[(p,i), 'DENSIDAD (BBL/TONMETRICA)'] for p in flujo_ref.index for i in flujo_compras.index if (p, i, b, m) in SUBSET_DENS_RefiBlendMezclap_i_b_m.index]
    #                       )
    #   Utilidad += ( RHS33 <= SUBSETVentaDENm_b.loc[(m,b),'Densidad (BBL/TONMetrica) Contractual']   * Mm_b[(m, b)] )      
    
    
    
    '________________________________________________________________________________________________________________________________'   
    
    '     RESTRICCIONES DE CALCULO DE CVC  '
    
    'xxxvii) Calculo VOL CVC POR CRUDO'
    for i, b, m in SETCVCCRUDOi_b_m.index:
    
       Utilidad += (VCVCi_b_m[(i, b, m)] ==  Vi_b_m[(i, b, m)] * SETCVCCRUDOi_b_m.loc[(i , b, m) , 'FACTOR CVC'] ) 
        
    'xxxviii) Calculo VOL CVC POR refinado'
    for p, i, b, m in SETCVCREFIp_i_b_m.index:
    
       Utilidad += (PCVCp_i_b_m[(p, i, b, m)] ==  Pp_i_b_m[(p, i, b,m)] * SETCVCREFIp_i_b_m.loc[(p, i ,b, m) , 'FACTOR CVC'] )    
    
    'xxxix) Balance de creacion de mezcla CVC: Calcula El volumen de una mezcla producida es la suma de crudos/productos + refinados'  
    for m, b in SUBSETCVCmezclab_m.index:
       RHS51 = pulp.lpSum( [VCVCi_b_m[(i, b, m )] for i in flujo_compras.index  if  (i, b, m ) in SETCVCCRUDOi_b_m.index]
                        + [PCVCp_i_b_m [(p, i, b, m)] for p in flujo_ref.index for i in flujo_compras.index if  (p, i, b, m) in SETCVCREFIp_i_b_m.index]
                         )
       Utilidad += ( MCVCm_b[(m, b)] == RHS51 ) 
       
    'xl) Toda Mezcla CVC Producida  es transportado'
    for m, b in SUBSETCVCmezclab_m.index:
        RHS441 = pulp.lpSum( [MCVCm_b_z_t[(m, b, z, t)] for z in nodos_venta.index for t in vectort.index if  (m, b, z, t) in SUBSETTransCVCpm_b_z_t.index]
                          )
        Utilidad += ( MCVCm_b[(m, b)] == RHS441 ) 
        
        
    'xli) Todo lo transporatado CVC se vende '
    for m, z in SUBSETVentaCVCm_z.index:
        RHS551 = pulp.lpSum( [MCVCm_b_z_t[(m, b, z, t)] for b in nodos_blend.index for t in vectort.index if  (m, b, z, t) in SUBSETTransCVCpm_b_z_t.index]
                          )
        Utilidad += ( MCVCm_z[(m, z)]== RHS551 )    
    
    'ii) Demanda. No se vende mas del limite comercial segunda parte para blend Espcieal formula densidad'
    for m, z in SUBSETVentaCVCm_z.index:
        Maxdisponibledc = SUBSETVentaCVCm_z.loc[(m,z),'Volumen Maximo a Venta (Si aplica)  (BPD)']
        Utilidad += ( MCVCm_z[(m, z)] <= Maxdisponibledc )
    '________________________________________________________________________________________________________________________________'   
       
    'xxxvii) Calculo del throughput de un Nodo de Blending'
    for b in CostosOPERA.index:
       Utilidad += ( Vb[b] ==  pulp.lpSum( Vi_b[(i, b)] for i in flujo_compras.index if (i,b) in SETCrudoBlend_i_b.index ) )
    
    'xxxviii) Calculo del throughput de un Nodo de Blending para refinados'
    for b in CostosOPERA.index:
       Utilidad += ( Pb[b] ==  pulp.lpSum( Pp_i_r_b_t[(p, i, r, b, t)]for p in flujo_ref.index for i in flujo_compras.index for r in nodos_ref.index for t in vectort.index if  (p, i, r, b, t) in SUBSETTransREFIOPp_i_r_b_t.index))
    
    'xxxviX) Calculo del throughput de un Nodo de Blending para refinados NORMALES'
    for b in CostosOPERA.index:
       Utilidad += ( PNORMALb[b] ==  pulp.lpSum( Pp_i_r_b_t[(p, i, r, b, t)]for p in flujo_ref.index for i in flujo_compras.index for r in nodos_ref.index for t in vectort.index if  (p, i, r, b, t) in SUBSETTransREFIREGOPp_i_r_b_t.index))
    
    
    ' xxxIV) Aseguramiento de entrada por Flash Point '  
    for i, b in SETCRUDOBLENDFLASHi_b.index:
    
       Utilidad += ( Vi_b[(i, b)] * SETCRUDOBLENDFLASHi_b.loc [(i ,b) , 'BINARY COND'] >=  Vi_b[(i, b)] ) 
    
          
        
    'PART5: Instrucciones de corrida'
    '_______________________________________________________________________________________________________________________________________________'
        
            
    # The problem data is written to an .lp file

    # Solve using CBC solver with 120 seconds limit
    Utilidad.solve(PULP_CBC_CMD(msg=0, timeLimit=120))
    status = LpStatus[Utilidad.status]
    
    if status in ['Undefined', 'Not Solved']:
        return sanitize_nans({
            'status': status,
            'utilidad_total': 0.0,
            'vol_compras_total': 0.0,
            'vol_ventas_total': 0.0,
            'compras': [],
            'ventas': [],
            'transporte': [],
            'refinacion': [],
            'throughput': [],
            'blending': [],
            'costos_operacionales': [],
            'costos_operacionales_ref': [],
            'composicion_blending': []
        })
        
    try:
        utilidad_total = float(value(Utilidad.objective)) if value(Utilidad.objective) is not None else 0.0
    except Exception:
        utilidad_total = 0.0

    def _safe_positive_float(value):
        try:
            v = float(value)
            return v if v > 0 else None
        except Exception:
            return None

    def _kg_per_gal_from_density(density_bbl_per_ton):
        dens = _safe_positive_float(density_bbl_per_ton)
        if dens is None:
            return None
        # kg/gal = (kg/bbl) / 42; kg/bbl = 1000 / (bbl/ton)
        return 1000.0 / (dens * 42.0)

    def _tpd_from_bpd(vol_bpd, density_bbl_per_ton):
        dens = _safe_positive_float(density_bbl_per_ton)
        vol = _safe_positive_float(vol_bpd)
        if dens is None or vol is None:
            return None
        return vol / dens

    def _density_from_compra(flow_name):
        try:
            return _safe_positive_float(Compras1.loc[(flow_name), 'DENSIDAD  (BBL/TONMETRICA)'])
        except Exception:
            return None

    def _density_from_refinado(prod_name, crude_name):
        try:
            return _safe_positive_float(CurvaDestilacion.loc[(prod_name, crude_name), 'DENSIDAD (BBL/TONMETRICA)'])
        except Exception:
            return None
    
    # 1. Compras Table Extraction
    compras_list = []
    for i, c, v in Ci_c_v:
        vol = Ci_c_v[(i, c, v)].varValue
        if vol is not None and vol > 0.001:
            variant_meta = compra_variant_meta.get((i, c, v), {})
            variants_count = len(compra_variants_by_ic.get((i, c), []))
            display_flow = str(i)
            if variants_count > 1:
                display_flow = f"{i} [{variant_meta.get('etiqueta_variacion', v)}]"

            price = float(Compras.loc[(i, c), 'Precio de Compra CALCULADO  (USD/BPD)'])
            density = _safe_positive_float(Compras.loc[(i, c), 'DENSIDAD  (BBL/TONMETRICA)'])
            kg_per_gal = _kg_per_gal_from_density(density)
            weight_tpd = _tpd_from_bpd(vol, density)
            compras_list.append({
                'Crudo o Producto': display_flow,
                'Origen': str(c),
                'Flujo Base Premium': str(i),
                'Origen Base Premium': str(c),
                'Variante Transporte': variant_meta.get('etiqueta_variacion', 'SIN RUTA'),
                'Volumen Comprado BPD': float(vol),
                'Precio Compra USD/BBL': price,
                'Costo Total USD': float(vol * price),
                'Densidad BBL/TON': density,
                'Peso por Galon kg/gal': kg_per_gal,
                'Peso Comprado TPD': weight_tpd
            })
    compras_list = sorted(compras_list, key=lambda x: (x.get('Flujo Base Premium', ''), x['Origen'], x.get('Variante Transporte', '')))
    
    # 2. Ventas Table Extraction
    # 2.1 Ventas mezcla normal
    ventas_list = []
    for m, z in Mm_z:
        vol = Mm_z[(m, z)].varValue
        if vol is not None and vol > 0.001:
            if (m, z) in SUBSETVentaNormalm_z.index:
                price = float(SUBSETVentaNormalm_z.loc[(m, z), 'Precio de venta (USD/BPD)'])
                ventas_list.append({
                    'Corriente Venta': str(m),
                    'Punto de Venta': str(z),
                    'Volumen Vendido BPD': float(vol),
                    'Precio de venta USD/BBL': price,
                    'Costo Total': float(vol * price),
                    'Densidad Contractual BBL/TON': 0.0,
                    'Densidad Entregada BBL/TON': 0.0,
                    'Ingreso Con Densidad Contractual (USD)': float(vol * price),
                    'Ingreso TEORICO Sin Densidad Contractual (USD)': float(vol * price),
                    'Δ(Ingreso Con Densidad Contractual - Ingreso Sin Densidad Contractual)(USD)': 0.0,
                    'Crudo Origen(SoloRefinados)': ''
                })
                
    # 2.1.1 Ventas mezcla CVC
    for m, z in MCVCm_z:
        vol = MCVCm_z[(m, z)].varValue
        if vol is not None and vol > 0.001:
            if (m, z) in SUBSETVentaCVCm_z.index:
                price = float(SUBSETVentaCVCm_z.loc[(m, z), 'Precio de venta (USD/BPD)'])
                ventas_list.append({
                    'Corriente Venta': str(m),
                    'Punto de Venta': str(z),
                    'Volumen Vendido BPD': float(vol),
                    'Precio de venta USD/BBL': price,
                    'Costo Total': float(vol * price),
                    'Densidad Contractual BBL/TON': 0.0,
                    'Densidad Entregada BBL/TON': 0.0,
                    'Ingreso Con Densidad Contractual (USD)': float(vol * price),
                    'Ingreso TEORICO Sin Densidad Contractual (USD)': float(vol * price),
                    'Δ(Ingreso Con Densidad Contractual - Ingreso Sin Densidad Contractual)(USD)': 0.0,
                    'Crudo Origen(SoloRefinados)': ''
                })
                
    # 2.2 Ventas crudo
    for i, z in CVi_z:
        vol = CVi_z[(i, z)].varValue
        if vol is not None and vol > 0.001:
            price = float(SETVentai_z.loc[(i, z), 'Precio de venta (USD/BPD)'])
            dens_contr = float(SETVentai_z.loc[(i, z), 'Densidad (BBL/TONMetrica) Contractual'])
            dens_entreg = float(SETVentai_z.loc[(i, z), 'CRUDO: DENSIDAD  (BBL/TONMETRICA)'])
            ventas_list.append({
                'Corriente Venta': str(i),
                'Punto de Venta': str(z),
                'Volumen Vendido BPD': float(vol),
                'Precio de venta USD/BBL': price,
                'Costo Total': float(vol * price),
                'Densidad Contractual BBL/TON': dens_contr,
                'Densidad Entregada BBL/TON': dens_entreg,
                'Ingreso Con Densidad Contractual (USD)': float(vol * price * dens_contr / dens_entreg) if dens_entreg > 0 else 0.0,
                'Ingreso TEORICO Sin Densidad Contractual (USD)': float(vol * price),
                'Δ(Ingreso Con Densidad Contractual - Ingreso Sin Densidad Contractual)(USD)': float(vol * price * ((dens_contr / dens_entreg) - 1)) if dens_entreg > 0 else 0.0,
                'Crudo Origen(SoloRefinados)': ''
            })
            
    # 2.3 Ventas refinados
    for p, i, z in Pp_i_z:
        vol = Pp_i_z[(p, i, z)].varValue
        if vol is not None and vol > 0.001:
            price = float(SETVentap_i_z.loc[(p, i, z), 'Precio de venta (USD/BPD)'])
            dens_contr = float(SETVentap_i_z.loc[(p, i, z), 'Densidad (BBL/TONMetrica) Contractual'])
            dens_entreg = float(SETVentap_i_z.loc[(p, i, z), 'REFINADO: DENSIDAD  (BBL/TONMETRICA)'])
            ventas_list.append({
                'Corriente Venta': str(p),
                'Punto de Venta': str(z),
                'Volumen Vendido BPD': float(vol),
                'Precio de venta USD/BBL': price,
                'Costo Total': float(vol * price),
                'Densidad Contractual BBL/TON': dens_contr,
                'Densidad Entregada BBL/TON': dens_entreg,
                'Ingreso Con Densidad Contractual (USD)': float(vol * price * dens_contr / dens_entreg) if dens_entreg > 0 else 0.0,
                'Ingreso TEORICO Sin Densidad Contractual (USD)': float(vol * price),
                'Δ(Ingreso Con Densidad Contractual - Ingreso Sin Densidad Contractual)(USD)': float(vol * price * ((dens_contr / dens_entreg) - 1)) if dens_entreg > 0 else 0.0,
                'Crudo Origen(SoloRefinados)': str(i)
            })
            
    # 2.4 Ventas mezcla formula densidad
    # Pre-calcular densidades resultantes de mezclas
    DENm_bE = {}
    DENdfE_records = {}
    for m, b in SUBSET_DENS_BlendGlobalm_b.index:
        vol_mb = Mm_b[(m, b)].varValue
        if vol_mb is not None and vol_mb > 0:
            RHS33 = sum([Vi_b_m[(i, b, m)].varValue * Compras1.loc[(i), 'SPG'] for i in flujo_compras.index if (i, b, m) in SETCrudoBlendMezcla_i_b_m.index]
                        + [Pp_i_b_m[(p, i, b, m)].varValue * CurvaDestilacion.loc[(p, i), 'SPG'] for p, i in CurvaDestilacion.index if (p, i, b, m) in SETRefiBlendMezclap_i_b_m.index])
            if RHS33 > 0:
                DENCALCE = (vol_mb * 6.2898) / RHS33
                if (m, b) in SUBSETVentaDENm_b.index:
                    price = float(SUBSETVentaDENm_b.loc[(m, b), 'Precio de venta (USD/BPD)'])
                    dens_contr = float(SUBSETVentaDENm_b.loc[(m, b), 'Densidad (BBL/TONMetrica) Contractual'])
                    ingreso_con = float(vol_mb * price * dens_contr / DENCALCE)
                    ingreso_sin = float(vol_mb * price)
                    dif_ing = ingreso_con - ingreso_sin
                else:
                    price = 0.0
                    dens_contr = 0.0
                    ingreso_con = 0.0
                    ingreso_sin = 0.0
                    dif_ing = 0.0
                
                DENm_bE[(m, b)] = DENCALCE
                DENdfE_records[(m, b)] = {
                    'Densidad Entregada BBL/TON': float(DENCALCE),
                    'Ingreso Con Densidad Contractual (USD)': ingreso_con,
                    'Ingreso TEORICO Sin Densidad Contractual (USD)': ingreso_sin,
                    'Δ(Ingreso Con Densidad Contractual - Ingreso Sin Densidad Contractual)(USD)': dif_ing
                }
                
    for m, b in Mm_b:
        vol = Mm_b[(m, b)].varValue
        if vol is not None and vol > 0.001:
            if (m, b) in SUBSETVentaDENm_b.index:
                price = float(SUBSETVentaDENm_b.loc[(m, b), 'Precio de venta (USD/BPD)'])
                dens_contr = float(SUBSETVentaDENm_b.loc[(m, b), 'Densidad (BBL/TONMetrica) Contractual'])
                dens_calc_info = DENdfE_records.get((m, b), {
                    'Densidad Entregada BBL/TON': 0.0,
                    'Ingreso Con Densidad Contractual (USD)': float(vol * price),
                    'Ingreso TEORICO Sin Densidad Contractual (USD)': float(vol * price),
                    'Δ(Ingreso Con Densidad Contractual - Ingreso Sin Densidad Contractual)(USD)': 0.0
                })
                ventas_list.append({
                    'Corriente Venta': str(m),
                    'Punto de Venta': str(b),
                    'Volumen Vendido BPD': float(vol),
                    'Precio de venta USD/BBL': price,
                    'Costo Total': float(vol * price),
                    'Densidad Contractual BBL/TON': dens_contr,
                    'Densidad Entregada BBL/TON': dens_calc_info['Densidad Entregada BBL/TON'],
                    'Ingreso Con Densidad Contractual (USD)': dens_calc_info['Ingreso Con Densidad Contractual (USD)'],
                    'Ingreso TEORICO Sin Densidad Contractual (USD)': dens_calc_info['Ingreso TEORICO Sin Densidad Contractual (USD)'],
                    'Δ(Ingreso Con Densidad Contractual - Ingreso Sin Densidad Contractual)(USD)': dens_calc_info['Δ(Ingreso Con Densidad Contractual - Ingreso Sin Densidad Contractual)(USD)'],
                    'Crudo Origen(SoloRefinados)': ''
                })
                
    # 3. Transporte Table Extraction
    transporte_list = []
    # 3.1 Vi_c_b_t
    for i, c, b, t in Vi_c_b_t:
        vol = Vi_c_b_t[(i, c, b, t)].varValue
        if vol is not None and vol > 0.001:
            rate = float(SETTranspi_c_b_t.loc[(i, c, b, t), 'Costo de transporte USD/BBL para modelo'])
            density = _density_from_compra(i)
            transporte_list.append({
                'Flujo': str(i),
                'Origen': str(c),
                'Destino': str(b),
                'Ruta': str(t),
                'Volumen Transportado BPD': float(vol),
                'Costo de transporte USD/BBL': rate,
                'Costo Total USD': float(vol * rate),
                'Densidad BBL/TON': density,
                'Peso por Galon kg/gal': _kg_per_gal_from_density(density),
                'Peso Transportado TPD': _tpd_from_bpd(vol, density)
            })
    # 3.2 Vi_c_z_t
    for i, c, z, t in Vi_c_z_t:
        vol = Vi_c_z_t[(i, c, z, t)].varValue
        if vol is not None and vol > 0.001:
            rate = float(SETTranspi_c_z_t.loc[(i, c, z, t), 'Costo de transporte USD/BBL para modelo'])
            density = _density_from_compra(i)
            transporte_list.append({
                'Flujo': str(i),
                'Origen': str(c),
                'Destino': str(z),
                'Ruta': str(t),
                'Volumen Transportado BPD': float(vol),
                'Costo de transporte USD/BBL': rate,
                'Costo Total USD': float(vol * rate),
                'Densidad BBL/TON': density,
                'Peso por Galon kg/gal': _kg_per_gal_from_density(density),
                'Peso Transportado TPD': _tpd_from_bpd(vol, density)
            })
    # 3.3 Vi_c_d_t
    for i, c, d, t in Vi_c_d_t:
        vol = Vi_c_d_t[(i, c, d, t)].varValue
        if vol is not None and vol > 0.001:
            rate = float(SETTranspi_c_d_t.loc[(i, c, d, t), 'Costo de transporte USD/BBL para modelo'])
            density = _density_from_compra(i)
            transporte_list.append({
                'Flujo': str(i),
                'Origen': str(c),
                'Destino': str(d),
                'Ruta': str(t),
                'Volumen Transportado BPD': float(vol),
                'Costo de transporte USD/BBL': rate,
                'Costo Total USD': float(vol * rate),
                'Densidad BBL/TON': density,
                'Peso por Galon kg/gal': _kg_per_gal_from_density(density),
                'Peso Transportado TPD': _tpd_from_bpd(vol, density)
            })
    # 3.4 Vi_c_r_t
    for i, c, r, t in Vi_c_r_t:
        vol = Vi_c_r_t[(i, c, r, t)].varValue
        if vol is not None and vol > 0.001:
            rate = float(SETTranspi_c_r_t.loc[(i, c, r, t), 'Costo de transporte USD/BBL para modelo'])
            density = _density_from_compra(i)
            transporte_list.append({
                'Flujo': str(i),
                'Origen': str(c),
                'Destino': str(r),
                'Ruta': str(t),
                'Volumen Transportado BPD': float(vol),
                'Costo de transporte USD/BBL': rate,
                'Costo Total USD': float(vol * rate),
                'Densidad BBL/TON': density,
                'Peso por Galon kg/gal': _kg_per_gal_from_density(density),
                'Peso Transportado TPD': _tpd_from_bpd(vol, density)
            })
    # 3.5 Vi_d_z_t
    for i, d, z, t in Vi_d_z_t:
        vol = Vi_d_z_t[(i, d, z, t)].varValue
        if vol is not None and vol > 0.001:
            rate = float(SETTranspi_d_z_t.loc[(i, d, z, t), 'Costo de transporte USD/BBL para modelo'])
            density = _density_from_compra(i)
            transporte_list.append({
                'Flujo': str(i),
                'Origen': str(d),
                'Destino': str(z),
                'Ruta': str(t),
                'Volumen Transportado BPD': float(vol),
                'Costo de transporte USD/BBL': rate,
                'Costo Total USD': float(vol * rate),
                'Densidad BBL/TON': density,
                'Peso por Galon kg/gal': _kg_per_gal_from_density(density),
                'Peso Transportado TPD': _tpd_from_bpd(vol, density)
            })
    # 3.6 Vi_d_b_t
    for i, d, b, t in Vi_d_b_t:
        vol = Vi_d_b_t[(i, d, b, t)].varValue
        if vol is not None and vol > 0.001:
            rate = float(SETTranspi_d_b_t.loc[(i, d, b, t), 'Costo de transporte USD/BBL para modelo'])
            density = _density_from_compra(i)
            transporte_list.append({
                'Flujo': str(i),
                'Origen': str(d),
                'Destino': str(b),
                'Ruta': str(t),
                'Volumen Transportado BPD': float(vol),
                'Costo de transporte USD/BBL': rate,
                'Costo Total USD': float(vol * rate),
                'Densidad BBL/TON': density,
                'Peso por Galon kg/gal': _kg_per_gal_from_density(density),
                'Peso Transportado TPD': _tpd_from_bpd(vol, density)
            })
    # 3.7 Vi_d_r_t
    for i, d, r, t in Vi_d_r_t:
        vol = Vi_d_r_t[(i, d, r, t)].varValue
        if vol is not None and vol > 0.001:
            rate = float(SETTranspi_d_r_t.loc[(i, d, r, t), 'Costo de transporte USD/BBL para modelo'])
            density = _density_from_compra(i)
            transporte_list.append({
                'Flujo': str(i),
                'Origen': str(d),
                'Destino': str(r),
                'Ruta': str(t),
                'Volumen Transportado BPD': float(vol),
                'Costo de transporte USD/BBL': rate,
                'Costo Total USD': float(vol * rate),
                'Densidad BBL/TON': density,
                'Peso por Galon kg/gal': _kg_per_gal_from_density(density),
                'Peso Transportado TPD': _tpd_from_bpd(vol, density)
            })
    # 3.8 Pp_i_r_z_t
    for p, i, r, z, t in Pp_i_r_z_t:
        vol = Pp_i_r_z_t[(p, i, r, z, t)].varValue
        if vol is not None and vol > 0.001:
            rate = float(SETTranspp_i_r_z_t.loc[(p, i, r, z, t), 'Costo de transporte USD/BBL para modelo'])
            density = _density_from_refinado(p, i)
            transporte_list.append({
                'Flujo': str(p),
                'Origen': str(r),
                'Destino': str(z),
                'Ruta': str(t),
                'Volumen Transportado BPD': float(vol),
                'Costo de transporte USD/BBL': rate,
                'Costo Total USD': float(vol * rate),
                'Densidad BBL/TON': density,
                'Peso por Galon kg/gal': _kg_per_gal_from_density(density),
                'Peso Transportado TPD': _tpd_from_bpd(vol, density)
            })
    # 3.9 Pp_i_r_b_t
    for p, i, r, b, t in Pp_i_r_b_t:
        vol = Pp_i_r_b_t[(p, i, r, b, t)].varValue
        if vol is not None and vol > 0.001:
            rate = float(SETTranspp_i_r_b_t.loc[(p, i, r, b, t), 'Costo de transporte USD/BBL para modelo'])
            density = _density_from_refinado(p, i)
            transporte_list.append({
                'Flujo': str(p),
                'Origen': str(r),
                'Destino': str(b),
                'Ruta': str(t),
                'Volumen Transportado BPD': float(vol),
                'Costo de transporte USD/BBL': rate,
                'Costo Total USD': float(vol * rate),
                'Densidad BBL/TON': density,
                'Peso por Galon kg/gal': _kg_per_gal_from_density(density),
                'Peso Transportado TPD': _tpd_from_bpd(vol, density)
            })
    # 3.10 Mm_b_z_t
    for m, b, z, t in Mm_b_z_t:
        vol = Mm_b_z_t[(m, b, z, t)].varValue
        if vol is not None and vol > 0.001:
            rate = float(SETTranspm_b_z_t.loc[(m, b, z, t), 'Costo de transporte USD/BBL para modelo'])
            transporte_list.append({
                'Flujo': str(m),
                'Origen': str(b),
                'Destino': str(z),
                'Ruta': str(t),
                'Volumen Transportado BPD': float(vol),
                'Costo de transporte USD/BBL': rate,
                'Costo Total USD': float(vol * rate),
                'Densidad BBL/TON': None,
                'Peso por Galon kg/gal': None,
                'Peso Transportado TPD': None
            })
            
    # 4. Refinacion Table Extraction
    refinacion_list = []
    for p, i, r in Pp_i_r:
        vol = Pp_i_r[(p, i, r)].varValue
        if vol is not None and vol > 0.001:
            refinacion_list.append({
                'Producto Refinado': str(p),
                'Crudo Origen': str(i),
                'Planta de Refinacion': str(r),
                'Volumen Producido BPD': float(vol)
            })
            
    # 5. Throughput Table Extraction
    throughput_list = []
    for r in Pr:
        vol = Pr[(r)].varValue
        if vol is not None and vol > 0.001:
            rate = float(CostosRef.loc[r, 'Costo de refinacion (USD/BPD)'])
            throughput_list.append({
                'Refineria': str(r),
                'Throughput Refineria BPD': float(vol),
                'Costo de Refinacion USD/BPD': rate,
                'Costo Total USD': float(vol * rate)
            })
            
    # 6. Blending Quality Calculations and Table Extraction
    blending_list = []
    for m, b in Mm_b:
        vol = Mm_b[(m, b)].varValue
        if vol is not None and vol > 0.001:
            record = {
                'Mezcla': str(m),
                'Centro de Blending': str(b),
                'Volumen BPD': float(vol),
                'API': 0.0,
                '%AZUFRE': 0.0,
                'Viscosidad Cst': 0.0,
                'ACID NUMBER mg KOH/g': 0.0,
                'Accelerated Total Sediment by Hot Filtration % m/m': 0.0,
                'Micro Carbon Residue % m/m': 0.0,
                'Water by Distillation % v/v': 0.0,
                'Ash Content % m/m': 0.0,
                'Vanadium (V) mg/kg': 0.0,
                'Sodium (Na) mg/kg': 0.0,
                'Aluminum (Al)  mg/kg': 0.0,
                'Silicon (Si) mg/kg': 0.0,
                'Aluminum plus Silicon mg/kg': 0.0,
                'Calcium (Ca)  mg/kg': 0.0,
                'Zinc (Zn)  mg/kg': 0.0,
                'Phosphorus (P)   mg/kg': 0.0
            }
            
            # API calculate
            RHS9 = sum([Vi_b_m[(i, b, m)].varValue * Compras1.loc[(i), 'SPG'] for i in flujo_compras.index if (i, b, m) in SETCrudoBlendMezcla_i_b_m.index]
                       + [Pp_i_b_m[(p, i, b, m)].varValue * CurvaDestilacion.loc[(p, i), 'SPG'] for p, i in CurvaDestilacion.index if (p, i, b, m) in SETRefiBlendMezclap_i_b_m.index])
            if RHS9 > 0:
                SPGCALC = RHS9 / vol
                record['API'] = float((141.5 / SPGCALC) - 131.5)
                
            # Azufre calculate
            RHS10 = sum([Vi_b_m[(i, b, m)].varValue * Compras1.loc[(i), '%AZUFRE'] for i in flujo_compras.index if (i, b, m) in SETCrudoBlendMezcla_i_b_m.index]
                        + [Pp_i_b_m[(p, i, b, m)].varValue * CurvaDestilacion.loc[(p, i), 'AZUFRE %'] for p, i in CurvaDestilacion.index if (p, i, b, m) in SETRefiBlendMezclap_i_b_m.index])
            record['%AZUFRE'] = float(RHS10 / vol)
            
            # Viscosidad calculate
            RHS901 = sum([(Vi_b_m[(i, b, m)].varValue * Compras1.loc[(i), 'Iv50'] * Compras1.loc[(i), 'SPG']) for i in flujo_compras.index if (i, b, m) in SETCrudoBlendMezcla_i_b_m.index]
                         + [(Pp_i_b_m[(p, i, b, m)].varValue * CurvaDestilacion.loc[(p, i), 'Iv50']) * CurvaDestilacion.loc[(p, i), 'SPG'] for p, i in CurvaDestilacion.index if (p, i, b, m) in SETRefiBlendMezclap_i_b_m.index])
            AUX_SPGXVOL1 = sum([Vi_b_m[(i, b, m)].varValue * Compras1.loc[(i), 'SPG'] for i in flujo_compras.index if (i, b, m) in SETCrudoBlendMezcla_i_b_m.index]
                               + [Pp_i_b_m[(p, i, b, m)].varValue * CurvaDestilacion.loc[(p, i), 'SPG'] for p, i in CurvaDestilacion.index if (p, i, b, m) in SETRefiBlendMezclap_i_b_m.index])
            if AUX_SPGXVOL1 > 0:
                V50CALC = RHS901 / AUX_SPGXVOL1
                try:
                    record['Viscosidad Cst'] = float(math.exp(math.exp(V50CALC)) - 0.8)
                except Exception:
                    record['Viscosidad Cst'] = 0.0
                    
            # Basic Weighted properties
            properties_to_calc = [
                ('ACID NUMBER mg KOH/g', 'ACID NUMBER mg KOH/g', 'ACID NUMBER mg KOH/g'),
                ('Accelerated Total Sediment by Hot Filtration % m/m', 'Accelerated Total Sediment by Hot Filtration % m/m', 'Accelerated Total Sediment by Hot Filtration % m/m'),
                ('Micro Carbon Residue % m/m', 'Micro Carbon Residue % m/m', 'Micro Carbon Residue % m/m'),
                ('Water by Distillation % v/v', 'Water by Distillation % v/v', 'Water by Distillation % v/v'),
                ('Ash Content % m/m', 'Ash Content % m/m', 'Ash Content % m/m'),
                ('Vanadium (V) mg/kg', 'Vanadium (V) mg/kg', 'Vanadium (V) mg/kg'),
                ('Sodium (Na) mg/kg', 'Sodium (Na) mg/kg', 'Sodium (Na) mg/kg'),
                ('Aluminum (Al)  mg/kg', 'Aluminum (Al)  mg/kg', 'Aluminum (Al)  mg/kg'),
                ('Silicon (Si) mg/kg', 'Silicon (Si) mg/kg', 'Silicon (Si) mg/kg'),
                ('Aluminum plus Silicon mg/kg', 'Aluminum plus Silicon mg/kg', 'Aluminum plus Silicon mg/kg'),
                ('Calcium (Ca)  mg/kg', 'Calcium (Ca)  mg/kg', 'Calcium (Ca)  mg/kg'),
                ('Zinc (Zn)  mg/kg', 'Zinc (Zn)  mg/kg', 'Zinc (Zn)  mg/kg'),
                ('Phosphorus (P)   mg/kg', 'Phosphorus (P)   mg/kg', 'Phosphorus (P)   mg/kg')
            ]
            
            for key_in_record, col_compra, col_ref in properties_to_calc:
                try:
                    rhs_val = sum([Vi_b_m[(i, b, m)].varValue * Compras1.loc[(i), col_compra] for i in flujo_compras.index if (i, b, m) in SETCrudoBlendMezcla_i_b_m.index]
                                  + [Pp_i_b_m[(p, i, b, m)].varValue * CurvaDestilacion.loc[(p, i), col_ref] for p, i in CurvaDestilacion.index if (p, i, b, m) in SETRefiBlendMezclap_i_b_m.index])
                    record[key_in_record] = float(rhs_val / vol)
                except Exception:
                    record[key_in_record] = 0.0
                    
            blending_list.append(record)
            
    # 7. Costos Operacionales Extraction
    costos_op_list = []
    for b in Vb:
        vol_vb = Vb[(b)].varValue
        vol_pn = PNORMALb[(b)].varValue
        tot_vol = float((vol_vb or 0.0) + (vol_pn or 0.0))
        if tot_vol > 0.001:
            rate = float(CostosOPERA.loc[(b), 'Costo Operacional (USD/BBL)'])
            costos_op_list.append({
                'Centro de Operacion': str(b),
                'Throughput Centro de Operacion BPD': tot_vol,
                'Costos Operacionales USD/BPD': rate,
                'Costo Total USD': float(tot_vol * rate)
            })
            
    # 8. Costos Operacionales Ref Blend
    costos_op_ref_list = []
    for b in Pb:
        vol = Pb[(b)].varValue
        if vol is not None and vol > 0.001:
            rate = float(CostosOPERA.loc[(b), 'Costo Operacion Refinados en Blend  (USD/BBL)'])
            costos_op_ref_list.append({
                'Centro de Operacion': str(b),
                'Throughput Centro de Operacion Refinados BPD': float(vol),
                'Costos Operacionales Refinados USD/BPD': rate,
                'Costo Total USD': float(vol * rate)
            })
            
    # 9. Composicion Blending Extraction
    composicion_list = []
    for i, b, m in Vi_b_m:
        vol = Vi_b_m[(i, b, m)].varValue
        if vol is not None and vol > 0.001:
            composicion_list.append({
                'Crudo/Refinado': str(i),
                'Crudo origen': '',
                'Centro de Operacion': str(b),
                'Blend': str(m),
                'Volumen a Blending BPD': float(vol)
            })
    for p, i, b, m in Pp_i_b_m:
        vol = Pp_i_b_m[(p, i, b, m)].varValue
        if vol is not None and vol > 0.001:
            composicion_list.append({
                'Crudo/Refinado': str(p),
                'Crudo origen': str(i),
                'Centro de Operacion': str(b),
                'Blend': str(m),
                'Volumen a Blending BPD': float(vol)
            })
            
    return sanitize_nans({
        'status': status,
        'utilidad_total': utilidad_total,
        'vol_compras_total': float(sum(r['Volumen Comprado BPD'] for r in compras_list)),
        'vol_ventas_total': float(sum(r['Volumen Vendido BPD'] for r in ventas_list)),
        'compras': compras_list,
        'ventas': ventas_list,
        'transporte': transporte_list,
        'refinacion': refinacion_list,
        'throughput': throughput_list,
        'blending': blending_list,
        'costos_operacionales': costos_op_list,
        'costos_operacionales_ref': costos_op_ref_list,
        'composicion_blending': composicion_list
    })
