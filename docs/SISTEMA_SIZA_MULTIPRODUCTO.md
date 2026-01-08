# 📊 SISTEMA SIZA MULTI-PRODUCTO - IMPLEMENTACIÓN COMPLETA

## ✅ Estado Actual: SISTEMA OPERATIVO

**Fecha de implementación:** 7 de Enero de 2026

---

## 🎯 Funcionalidades Implementadas

### 1. Control Multi-Producto
El sistema ahora maneja **4 productos diferentes** de forma independiente:

| Producto | Código | Color Badge | Estado |
|----------|--------|-------------|--------|
| F04 | `F04` | 🟣 Primary | ✅ Activo |
| DILUYENTE | `DILUYENTE` | 🟢 Success | ✅ Activo |
| MGO | `MGO` | 🟡 Warning | ✅ Activo |
| AGUA RESIDUAL | `AGUA_RESIDUAL` | 🔴 Danger | ✅ Activo |

### 2. Dashboard Visual
- **URL de Acceso:** `/dashboard-siza`
- **Diseño:** 4 tarjetas con gradientes de color por producto
- **Métricas en tiempo real:**
  - 📊 Cupo Web del día
  - ⚠️ Volumen comprometido (pedidos pendientes)
  - ✅ Volumen disponible
  - 📋 Total de pedidos

### 3. Gestión de Inventario
#### Inventario Diario
- Registro independiente por producto y fecha
- Control de cupo web actualizable
- Historial de actualizaciones con usuario y fecha

#### Sistema de Recargas
- Botón de recarga individual por producto
- Registro de:
  - Fecha de recarga
  - Volumen recargado
  - Observaciones
  - Usuario que realizó la recarga
- Historial completo de recargas

### 4. Gestión de Pedidos
- Selección del producto en el formulario
- Estados: `Pendiente`, `Aprobado`, `Rechazado`
- Validación automática de disponibilidad por producto
- Tabla visual con badges de color por producto
- Acciones: Aprobar/Rechazar con validación de inventario

---

## 🗄️ Base de Datos

### Tablas Creadas

#### 1. `productos_siza`
```sql
- id (PK)
- codigo (UNIQUE)
- nombre
- activo (boolean)
- color_badge
- orden
```

#### 2. `inventario_siza_diario`
```sql
- id (PK)
- fecha (INDEX)
- producto_id (FK → productos_siza)
- cupo_web
- usuario_actualizacion
- fecha_actualizacion
UNIQUE(fecha, producto_id)
```

#### 3. `recargas_siza`
```sql
- id (PK)
- fecha (INDEX)
- producto_id (FK → productos_siza)
- volumen_recargado
- observacion
- usuario_registro
- fecha_registro
```

#### 4. `pedidos_siza` (actualizada)
```sql
- id (PK)
- numero_pedido
- volumen_solicitado
- producto_id (FK → productos_siza) ← NUEVO
- observacion
- estado
- fecha_registro
- usuario_registro
- fecha_gestion
- usuario_gestion
```

---

## 👥 Control de Acceso

**Usuarios autorizados:**
- ✅ **Daniela Cuadrado** - `comex@conquerstrading.com`
- ✅ **Shirli Diaz** - `comexzf@conquerstrading.com`

**Permiso requerido:** `cupo_siza`

---

## 🚀 Cómo Usar el Sistema

### 1️⃣ Actualizar Cupo Web Diario
1. Acceder a `/dashboard-siza`
2. Hacer clic en el botón "Actualizar Cupo Web" de cualquier producto
3. Ingresar el nuevo valor del cupo
4. El sistema registra automáticamente usuario y fecha

### 2️⃣ Recargar Producto
1. Hacer clic en el botón "⚡ Recargar" del producto deseado
2. Ingresar:
   - Volumen a recargar (en galones)
   - Observaciones (opcional)
3. El sistema:
   - Registra la recarga
   - Actualiza el inventario del día sumando el volumen

### 3️⃣ Registrar Pedido
1. Hacer clic en "➕ Nuevo Pedido"
2. Completar formulario:
   - Seleccionar producto
   - Número de pedido
   - Volumen solicitado
   - Observaciones
3. El pedido queda en estado `Pendiente`

