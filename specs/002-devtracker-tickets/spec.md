# Feature Specification: DevTracker — Registro y Control de Tickets de Desarrollo

**Feature Branch**: `002-devtracker-tickets`

**Created**: 2026-08-07

**Status**: Draft

**Input**: User description: "Sistema de registro y control de tickets de desarrollo (DevTracker): registrar cada requerimiento/desarrollo que me piden (quién lo solicita, descripción, prioridad), controlar fechas (solicitud, fecha comprometida de entrega, entrada a pruebas/QA, salida a producción) con indicadores visuales de a tiempo / próximo a vencer / retrasado, flujo de estados Solicitado → En Desarrollo → En Pruebas (QA) → En Producción, registro de errores/bugs encontrados en pruebas o producción con severidad y estado de resolución, checklist de puntos a revisar antes de cada despliegue, y métricas/resumen (tickets totales, entregados a tiempo, pendientes en pruebas, bugs abiertos). Vista tablero Kanban y vista lista con filtros y búsqueda."

**Ampliación (2026-08-07)**: el alcance se extendió a **dos portales sobre una misma base de datos**: (1) el espacio de trabajo del desarrollador, con el tablero completo, y (2) un portal donde los propios solicitantes radican sus requerimientos y consultan el estado de lo suyo. Lo radicado en el portal llega a una bandeja de entrada que el desarrollador tría antes de que entre al tablero. Ver Historias 6 y 7 y los requerimientos FR-038 a FR-052.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Registrar un requerimiento y saber qué prometí (Priority: P1)

Llega un requerimiento nuevo por WhatsApp, correo o en una llamada. El desarrollador lo registra en menos de un minuto: quién lo pidió, qué pidió en sus propias palabras, qué tan urgente es y para cuándo se comprometió a entregarlo. A partir de ese momento el requerimiento deja de vivir en la memoria o en un chat y pasa a estar en una sola lista consultable.

Al abrir el sistema en cualquier momento, el desarrollador ve de un vistazo cuáles compromisos están al día, cuáles vencen en los próximos días y cuáles ya están retrasados, sin tener que abrir cada ticket ni hacer cuentas de fechas mentalmente.

**Why this priority**: Es el problema de raíz que motivó la solicitud: no existe registro de lo que le piden ni de lo que prometió. Sin esto, ninguna otra funcionalidad tiene sobre qué operar. Un sistema que solo hiciera esto ya elimina el olvido de requerimientos y los compromisos incumplidos por descuido.

**Independent Test**: Se puede probar completo registrando tres requerimientos con fechas comprometidas distintas (una pasada, una para mañana, una para dentro de dos semanas) y verificando que la lista los muestra clasificados como retrasado, próximo a vencer y a tiempo respectivamente, y que la clasificación se mantiene correcta al día siguiente sin intervención manual.

**Acceptance Scenarios**:

1. **Given** que no existe ningún registro del requerimiento, **When** el desarrollador registra solicitante, descripción, prioridad y fecha comprometida, **Then** el ticket queda guardado con un identificador propio, su fecha de solicitud y estado inicial "Solicitado".
2. **Given** un ticket con fecha comprometida ya vencida y que aún no está en producción, **When** el desarrollador abre la lista de tickets, **Then** el ticket aparece marcado como retrasado e indica cuántos días lleva de retraso.
3. **Given** un ticket cuya fecha comprometida está dentro del umbral de aviso, **When** el desarrollador abre la lista, **Then** el ticket aparece marcado como próximo a vencer e indica cuántos días faltan.
4. **Given** un ticket que ya llegó a producción, **When** se evalúa su indicador de tiempo, **Then** el sistema deja de mostrarlo como retrasado o próximo a vencer y muestra si la entrega final fue a tiempo o fuera de plazo respecto a lo comprometido.
5. **Given** un ticket registrado sin fecha comprometida, **When** el desarrollador abre la lista, **Then** el ticket se muestra como "sin compromiso de fecha" y no genera alertas falsas de retraso.

---

### User Story 2 - Mover el trabajo por sus etapas y ver el tablero (Priority: P2)

El desarrollador arranca a trabajar en un requerimiento, lo termina y lo pasa a pruebas, y cuando queda validado lo sube a producción. En cada paso registra la fecha real en que ocurrió, de modo que después pueda responder con evidencia preguntas como "¿desde cuándo está en pruebas?" o "¿cuándo salió esto a producción?".

El tablero muestra el trabajo repartido en columnas por etapa (Solicitado, En Desarrollo, En Pruebas, En Producción), de forma que se vea en segundos cuánto hay pendiente en cada etapa y qué está atascado.

