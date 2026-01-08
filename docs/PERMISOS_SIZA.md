# Sistema de Permisos para SIZA Dashboard

## Resumen
Se implementó un sistema de permisos de dos niveles para el dashboard de SIZA, separando las funciones de **solicitantes** y **gestores**.

---

## 📋 Niveles de Permisos

### 1. **siza_solicitante** (Solicitantes)
Usuarios que pueden ver el inventario y gestionar sus propios pedidos.

**Permisos:**
- ✅ Ver dashboard de SIZA
- ✅ Ver inventario en tiempo real de todos los productos
- ✅ Solicitar nuevos pedidos
- ✅ Editar **solo** sus propios pedidos (pendientes, aprobados o rechazados)
- ✅ Ver historial completo de movimientos
- ✅ Ver historial completo de pedidos
- ❌ **NO** pueden aprobar/rechazar pedidos
- ❌ **NO** pueden recargar inventario
- ❌ **NO** pueden registrar consumos
- ❌ **NO** pueden editar/eliminar movimientos de otros

**Usuarios con este permiso:**
- Carlos Baron (`carlos.baron@conquerstrading.com`)
- Samantha Roa (`logistic@conquerstrading.com`)
- Juliana Torres (`ops@conquerstrading.com`)
- Juan Diego Cuadros (`juandiego.cuadros@conquerstrading.com`)
- Brando (`brando@conquerstrading.com`)

---

### 2. **siza_gestor** (Gestores)
Usuarios con acceso completo para gestionar todo el sistema SIZA.

**Permisos:**
- ✅ Todo lo que puede hacer un solicitante, **MÁS:**
- ✅ Aprobar/Rechazar pedidos
- ✅ Recargar inventario de productos
- ✅ Registrar consumos manuales
- ✅ Consumir automáticamente pedidos aprobados
- ✅ Editar **cualquier** pedido (no solo los propios)
- ✅ Editar/Eliminar movimientos (recargas y consumos)
- ✅ Actualizar inventario directamente

**Usuarios con este permiso:**
- Daniela Cuadrado (`comex@conquerstrading.com`)
- Shirli Diaz (`comexzf@conquerstrading.com`)

---

## 🔐 Validaciones de Seguridad

### En el Backend (app.py)

1. **Rutas Protegidas por Decorador:**
   - `@permiso_requerido("siza_solicitante")` → Acceso para solicitantes y gestores
   - `@permiso_requerido("siza_gestor")` → Acceso solo para gestores

2. **Validación de Propiedad de Pedidos:**
   ```python
   # En editar_pedido_siza()
   if not es_gestor and pedido.usuario_registro != usuario_actual:
       flash('No tienes permiso para editar este pedido.')
       return redirect(url_for('dashboard_siza'))
   ```
   - Los solicitantes **solo** pueden editar pedidos que ellos mismos registraron
   - Los gestores pueden editar **cualquier** pedido

### En el Frontend (siza_dashboard.html)

Los botones de gestión se ocultan para solicitantes usando Jinja:

```jinja
{% if es_gestor %}
    <!-- Botones de aprobar/rechazar/recargar/consumir -->
{% endif %}
```

**Elementos Protegidos:**
- Botones de "Recargar" y "Consumo" en tarjetas de productos
- Botones de "Aprobar" y "Rechazar" en tabla de pedidos
- Botón de "Consumir Automáticamente" en modales
- Botones de "Editar" y "Eliminar" en historial de movimientos

---

## 📊 Rutas y Permisos

| Ruta | Permiso Requerido | Descripción |
|------|------------------|-------------|
| `/dashboard-siza` | `siza_solicitante` | Ver dashboard principal |
| `/siza/registrar-pedido` | `siza_solicitante` | Solicitar nuevo pedido |
| `/siza/editar-pedido/<id>` | `siza_solicitante` | Editar pedido (con validación de propiedad) |
| `/siza/historial-movimientos` | `siza_solicitante` | Ver historial de recargas/consumos |
| `/siza/historial-pedidos` | `siza_solicitante` | Ver historial de pedidos |
| `/siza/gestionar-pedido/<id>` | `siza_gestor` | Aprobar/Rechazar pedido |
| `/siza/recargar-producto` | `siza_gestor` | Recargar inventario |
| `/siza/registrar-consumo` | `siza_gestor` | Registrar consumo manual |
| `/siza/consumir-pedidos` | `siza_gestor` | Consumir pedidos automáticamente |
| `/siza/actualizar-inventario` | `siza_gestor` | Actualizar inventario directamente |
| `/siza/editar-recarga/<id>` | `siza_gestor` | Editar recarga existente |
| `/siza/editar-consumo/<id>` | `siza_gestor` | Editar consumo existente |
| `/siza/eliminar-movimiento/<tipo>/<id>` | `siza_gestor` | Eliminar movimiento |

