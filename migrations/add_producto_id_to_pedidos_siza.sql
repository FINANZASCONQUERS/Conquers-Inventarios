-- Script para agregar el campo producto_id a la tabla pedidos_siza
-- Ejecutar después de crear las tablas multi-producto

-- Agregar columna producto_id
ALTER TABLE pedidos_siza ADD COLUMN producto_id INTEGER REFERENCES productos_siza(id);

-- Crear índice para mejorar rendimiento
CREATE INDEX IF NOT EXISTS idx_pedidos_siza_producto_id ON pedidos_siza(producto_id);

-- Opcional: Asignar un producto por defecto a los pedidos existentes (si los hay)
-- UPDATE pedidos_siza SET producto_id = (SELECT id FROM productos_siza WHERE codigo = 'F04' LIMIT 1) WHERE producto_id IS NULL;
