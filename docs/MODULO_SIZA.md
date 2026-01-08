# Módulo de Control de Cupo SIZA

## 📋 Descripción

Sistema de control y gestión del cupo SIZA para prevenir sobregiros y gestionar pedidos de manera eficiente. Incluye un dashboard visual con alertas automáticas y gestión de aprobaciones.

## 👥 Usuarios con Acceso

Solo los siguientes usuarios pueden acceder al módulo:

- **Daniela Cuadrado** - `comex@conquerstrading.com`
- **Shirli Diaz** - `comexzf@conquerstrading.com`

## 🚀 Instalación

### 1. Ejecutar la Migración de Base de Datos

Opción A - Usando Python (Recomendado):
```powershell
python migrations/crear_tablas_siza.py
```

Opción B - Usando SQL directamente:
```powershell
# Si usas PostgreSQL
psql -U tu_usuario -d tu_base_de_datos -f migrations/crear_tablas_siza.sql
```

### 2. Verificar las Tablas Creadas

Las siguientes tablas deben estar creadas:

- `pedidos_siza` - Registro de pedidos
- `cupo_siza_config` - Configuración diaria del cupo

### 3. Acceder al Dashboard

URL: `http://tu-servidor/dashboard-siza`

## 📊 Características

### Dashboard Principal

1. **Tarjeta de Volumen SIZA (Web)**
   - Muestra el cupo disponible del día
   - Incluye un input rápido para actualizar el cupo
   - Color: Azul

2. **Tarjeta de Inventario Físico**
   - Solo lectura
   - Color: Cian

3. **Tarjeta de Pedidos Comprometidos**
   - Suma de todos los pedidos pendientes
   - Muestra cantidad de pedidos
   - Color: Amarillo

4. **Tarjeta DISPONIBLE REAL** ⭐
   - **Verde**: Si hay cupo disponible (positivo)
   - **Rojo con animación**: Si el cupo está agotado (negativo o cero)
   - La tarjeta más importante del dashboard

### Gestión de Pedidos

- Tabla con todos los pedidos pendientes
- Botones de acción por pedido:
  - ✅ **Aprobar** - Se deshabilita automáticamente si no hay cupo
  - ❌ **Rechazar** - Disponible siempre
- Confirmación JavaScript antes de ejecutar acciones

### Ingreso Rápido

- Modal Bootstrap para registrar nuevos pedidos
- Campos:
  - Número de Pedido (único, obligatorio)
  - Volumen Solicitado en Galones (obligatorio)
  - Observación (opcional)

## 🔄 Flujo de Trabajo

1. **Actualizar Cupo del Día**
   - Daniela o Shirli actualizan el cupo web en la tarjeta superior
   - El sistema registra quién y cuándo lo actualizó

2. **Registrar Pedido**
   - Click en "Registrar Nuevo Pedido"
   - Llenar el formulario
   - El pedido queda en estado PENDIENTE

3. **Aprobar/Rechazar Pedidos**
   - Revisar lista de pedidos pendientes
   - Click en ✅ Aprobar (solo si hay cupo disponible)
   - Click en ❌ Rechazar (para selectividad o rechazo)

4. **Monitoreo Visual**
   - Si DISPONIBLE REAL es negativo/cero → Alerta roja
   - Se bloquean automáticamente las aprobaciones
   - Mensaje de advertencia en la parte superior

## 📁 Archivos del Módulo

```
├── app.py                              # Rutas y modelos agregados
├── templates/
│   └── siza_dashboard.html            # Dashboard principal
├── migrations/
│   ├── crear_tablas_siza.sql          # Script SQL
│   └── crear_tablas_siza.py           # Script Python
└── docs/
    └── MODULO_SIZA.md                 # Este archivo
```

## 🎨 Diseño

- Framework: Bootstrap 5
- Estilos: Gradientes modernos
- Animaciones: Hover, pulse, shake
- Responsive: Mobile-friendly
- Iconos: Bootstrap Icons + Emojis

## 🔒 Seguridad

- Decoradores `@login_required` y `@permiso_requerido("cupo_siza")`
- Validación de datos en backend
- Confirmación JavaScript para acciones críticas
- Auditoría: Cada acción registra usuario y timestamp

## 📝 Estados de Pedidos

- **PENDIENTE** - Pedido registrado, esperando aprobación
- **APROBADO** - Pedido aprobado, cupo comprometido
- **RECHAZADO** - Pedido rechazado o en selectividad

## 🐛 Solución de Problemas

### Error: "No hay cupo disponible"
- Verificar que el cupo del día esté actualizado
- Revisar pedidos pendientes que estén consumiendo el cupo

### Error: "El pedido ya está registrado"
- Usar un número de pedido único
- Verificar en la tabla si existe duplicado

### No puedo acceder al módulo
- Verificar que tu usuario tenga el permiso `cupo_siza`
- Revisar el diccionario USUARIOS en app.py

## 📞 Soporte

Para dudas o problemas técnicos contactar a:
- Juan Diego Ayala (numbers@conquerstrading.com)
- Brandon Niño (logistics.inventory@conquerstrading.com)
