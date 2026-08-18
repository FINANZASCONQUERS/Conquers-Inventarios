/* DevTracker — espacio de trabajo del desarrollador.
   Tablero Kanban con arrastre, lista filtrable, bandeja de triage, bugs y
   checklist. Todo contra /api/dev-tracker/*. */
(function () {
    'use strict';

    var estado = {
        vista: 'tablero',
        tickets: [],
        bandeja: { pendientes: [], esperando: [], fallas: [] },
        ticketAbierto: null
    };

    var modalTicket = new bootstrap.Modal(document.getElementById('modalTicket'));
    var modalNuevo = new bootstrap.Modal(document.getElementById('modalNuevo'));
    var modalTriage = new bootstrap.Modal(document.getElementById('modalTriage'));

    // --- utilidades --------------------------------------------------------
    function esc(t) {
        var d = document.createElement('div');
        d.textContent = t == null ? '' : String(t);
        return d.innerHTML;
    }

    function fecha(iso) {
        if (!iso) return '—';
        var d = new Date(iso);
        if (isNaN(d)) return '—';
        return d.toLocaleDateString('es-CO', { day: '2-digit', month: 'short', year: 'numeric' });
    }

    function soloFecha(iso) {
        return iso ? String(iso).slice(0, 10) : '';
    }

    function api(url, opciones) {
        opciones = opciones || {};
        opciones.headers = Object.assign(
            { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
            opciones.headers || {}
        );
        return fetch(url, opciones).then(function (r) {
            return r.json().then(function (d) { return { ok: r.ok, status: r.status, d: d }; });
        });
    }

    function chipPlazo(t) {
        var mapa = {
            retrasado: ['dt-chip-retrasado', 'bi-exclamation-triangle-fill',
                (t.dias_retraso || 0) + 'd de retraso'],
            por_vencer: ['dt-chip-por_vencer', 'bi-clock-fill',
                t.dias_restantes === 0 ? 'Vence hoy' : 'Faltan ' + t.dias_restantes + 'd'],
            a_tiempo: ['dt-chip-a_tiempo', 'bi-check-circle-fill', t.dias_restantes + 'd'],
            sin_fecha: ['dt-chip-sin_fecha', 'bi-dash-circle', 'Sin fecha'],
            entregado_a_tiempo: ['dt-chip-entregado_a_tiempo', 'bi-trophy-fill', 'A tiempo'],
            entregado_tarde: ['dt-chip-entregado_tarde', 'bi-hourglass-bottom', 'Fuera de plazo'],
            no_aplica: ['dt-chip-sin_fecha', 'bi-dash', '—']
        };
        var m = mapa[t.estado_plazo] || mapa.sin_fecha;
        return '<span class="dt-chip ' + m[0] + '"><i class="bi ' + m[1] + '"></i>' + m[2] + '</span>';
    }

    function chipPrioridad(p) {
        if (!p) return '';
        return '<span class="dt-chip dt-chip-' + p.toLowerCase() + '">' + esc(p) + '</span>';
    }

    // --- tablero -----------------------------------------------------------
    function tarjeta(t) {
        var bugs = t.bugs_abiertos > 0
            ? '<span class="dt-chip dt-chip-bug"><i class="bi bi-bug-fill"></i>' + t.bugs_abiertos + '</span>'
            : '';
        var sinClasificar = t.fallas_sin_clasificar > 0
            ? '<span class="dt-chip dt-chip-bug" title="Fallas reportadas sin clasificar">' +
            '<i class="bi bi-flag-fill"></i>' + t.fallas_sin_clasificar + ' por clasificar</span>'
            : '';
        var ajuste = t.relacionado_con_code
            ? '<span class="dt-chip dt-chip-portal" title="Ajuste sobre otro ticket">' +
            '<i class="bi bi-link-45deg"></i>' + esc(t.relacionado_con_code) + '</span>'
            : '';
        var portal = t.origen === 'portal'
            ? '<span class="dt-chip dt-chip-portal"><i class="bi bi-inbox"></i>Portal</span>'
            : '';
        var checklist = t.checklist_total > 0
            ? '<span title="Puntos de revisión"><i class="bi bi-list-check me-1"></i>' +
            t.checklist_verificados + '/' + t.checklist_total + '</span>'
            : '';
        var estancado = (t.dias_en_estado_actual != null && t.dias_en_estado_actual >= 5)
            ? '<span title="Días en esta etapa"><i class="bi bi-hourglass-split me-1"></i>' +
            t.dias_en_estado_actual + 'd</span>'
            : '';

        return '<article class="dt-card" draggable="true" data-id="' + t.id +
            '" data-plazo="' + esc(t.estado_plazo) + '">' +
            '<div class="dt-card-top"><span class="dt-code">' + esc(t.code) + '</span>' +
            chipPrioridad(t.prioridad) + '</div>' +
            '<div class="dt-card-titulo">' + esc(t.titulo) + '</div>' +
            '<div class="dt-card-pie">' + chipPlazo(t) + bugs + sinClasificar + ajuste +
            portal + checklist + estancado + '</div>' +
            '</article>';
    }

    function pintarTablero() {
        document.querySelectorAll('.dt-columna-body').forEach(function (col) {
            var e = col.getAttribute('data-drop');
            var propios = estado.tickets.filter(function (t) { return t.estado === e; });
            col.innerHTML = propios.length
                ? propios.map(tarjeta).join('')
                : '<p class="text-muted small text-center py-3 mb-0">Nada aquí</p>';
            var contador = document.querySelector('[data-contador="' + e + '"]');
            if (contador) contador.textContent = propios.length;
        });
        activarArrastre();
    }

    function pintarLista() {
        var cuerpo = document.getElementById('cuerpoLista');
        if (!estado.tickets.length) {
            cuerpo.innerHTML = '<tr><td colspan="8" class="text-center text-muted py-4">' +
                'No hay tickets con estos filtros.</td></tr>';
            return;
        }
        cuerpo.innerHTML = estado.tickets.map(function (t) {
            return '<tr data-id="' + t.id + '">' +
                '<td><span class="dt-code">' + esc(t.code) + '</span></td>' +
                '<td>' + esc(t.titulo) + '</td>' +
                '<td class="d-none d-lg-table-cell small text-muted">' +
                esc(t.solicitante_nombre || '—') + '</td>' +
                '<td>' + chipPrioridad(t.prioridad) + '</td>' +
                '<td><span class="small">' + esc(t.estado_label) + '</span></td>' +
                '<td class="small">' + fecha(t.fecha_comprometida) + '</td>' +
                '<td>' + chipPlazo(t) + '</td>' +
                '<td class="text-center">' + (t.bugs_abiertos || '—') + '</td>' +
                '</tr>';
        }).join('');
    }

    // --- arrastre ----------------------------------------------------------
    function activarArrastre() {
        document.querySelectorAll('.dt-card').forEach(function (card) {
            card.addEventListener('dragstart', function (ev) {
                ev.dataTransfer.setData('text/plain', card.getAttribute('data-id'));
                card.classList.add('dt-arrastrando');
            });
            card.addEventListener('dragend', function () {
                card.classList.remove('dt-arrastrando');
            });
        });

        document.querySelectorAll('.dt-columna-body').forEach(function (col) {
            col.addEventListener('dragover', function (ev) {
                ev.preventDefault();
                col.classList.add('dt-drop-activo');
            });
            col.addEventListener('dragleave', function () {
                col.classList.remove('dt-drop-activo');
            });
            col.addEventListener('drop', function (ev) {
                ev.preventDefault();
                col.classList.remove('dt-drop-activo');
                var id = ev.dataTransfer.getData('text/plain');
                var destino = col.getAttribute('data-drop');
                if (id && destino) cambiarEstado(id, destino, false);
            });
        });
    }

    function cambiarEstado(id, nuevoEstado, confirmado) {
        api('/api/dev-tracker/tickets/' + id, {
            method: 'PUT',
            body: JSON.stringify({ estado: nuevoEstado, confirmar: !!confirmado })
        }).then(function (res) {
            // 409 con advertencias = falta confirmación explícita (FR-021, FR-025, FR-011)
            if (res.status === 409 && res.d && res.d.requiere_confirmacion) {
                Swal.fire({
                    icon: 'warning',
                    title: 'Revisa antes de continuar',
                    html: '<ul class="text-start small mb-0">' +
                        res.d.advertencias.map(function (a) { return '<li>' + esc(a) + '</li>'; }).join('') +
                        '</ul>',
                    showCancelButton: true,
                    confirmButtonText: 'Continuar de todas formas',
                    cancelButtonText: 'Cancelar',
                    confirmButtonColor: '#dc3545'
                }).then(function (r) {
                    if (r.isConfirmed) cambiarEstado(id, nuevoEstado, true);
                    else recargar();
                });
                return;
            }
            if (!res.ok) {
                Swal.fire('No se pudo mover', (res.d && res.d.message) || '', 'error');
                recargar();
                return;
            }
            recargar();
            if (estado.ticketAbierto === Number(id)) abrirTicket(id);
        });
    }

    // --- bandeja -----------------------------------------------------------
    function tarjetaSolicitud(s, esperando) {
        var propuesto = '<div class="dt-propuesto mt-2">' +
            '<strong>Pidió:</strong> urgencia ' + esc(s.urgencia_propuesta || 'sin definir') +
            ' · para ' + fecha(s.fecha_deseada) + '</div>';
        var acciones = esperando
            ? '<span class="badge bg-warning text-dark">Esperando respuesta del solicitante</span>'
            : '<button class="btn btn-sm btn-primary" data-triage="' + s.id + '">' +
            '<i class="bi bi-clipboard-check me-1"></i>Revisar</button>';

        return '<div class="dt-solicitud">' +
            '<div class="d-flex justify-content-between align-items-start gap-2">' +
            '<div><span class="dt-code">' + esc(s.code) + '</span>' +
            '<h6 class="fw-semibold mb-1 mt-1">' + esc(s.titulo) + '</h6></div>' + acciones + '</div>' +
            '<div class="dt-solicitud-meta">' +
            '<span><i class="bi bi-person me-1"></i>' + esc(s.solicitante_nombre || '—') + '</span>' +
            '<span><i class="bi bi-building me-1"></i>' + esc(s.solicitante_area || '—') + '</span>' +
            '<span><i class="bi bi-calendar3 me-1"></i>' + fecha(s.fecha_radicacion) + '</span>' +
            '</div>' +
            '<p class="small mb-0">' + esc(s.descripcion || 'Sin descripción.') + '</p>' +
            propuesto + '</div>';
    }

    function tarjetaFalla(b) {
        // La severidad la pone el desarrollador, no quien reportó: es la que
        // gobierna el freno de despliegue.
        var opciones = (window.DT_CONFIG.severidades || []).map(function (s) {
            return '<button class="btn btn-sm btn-outline-' +
                (s[0] === 'Critico' ? 'danger' : s[0] === 'Mayor' ? 'warning' : 'secondary') +
                '" data-clasificar="' + b.id + '" data-severidad="' + s[0] + '">' + s[1] + '</button>';
        }).join(' ');

        return '<div class="dt-solicitud" style="border-left-color:#dc3545">' +
            '<div class="d-flex justify-content-between align-items-start gap-2 flex-wrap">' +
            '<div><span class="dt-code">' + esc(b.ticket_code) + '</span>' +
            '<h6 class="fw-semibold mb-1 mt-1">' + esc(b.ticket_titulo) + '</h6></div>' +
            '<span class="badge bg-danger">Sin clasificar</span></div>' +
            '<div class="dt-solicitud-meta">' +
            '<span><i class="bi bi-person me-1"></i>' + esc(b.reportado_por || '—') + '</span>' +
            '<span><i class="bi bi-calendar3 me-1"></i>' + fecha(b.fecha_deteccion) + '</span>' +
            '<span><i class="bi bi-signpost-split me-1"></i>Detectada en ' +
            esc(b.etapa_deteccion) + '</span></div>' +
            '<p class="small mb-2">' + esc(b.descripcion) + '</p>' +
            '<div class="d-flex gap-2 flex-wrap align-items-center">' +
            '<span class="small text-muted me-1">Clasificar como:</span>' + opciones +
            '<button class="btn btn-sm btn-link" data-abrir-ticket="' + b.ticket_id + '">' +
            'Abrir ticket</button></div></div>';
    }

    function pintarBandeja() {
        var lista = document.getElementById('listaBandeja');
        var esperandoDiv = document.getElementById('listaEsperando');
        var titulo = document.getElementById('tituloEsperando');
        var fallasDiv = document.getElementById('listaFallas');
        var tituloFallas = document.getElementById('tituloFallas');

        if (estado.bandeja.fallas.length) {
            tituloFallas.classList.remove('d-none');
            fallasDiv.innerHTML = estado.bandeja.fallas.map(tarjetaFalla).join('');
        } else {
            tituloFallas.classList.add('d-none');
            fallasDiv.innerHTML = '';
        }

        lista.innerHTML = estado.bandeja.pendientes.length
            ? estado.bandeja.pendientes.map(function (s) { return tarjetaSolicitud(s, false); }).join('')
            : '<div class="text-center text-muted py-5">' +
            '<i class="bi bi-check2-circle display-5 opacity-50"></i>' +
            '<p class="mt-3 mb-0">Bandeja al día. No hay solicitudes por revisar.</p></div>';

        if (estado.bandeja.esperando.length) {
            titulo.classList.remove('d-none');
            esperandoDiv.innerHTML = estado.bandeja.esperando
                .map(function (s) { return tarjetaSolicitud(s, true); }).join('');
        } else {
            titulo.classList.add('d-none');
            esperandoDiv.innerHTML = '';
        }
    }

    function abrirTriage(id) {
        var s = estado.bandeja.pendientes.filter(function (x) { return String(x.id) === String(id); })[0];
        if (!s) return;
        document.getElementById('triageTitulo').textContent = s.code + ' — ' + s.titulo;
        document.getElementById('triageCuerpo').innerHTML =
            '<p class="small text-muted mb-1">' + esc(s.solicitante_nombre || '') +
            (s.solicitante_area ? ' · ' + esc(s.solicitante_area) : '') + '</p>' +
            (s.relacionado_con_code
                ? '<div class="alert alert-info py-2 px-2 small"><i class="bi bi-link-45deg me-1"></i>' +
                'Ajuste pedido sobre <strong>' + esc(s.relacionado_con_code) + '</strong>. ' +
                'Lleva su propia fecha; la entrega de aquel queda como está.</div>'
                : '') +
            '<p>' + esc(s.descripcion || 'Sin descripción.') + '</p>' +
            '<div class="dt-propuesto mb-3"><strong>Propuesto por quien pidió:</strong> urgencia ' +
            esc(s.urgencia_propuesta || 'sin definir') + ' · para ' + fecha(s.fecha_deseada) +
            '<div class="text-muted mt-1" style="font-size:.75rem">' +
            'Informativo. La prioridad real y la fecha las defines tú.</div></div>' +
            '<hr>' +
            '<div class="row g-3 mb-3">' +
            '<div class="col-md-6"><label class="form-label fw-semibold small">Prioridad real *</label>' +
            '<select class="form-select" id="triagePrioridad">' +
            '<option value="">Elegir...</option>' +
            (window.DT_CONFIG.prioridades || []).map(function (p) {
                return '<option value="' + p + '">' + p + '</option>';
            }).join('') + '</select></div>' +
            '<div class="col-md-6"><label class="form-label fw-semibold small">Me comprometo a</label>' +
            '<input type="date" class="form-control" id="triageFecha" value="' +
            soloFecha(s.fecha_deseada) + '"></div>' +
            '</div>' +
            '<div class="mb-3"><label class="form-label fw-semibold small">' +
            'Comentario (obligatorio si devuelves o rechazas)</label>' +
            '<textarea class="form-control" id="triageComentario" rows="3" ' +
            'placeholder="Qué falta, o por qué no procede."></textarea></div>' +
            '<div class="d-flex gap-2 flex-wrap justify-content-end">' +
            '<button class="btn btn-outline-danger" data-accion="rechazar" data-id="' + s.id + '">' +
            '<i class="bi bi-x-circle me-1"></i>Rechazar</button>' +
            '<button class="btn btn-outline-warning" data-accion="devolver" data-id="' + s.id + '">' +
            '<i class="bi bi-arrow-counterclockwise me-1"></i>Devolver</button>' +
            '<button class="btn btn-success" data-accion="aceptar" data-id="' + s.id + '">' +
            '<i class="bi bi-check-lg me-1"></i>Aceptar y programar</button>' +
            '</div>';
        modalTriage.show();
    }

    document.getElementById('triageCuerpo').addEventListener('click', function (ev) {
        var btn = ev.target.closest('[data-accion]');
        if (!btn) return;
        var accion = btn.getAttribute('data-accion');
        var id = btn.getAttribute('data-id');
        var cuerpo = {
            accion: accion,
            comentario: document.getElementById('triageComentario').value.trim(),
            prioridad: document.getElementById('triagePrioridad').value,
            fecha_comprometida: document.getElementById('triageFecha').value || null
        };
        api('/api/dev-tracker/inbox/' + id + '/resolve', {
            method: 'POST', body: JSON.stringify(cuerpo)
        }).then(function (res) {
            if (!res.ok) {
                Swal.fire('Falta algo', (res.d && res.d.message) || '', 'warning');
                return;
            }
            modalTriage.hide();
            recargar();
            var textos = {
                aceptar: 'Aceptada. Ya está en el tablero.',
                devolver: 'Devuelta al solicitante.',
                rechazar: 'Rechazada.'
            };
            Swal.fire({
                icon: 'success', title: textos[accion], timer: 1800, showConfirmButton: false
            });
        });
    });

    // --- detalle de ticket -------------------------------------------------
    function abrirTicket(id) {
        api('/api/dev-tracker/tickets/' + id).then(function (res) {
            if (!res.ok) return;
            var t = res.d.ticket;
            estado.ticketAbierto = t.id;
            document.getElementById('ticketTitulo').innerHTML =
                '<span class="dt-code me-2">' + esc(t.code) + '</span>' + esc(t.titulo);
            document.getElementById('ticketCuerpo').innerHTML = detalleHTML(t);
            modalTicket.show();
        });
    }

    function detalleHTML(t) {
        var estados = (window.DT_CONFIG.estados || []).map(function (par) {
            return '<option value="' + par[0] + '"' + (t.estado === par[0] ? ' selected' : '') +
                '>' + par[1] + '</option>';
        }).join('');

        var bugs = t.bugs.length ? t.bugs.map(function (b) {
            return '<div class="dt-bug' + (b.estado === 'Corregido' ? ' dt-bug-corregido' : '') + '">' +
                '<div><span class="dt-chip dt-chip-' +
                (b.severidad === 'Critico' ? 'alta' : b.severidad === 'Mayor' ? 'media' : 'baja') + '">' +
                esc(b.severidad_label) + '</span> ' +
                '<span class="text-muted small ms-1">' + esc(b.etapa_deteccion) + ' · ' +
                fecha(b.fecha_deteccion) + '</span>' +
                '<div class="dt-bug-texto mt-1 small">' + esc(b.descripcion) + '</div></div>' +
                (b.estado === 'Abierto'
                    ? '<button class="btn btn-sm btn-outline-success" data-corregir="' + b.id +
                    '" title="Marcar corregido"><i class="bi bi-check-lg"></i></button>'
                    : '<button class="btn btn-sm btn-outline-secondary" data-reabrir="' + b.id +
                    '" title="Reabrir"><i class="bi bi-arrow-counterclockwise"></i></button>') +
                '</div>';
        }).join('') : '<p class="text-muted small mb-0">Sin errores registrados.</p>';

        var checklist = t.checklist.length ? t.checklist.map(function (c) {
            return '<div class="form-check d-flex align-items-center gap-2">' +
                '<input class="form-check-input mt-0" type="checkbox" id="chk' + c.id + '"' +
                (c.verificado ? ' checked' : '') + ' data-check="' + c.id + '">' +
                '<label class="form-check-label small flex-grow-1" for="chk' + c.id + '">' +
                esc(c.texto) + '</label>' +
                '<button class="btn btn-sm btn-link text-danger p-0" data-quitar="' + c.id +
                '" title="Quitar"><i class="bi bi-x-lg"></i></button></div>';
        }).join('') : '<p class="text-muted small">Sin puntos de revisión.</p>';

        var linea = t.transiciones.map(function (x) {
            return '<li><strong>' + esc(x.estado_destino) + '</strong>' +
                (x.estado_origen ? ' <span class="text-muted">desde ' + esc(x.estado_origen) + '</span>' : '') +
                '<div class="text-muted" style="font-size:.75rem">' + fecha(x.fecha) + '</div></li>';
        }).join('');

        var movida = t.fecha_comprometida_movida
            ? '<div class="alert alert-warning py-1 px-2 small mt-2 mb-0">' +
            'Fecha movida. La original era ' + fecha(t.fecha_comprometida_original) + '.</div>'
            : '';

        return '<div class="row g-3">' +
            '<div class="col-lg-7">' +
            '<div class="dt-seccion"><div class="dt-seccion-titulo">Requerimiento</div>' +
            '<p class="small">' + esc(t.descripcion || 'Sin descripción.') + '</p>' +
            '<div class="row g-2 small text-muted">' +
            '<div class="col-6"><i class="bi bi-person me-1"></i>' +
            esc(t.solicitante_nombre || '—') + '</div>' +
            '<div class="col-6"><i class="bi bi-signpost me-1"></i>' +
            (t.origen === 'portal' ? 'Radicado en el portal' : 'Registro directo') + '</div>' +
            (t.relacionado_con_code
                ? '<div class="col-12"><i class="bi bi-link-45deg me-1"></i>Ajuste sobre <strong>' +
                esc(t.relacionado_con_code) + '</strong> — la entrega de aquel no se ve afectada</div>'
                : '') +
            (t.origen === 'portal'
                ? '<div class="col-12"><i class="bi bi-hand-index me-1"></i>Pidió urgencia ' +
                esc(t.urgencia_propuesta || 'sin definir') + ' para ' + fecha(t.fecha_deseada) + '</div>'
                : '') +
            '</div></div>' +

            '<div class="dt-seccion"><div class="dt-seccion-titulo">Errores encontrados</div>' +
            bugs +
            '<div class="input-group input-group-sm mt-3">' +
            '<input type="text" class="form-control" id="nuevoBug" placeholder="Describe el error...">' +
            '<select class="form-select" id="nuevoBugSev" style="max-width:110px">' +
            (window.DT_CONFIG.severidades || []).map(function (s) {
                return '<option value="' + s[0] + '">' + s[1] + '</option>';
            }).join('') + '</select>' +
            '<button class="btn btn-outline-danger" id="btnAgregarBug">' +
            '<i class="bi bi-plus-lg"></i></button></div></div>' +

            '<div class="dt-seccion"><div class="dt-seccion-titulo">' +
            'Antes de desplegar (' + t.checklist_verificados + '/' + t.checklist_total + ')</div>' +
            checklist +
            '<div class="input-group input-group-sm mt-3">' +
            '<input type="text" class="form-control" id="nuevoCheck" placeholder="Agregar punto...">' +
            '<button class="btn btn-outline-primary" id="btnAgregarCheck">' +
            '<i class="bi bi-plus-lg"></i></button></div></div>' +
            '</div>' +

            '<div class="col-lg-5">' +
            '<div class="dt-seccion"><div class="dt-seccion-titulo">Control</div>' +
            '<label class="form-label small fw-semibold">Estado</label>' +
            '<select class="form-select form-select-sm mb-3" id="edEstado">' + estados +
            '<option value="Cancelado"' + (t.estado === 'Cancelado' ? ' selected' : '') +
            '>Cancelado</option></select>' +
            '<label class="form-label small fw-semibold">Prioridad</label>' +
            '<select class="form-select form-select-sm mb-3" id="edPrioridad">' +
            (window.DT_CONFIG.prioridades || []).map(function (p) {
                return '<option value="' + p + '"' + (t.prioridad === p ? ' selected' : '') +
                    '>' + p + '</option>';
            }).join('') + '</select>' +
            '<label class="form-label small fw-semibold">Fecha comprometida</label>' +
            '<input type="date" class="form-control form-control-sm" id="edFecha" value="' +
            soloFecha(t.fecha_comprometida) + '">' + movida +
            '<button class="btn btn-primary btn-sm w-100 mt-3" id="btnGuardar">' +
            '<i class="bi bi-save me-1"></i>Guardar cambios</button>' +
            '</div>' +

            '<div class="dt-seccion"><div class="dt-seccion-titulo">Fechas reales</div>' +
            '<div class="mb-2"><label class="form-label small mb-1">Inicio de desarrollo</label>' +
            '<input type="date" class="form-control form-control-sm" id="edInicio" value="' +
            soloFecha(t.fecha_inicio_desarrollo) + '"></div>' +
            '<div class="mb-2"><label class="form-label small mb-1">Entrada a pruebas</label>' +
            '<input type="date" class="form-control form-control-sm" id="edPruebas" value="' +
            soloFecha(t.fecha_entrada_pruebas) + '"></div>' +
            '<div class="mb-2"><label class="form-label small mb-1">Salida a producción</label>' +
            '<input type="date" class="form-control form-control-sm" id="edProduccion" value="' +
            soloFecha(t.fecha_salida_produccion) + '"></div>' +
            '<p class="small text-muted mb-0">' + chipPlazo(t) +
            (t.dias_en_estado_actual != null
                ? ' <span class="ms-1">' + t.dias_en_estado_actual + ' días en esta etapa</span>' : '') +
            '</p></div>' +

            '<div class="dt-seccion"><div class="dt-seccion-titulo">Historia</div>' +
            '<ul class="dt-linea-tiempo">' + linea + '</ul></div>' +
            '</div></div>';
    }

    document.getElementById('ticketCuerpo').addEventListener('click', function (ev) {
        var id = estado.ticketAbierto;
        var corregir = ev.target.closest('[data-corregir]');
        var reabrir = ev.target.closest('[data-reabrir]');
        var quitar = ev.target.closest('[data-quitar]');

        if (corregir) {
            api('/api/dev-tracker/bugs/' + corregir.getAttribute('data-corregir'), {
                method: 'PUT', body: JSON.stringify({ estado: 'Corregido' })
            }).then(function () { abrirTicket(id); recargar(); });
            return;
        }
        if (reabrir) {
            api('/api/dev-tracker/bugs/' + reabrir.getAttribute('data-reabrir'), {
                method: 'PUT', body: JSON.stringify({ estado: 'Abierto' })
            }).then(function () { abrirTicket(id); recargar(); });
            return;
        }
        if (quitar) {
            api('/api/dev-tracker/tickets/' + id + '/checklist/items/' +
                quitar.getAttribute('data-quitar'), { method: 'DELETE' })
                .then(function () { abrirTicket(id); recargar(); });
            return;
        }
        if (ev.target.id === 'btnAgregarBug') {
            var texto = document.getElementById('nuevoBug').value.trim();
            if (!texto) return;
            api('/api/dev-tracker/tickets/' + id + '/bugs', {
                method: 'POST',
                body: JSON.stringify({
                    descripcion: texto,
                    severidad: document.getElementById('nuevoBugSev').value
                })
            }).then(function () { abrirTicket(id); recargar(); });
            return;
        }
        if (ev.target.id === 'btnAgregarCheck') {
            var punto = document.getElementById('nuevoCheck').value.trim();
            if (!punto) return;
            api('/api/dev-tracker/tickets/' + id + '/checklist/items', {
                method: 'POST', body: JSON.stringify({ texto: punto })
            }).then(function () { abrirTicket(id); recargar(); });
            return;
        }
        if (ev.target.id === 'btnGuardar') {
            guardarTicket(id, false);
        }
    });

    document.getElementById('ticketCuerpo').addEventListener('change', function (ev) {
        var chk = ev.target.closest('[data-check]');
        if (!chk) return;
        api('/api/dev-tracker/tickets/' + estado.ticketAbierto + '/checklist/toggle', {
            method: 'PUT',
            body: JSON.stringify({ item_id: Number(chk.getAttribute('data-check')), verificado: chk.checked })
        }).then(function () { recargar(); });
    });

    function guardarTicket(id, confirmado) {
        var cuerpo = {
            estado: document.getElementById('edEstado').value,
            prioridad: document.getElementById('edPrioridad').value,
            fecha_comprometida: document.getElementById('edFecha').value || null,
            fecha_inicio_desarrollo: document.getElementById('edInicio').value || null,
            fecha_entrada_pruebas: document.getElementById('edPruebas').value || null,
            fecha_salida_produccion: document.getElementById('edProduccion').value || null,
            confirmar: !!confirmado
        };
        api('/api/dev-tracker/tickets/' + id, { method: 'PUT', body: JSON.stringify(cuerpo) })
            .then(function (res) {
                if (res.status === 409 && res.d && res.d.requiere_confirmacion) {
                    Swal.fire({
                        icon: 'warning',
                        title: 'Revisa antes de continuar',
                        html: '<ul class="text-start small mb-0">' +
                            res.d.advertencias.map(function (a) { return '<li>' + esc(a) + '</li>'; }).join('') +
                            '</ul>',
                        showCancelButton: true,
                        confirmButtonText: 'Guardar de todas formas',
                        cancelButtonText: 'Cancelar',
                        confirmButtonColor: '#dc3545'
                    }).then(function (r) { if (r.isConfirmed) guardarTicket(id, true); });
                    return;
                }
                if (!res.ok) {
                    Swal.fire('No se pudo guardar', (res.d && res.d.message) || '', 'error');
                    return;
                }
                modalTicket.hide();
                recargar();
                Swal.fire({ icon: 'success', title: 'Guardado', timer: 1200, showConfirmButton: false });
            });
    }

    // --- carga -------------------------------------------------------------
    function parametros() {
        var p = new URLSearchParams();
        var q = document.getElementById('fBusqueda').value.trim();
        if (q) p.set('q', q);
        var pr = document.getElementById('fPrioridad').value;
        if (pr) p.set('prioridad', pr);
        var pl = document.getElementById('fPlazo').value;
        if (pl) p.set('plazo', pl);
        var or = document.getElementById('fOrigen').value;
        if (or) p.set('origen', or);
        if (document.getElementById('fHistorico').checked) p.set('historico', 'true');
        return p.toString();
    }

    function recargar() {
        api('/api/dev-tracker/tickets?' + parametros()).then(function (res) {
            if (!res.ok) return;
            estado.tickets = res.d.tickets || [];
            if (estado.vista === 'tablero') pintarTablero(); else pintarLista();
        });

        api('/api/dev-tracker/inbox').then(function (res) {
            if (!res.ok) return;
            estado.bandeja.pendientes = res.d.pendientes || [];
            estado.bandeja.esperando = res.d.esperando_solicitante || [];
            estado.bandeja.fallas = res.d.fallas_por_clasificar || [];
            var badge = document.getElementById('badgeBandeja');
            // El contador suma solicitudes nuevas + fallas sin clasificar: las
            // dos cosas exigen una decisión tuya.
            if (res.d.total_por_atender > 0) {
                badge.textContent = res.d.total_por_atender;
                badge.classList.remove('d-none');
            } else {
                badge.classList.add('d-none');
            }
            if (estado.vista === 'bandeja') pintarBandeja();
        });

        api('/api/dev-tracker/metrics').then(function (res) {
            if (!res.ok) return;
            var m = res.d.metricas;
            document.getElementById('mTotalActivos').textContent = m.total_activos;
            document.getElementById('mEnPruebas').textContent = m.en_pruebas;
            document.getElementById('mRetrasados').textContent = m.retrasados;
            document.getElementById('mBugs').textContent = m.bugs_abiertos;
            document.getElementById('mCumplimiento').textContent =
                m.pct_cumplimiento == null ? '—' : m.pct_cumplimiento + '%';
        });
    }

    // --- eventos -----------------------------------------------------------
    document.querySelectorAll('[data-vista]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            document.querySelectorAll('[data-vista]').forEach(function (b) {
                b.classList.remove('active');
            });
            btn.classList.add('active');
            estado.vista = btn.getAttribute('data-vista');

            document.getElementById('vistaTablero').classList.toggle('d-none', estado.vista !== 'tablero');
            document.getElementById('vistaLista').classList.toggle('d-none', estado.vista !== 'lista');
            document.getElementById('vistaBandeja').classList.toggle('d-none', estado.vista !== 'bandeja');
            // Los filtros no aplican a la bandeja: ahí no hay nada que filtrar todavía.
            document.getElementById('barraFiltros').classList.toggle('d-none', estado.vista === 'bandeja');

            if (estado.vista === 'tablero') pintarTablero();
            else if (estado.vista === 'lista') pintarLista();
            else pintarBandeja();
        });
    });

    ['fBusqueda', 'fPrioridad', 'fPlazo', 'fOrigen', 'fHistorico'].forEach(function (id) {
        var el = document.getElementById(id);
        var evento = (id === 'fBusqueda') ? 'input' : 'change';
        var temporizador;
        el.addEventListener(evento, function () {
            clearTimeout(temporizador);
            temporizador = setTimeout(recargar, evento === 'input' ? 300 : 0);
        });
    });

    document.getElementById('vistaTablero').addEventListener('click', function (ev) {
        var card = ev.target.closest('.dt-card');
        if (card) abrirTicket(card.getAttribute('data-id'));
    });

    document.getElementById('cuerpoLista').addEventListener('click', function (ev) {
        var fila = ev.target.closest('tr[data-id]');
        if (fila) abrirTicket(fila.getAttribute('data-id'));
    });

    document.getElementById('vistaBandeja').addEventListener('click', function (ev) {
        var btn = ev.target.closest('[data-triage]');
        if (btn) {
            abrirTriage(btn.getAttribute('data-triage'));
            return;
        }
        var clasificar = ev.target.closest('[data-clasificar]');
        if (clasificar) {
            api('/api/dev-tracker/bugs/' + clasificar.getAttribute('data-clasificar'), {
                method: 'PUT',
                body: JSON.stringify({ severidad: clasificar.getAttribute('data-severidad') })
            }).then(function (res) {
                if (!res.ok) return;
                recargar();
                Swal.fire({
                    icon: 'success', title: 'Falla clasificada',
                    timer: 1200, showConfirmButton: false
                });
            });
            return;
        }
        var abrir = ev.target.closest('[data-abrir-ticket]');
        if (abrir) abrirTicket(abrir.getAttribute('data-abrir-ticket'));
    });

    document.querySelectorAll('[data-orden]').forEach(function (th) {
        th.addEventListener('click', function () {
            var orden = th.getAttribute('data-orden');
            api('/api/dev-tracker/tickets?' + parametros() + '&orden=' + orden).then(function (res) {
                if (!res.ok) return;
                estado.tickets = res.d.tickets || [];
                pintarLista();
            });
        });
    });

    document.getElementById('btnNuevoTicket').addEventListener('click', function () {
        modalNuevo.show();
    });

    document.getElementById('formNuevo').addEventListener('submit', function (ev) {
        ev.preventDefault();
        api('/api/dev-tracker/tickets', {
            method: 'POST',
            body: JSON.stringify({
                titulo: document.getElementById('nTitulo').value.trim(),
                descripcion: document.getElementById('nDescripcion').value.trim(),
                solicitante_nombre: document.getElementById('nSolicitante').value.trim(),
                prioridad: document.getElementById('nPrioridad').value,
                fecha_comprometida: document.getElementById('nFecha').value || null
            })
        }).then(function (res) {
            if (!res.ok) {
                Swal.fire('No se pudo crear', (res.d && res.d.message) || '', 'error');
                return;
            }
            modalNuevo.hide();
            document.getElementById('formNuevo').reset();
            recargar();
        });
    });

    document.getElementById('btnPlantilla').addEventListener('click', function () {
        api('/api/dev-tracker/plantilla').then(function (res) {
            if (!res.ok) return;
            var textos = (res.d.plantilla || []).map(function (i) { return i.texto; }).join('\n');
            Swal.fire({
                title: 'Puntos de revisión por defecto',
                input: 'textarea',
                inputValue: textos,
                inputAttributes: { rows: 10 },
                html: '<p class="small text-muted mb-0">Uno por línea. Los cambios solo aplican a ' +
                    'los tickets que se creen de aquí en adelante.</p>',
                showCancelButton: true,
                confirmButtonText: 'Guardar plantilla'
            }).then(function (r) {
                if (!r.isConfirmed) return;
                api('/api/dev-tracker/plantilla', {
                    method: 'POST',
                    body: JSON.stringify({ items: (r.value || '').split('\n') })
                }).then(function () {
                    Swal.fire({ icon: 'success', title: 'Plantilla guardada', timer: 1400, showConfirmButton: false });
                });
            });
        });
    });

    recargar();
})();
