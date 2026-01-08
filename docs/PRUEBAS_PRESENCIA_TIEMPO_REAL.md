# 🧪 Guía de Pruebas - Sistema de Presencia en Tiempo Real

## 📋 Resumen del Sistema

El sistema de presencia en tiempo real muestra qué usuarios están editando qué campos en la programación de cargue, **sin interrumpir** la escritura de datos.

### Características Visuales

1. **Contador de Usuarios en Línea** - Badge verde en el botón del panel de actividad
2. **Panel de Actividad** - Muestra lista de usuarios activos y qué están editando
3. **Fila Resaltada** - La fila completa se ilumina con color azul claro cuando alguien la edita
4. **Badge Flotante** - Aparece en la primera columna mostrando "👤 Nombre · Campo"
5. **Indicador en Celda** - Círculo azul con iniciales en la celda específica siendo editada

---

## 🔍 Métodos para Probar

### Opción 1: Dos Navegadores Diferentes (Más Fácil)

1. **Abre el sistema en Chrome:**
   - Inicia sesión con un usuario (ej: `ops@conquerstrading.com`)
   - Ve a Programación de Cargue
   - Haz clic en algún campo para editarlo

2. **Abre el sistema en Edge/Firefox:**
   - Inicia sesión con OTRO usuario (ej: `refinery.control@conquerstrading.com`)
   - Ve a Programación de Cargue
   - **Observa:**
     - ✅ Contador muestra "1" usuario en línea
     - ✅ La fila del primer usuario tiene fondo azul claro
     - ✅ Badge flotante dice "Nombre · Campo"
     - ✅ Círculo azul en la celda específica

3. **Edita en el segundo navegador:**
   - Haz clic en otro campo
   - Regresa al primer navegador
   - **Deberías ver** los mismos indicadores para el segundo usuario

---

### Opción 2: Modo Incógnito (Mismo Navegador)

1. **Ventana Normal:**
   - Chrome normal
   - Inicia sesión con usuario 1
   - Ve a Programación de Cargue

2. **Ventana Incógnito:**
   - `Ctrl + Shift + N` (Chrome)
   - Inicia sesión con usuario 2
   - Ve a Programación de Cargue

3. **Prueba la interacción:**
   - Edita en una ventana
   - La otra ventana mostrará los indicadores en 5 segundos

---

### Opción 3: Dos Computadoras/Dispositivos

1. **Computadora 1:**
   - Inicia sesión en el sistema
   - Edita un campo

2. **Computadora 2 / Celular:**
   - Inicia sesión con otro usuario
   - Abre la misma página
   - Verás la actividad de la primera computadora

---

## ✅ Checklist de Pruebas

### Prueba 1: Visualización de Presencia
- [ ] El contador muestra el número correcto de usuarios
- [ ] El panel de actividad lista los usuarios activos
- [ ] La fila tiene fondo azul cuando alguien edita
- [ ] El badge flotante muestra nombre y campo correctos
- [ ] El círculo azul aparece en la celda correcta

### Prueba 2: Actualización en Tiempo Real
- [ ] Al editar en navegador A, navegador B muestra indicadores en ~5 segundos
- [ ] Al cambiar de campo, los indicadores se mueven a la nueva celda
- [ ] Al salir del campo (blur), los indicadores desaparecen en ~5 segundos

### Prueba 3: No Intrusividad
- [ ] Mientras escribes, la página NO se actualiza
- [ ] Puedes escribir sin interrupciones
- [ ] Los datos no se pierden durante la edición

### Prueba 4: Múltiples Usuarios
- [ ] Con 3+ usuarios, todos ven la actividad de los demás
- [ ] Cada usuario tiene su propio color/identificación
- [ ] No hay conflictos visuales

### Prueba 5: Limpieza Automática
- [ ] Al cerrar el navegador de un usuario, sus indicadores desaparecen en ~30 segundos
- [ ] Al cambiar de página, los indicadores se limpian
- [ ] No quedan indicadores "fantasma"

---

## 🎯 Casos de Uso Específicos

### Caso 1: Refinery y Logística Editando Simultáneamente

**Escenario:** Refinería completa campos de galones mientras logística programa la fecha

