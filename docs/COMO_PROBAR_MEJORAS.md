# 🧪 Guía Rápida - Prueba de Mejoras Implementadas

## ✅ Cambios Realizados

### 1. Campo "Tipo Guia" con Selector
- ✅ Agregado renderizado de campos `select`
- ✅ Opciones: "Física" o "Digital"
- ✅ Guardado automático al cambiar
- ✅ Visible en la tabla para usuarios con permisos

### 2. Sistema de Presencia en Tiempo Real
- ✅ Panel flotante de actividad
- ✅ Contador de usuarios en línea
- ✅ Indicadores visuales en filas editadas
- ✅ Badge con nombre de usuario y campo editado
- ✅ Polling inteligente (no interrumpe escritura)

---

## 🔍 Cómo Probar AHORA MISMO

### Prueba 1: Campo "Tipo Guia"

1. **Refresca la página** (`F5`)
2. **Busca la columna "TIPO GUIA"** (entre PRODUCTO y DESTINO)
3. **Haz clic en una fila** donde tengas permisos
4. **Deberías ver**:
   - Un dropdown con opciones: `[Seleccionar...] [Física] [Digital]`
   - Al seleccionar, se guarda automáticamente
   - Aparece ✅ verde en la columna de acciones

**Usuarios con permisos:**
- ops@conquerstrading.com
- logistic@conquerstrading.com
- production@conquerstrading.com
- oci@conquerstrading.com

---

### Prueba 2: Sistema de Presencia (DOS NAVEGADORES)

#### Navegador 1 (Chrome):
1. Inicia sesión como `logistic@conquerstrading.com`
2. Ve a "Programación de Cargue"
3. **Busca en el header** (arriba a la derecha):
   - Botón con ícono 👥 (usuarios)
   - Badge redondo con número "0"
4. **Haz clic en un campo** (ej: Placa)
5. Empieza a escribir

#### Navegador 2 (Edge/Firefox):
1. Inicia sesión como `ops@conquerstrading.com`
2. Ve a "Programación de Cargue"
3. **Espera 5 segundos**
4. **Deberías ver**:
   - Badge del botón 👥 cambia a "1" (verde)
   - La fila tiene fondo azul claro
   - Badge flotante: "👤 Samantha · Placa"
   - Círculo azul en la celda de Placa

#### Verificar el Panel:
1. En el navegador 2, **haz clic en el botón 👥**
2. **Se abre panel lateral** mostrando:
   ```
   👤 Samantha Roa
      📝 Editando: Placa
   ```

---

### Prueba 3: Modo Incógnito (Un Solo Navegador)

1. **Ventana Normal:**
   - `Ctrl + Shift + N` para abrir incógnito
   - Login con usuario 1
   - Programación de Cargue

2. **Ventana Incógnito:**
   - Login con usuario 2
   - Programación de Cargue

3. **Edita en una** y observa en la otra

---

## 🎨 Indicadores Visuales que Verás

### Cuando Alguien Edita:

1. **Fila Completa**:
   - Fondo azul claro degradado
   - Borde izquierdo azul animado (pulso)

2. **Badge Flotante** (primera columna):
   ```
   ✏️ Nombre Usuario · Campo Editando
   ```
   - Fondo azul degradado
   - Ícono de lápiz animado
   - Sombra suave

3. **Círculo en Celda**:
   - Círculo azul con iniciales (ej: "SR")
   - Efecto ripple (onda expansiva)
   - Tooltip al pasar el mouse

4. **Contador en Header**:
   - Badge verde: Hay usuarios
   - Badge gris: Sin usuarios

---

## 🐛 Solución de Problemas

### "No veo la columna TIPO GUIA"
**Solución:**
1. Presiona `F5` para refrescar
2. Verifica que estés logueado como usuario con permisos
3. La columna aparece después de PRODUCTO

### "No veo el botón de usuarios 👥"
**Solución:**
1. Busca en el header de la card (arriba a la derecha)
2. Está junto a "Ver historial" y "Ordenar estados"
3. Tiene un badge circular pequeño con número

