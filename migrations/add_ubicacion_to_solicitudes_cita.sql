-- Script de migración para agregar latitud y longitud a solicitudes_cita
ALTER TABLE solicitudes_cita ADD COLUMN ubicacion_lat DOUBLE PRECISION;
ALTER TABLE solicitudes_cita ADD COLUMN ubicacion_lng DOUBLE PRECISION;