1. **Usuario Refinery:**
   - Haz clic en campo "Galones" de la fila #5
   - Empieza a escribir: `12500`

2. **Usuario Logística:**
   - Verás la fila #5 con fondo azul
   - Badge: "👤 Refinery Control · Galones"
   - Puedes editar "Fecha Programación" sin conflictos

3. **Resultado:** Ambos pueden trabajar sin interferencias

---

### Caso 2: Evitar Sobreescritura de Datos

**Escenario:** Dos usuarios intentan editar el mismo campo

1. **Usuario A:**
   - Edita "Número de Guía" en fila #10
   - Badge aparece para otros usuarios

2. **Usuario B:**
   - Ve el badge "Usuario A · Número de Guía"
   - Sabe que no debe editar ese campo ahora
   - Espera o edita otro campo

3. **Resultado:** Se evitan conflictos de datos

---

### Caso 3: Coordinación de Equipo

**Escenario:** Supervisar trabajo de múltiples usuarios

1. **Usuario Admin:**
   - Abre el panel de actividad (botón con ícono de usuarios)
   - Ve lista completa:
     ```
     👤 Samantha
        📝 Editando: Placa
     
     👤 Refinery Control
        📝 Editando: Temperatura
     
     👤 Ignacio
        🌐 Navegando
     ```

2. **Resultado:** Visibilidad total del equipo

---

## 🐛 Solución de Problemas

### Problema: "No veo los indicadores"

**Soluciones:**
1. Verifica que ambos usuarios estén en la misma vista (Programación de Cargue)
2. Espera 5 segundos para la actualización automática
3. Refresca la página (`F5`)
4. Verifica que el usuario esté realmente editando (foco en input)

---

### Problema: "El contador dice 0 pero hay otros usuarios"

**Soluciones:**
1. Los otros usuarios deben tener la página abierta hace menos de 30 segundos
2. Verifica que el otro usuario tenga permisos de `programacion_cargue`
3. Revisa la consola del navegador (`F12`) por errores

---

### Problema: "Los indicadores no desaparecen"

**Soluciones:**
1. Espera 30 segundos (limpieza automática)
2. El usuario debe hacer `blur` (salir del campo)
3. Refresca la página

---

## 📊 Tiempos de Actualización

| Evento | Tiempo |
|--------|--------|
| Envío de presencia al servidor | Inmediato (al hacer foco) |
| Actualización de indicadores | Cada 5 segundos |
| Limpieza de inactivos | 30 segundos |
| Pausa durante edición | Automática (no interrumpe) |

---

## 🎨 Significado Visual

### Colores
- **🟦 Azul Claro** (fondo de fila): Alguien está editando
- **🔵 Azul Oscuro** (badge/círculo): Color de presencia activa
- **🟢 Verde** (contador): Usuarios en línea

### Animaciones
- **Pulso** en el borde de la fila: Indica edición activa
- **Ripple** en el círculo: Llama la atención a la celda
- **Fade in** del badge: Entrada suave del indicador

---

## 📝 Notas Técnicas

### Backend
- **Almacenamiento:** Memoria (no base de datos)
- **Endpoints:**
  - `POST /api/programacion/presence` - Actualizar presencia
  - `GET /api/programacion/presence` - Obtener usuarios activos
- **Limpieza:** Automática cada petición

### Frontend
- **Polling:** Cada 5 segundos
- **Pausa automática:** Durante `focusin` en inputs
- **Eventos:** `focusin`, `focusout`, `beforeunload`

---

## 🚀 Próximos Pasos

1. **Probar con usuarios reales** en producción
2. **Ajustar tiempos** si es necesario (5s → 3s o 10s)
3. **Agregar sonido** (opcional) cuando alguien edita
4. **Persistencia** en base de datos (opcional, para auditoría)

---

## 📞 Soporte

Si encuentras problemas:
1. Revisa la consola del navegador (`F12` → Console)
2. Verifica los logs del servidor
3. Comprueba que los endpoints respondan correctamente

---

**Fecha de creación:** Enero 8, 2026  
**Versión:** 1.0  
**Sistema:** Programación de Cargue - Conquers Trading