**Why this priority**: Sobre el registro base, esto es lo que convierte la lista en control de avance. Responde a "que ya se encuentra en prueba, que ya lo subí a producción". Es independiente de la Historia 1 en cuanto a prueba, pero aporta más valor cuando ya hay tickets registrados.

**Independent Test**: Se puede probar tomando un ticket registrado y llevándolo por las cuatro etapas, verificando que cada cambio de etapa queda con su fecha real registrada, que el tablero lo reubica de columna y que el historial del ticket permite reconstruir la secuencia de fechas.

**Acceptance Scenarios**:

1. **Given** un ticket en estado "Solicitado", **When** el desarrollador lo pasa a "En Desarrollo", **Then** el sistema registra la fecha de inicio de desarrollo y el ticket aparece en la columna correspondiente del tablero.
2. **Given** un ticket en "En Desarrollo", **When** el desarrollador lo pasa a "En Pruebas", **Then** el sistema registra la fecha de entrada a pruebas y muestra desde ese momento cuántos días lleva en pruebas.
3. **Given** un ticket en "En Pruebas", **When** el desarrollador lo pasa a "En Producción", **Then** el sistema registra la fecha de salida a producción y la compara contra la fecha comprometida para determinar si se cumplió el plazo.
4. **Given** un ticket que ya está en producción y presenta un problema, **When** el desarrollador lo devuelve a "En Desarrollo", **Then** el sistema permite el retroceso, conserva las fechas anteriores como historial y registra el nuevo ciclo sin borrar el anterior.
5. **Given** un ticket cancelado o descartado por el solicitante, **When** el desarrollador lo marca como cancelado, **Then** el ticket sale del flujo activo y deja de contar en los indicadores de pendientes y de cumplimiento de plazos.

---

### User Story 3 - Registrar los errores encontrados y su resolución (Priority: P2)

Durante las pruebas, o ya con el desarrollo en producción, aparecen fallas. El desarrollador las anota dentro del ticket que las originó: qué falló, qué tan grave es y si ya quedó corregida. Así, cuando el solicitante pregunta por qué algo sigue en pruebas, hay una respuesta concreta y no una explicación de memoria.

**Why this priority**: Cubre explícitamente "qué error se encontraron". Es la razón más frecuente por la que un desarrollo se demora entre pruebas y producción, y sin registrarlo el retraso queda sin explicación. Se prueba de forma independiente sobre cualquier ticket existente.

**Independent Test**: Se puede probar registrando dos errores de distinta severidad sobre un mismo ticket, marcando uno como corregido, y verificando que el ticket refleja que aún tiene un error abierto y que el contador global de errores abiertos disminuyó en uno.

**Acceptance Scenarios**:

1. **Given** un ticket en pruebas, **When** el desarrollador registra un error con descripción y severidad (Crítico, Mayor, Menor), **Then** el error queda asociado al ticket con su fecha de detección y estado "Abierto".
2. **Given** un ticket con errores abiertos, **When** el desarrollador consulta el ticket o el tablero, **Then** ve de forma visible cuántos errores abiertos tiene y cuál es la severidad más alta entre ellos.
3. **Given** un error abierto, **When** el desarrollador lo marca como corregido, **Then** el sistema registra la fecha de corrección y el error deja de contar como abierto sin desaparecer del historial.
4. **Given** un ticket con al menos un error abierto de severidad Crítico, **When** el desarrollador intenta pasarlo a "En Producción", **Then** el sistema advierte sobre los errores críticos abiertos y exige confirmación explícita antes de permitir el cambio.
5. **Given** un error detectado con el desarrollo ya en producción, **When** el desarrollador lo registra, **Then** el error queda marcado como detectado en producción, para diferenciarlo de los hallados en pruebas.

---

### User Story 4 - Checklist de revisión antes de desplegar (Priority: P3)

Antes de subir algo a pruebas o a producción, el desarrollador recorre una lista de puntos que siempre debe revisar (respaldo de base de datos, variables de entorno, permisos, logs, prueba de regresión) y va marcando lo verificado en el propio ticket. La lista se propone automáticamente para cada ticket nuevo a partir de una plantilla, y puede ajustarse por ticket cuando ese desarrollo tiene revisiones particulares.

**Why this priority**: Cubre "cosas que debo revisar". Previene errores repetidos por olvido, pero aporta valor pleno solo cuando ya existen tickets fluyendo por las etapas, por eso va después del flujo y del registro de errores.

**Independent Test**: Se puede probar sobre un ticket nuevo verificando que aparece la lista de revisión por defecto, marcando parte de los ítems, agregando un ítem propio y comprobando que al intentar pasar a producción el sistema advierte sobre los puntos sin verificar.

