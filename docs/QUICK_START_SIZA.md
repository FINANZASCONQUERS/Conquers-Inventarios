# ⚡ QUICK START - Módulo Control de Cupo SIZA

## 🚀 Instalación en 3 Comandos

```powershell
# 1. Instalar el módulo (crea tablas y configura todo)
python instalar_modulo_siza.py

# 2. Reiniciar Flask (si está corriendo)
# Presionar Ctrl+C y luego:
python app.py

# 3. ¡Listo! Acceder en el navegador
# http://localhost:5000/dashboard-siza
```

---

## 🔐 Login

**Usuario 1:**
- Email: `comex@conquerstrading.com`
- Password: `Conquers2025`

**Usuario 2:**
- Email: `comexzf@conquerstrading.com`  
- Password: `Conquers2025`

---

## 📝 Primer Uso (Tutorial 2 Minutos)

### Paso 1: Actualizar Cupo
![Tarjeta Azul superior izquierda]
- En el input pequeño, escribir: `100000`
- Click en el botón ↻
- ✅ Cupo actualizado a 100,000 Galones

### Paso 2: Registrar un Pedido
- Click en botón azul "Registrar Nuevo Pedido"
- Llenar:
  - Número: `PED-2026-001`
  - Volumen: `15000`
  - Observación: `Pedido de prueba`
- Click "Guardar Pedido"
- ✅ Pedido registrado

### Paso 3: Aprobar el Pedido
- En la tabla, localizar el pedido `PED-2026-001`
- Click en botón verde "✅ Aprobar"
- Confirmar en el popup
- ✅ Pedido aprobado

### Paso 4: Verificar
- La tarjeta "DISPONIBLE REAL" debe mostrar: `85,000 Gls`
- Color: Verde ✅
- Cálculo: 100,000 - 15,000 = 85,000

---

## 🎯 Funciones Principales

| Acción | Ubicación | Resultado |
|--------|-----------|-----------|
| Actualizar cupo | Input en tarjeta azul | Cupo del día actualizado |
| Nuevo pedido | Botón azul superior derecha | Modal de registro |
| Aprobar pedido | Botón verde en tabla | Pedido aprobado |
| Rechazar pedido | Botón rojo en tabla | Pedido rechazado |

---

## ⚠️ Alertas Importantes

### 🔴 Cupo Agotado
Si ves la tarjeta DISPONIBLE REAL en ROJO:
- ❌ No puedes aprobar más pedidos
- ⚠️ Aparece alerta en la parte superior
- 💡 Solución: Actualizar el cupo o rechazar pedidos

### 🟢 Cupo Disponible
Si ves la tarjeta en VERDE:
- ✅ Puedes aprobar pedidos
- ✅ Sistema funcionando normal

---

## 🐛 Problemas Comunes

### No puedo acceder al módulo
✅ Verifica que tu usuario tenga acceso (Daniela o Shirli)  
✅ Verifica que hayas ejecutado la instalación

### Error al crear tablas
✅ Verifica conexión a la base de datos  
✅ Verifica que Flask esté corriendo

### Botón "Aprobar" deshabilitado
✅ Esto es NORMAL cuando no hay cupo disponible  
✅ Actualiza el cupo del día primero

---

## 📚 Documentación Completa

Si necesitas más detalles, consulta:
- `docs/RESUMEN_EJECUTIVO_SIZA.md` - Vista general
- `docs/MODULO_SIZA.md` - Documentación completa
- `docs/IMPLEMENTACION_SIZA.md` - Detalles técnicos

---

## 📞 Ayuda

**Soporte Técnico:**  
Juan Diego Ayala - numbers@conquerstrading.com

---

**¡Eso es todo! El módulo está listo para usar. 🎉**
