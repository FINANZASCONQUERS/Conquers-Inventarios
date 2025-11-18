from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
db = SQLAlchemy()

from models.extensions import db

class TurnoCarro(db.Model):
    __tablename__ = 'turnos_carro'
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(32), nullable=False)  # Número de WhatsApp
    estado = db.Column(db.String(16), default='pendiente')
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<TurnoCarro {self.numero} {self.estado}>"
