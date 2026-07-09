# Manual de uso - Modelo de Optimizacion LP

## 1) Proposito del modulo
Este modulo calcula la mejor configuracion operativa y comercial (compras, transporte, refinacion, blending y ventas) para maximizar la utilidad diaria del sistema, respetando restricciones de capacidad, calidad y demanda.

El resultado principal es una solucion de optimizacion lineal con:
- utilidad total esperada
- volumenes optimos por etapa
- costos operativos y logisticos
- trazabilidad de composicion y calidad de mezclas

---

## 2) Que se puede hacer con el modelo
Con la version actual puedes:
- cargar un archivo de parametros Excel propio o usar el archivo base por defecto
- ejecutar el solver y obtener una solucion optima (o diagnostico de inviabilidad)
- editar premium por compra directamente en la interfaz (escenario) sin modificar la hoja base de parametros
- ver crudos/productos desagregados por variacion logistica de primer tramo (duplicacion por variante de transporte)
- analizar peso por galon (kg/gal) y peso diario equivalente (TPD) en compras y transporte
- revisar refinacion agrupada por producto con subtotales por grupo y total conjunto por proceso
- usar filtros por pestana para auditar rapidamente resultados
- exportar un informe Excel consolidado del escenario

---

## 3) Acceso y permisos
Para usar la pantalla del modelo en la aplicacion web:
- requiere permiso del modulo modelo_optimizacion
- adicionalmente, el backend restringe acceso a:
  - rol admin
  - o correos autorizados explicitamente en el codigo

Si no tienes acceso, la app mostrara mensaje de permiso denegado.

---

## 4) Archivo de parametros: estructura requerida
El modelo utiliza un Excel con hojas de negocio y restricciones. En operacion normal se esperan, como minimo, estas hojas:
- 1.NODOS
- 2.FLUJOS
- 3.COMPRAS
- 4.RUTAS_TRANSPORTE
- 5.CURVA_DESTILACION
- 6.VENTAS
- 7.COSTOS_REFINACION
- 8.LIMITES_CALIDAD
- 9.FLASH_RESTR
- 10.CVC
- 11.REL_CRUDO_MEZCLA
- 12.COSTOS_OPERACIONALES

### Validaciones criticas previas a la corrida
Antes de resolver, el backend valida de forma estricta:

#### Hoja 3.COMPRAS
Columnas requeridas:
- CRUDO O PRODUCTO
- ORIGEN
- Volumen Minimo a Compra (BPD)
- Volumen Disponible a Compra (BPD)

Reglas:
- volumen minimo no puede ser mayor al volumen maximo
- no puede haber claves duplicadas por (CRUDO O PRODUCTO, ORIGEN)

#### Hoja 11.REL_CRUDO_MEZCLA
Columnas requeridas:
- FLUJO
- CRUDO ORIGEN
- TIPO FLUJO
- DESTINO
- MEZCLA A PERTENECER

Reglas:
- TIPO FLUJO solo permite: CRUDO, PRODUCTO COMPRADO, PRODUCTO REFINADO
- en CRUDO/PRODUCTO COMPRADO no deben faltar FLUJO, DESTINO, MEZCLA A PERTENECER
- en PRODUCTO REFINADO no deben faltar FLUJO, CRUDO ORIGEN, DESTINO, MEZCLA A PERTENECER
- no deben existir duplicados de llave segun el tipo de flujo

Si falla una validacion critica, la corrida se bloquea y debes corregir el Excel.

---

## 5) Flujo recomendado de uso (paso a paso)

### Paso 1. Entrar al modulo
Abre la pantalla de Modelo de Optimizacion LP en la aplicacion web.

### Paso 2. Definir escenario
En el campo Nombre del Escenario, escribe un nombre claro (ejemplo: ESC_BASE_MAYO, ESC_PREMIUM_ALTO, ESC_LOGISTICA_NORTE).

### Paso 3. Cargar archivo de parametros (opcional)
- Si deseas probar otro archivo: arrastralo o selecciona .xlsx en la zona de carga.
- Si no cargas archivo: se usa la ruta por defecto definida en backend.

### Paso 4. Ejecutar modelo
Pulsa Ejecutar Modelo.

El sistema hace:
1. lectura del archivo
2. aplicacion temporal de premium (si hay overrides)
3. validaciones criticas
4. corrida del solver CBC
5. construccion de tablas y KPIs

### Paso 5. Revisar estado del solver
Estados posibles:
- Optimo: solucion factible y objetivo resuelto
- Infeasible: restricciones incompatibles entre si
- Not Solved / Undefined: el solver no entrego solucion util

### Paso 6. Analizar resultados por pestana
Usa KPIs, tarjetas de senales, filtros y tablas para auditar la solucion.

### Paso 7. Exportar informe
Pulsa Descargar Informe para generar el Excel del escenario con resumen y detalle.

### Explicacion de uso del modelo (como decide)
Esta seccion explica como usar el resultado para tomar decisiones, no solo para ejecutar el boton.

