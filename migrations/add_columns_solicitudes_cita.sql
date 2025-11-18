-- Migración manual para agregar columnas faltantes a solicitudes_cita
ALTER TABLE solicitudes_cita
ADD COLUMN turno INTEGER UNIQUE,
ADD COLUMN fecha_descargue TIMESTAMP,
ADD COLUMN lugar_descargue VARCHAR(255) DEFAULT 'Sociedad Portuaria del Dique';
