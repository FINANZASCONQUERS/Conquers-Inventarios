-- Migración para agregar tabla de volumen pendiente DIAN
-- Fecha: 2026-01-08

CREATE TABLE IF NOT EXISTS volumen_pendiente_dian (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha DATE NOT NULL UNIQUE,
    volumen_pendiente FLOAT NOT NULL DEFAULT 0.0,
    observacion TEXT,
    usuario_actualizacion VARCHAR(100) NOT NULL,
    fecha_actualizacion DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Crear índice en fecha para búsquedas rápidas
CREATE INDEX IF NOT EXISTS idx_volumen_dian_fecha ON volumen_pendiente_dian(fecha);

-- Insertar registro inicial para hoy
INSERT OR IGNORE INTO volumen_pendiente_dian (fecha, volumen_pendiente, usuario_actualizacion)
VALUES (date('now'), 0.0, 'Sistema');