### 4️⃣ Aprobar/Rechazar Pedido
1. Localizar el pedido en la tabla
2. Hacer clic en "✅ Aprobar" o "❌ Rechazar"
3. Para aprobación:
   - Sistema valida disponibilidad del producto específico
   - Si hay suficiente volumen, descuenta del cupo
   - Actualiza estado a `Aprobado`

---

## 📊 Lógica de Cálculo

Para cada producto, el dashboard calcula:

```python
# Cupo del día (inventario)
cupo_web = inventario_siza_diario.cupo_web

# Volumen comprometido
comprometido = SUM(pedidos_siza.volumen_solicitado) 
               WHERE estado = 'Pendiente' AND producto_id = X

# Disponible
disponible = cupo_web - comprometido

# Total de pedidos
total_pedidos = COUNT(pedidos_siza) WHERE producto_id = X
```

---

## 🎨 Colores por Producto

El dashboard utiliza gradientes visuales distintos:

- **F04:** Gradiente morado/púrpura (`bg-f04`)
- **DILUYENTE:** Gradiente rosa/fucsia (`bg-diluyente`)
- **MGO:** Gradiente cian/azul (`bg-mgo`)
- **AGUA RESIDUAL:** Gradiente verde (`bg-agua`)

---

## 📝 Migraciones Ejecutadas

✅ **Script:** `actualizar_siza_multiproducto.py`
- Creó tablas: `productos_siza`, `inventario_siza_diario`, `recargas_siza`
- Insertó 4 productos por defecto
- Creó inventarios iniciales para hoy

✅ **Script:** `agregar_producto_id_pedidos.py`
- Agregó columna `producto_id` a `pedidos_siza`
- Creó índice para optimización

---

## 📁 Archivos del Sistema

### Templates
- `templates/siza_dashboard.html` - Dashboard principal

### Backend (app.py)
- Modelos: `ProductoSiza`, `InventarioSizaDiario`, `RecargaSiza`, `PedidoSiza`
- Rutas:
  - `@app.route('/dashboard-siza')` - Dashboard principal
  - `@app.route('/actualizar-inventario-siza', methods=['POST'])` - Actualizar cupo
  - `@app.route('/recargar-producto-siza', methods=['POST'])` - Recargar volumen
  - `@app.route('/registrar-pedido-siza', methods=['POST'])` - Nuevo pedido
  - `@app.route('/gestionar-pedido-siza/<int:pedido_id>/<accion>', methods=['POST'])` - Aprobar/Rechazar

### Scripts de Utilidad
- `verificar_sistema_siza.py` - Verificación completa del sistema
- `verificar_pedidos_siza.py` - Verificar estructura de pedidos
- `actualizar_siza_multiproducto.py` - Script de migración principal
- `agregar_producto_id_pedidos.py` - Agregar campo producto_id

---

## 🔔 Alertas Automáticas

El dashboard muestra alertas visuales:

- 🟢 **Verde:** Disponible > 50% del cupo
- 🟡 **Amarillo:** Disponible entre 20% y 50%
- 🔴 **Rojo:** Disponible < 20%
- ⚠️ **Crítico:** Disponible negativo (sobregiro)

---

## 🔄 Próximos Pasos Sugeridos

1. **Configurar cupos iniciales** para cada producto
2. **Probar recargas** de cada tipo de producto
3. **Registrar pedidos de prueba** para validar el flujo completo
4. **Revisar reportes** y ajustar según necesidades
5. **Agregar notificaciones** por email cuando disponible sea bajo (opcional)

---

## 📞 Soporte

Para cualquier ajuste o mejora al sistema, contactar al equipo de desarrollo.

**Versión:** 2.0 Multi-Producto  
**Última actualización:** Enero 7, 2026

---

## ✨ Ventajas del Nuevo Sistema

✅ **Separación clara** de inventarios por tipo de producto  
✅ **Trazabilidad completa** con historial de recargas  
✅ **Validación automática** de disponibilidad por producto  
✅ **Dashboard visual** intuitivo con código de colores  
✅ **Registro diario** para análisis histórico  
✅ **Gestión de pedidos** asociados a productos específicos  
✅ **Control de acceso** por usuario autorizado  
✅ **Escalable** - fácil agregar nuevos productos

---

**🎉 ¡Sistema listo para producción!**