**Acceptance Scenarios**:

1. **Given** un ticket recién creado, **When** el desarrollador lo abre, **Then** encuentra la lista de puntos de revisión por defecto ya cargada y sin marcar.
2. **Given** un ticket con lista de revisión, **When** el desarrollador marca un punto como verificado, **Then** el sistema guarda la marca y muestra el avance de la lista (verificados sobre total).
3. **Given** un ticket con puntos de revisión sin marcar, **When** el desarrollador intenta pasarlo a "En Producción", **Then** el sistema advierte cuáles quedaron sin verificar y exige confirmación explícita para continuar.
4. **Given** un ticket con necesidades particulares, **When** el desarrollador agrega o elimina un punto de la lista de ese ticket, **Then** el cambio afecta solo a ese ticket y no a la plantilla ni a los demás tickets.
5. **Given** la plantilla de revisión por defecto, **When** el desarrollador la modifica, **Then** los cambios aplican a los tickets creados desde ese momento y no alteran los tickets ya existentes.

---

### User Story 5 - Encontrar tickets y ver el resumen de la operación (Priority: P3)

Con decenas de tickets acumulados, el desarrollador necesita llegar rápido a uno concreto ("lo que pidió Contabilidad el mes pasado") y también responder preguntas de conjunto: cuántos desarrollos tengo abiertos, cuántos entregué a tiempo, cuántos están esperando validación, cuántos errores tengo sin corregir.

**Why this priority**: Es lo que hace sostenible el sistema en el tiempo y permite rendir cuentas hacia arriba. No es indispensable con pocos tickets, por eso va al final, pero se vuelve crítico a partir de cierto volumen.

**Independent Test**: Se puede probar con un conjunto de tickets de prueba en distintos estados y prioridades, verificando que la búsqueda por texto y los filtros por estado, prioridad y solicitante devuelven exactamente el subconjunto esperado, y que los contadores del resumen coinciden con lo que muestra la lista filtrada.

**Acceptance Scenarios**:

1. **Given** un conjunto de tickets registrados, **When** el desarrollador escribe un término en la búsqueda, **Then** la vista muestra solo los tickets cuyo título, descripción o solicitante contienen ese término.
2. **Given** un conjunto de tickets en distintos estados, **When** el desarrollador aplica filtros por estado, prioridad y solicitante, **Then** ambas vistas (tablero y lista) muestran únicamente los tickets que cumplen todos los filtros aplicados simultáneamente.
3. **Given** tickets registrados con distintos desenlaces de plazo, **When** el desarrollador abre el resumen, **Then** ve los totales de tickets activos, tickets en pruebas, tickets retrasados, errores abiertos y porcentaje de entregas a tiempo sobre lo ya entregado.
4. **Given** la vista de tablero, **When** el desarrollador cambia a la vista de lista, **Then** conserva los filtros y la búsqueda aplicados y ve los mismos tickets en formato de tabla ordenable por fecha comprometida, prioridad o estado.
5. **Given** el registro histórico de tickets, **When** el desarrollador exporta la información, **Then** obtiene un archivo con los tickets, sus fechas, sus errores y su estado, utilizable fuera del sistema.

---

### User Story 6 - El solicitante radica su requerimiento y el desarrollador lo tría (Priority: P2)

Hoy los requerimientos llegan por WhatsApp, correo o de viva voz, y el desarrollador tiene que transcribirlos. En vez de eso, el solicitante entra al portal de solicitudes con la misma cuenta con la que ya usa el sistema, describe lo que necesita, indica qué tan urgente le parece y para cuándo lo necesitaría, y radica. Su solicitud queda firmada automáticamente con su nombre y su área, sin que tenga que escribirlo.

Esa solicitud **no entra directo al tablero**: cae en una bandeja de entrada del desarrollador. Él la revisa y decide: la acepta (y ahí sí le pone la prioridad real y **la fecha que él se compromete a cumplir**), la devuelve pidiendo más detalle, o la rechaza explicando por qué. Solo lo aceptado entra al flujo de trabajo.

La separación es deliberada: el solicitante **propone** urgencia y fecha deseada; el desarrollador **compromete** la fecha real. Si el solicitante pudiera fijar la fecha de entrega, todo llegaría marcado como urgente para mañana y el tablero perdería sentido.

**Why this priority**: Elimina el trabajo de transcripción y hace que el requerimiento quede escrito por quien lo necesita, con sus propias palabras y sin intermediarios. Requiere que el registro base (Historia 1) exista, pero se prueba de forma independiente.