### "Los indicadores no aparecen"
**Solución:**
1. Asegúrate de usar **DOS navegadores diferentes** o incógnito
2. **Espera 5 segundos** después de editar
3. Verifica que ambos usuarios estén en "Programación de Cargue"
4. El usuario que edita **NO ve** sus propios indicadores

### "El select no guarda"
**Solución:**
1. Abre la consola del navegador (`F12` → Console)
2. Busca errores en rojo
3. Verifica que seleccionaste una opción válida
4. Espera el ✅ verde en la columna de acciones

---

## 📊 Checklist de Verificación

### Campo Tipo Guia:
- [ ] La columna "TIPO GUIA" aparece en la tabla
- [ ] Es un dropdown con 3 opciones
- [ ] Al seleccionar "Física" se guarda
- [ ] Al seleccionar "Digital" se guarda
- [ ] Aparece ✅ verde después de guardar
- [ ] El valor se mantiene al refrescar

### Sistema de Presencia:
- [ ] Botón 👥 visible en header
- [ ] Badge muestra "0" sin usuarios
- [ ] Al editar en otro navegador, badge cambia a "1"
- [ ] Fila se ilumina de azul
- [ ] Badge flotante muestra nombre y campo
- [ ] Círculo azul en celda específica
- [ ] Panel lateral muestra usuarios activos
- [ ] Al salir del campo, indicadores desaparecen en ~5 seg

---

## 🎯 Casos de Prueba Específicos

### Caso 1: Samantha edita TIPO GUIA
1. **Samantha (logistic):**
   - Selecciona "Digital" en fila #5
   
2. **Juan Diego (ops):**
   - Ve la fila #5 iluminada
   - Badge: "👤 Samantha · Tipo Guia"
   - Puede editar otro campo sin conflicto

### Caso 2: Múltiples Usuarios
1. **3 usuarios** en 3 navegadores
2. Cada uno edita una fila diferente
3. **Todos ven** los 3 indicadores
4. Panel muestra "3" usuarios en línea

### Caso 3: Mismo Campo
1. **Usuario A:** Edita "Placa" en fila #10
2. **Usuario B:** Ve el indicador
3. **Usuario B:** Espera a que A termine
4. **Usuario B:** Edita cuando desaparece el indicador

---

## 📸 Screenshots Esperados

### Header con Botón:
```
[Badge rol] [👥 1] [Ver historial] [Ordenar estados] [+ Agregar]
```

### Fila Editada:
```
┌────────────────────────────────────────────────┐
│ [FONDO AZUL CLARO CON BORDE ANIMADO]          │
│ ✏️ Samantha Roa · Placa                       │
│ [Datos de la fila...]              [SR]       │
└────────────────────────────────────────────────┘
```

### Panel Lateral:
```
┌─────────────────────────┐
│ 👥 Usuarios Activos     │
├─────────────────────────┤
│ 👤 SR                   │
│    Samantha Roa         │
│    📝 Editando: Placa   │
│                         │
│ 👤 JA                   │
│    Juan Diego           │
│    🌐 Navegando         │
└─────────────────────────┘
```

---

## ⏱️ Tiempos Esperados

| Acción | Tiempo |
|--------|--------|
| Envío de presencia | Inmediato |
| Actualización visual | 5 segundos |
| Limpieza de inactivos | 30 segundos |
| Guardado de select | <1 segundo |

---

## 🚀 Siguiente Paso

**Probar AHORA:**
1. Abre Chrome e inicia sesión
2. Abre Edge e inicia sesión con otro usuario
3. En Chrome: edita un campo
4. En Edge: observa los indicadores

**¿Funciona?** ✅ Listo para producción
**¿No funciona?** Revisa la consola del navegador (`F12`)

---

**Fecha:** Enero 8, 2026  
**Versión:** 2.0 (con Tipo Guia + Presencia)
