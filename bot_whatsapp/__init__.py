# bot_whatsapp/__init__.py
from flask import Blueprint

# Creamos el Blueprint
bot_bp = Blueprint(
    'bot_bp', __name__,
    template_folder='templates',
    static_folder='static'
)

# Importamos las rutas al final para evitar importaciones circulares
from . import routes