1. El modelo maximiza utilidad total diaria.
  - Busca la combinacion de compras, rutas, refinacion, blending y ventas que deje mayor margen economico.

2. El modelo decide volumenes, no opiniones.
  - Salidas clave de decision: cuanto comprar por flujo/origen, por donde transportarlo, cuanto refinar, como mezclar y cuanto vender por punto.

3. Todo esta limitado por restricciones reales.
  - Oferta y demanda (min/max de compra y venta).
  - Capacidades de rutas y plantas.
  - Reglas de calidad de blending.
  - Balance de masa (lo que entra y sale debe cuadrar).

4. Premium cambia el costo de compra en escenarios.
  - Al subir premium, ese flujo se vuelve menos atractivo y el modelo puede mover volumen a otras opciones.
  - Al bajar premium, ese flujo se vuelve mas competitivo y puede ganar participacion.

5. Variantes de transporte muestran por que se duplica una compra.
  - Si un mismo flujo/origen tiene varios primeros tramos logisticos, aparece en varias filas.
  - No son compras distintas de negocio; son variantes logisticas del mismo flujo base.

6. Como interpretar una corrida de forma practica.
  - Primero: estado del solver (debe ser Optimo para tomarlo como plan base).
  - Segundo: utilidad y margen neto (resultado economico).
  - Tercero: concentracion de ventas, rutas costosas y cumplimiento de calidad.
  - Cuarto: revisar sensibilidad (premium, rutas, limites) y comparar escenarios.

7. Regla de oro de uso.
  - Usa el modelo para comparar escenarios y soportar decisiones.
  - No uses una corrida aislada sin validar supuestos de entrada y restricciones.

---

## 6) Controles principales de la pantalla
- Ejecutar Modelo: corre el escenario
- Descargar Informe: exporta reporte Excel del resultado activo
- Limpiar Premium: elimina ajustes premium de escenario en la UI
- Premiums activos: badge que indica cuantos ajustes no cero estan cargados
- Filtros por pestana: caja de busqueda para acotar filas
- Vista compacta: reduce densidad visual de tablas

Nota: el resultado queda cacheado en sesion temporal. Si expira, debes ejecutar de nuevo.

---

## 7) Uso de Premium por escenario (sin tocar el archivo base)
Esta funcion permite simulacion comercial rapida sin editar manualmente el Excel maestro.

### Como usarlo
1. Ejecuta una corrida inicial.
2. Ve a pestana Compras.
3. En columna Premium USD/BBL, escribe ajustes por fila.
4. Vuelve a ejecutar modelo.

### Como se aplica internamente
- clave de premium: (Flujo Base Premium, Origen Base Premium)
- precio ajustado usado por el escenario:
  - Precio Ajustado = Precio Base + Premium
- costo ajustado visual:
  - Costo Ajustado = Volumen Comprado BPD x Precio Ajustado
- el backend crea una copia temporal del archivo y aplica premium solo ahi
- la hoja original de parametros no se modifica

### Buenas practicas
- usa premium solo para escenarios (no para corregir datos estructurales)
- documenta en el nombre del escenario el supuesto premium
- limpia premium antes de volver a base

---

## 8) Duplicacion de crudos por variacion de transporte
Se implemento desagregacion de compras por variante logistica del primer tramo.

Que significa:
- una compra (flujo, origen) puede aparecer en varias filas si tiene multiples rutas iniciales
- cada fila representa una variante de destino/ruta inicial
- la tabla Compras muestra columna Variante Transporte para distinguirlas

Esto permite:
- ver en que variante logistica cae el volumen comprado
- comparar impacto economico por variacion de ruta
- mantener premium por clave base sin romper la consistencia comercial

Importante:
- si no existe ruta de primer tramo para una compra, se etiqueta SIN RUTA
- no es aun un esquema de tramos tarifarios por bloques de volumen; es desagregacion por variante de ruta inicial

---

## 9) Indicadores de peso y densidad
En Compras y Transporte aparecen indicadores nuevos:
- Densidad BBL/TON
- Peso por Galon kg/gal
- Peso diario equivalente TPD

Conversiones usadas:
- kg/gal = 1000 / (densidad_bbl_por_ton x 42)
- TPD = BPD / densidad_bbl_por_ton

Esto ayuda a:
- validar consistencia fisica de los volumenes
- comparar corrientes con diferentes densidades
- traducir impactos volumetricos a masa

---

## 10) Como leer cada pestana

### Compras
Muestra:
- crudo/producto y origen
- variante de transporte
- volumen comprado
- precio base, premium y precio ajustado
- costo ajustado total

Uso recomendado:
- detectar productos de mayor impacto economico
- simular sensibilidad por premium
- comparar reparticion por variante logistica

### Ventas
Muestra:
- corriente de venta
- punto de venta
- volumen, precio e ingreso
- origen (para refinados)
- graficos de distribucion por punto y participacion de ingresos

Uso recomendado:
- identificar concentracion comercial
- validar que el mix de venta soporte utilidad