**Independent Test**: Se puede probar entrando con una cuenta distinta a la del desarrollador, radicando una solicitud, y verificando que aparece en la bandeja de entrada del desarrollador firmada con el nombre y área correctos, que no aparece en el tablero hasta ser aceptada, y que al aceptarla con prioridad y fecha comprometida entra al tablero como ticket normal.

**Acceptance Scenarios**:

1. **Given** un usuario con sesión iniciada que no es el desarrollador, **When** entra al portal de solicitudes, **Then** ve el formulario para radicar y la lista de sus propias solicitudes, y no ve el tablero de trabajo ni solicitudes de otras personas.
2. **Given** un usuario en el portal, **When** radica una solicitud con título, descripción, urgencia percibida y fecha deseada, **Then** la solicitud queda registrada con su nombre y área tomados de su sesión, con fecha de radicación y en estado "Por revisar".
3. **Given** una solicitud radicada, **When** el desarrollador abre su espacio de trabajo, **Then** la ve en la bandeja de entrada con un indicador de cuántas solicitudes nuevas hay sin triar, y la solicitud **no** aparece todavía en ninguna columna del tablero.
4. **Given** una solicitud en la bandeja, **When** el desarrollador la acepta asignándole prioridad real y fecha comprometida, **Then** pasa a estado "Solicitado", entra al tablero como ticket con todo el comportamiento de fechas e indicadores, y conserva la constancia de que se originó en el portal, quién la radicó y qué fecha había pedido.
5. **Given** una solicitud sin detalle suficiente, **When** el desarrollador la devuelve con un comentario, **Then** el solicitante ve el comentario en su portal y puede completar y volver a radicar la misma solicitud sin crear una nueva.
6. **Given** una solicitud que no procede, **When** el desarrollador la rechaza con un motivo, **Then** el solicitante ve el motivo, la solicitud queda cerrada sin entrar al tablero y no cuenta en los indicadores de cumplimiento de plazos.
7. **Given** un requerimiento que le pidieron al desarrollador por fuera del portal, **When** él lo registra directamente en su espacio de trabajo, **Then** el ticket entra de una vez como "Solicitado" sin pasar por la bandeja de entrada.

---

### User Story 7 - El solicitante consulta en qué va lo suyo (Priority: P3)

En vez de escribirle al desarrollador para preguntar "¿ya quedó?", el solicitante entra a su portal y ve sus requerimientos con la etapa en que van, la fecha que el desarrollador se comprometió a cumplir y, si aplica, que está en pruebas o ya salió a producción.

Lo que el solicitante ve es deliberadamente resumido: etapa, fecha comprometida y fecha de salida a producción. No ve el detalle técnico de errores, ni la lista de revisión previa al despliegue, ni las métricas de cumplimiento del desarrollador.

**Why this priority**: Reduce las interrupciones, que es el segundo problema detrás del registro. Aporta valor pleno cuando ya hay tickets fluyendo, por eso va después del triage.

**Independent Test**: Se puede probar con dos solicitantes distintos, cada uno con tickets propios en etapas diferentes, verificando que cada uno ve únicamente los suyos con la etapa y fecha correctas, y que ninguno ve errores, checklists ni tickets del otro.

**Acceptance Scenarios**:

1. **Given** un solicitante con varios requerimientos en distintas etapas, **When** entra a su portal, **Then** ve solo los suyos, cada uno con su etapa actual y su fecha comprometida cuando ya fue asignada.
2. **Given** un requerimiento que aún está en la bandeja sin triar, **When** el solicitante lo consulta, **Then** ve que está "Por revisar" y que aún no tiene fecha comprometida, en vez de una fecha en blanco sin explicación.
3. **Given** un requerimiento que llegó a producción, **When** el solicitante lo consulta, **Then** ve la fecha en que salió a producción y que quedó entregado.
4. **Given** un requerimiento con errores registrados, **When** el solicitante lo consulta, **Then** ve que está en etapa de pruebas pero **no** ve el detalle de los errores ni la lista de revisión interna.
5. **Given** el desarrollador cambia un ticket de etapa, **When** el solicitante entra a su portal después, **Then** ve la etapa actualizada sin que el desarrollador haya tenido que avisarle por otro medio.

---

### Edge Cases

