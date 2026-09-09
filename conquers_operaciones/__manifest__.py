{
    'name': 'Operaciones',
    'version': '17.0.1.0.0',
    'category': 'Operations',
    'summary': 'Pedidos, programacion de cargue, precintos y guias de transporte',
    'author': 'Conquers Trading',
    'license': 'LGPL-3',

    # Solo lo que se usa de verdad.
    #   base    -> res.users, res.partner (clientes y transportadoras)
    #   mail    -> chatter, reemplaza las columnas ultimo_editor/fecha_actualizacion
    #   product -> product.product (productos a cargar)
    # Se excluyen a proposito 'stock' y 'sale_management': los precintos son un
    # modelo propio con su propia maquina de estados, no stock.lot, y arrastrar
    # esos modulos solo traeria menus, permisos y datos demo sin uso.
    'depends': ['base', 'mail', 'product'],

    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'wizards/wizard_views.xml',
        'views/conductor_views.xml',
        'views/lote_precintos_views.xml',
        'views/inventario_precinto_views.xml',
        'views/programacion_base_views.xml',
        'views/programacion_cargue_views.xml',
        'reports/report_actions.xml',
        'reports/report_programacion_cargue.xml',
        'reports/report_guia_transporte.xml',
        'views/menus.xml',
    ],
    'application': True,
    'installable': True,
}