### Transporte
Muestra:
- flujo, origen, destino y ruta
- volumen transportado
- costo unitario y costo total
- metricas de peso

Uso recomendado:
- ubicar rutas mas costosas
- comparar alternativas de logistica

### Blending
Muestra por mezcla/centro:
- volumen producido
- API, azufre, viscosidad y otras propiedades

Uso recomendado:
- validar cumplimiento de limites de calidad
- detectar cuellos de botella de factibilidad

### Refinacion
Vista mejorada con:
- agrupacion desplegable por producto refinado
- subtotales por producto
- tarjetas de volumen por planta/proceso
- total conjunto refinado/proceso

Uso recomendado:
- evaluar que plantas empujan cada producto
- revisar dependencia por crudo origen

### Costos
Incluye tres bloques:
- Throughput refinerias
- Costos operacionales por centro
- Costos operacionales refinados en blend

Uso recomendado:
- descomponer costo total en componentes operativos
- identificar drivers de costo no comerciales

### Composicion
Muestra:
- componentes que forman cada blend
- volumen por componente
- grafico de participacion por blend

Uso recomendado:
- trazabilidad de receta real
- auditoria de dependencia de componentes

---

## 11) Estados del solver y que hacer

### Estado: Optimo
Interpretacion:
- existe solucion factible y economicamente evaluada

Accion:
- analizar sensibilidad (premium, rutas, limites)
- guardar informe del escenario

### Estado: Infeasible
Interpretacion:
- alguna combinacion de restricciones vuelve imposible cumplir todo a la vez

Accion sugerida:
- revisar limites en 8.LIMITES_CALIDAD
- revisar capacidades/rutas en 4.RUTAS_TRANSPORTE
- revisar minimos/maximos en 3.COMPRAS y 6.VENTAS
- revisar pertenencias en 11.REL_CRUDO_MEZCLA

### Estado: Not Solved / Undefined
Interpretacion:
- el solver no devolvio solucion util (tiempo, estructura o datos)

Accion sugerida:
- simplificar escenario temporalmente
- validar datos base
- reintentar corrida

---

## 12) Reporte Excel exportado
El boton Descargar Informe genera un archivo con nombre:
- Resultados_<NombreEscenario>.xlsx

Contenido tipico:
- Resumen Ejecutivo
- Compras
- Ventas
- Transporte
- Blending y calidades
- (y otras hojas de detalle segun la version del generador)

Recomendacion:
- usa una convencion de nombres de escenario para trazabilidad historica

---

## 13) Errores frecuentes y solucion rapida

### Error: faltan hojas requeridas
Causa:
- archivo sin 3.COMPRAS o 11.REL_CRUDO_MEZCLA

Solucion:
- usa plantilla completa del modelo

### Error: Volumen Minimo mayor a Volumen Disponible
Causa:
- parametrizacion inconsistente en compras

Solucion:
- corregir min/max por fila

### Error: claves duplicadas en compras
Causa:
- misma combinacion (CRUDO O PRODUCTO, ORIGEN) repetida

Solucion:
- consolidar o depurar duplicados

### Error: tipo flujo invalido en REL_CRUDO_MEZCLA
Causa:
- valor fuera de catalogo permitido

Solucion:
- usar exactamente CRUDO, PRODUCTO COMPRADO o PRODUCTO REFINADO

### Resultado infeasible con tablas visibles
Causa:
- el solver genero aproximacion pero declaro inviabilidad final

Solucion:
- usar tablas como diagnostico, no como plan definitivo

---

## 14) Checklist operativo (antes de publicar un escenario)
- [ ] el estado del solver es Optimo
- [ ] los premium usados estan justificados y documentados
- [ ] no hay rutas/costos outlier sin explicacion
- [ ] volumenes de compras y ventas tienen coherencia operativa
- [ ] blending cumple especificaciones objetivo
- [ ] refinacion presenta distribucion razonable por planta
- [ ] informe Excel exportado y archivado con nombre estandar

---

## 15) Limites actuales del modulo
- El tiempo de corrida del solver esta limitado (aprox. 120 segundos por corrida).
- La validacion previa estricta se concentra en hojas criticas (compras y relacion crudo-mezcla).
- La desagregacion de compras por transporte es por variante de primer tramo, no por bloques tarifarios de volumen escalonado.

---

## 16) Recomendaciones de trabajo en equipo
- Mantener un archivo maestro controlado y usar upload solo para pruebas
- Estandarizar nombres de escenario (fecha + objetivo + supuesto)
- Registrar cambios de premium y supuestos logisticos
- Comparar escenarios por utilidad, riesgo de calidad y concentracion comercial

---

## 17) Mini guia express (5 minutos)
1. Abre el modulo y define nombre de escenario.
2. Carga Excel de parametros o usa el base.
3. Ejecuta modelo y confirma estado Optimo.
4. Revisa Compras, Ventas y Transporte para impactos economicos.
5. Ajusta premium en Compras si quieres simulacion comercial.
6. Reejecuta y compara KPIs.
7. Exporta informe final.

---

Fin del manual.