- **Fecha comprometida movida**: cuando el solicitante concede más plazo, el sistema debe conservar la fecha comprometida original además de la nueva, para que el indicador de cumplimiento no se "limpie" simplemente corriendo la fecha.
- **Ticket que vuelve de producción a desarrollo**: un desarrollo que ya salió y presenta fallas regresa a etapas anteriores; el sistema conserva las fechas del ciclo anterior y no las sobrescribe.
- **Ticket sin fecha comprometida**: no genera indicadores de retraso ni entra en el cálculo de porcentaje de cumplimiento.
- **Estado que salta etapas**: un cambio pequeño puede pasar de "Solicitado" directo a "En Producción" sin pasar por pruebas; el sistema lo permite y deja constancia de que no hubo etapa de pruebas.
- **Fechas incoherentes**: una fecha de salida a producción anterior a la fecha de entrada a pruebas, o una fecha comprometida anterior a la de solicitud, deben ser advertidas al guardar.
- **Errores heredados**: un ticket que se cierra con errores menores aún abiertos debe advertirlo, y esos errores deben seguir siendo visibles en el resumen.
- **Tickets antiguos en producción**: los desarrollos ya cerrados no deben saturar el tablero; el sistema los conserva consultables sin ocupar espacio en la vista activa.
- **Zona horaria y cambio de día**: el cálculo de "días restantes" y "días de retraso" debe recalcularse contra el día actual local sin requerir acción del usuario.
- **Solicitudes duplicadas**: dos personas pueden radicar el mismo requerimiento; el desarrollador debe poder marcar una como duplicada de otra al triarla, sin que la duplicada cuente dos veces en los indicadores.
- **Solicitud radicada y luego abandonada**: si el desarrollador la devuelve pidiendo detalle y el solicitante nunca responde, la solicitud no debe quedar contando como trabajo pendiente ni como incumplimiento; debe ser visible como "esperando al solicitante".
- **Fecha deseada imposible**: el solicitante puede pedir una fecha ya pasada o irrealizable; el sistema la registra como dato informativo y nunca la usa como fecha comprometida.
- **Solicitante que deja la empresa**: los tickets radicados por una cuenta que ya no está activa deben seguir siendo consultables por el desarrollador, conservando el nombre de quien los radicó.
- **Solicitud radicada sin urgencia ni fecha deseada**: es válida; entra a la bandeja y el desarrollador define ambos valores al aceptarla.
- **Ticket rechazado que se reactiva**: un requerimiento rechazado que después sí se aprueba debe poder reabrirse conservando su historia, en vez de radicarse de nuevo desde cero.

## Requirements *(mandatory)*

### Functional Requirements

**Registro de tickets**

- **FR-001**: El sistema MUST permitir registrar un ticket con, como mínimo: título, descripción del requerimiento, solicitante, prioridad y fecha comprometida de entrega.
- **FR-002**: El sistema MUST asignar automáticamente a cada ticket un identificador único y visible, y registrar su fecha de solicitud.
- **FR-003**: El sistema MUST permitir que la fecha comprometida sea opcional, y en ese caso NO MUST generar indicadores de retraso ni incluir el ticket en el cálculo de cumplimiento de plazos.
- **FR-004**: El sistema MUST permitir editar cualquier dato del ticket después de creado, conservando la fecha comprometida original cuando esta se modifica.
- **FR-005**: Los usuarios MUST poder eliminar o cancelar un ticket; un ticket cancelado MUST salir de los conteos de trabajo activo y de cumplimiento de plazos, permaneciendo consultable.
- **FR-006**: El sistema MUST soportar al menos tres niveles de prioridad (Alta, Media, Baja) y mostrarlos de forma visualmente distinguible.

**Flujo de estados y fechas**

- **FR-007**: El sistema MUST soportar los estados de flujo de trabajo: Solicitado, En Desarrollo, En Pruebas, En Producción y Cancelado; más los estados previos al flujo, propios de las solicitudes radicadas en el portal: Por revisar, Devuelta al solicitante y Rechazada.
- **FR-008**: El sistema MUST registrar automáticamente la fecha real en que un ticket entra a cada estado, y MUST permitir corregir esas fechas manualmente cuando el registro se hace en diferido.
- **FR-009**: Los usuarios MUST poder cambiar el estado de un ticket en cualquier dirección, incluyendo retrocesos y saltos de etapa, sin perder las fechas ya registradas.
- **FR-010**: El sistema MUST conservar el historial de cambios de estado de cada ticket, con fecha de cada transición.
- **FR-011**: El sistema MUST advertir al guardar cuando las fechas de un ticket sean incoherentes entre sí (por ejemplo, producción antes de pruebas, o compromiso antes de la solicitud).

**Indicadores de tiempo**

