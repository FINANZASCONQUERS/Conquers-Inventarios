"""
Manejo de tiempo del modulo DevTracker.

Regla del modulo (y del repositorio completo): se ALMACENA en UTC naive, con
datetime.utcnow(), igual que las ~25 tablas que ya existen en app.py. Se COMPARA
y se MUESTRA en hora de Bogota.

Mezclar las dos convenciones en la misma base es un error silencioso de 5 horas:
si dev_tickets guardara hora local y el resto UTC, cualquier consulta que cruce
tablas quedaria corrida sin que nadie lo note. Por eso el unico lugar donde
aparece la zona horaria es aqui.

El caso concreto que esto evita: entre las 7:00 p.m. y medianoche hora Colombia
el servidor UTC ya esta en el dia siguiente. Un ticket que vence hoy apareceria
como retrasado esa misma tarde si los dias se calcularan con utcnow().date().
"""
from datetime import datetime, date

import pytz

BOGOTA_TZ = pytz.timezone('America/Bogota')

# FR-013: umbral de "proximo a vencer", en dias.
DIAS_AVISO_VENCIMIENTO = 2

# Ventana de la columna "En Produccion" del tablero. Lo entregado hace mas de
# esto se consulta por el filtro de historico (FR-033) y deja de ocupar espacio
# en la vista activa, pero la columna no queda vacia.
DIAS_VENTANA_PRODUCCION = 30


def ahora_utc():
    """Instante actual para persistir. Naive UTC, como el resto del repo."""
    return datetime.utcnow()


def a_bogota(dt_utc):
    """Convierte un datetime naive-UTC de la BD a datetime aware en Bogota."""
    if dt_utc is None:
        return None
    if dt_utc.tzinfo is None:
        dt_utc = pytz.utc.localize(dt_utc)
    return dt_utc.astimezone(BOGOTA_TZ)


def fecha_bogota(dt_utc):
    """Fecha calendario en Bogota de un datetime naive-UTC de la BD."""
    local = a_bogota(dt_utc)
    return local.date() if local else None


def hoy_bogota():
    """Fecha de hoy en Bogota. Toda comparacion de plazos parte de aqui."""
    return datetime.now(BOGOTA_TZ).date()


def iso(valor):
    """Serializa date/datetime a ISO. Los datetime salen en hora de Bogota."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        local = a_bogota(valor)
        return local.isoformat() if local else None
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor)


def parse_fecha(valor):
    """Lee 'YYYY-MM-DD' del cliente y devuelve date. None si viene vacio o mal."""
    if not valor:
        return None
    if isinstance(valor, date) and not isinstance(valor, datetime):
        return valor
    if isinstance(valor, datetime):
        return valor.date()
    try:
        return datetime.strptime(str(valor).strip()[:10], '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None