---

## 🎯 Flujo de Trabajo

### Para Solicitantes:
1. Ingresar al dashboard de SIZA
2. Ver inventario disponible de todos los productos
3. Hacer clic en "Solicitar Pedido"
4. Llenar formulario (producto, volumen, observación)
5. Sistema valida si hay suficiente inventario disponible
   - ⚠️ Si no hay suficiente: Muestra advertencia pero permite registrar
   - ✅ Si hay suficiente: Registra sin advertencias
6. Pedido queda en estado **PENDIENTE**
7. Solicitante puede editar su pedido mientras esté pendiente o después

### Para Gestores:
1. Recibir notificación de pedidos pendientes
2. Revisar pedidos en tabla principal
3. Aprobar o rechazar según disponibilidad
   - Botón "Aprobar" se deshabilita si no hay inventario disponible
4. Pedidos aprobados quedan disponibles para consumo
5. Recargar inventario cuando llegue nuevo producto
6. Consumir pedidos aprobados (manual o automáticamente)
7. Monitorear historial completo

---

## 🔧 Cambios Técnicos Realizados

### 1. app.py
- Creada función `tiene_permiso(permiso_requerido)` para verificar permisos
- Actualizados decoradores de 17 rutas con permisos específicos
- Agregada validación de propiedad en `editar_pedido_siza()`
- Agregados 3 nuevos usuarios al sistema
- Actualizados permisos de Samantha y Juliana
- Variable `es_gestor` enviada al template

### 2. siza_dashboard.html
- Protegidos botones de Recargar/Consumo con `{% if es_gestor %}`
- Protegidos botones de Aprobar/Rechazar con `{% if es_gestor %}`
- Protegidos botones de Editar/Eliminar movimientos con `{% if es_gestor %}`
- Mantiene visible el botón "Editar" de pedidos para todos

### 3. USUARIOS_MOCK
```python
# Gestores (acceso completo)
"comex@conquerstrading.com": ["siza_solicitante", "siza_gestor"]
"comexzf@conquerstrading.com": ["siza_solicitante", "siza_gestor"]

# Solicitantes (acceso limitado)
"carlos.baron@conquerstrading.com": ["siza_solicitante"]
"logistic@conquerstrading.com": ["siza_solicitante"]  # Samantha
"ops@conquerstrading.com": ["siza_solicitante"]  # Juliana
"juandiego.cuadros@conquerstrading.com": ["siza_solicitante"]
"brando@conquerstrading.com": ["siza_solicitante"]
```

---

## ✅ Validación de Implementación

### Testing Recomendado:

1. **Como Solicitante (ej: Carlos Baron):**
   - [ ] Login y acceso a dashboard SIZA
   - [ ] Crear un nuevo pedido
   - [ ] Editar el pedido propio
   - [ ] Intentar editar pedido de otro usuario (debe fallar)
   - [ ] Verificar que NO aparecen botones de Aprobar/Rechazar
   - [ ] Verificar que NO aparecen botones de Recargar/Consumir
   - [ ] Ver historial de movimientos (solo lectura)

2. **Como Gestor (ej: Daniela):**
   - [ ] Ver todos los botones de gestión
   - [ ] Aprobar/Rechazar pedidos
   - [ ] Recargar inventario
   - [ ] Consumir pedidos automáticamente
   - [ ] Editar cualquier pedido
   - [ ] Editar/Eliminar movimientos

---

## 📌 Notas Importantes

1. **Los solicitantes pueden ver TODO** pero solo **actuar sobre sus propios pedidos**
2. **El sistema valida tanto en frontend (UI) como en backend (seguridad)**
3. **Los gestores heredan todos los permisos de solicitantes**
4. **La validación de propiedad es crítica** para seguridad

---

## 🚀 Próximos Pasos (Opcional)

- [ ] Agregar filtro en historial de pedidos por "Mis Pedidos" para solicitantes
- [ ] Notificaciones por email cuando un pedido es aprobado/rechazado
- [ ] Dashboard personalizado por tipo de usuario
- [ ] Reportes de consumo por solicitante