- **FR-012**: El sistema MUST clasificar cada ticket activo con fecha comprometida en uno de tres estados de plazo: a tiempo, próximo a vencer o retrasado.
- **FR-013**: El sistema MUST considerar "próximo a vencer" los tickets cuya fecha comprometida esté dentro de los 2 días siguientes, y "retrasado" los que la hayan superado sin llegar a producción.
- **FR-014**: El sistema MUST mostrar, para cada ticket con fecha comprometida, los días restantes o los días de retraso respecto al día actual.
- **FR-015**: El sistema MUST recalcular los indicadores de plazo contra la fecha actual cada vez que se consulta, sin requerir acción manual del usuario.
- **FR-016**: El sistema MUST indicar, para los tickets ya en producción, si la entrega ocurrió dentro o fuera del plazo comprometido, y con cuántos días de diferencia.
- **FR-017**: El sistema MUST mostrar cuántos días lleva un ticket en su estado actual, en particular para los tickets detenidos en pruebas.

**Errores y bugs**

- **FR-018**: El sistema MUST permitir registrar múltiples errores asociados a un ticket, cada uno con descripción, severidad (Crítico, Mayor, Menor), fecha de detección y etapa en que se detectó (pruebas o producción).
- **FR-019**: Los usuarios MUST poder marcar un error como corregido, quedando registrada la fecha de corrección y conservándose el error en el historial del ticket.
- **FR-020**: El sistema MUST mostrar en el ticket y en su tarjeta del tablero la cantidad de errores abiertos y la severidad más alta entre ellos.
- **FR-021**: El sistema MUST advertir y exigir confirmación explícita cuando se intente pasar a producción un ticket con errores críticos abiertos.

**Checklist de revisión**

- **FR-022**: El sistema MUST proponer automáticamente en cada ticket nuevo una lista de puntos de revisión tomada de una plantilla configurable por el usuario.
- **FR-023**: Los usuarios MUST poder marcar, desmarcar, agregar y eliminar puntos de revisión dentro de un ticket, sin que ello afecte a otros tickets ni a la plantilla.
- **FR-024**: El sistema MUST mostrar el avance de la lista de revisión de cada ticket (puntos verificados sobre total).
- **FR-025**: El sistema MUST advertir y exigir confirmación explícita cuando se intente pasar a producción un ticket con puntos de revisión sin verificar.
- **FR-026**: Los cambios a la plantilla de revisión MUST aplicar solo a los tickets creados después del cambio.

**Vistas, filtros y resumen**

- **FR-027**: El sistema MUST ofrecer una vista de tablero con una columna por estado del flujo y una vista de lista en formato de tabla, intercambiables conservando los filtros aplicados.
- **FR-028**: Los usuarios MUST poder cambiar el estado de un ticket directamente desde el tablero, sin abrir el detalle del ticket.
- **FR-029**: El sistema MUST permitir buscar tickets por texto libre sobre título, descripción y solicitante.
- **FR-030**: El sistema MUST permitir filtrar por estado, prioridad, solicitante, origen (portal o registro directo) y estado de plazo (a tiempo / próximo a vencer / retrasado), combinando varios filtros simultáneamente.
- **FR-031**: La vista de lista MUST permitir ordenar por fecha comprometida, prioridad, estado y fecha de solicitud.
- **FR-032**: El sistema MUST mostrar un resumen con: total de tickets activos, tickets por estado, tickets retrasados, errores abiertos y porcentaje de entregas dentro del plazo sobre los tickets ya entregados.
- **FR-033**: El sistema MUST mantener los tickets cerrados (en producción o cancelados) fuera de la vista activa por defecto, accesibles mediante un filtro de histórico.
- **FR-034**: Los usuarios MUST poder exportar la información de tickets, fechas y errores a un archivo utilizable fuera del sistema.

**Acceso y datos**

- **FR-035**: El sistema MUST persistir toda la información de forma que sobreviva al cierre y reapertura de la aplicación.
- **FR-036**: El sistema MUST ofrecer dos espacios diferenciados sobre una misma base de datos: el **espacio de trabajo del desarrollador**, con acceso total al tablero, fechas, errores, listas de revisión y métricas; y el **portal de solicitudes**, donde cualquier usuario con sesión radica requerimientos y consulta el estado de los suyos.
- **FR-037**: La información MUST estar centralizada e integrada en el sistema INVENTARIO (Flask + Base de Datos), siendo accesible desde cualquier equipo o dispositivo conectado a la aplicación.

**Portal de solicitudes y bandeja de entrada**

