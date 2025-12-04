-- Agregar columna producto a registros_calidad
-- Fecha: 2025-12-03

-- Verificar si la columna ya existe antes de agregarla
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'registros_calidad' 
        AND column_name = 'producto'
    ) THEN
        ALTER TABLE registros_calidad 
        ADD COLUMN producto VARCHAR(50);
        
        RAISE NOTICE 'Columna producto agregada exitosamente a registros_calidad';
    ELSE
        RAISE NOTICE 'La columna producto ya existe en registros_calidad';
    END IF;
END $$;
