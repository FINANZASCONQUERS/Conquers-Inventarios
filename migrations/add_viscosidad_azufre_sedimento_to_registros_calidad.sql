-- Agregar columnas viscosidad, azufre y sedimento a registros_calidad
-- Fecha: 2026-08-31

DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'registros_calidad' 
        AND column_name = 'viscosidad'
    ) THEN
        ALTER TABLE registros_calidad 
        ADD COLUMN viscosidad FLOAT;
        RAISE NOTICE 'Columna viscosidad agregada exitosamente a registros_calidad';
    END IF;

    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'registros_calidad' 
        AND column_name = 'azufre'
    ) THEN
        ALTER TABLE registros_calidad 
        ADD COLUMN azufre FLOAT;
        RAISE NOTICE 'Columna azufre agregada exitosamente a registros_calidad';
    END IF;

    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'registros_calidad' 
        AND column_name = 'sedimento'
    ) THEN
        ALTER TABLE registros_calidad 
        ADD COLUMN sedimento FLOAT;
        RAISE NOTICE 'Columna sedimento agregada exitosamente a registros_calidad';
    END IF;
END $$;