- **FR-038**: El portal de solicitudes MUST estar disponible para todo usuario con sesión iniciada en el sistema, sin necesidad de crear cuentas ni credenciales adicionales.
- **FR-039**: El sistema MUST permitir radicar una solicitud con, como mínimo: título, descripción del requerimiento, urgencia percibida y, opcionalmente, fecha deseada.
- **FR-040**: El sistema MUST tomar automáticamente el nombre y el área del solicitante desde su sesión, sin que este los escriba, y MUST registrar la fecha de radicación.
- **FR-041**: El solicitante NO MUST poder fijar la prioridad real, la fecha comprometida de entrega ni el estado de flujo de trabajo de ningún ticket; la urgencia y la fecha que indica se registran como valores propuestos, informativos.
- **FR-042**: Toda solicitud radicada en el portal MUST entrar en estado "Por revisar" y NO MUST aparecer en las columnas del tablero de trabajo hasta ser aceptada.
- **FR-043**: El espacio de trabajo del desarrollador MUST mostrar de forma visible la cantidad de solicitudes sin triar en la bandeja de entrada.
- **FR-044**: El desarrollador MUST poder resolver cada solicitud de la bandeja de una de tres formas: aceptarla, devolverla al solicitante con un comentario, o rechazarla con un motivo.
- **FR-045**: Al aceptar una solicitud, el sistema MUST exigir prioridad real y MUST permitir fijar la fecha comprometida; a partir de ese momento la solicitud se comporta como un ticket normal en estado "Solicitado".
- **FR-046**: El sistema MUST conservar en cada ticket originado en el portal: quién lo radicó, su área, la fecha de radicación, la urgencia propuesta y la fecha deseada, aun después de que el desarrollador asigne los valores reales.
- **FR-047**: El desarrollador MUST poder registrar tickets directamente en su espacio de trabajo, sin pasar por la bandeja de entrada, para los requerimientos que le llegan por WhatsApp, correo o llamada.
- **FR-048**: El sistema MUST distinguir y permitir filtrar los tickets según su origen: radicados en el portal o registrados directamente por el desarrollador.
- **FR-049**: Una solicitud devuelta al solicitante MUST poder ser completada y vuelta a radicar por este sobre el mismo registro, sin crear una solicitud nueva, y MUST conservar el comentario de devolución.
- **FR-050**: Las solicitudes rechazadas, devueltas o en estado "Por revisar" NO MUST contar en los indicadores de trabajo activo ni en el cálculo de cumplimiento de plazos.
- **FR-051**: En el portal, cada solicitante MUST ver únicamente los requerimientos que él mismo radicó, con su etapa actual, su fecha comprometida cuando ya exista y su fecha de salida a producción cuando aplique.
- **FR-052**: El portal NO MUST exponer al solicitante el detalle de errores registrados, las listas de revisión previas al despliegue, las métricas de cumplimiento del desarrollador ni los tickets de otras personas.

### Key Entities

- **Ticket de desarrollo**: el requerimiento solicitado. Atributos: identificador, título, descripción, solicitante, prioridad, estado actual, origen (portal o registro directo), fecha de solicitud, fecha comprometida (actual y original), fechas reales de inicio de desarrollo, entrada a pruebas y salida a producción, notas. Cuando proviene del portal, incorpora además los datos de radicación: urgencia propuesta, fecha deseada y fecha de radicación. Es el elemento central; todo lo demás cuelga de él.
- **Transición de estado**: cada movimiento de un ticket de un estado a otro. Atributos: estado origen, estado destino, fecha. Permite reconstruir la historia del ticket y calcular tiempos por etapa.
- **Error / bug**: falla detectada sobre un ticket. Atributos: descripción, severidad, etapa de detección (pruebas o producción), fecha de detección, estado (abierto/corregido), fecha de corrección. Un ticket puede tener varios; un error pertenece a un solo ticket.
- **Punto de revisión**: ítem de verificación previo al despliegue, asociado a un ticket. Atributos: texto, verificado sí/no, fecha de verificación. Se genera inicialmente desde la plantilla.
- **Plantilla de revisión**: conjunto de puntos de revisión por defecto que se copia a cada ticket nuevo. Editable por el usuario, independiente de los tickets ya creados.
- **Solicitante**: persona que pide el desarrollo. Corresponde a un usuario existente del sistema; su nombre y área se toman de la sesión al radicar. Se usa para firmar la solicitud, filtrar y agrupar tickets, y para determinar qué ve cada quien en el portal.
- **Resolución de triage**: la decisión del desarrollador sobre una solicitud radicada. Atributos: tipo (aceptada, devuelta, rechazada), comentario o motivo, fecha. Explica al solicitante por qué su requerimiento avanzó o no, y queda en el historial del ticket.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Registrar un requerimiento nuevo completo (solicitante, descripción, prioridad y fecha comprometida) toma menos de 60 segundos.
- **SC-002**: Al abrir el sistema, el desarrollador identifica en menos de 10 segundos y sin abrir ningún ticket cuántos compromisos están retrasados y cuáles son.
- **SC-003**: El 100 % de los requerimientos recibidos queda registrado con solicitante y fecha comprometida, eliminando los requerimientos que hoy se pierden en chats o en la memoria.
- **SC-004**: Cambiar un ticket de etapa y dejar registrada la fecha real toma menos de 5 segundos y no exige llenar formularios adicionales.
- **SC-005**: Ante la pregunta "¿en qué va lo que pedí?", el desarrollador responde con etapa actual, fecha de entrada a esa etapa y errores pendientes en menos de 30 segundos.
- **SC-006**: El porcentaje de entregas dentro del plazo comprometido es visible en todo momento y se calcula sobre el histórico completo de tickets entregados.
- **SC-007**: Ningún despliegue a producción ocurre sin que el sistema haya mostrado los puntos de revisión sin verificar y los errores críticos abiertos.
- **SC-008**: El sistema mantiene la información consultable y con tiempos de respuesta iguales a los del primer día con al menos 500 tickets acumulados y 1 000 errores registrados.
- **SC-009**: Después de tres meses de uso, el desarrollador puede responder con datos —no de memoria— cuántos desarrollos entregó, para quién y cuántos salieron con retraso.
- **SC-010**: Un solicitante que nunca ha usado el sistema radica su primer requerimiento en menos de 3 minutos y sin necesidad de instrucciones previas.
- **SC-011**: Triar una solicitud de la bandeja (aceptarla con prioridad y fecha, devolverla o rechazarla) toma menos de 30 segundos.
- **SC-012**: Al menos el 70 % de los requerimientos llega radicado por el portal en lugar de por WhatsApp, correo o llamada, eliminando ese porcentaje de trabajo de transcripción.
- **SC-013**: Las interrupciones para preguntar "¿en qué va lo que pedí?" se reducen porque el solicitante obtiene esa respuesta por sí mismo en menos de 30 segundos desde su portal.
- **SC-014**: Ningún solicitante puede ver requerimientos de otra persona, ni el detalle de errores, ni las métricas internas, verificado entrando con cuentas distintas.

## Assumptions

- **Volumen**: el sistema se dimensiona para un solo desarrollador atendiendo a la veintena larga de usuarios que ya existen en el sistema, con un orden de magnitud de decenas de tickets activos y unos cientos al año; no se requieren capacidades de gestión de portafolio ni de equipos grandes.
- **Umbral de aviso**: "próximo a vencer" se fija en 2 días o menos respecto a la fecha comprometida, siguiendo la propuesta inicial. Es un valor configurable si el uso demuestra que conviene otro.
- **Alertas**: los indicadores de plazo son visuales dentro de la aplicación. No se contemplan notificaciones por correo, WhatsApp ni recordatorios automáticos en esta versión.
- **Estimaciones**: se registra la fecha comprometida acordada, no estimaciones de esfuerzo en horas ni puntos de historia.
- **Integraciones**: no se contempla integración con repositorios de código, sistemas de tickets externos ni despliegues automáticos. Las fechas de pruebas y producción se registran manualmente.
- **Solicitantes**: son los usuarios que ya existen en el sistema de acceso de INVENTARIO. No se crean cuentas ni credenciales nuevas: quien ya entra al sistema puede radicar. Para los requerimientos que el desarrollador registra directamente (los que le llegan por WhatsApp o llamada), el solicitante puede escribirse como texto libre, incluso si esa persona no tiene cuenta.
- **Quién es el desarrollador**: el espacio de trabajo lo usa una sola persona (el desarrollador). No se contempla repartir tickets entre varios desarrolladores ni asignar responsables en esta versión.
- **Aviso de solicitudes nuevas**: el desarrollador se entera de lo radicado al entrar a su espacio de trabajo, donde ve el contador de la bandeja. No se contemplan avisos por correo ni por WhatsApp en esta versión.
- **Aviso al solicitante**: el solicitante se entera de los cambios de etapa y de las devoluciones al entrar a su portal. No se le notifica por otros medios en esta versión.
- **Retención**: los tickets se conservan indefinidamente; los cerrados salen de la vista activa pero siguen consultables y cuentan en las métricas históricas.
- **Idioma y formato de fechas**: interfaz en español con fechas en formato local colombiano.
- **Respaldo**: la exportación de datos sirve tanto para análisis externo como para respaldo manual; no se contempla respaldo automático programado en esta versión.
- **Adjuntos**: no se contempla adjuntar archivos ni capturas de pantalla a tickets o errores en esta versión; las descripciones son de texto.
