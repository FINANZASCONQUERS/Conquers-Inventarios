/* DevTracker — portal del solicitante.
   Vista deliberadamente reducida: etapa y fechas. El backend no expone bugs,
   checklist ni métricas por este lado, así que aquí no hay nada que ocultar. */
(function () {
    'use strict';

    var PASOS = ['Solicitado', 'En Desarrollo', 'En Pruebas', 'En Produccion'];
    var contenedor = document.getElementById('misSolicitudes');
    var cargando = document.getElementById('cargandoSolicitudes');
    var vacio = document.getElementById('sinSolicitudes');
    var form = document.getElementById('formRadicar');
    var modalRadicar = new bootstrap.Modal(document.getElementById('modalRadicar'));
    var modalDetalle = new bootstrap.Modal(document.getElementById('modalDetalle'));
    var solicitudes = [];

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

    function colorEstado(estado) {
        switch (estado) {
            case 'Por revisar': return 'secondary';
            case 'Devuelta': return 'warning';
            case 'Rechazada': return 'danger';
            case 'Solicitado': return 'info';
            case 'En Desarrollo': return 'primary';
            case 'En Pruebas': return 'warning';
            case 'En Produccion': return 'success';
            case 'Cancelado': return 'secondary';
            default: return 'secondary';
        }
    }

    function barraProgreso(estado) {
        var idx = PASOS.indexOf(estado);
        if (idx < 0) return '';
        var pasos = PASOS.map(function (_, i) {
            var clase = i < idx ? 'dt-paso-hecho' : (i === idx ? 'dt-paso-actual' : '');
            return '<span class="dt-paso ' + clase + '"></span>';
        }).join('');
        return '<div class="dt-progreso">' + pasos + '</div>' +
            '<div class="dt-paso-labels"><span>Solicitado</span><span>Desarrollo</span>' +
            '<span>Pruebas</span><span>Producción</span></div>';
    }

    function tarjeta(s) {
        var color = colorEstado(s.estado);
        var aviso = '';
        if (s.estado === 'Devuelta') {
            aviso = '<div class="alert alert-warning py-2 px-2 small mt-2 mb-0">' +
                '<i class="bi bi-arrow-counterclockwise me-1"></i>' +
                '<strong>Falta información:</strong> ' + esc(s.comentario_dev || '') + '</div>';
        } else if (s.estado === 'Rechazada') {
            aviso = '<div class="alert alert-danger py-2 px-2 small mt-2 mb-0">' +
                '<strong>No procede:</strong> ' + esc(s.comentario_dev || '') + '</div>';
        }

        var compromiso = s.fecha_comprometida
            ? '<span class="text-success fw-semibold"><i class="bi bi-calendar-check me-1"></i>' +
            fecha(s.fecha_comprometida) + '</span>'
            : '<span class="text-muted"><i class="bi bi-hourglass me-1"></i>Sin fecha aún</span>';

        if (s.entregado) {
            compromiso = '<span class="text-success fw-semibold">' +
                '<i class="bi bi-check-circle-fill me-1"></i>Entregado el ' +
                fecha(s.fecha_salida_produccion) + '</span>';
        }

        var botones = '<button class="btn btn-sm btn-outline-secondary" data-ver="' + s.id + '">' +
            '<i class="bi bi-eye me-1"></i>Ver</button>';
        if (s.puede_re_radicar) {
            botones += ' <button class="btn btn-sm btn-warning" data-reenviar="' + s.id + '">' +
                '<i class="bi bi-send me-1"></i>Completar y reenviar</button>';
        }
        // Sobre lo que ya se puede ver funcionando: reportar falla o pedir ajuste.
        if (s.puede_reportar_falla) {
            botones += ' <button class="btn btn-sm btn-outline-danger" data-falla="' + s.id + '">' +
                '<i class="bi bi-exclamation-triangle me-1"></i>Me falla</button>';
        }
        if (s.puede_solicitar_ajuste) {
            botones += ' <button class="btn btn-sm btn-outline-primary" data-ajuste="' + s.id + '">' +
                '<i class="bi bi-plus-circle me-1"></i>Pedir ajuste</button>';
        }

        // Sus propios reportes, para que no reporte dos veces lo mismo.
        var reportes = '';
        if (s.mis_reportes && s.mis_reportes.length) {
            reportes = '<div class="alert alert-light border small mt-2 mb-0">' +
                '<strong><i class="bi bi-flag me-1"></i>Fallas que reportaste:</strong><ul class="mb-0 ps-3">' +
                s.mis_reportes.map(function (r) {
                    return '<li>' + esc(r.descripcion) +
                        (r.resuelto
                            ? ' <span class="badge bg-success">Corregida</span>'
                            : ' <span class="badge bg-secondary">En revisión</span>') + '</li>';
                }).join('') + '</ul></div>';
        }

        var vinculo = s.relacionado_con_code
            ? '<p class="text-muted small mb-0"><i class="bi bi-link-45deg me-1"></i>' +
            'Ajuste sobre ' + esc(s.relacionado_con_code) + '</p>'
            : '';

        return '<div class="col-12 col-lg-6"><div class="dt-solicitud-card">' +
            '<div class="d-flex justify-content-between align-items-start gap-2">' +
            '<span class="dt-code">' + esc(s.code) + '</span>' +
            '<span class="badge bg-' + color + '">' + esc(s.estado_label) + '</span>' +
            '</div>' +
            '<h6 class="fw-semibold mt-2 mb-1">' + esc(s.titulo) + '</h6>' +
            vinculo +
            '<p class="text-muted small mb-0">Radicada el ' + fecha(s.fecha_radicacion) + '</p>' +
            barraProgreso(s.estado) +
            '<div class="mt-2 small">' + compromiso + '</div>' +
            aviso + reportes +
            '<div class="mt-3 d-flex gap-2 flex-wrap">' + botones + '</div>' +
            '</div></div>';
    }

    function pintar() {
        cargando.classList.add('d-none');
        if (!solicitudes.length) {
            contenedor.innerHTML = '';
            vacio.classList.remove('d-none');
            return;
        }
        vacio.classList.add('d-none');
        contenedor.innerHTML = solicitudes.map(tarjeta).join('');
    }

    function cargar() {
        fetch('/api/solicitudes/mias', { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function (r) { return r.json(); })
            .then(function (d) {
                solicitudes = (d && d.solicitudes) || [];
                pintar();
            })
            .catch(function () {
                cargando.innerHTML =
                    '<p class="text-danger small mb-0">No se pudieron cargar tus solicitudes.</p>';
            });
    }

    function buscar(id) {
        return solicitudes.filter(function (s) { return String(s.id) === String(id); })[0];
    }

    contenedor.addEventListener('click', function (ev) {
        var verBtn = ev.target.closest('[data-ver]');
        var reBtn = ev.target.closest('[data-reenviar]');

        if (verBtn) {
            var s = buscar(verBtn.getAttribute('data-ver'));
            if (!s) return;
            document.getElementById('detalleTitulo').textContent = s.code + ' — ' + s.titulo;
            document.getElementById('detalleCuerpo').innerHTML =
                '<p>' + esc(s.descripcion || 'Sin descripción.') + '</p>' +
                '<hr><dl class="row small mb-0">' +
                '<dt class="col-5">Estado</dt><dd class="col-7">' + esc(s.estado_label) + '</dd>' +
                '<dt class="col-5">Radicada</dt><dd class="col-7">' + fecha(s.fecha_radicacion) + '</dd>' +
                '<dt class="col-5">Urgencia que pediste</dt><dd class="col-7">' +
                esc(s.urgencia_propuesta || '—') + '</dd>' +
                '<dt class="col-5">Fecha que pediste</dt><dd class="col-7">' + fecha(s.fecha_deseada) + '</dd>' +
                '<dt class="col-5">Fecha comprometida</dt><dd class="col-7">' +
                (s.fecha_comprometida ? fecha(s.fecha_comprometida) : 'Aún sin definir') + '</dd>' +
                '<dt class="col-5">Salida a producción</dt><dd class="col-7">' +
                fecha(s.fecha_salida_produccion) + '</dd>' +
                '</dl>' +
                (s.comentario_dev
                    ? '<div class="alert alert-warning small mt-3 mb-0">' + esc(s.comentario_dev) + '</div>'
                    : '');
            modalDetalle.show();
            return;
        }

        var fallaBtn = ev.target.closest('[data-falla]');
        var ajusteBtn = ev.target.closest('[data-ajuste]');

        if (fallaBtn || ajusteBtn) {
            abrirPosventa(
                (fallaBtn || ajusteBtn).getAttribute(fallaBtn ? 'data-falla' : 'data-ajuste'),
                fallaBtn ? 'falla' : 'ajuste'
            );
            return;
        }

        if (reBtn) {
            var t = buscar(reBtn.getAttribute('data-reenviar'));
            if (!t) return;
            document.getElementById('reRadicarId').value = t.id;
            document.getElementById('titulo').value = t.titulo || '';
            document.getElementById('descripcion').value = t.descripcion || '';
            document.getElementById('urgencia').value = t.urgencia_propuesta || '';
            document.getElementById('fechaDeseada').value = (t.fecha_deseada || '').slice(0, 10);
            document.getElementById('tituloModalRadicar').innerHTML =
                '<i class="bi bi-arrow-counterclockwise text-warning me-2"></i>Completar y reenviar';
            document.getElementById('btnEnviarSolicitud').innerHTML =
                '<i class="bi bi-send me-2"></i>Reenviar solicitud';
            var aviso = document.getElementById('avisoDevolucion');
            aviso.textContent = 'Te la devolvieron con este comentario: ' + (t.comentario_dev || '');
            aviso.classList.remove('d-none');
            modalRadicar.show();
        }
    });

    // --- reportar falla / pedir ajuste sobre lo ya entregado ---------------
    var modalPosventa = new bootstrap.Modal(document.getElementById('modalPosventa'));

    function abrirPosventa(id, tipo) {
        var s = buscar(id);
        if (!s) return;

        document.getElementById('posventaId').value = id;
        document.getElementById('posventaTipo').value = tipo;
        document.getElementById('formPosventa').reset();

        var ayuda = document.getElementById('posventaAyuda');
        var grupoTitulo = document.getElementById('grupoPosventaTitulo');
        var grupoUrgencia = document.getElementById('grupoPosventaUrgencia');

        if (tipo === 'falla') {
            document.getElementById('posventaTitulo').innerHTML =
                '<i class="bi bi-exclamation-triangle text-danger me-2"></i>Reportar una falla en ' + esc(s.code);
            ayuda.className = 'alert alert-danger border-0 small';
            ayuda.innerHTML = '<strong>Esto es para cuando algo <em>no funciona</em>.</strong> ' +
                'Queda registrado sobre este mismo desarrollo. ' +
                'Si lo que quieres es que funcione <em>de otra forma</em>, usa "Pedir ajuste".';
            document.getElementById('posventaLabelDesc').innerHTML =
                '¿Qué te está fallando? <span class="text-danger">*</span>';
            document.getElementById('posventaDescripcion').placeholder =
                'Qué hiciste, qué esperabas que pasara y qué pasó en su lugar. ' +
                'Si sale un mensaje de error, cópialo tal cual.';
            grupoTitulo.classList.add('d-none');
            grupoUrgencia.classList.add('d-none');
            document.getElementById('btnEnviarPosventa').className = 'btn btn-danger';
            document.getElementById('btnEnviarPosventa').innerHTML =
                '<i class="bi bi-send me-1"></i>Reportar falla';
        } else {
            document.getElementById('posventaTitulo').innerHTML =
                '<i class="bi bi-plus-circle text-primary me-2"></i>Pedir un ajuste sobre ' + esc(s.code);
            ayuda.className = 'alert alert-info border-0 small';
            ayuda.innerHTML = '<strong>Esto crea una solicitud nueva</strong> vinculada a ' +
                esc(s.code) + '. Se revisa y se le pone su propia fecha, sin afectar la entrega anterior.';
            document.getElementById('posventaLabelDesc').textContent = 'Explícalo con detalle';
            document.getElementById('posventaDescripcion').placeholder =
                '¿Qué te gustaría que hiciera distinto?, ¿por qué te sirve más así?';
            grupoTitulo.classList.remove('d-none');
            grupoUrgencia.classList.remove('d-none');
            document.getElementById('btnEnviarPosventa').className = 'btn btn-primary';
            document.getElementById('btnEnviarPosventa').innerHTML =
                '<i class="bi bi-send me-1"></i>Enviar solicitud';
        }
        modalPosventa.show();
    }

    document.getElementById('formPosventa').addEventListener('submit', function (ev) {
        ev.preventDefault();
        var id = document.getElementById('posventaId').value;
        var tipo = document.getElementById('posventaTipo').value;
        var descripcion = document.getElementById('posventaDescripcion').value.trim();
        var boton = document.getElementById('btnEnviarPosventa');

        var url, cuerpo;
        if (tipo === 'falla') {
            if (!descripcion) {
                Swal.fire('Falta el detalle', 'Cuéntanos qué te está fallando.', 'warning');
                return;
            }
            url = '/api/solicitudes/' + id + '/reportar-falla';
            cuerpo = { descripcion: descripcion };
        } else {
            var titulo = document.getElementById('posventaCampoTitulo').value.trim();
            if (!titulo) {
                Swal.fire('Falta el título', 'Escribe en una frase qué ajuste necesitas.', 'warning');
                return;
            }
            url = '/api/solicitudes/' + id + '/solicitar-ajuste';
            cuerpo = {
                titulo: titulo,
                descripcion: descripcion,
                urgencia_propuesta: document.getElementById('posventaUrgencia').value,
                fecha_deseada: document.getElementById('posventaFecha').value || null
            };
        }

        boton.disabled = true;
        fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
            body: JSON.stringify(cuerpo)
        })
            .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
            .then(function (res) {
                boton.disabled = false;
                if (!res.ok) {
                    Swal.fire('No se pudo enviar', (res.d && res.d.message) || 'Intenta de nuevo.', 'error');
                    return;
                }
                modalPosventa.hide();
                Swal.fire({
                    icon: 'success',
                    title: tipo === 'falla' ? 'Falla reportada' : 'Ajuste solicitado',
                    text: tipo === 'falla'
                        ? 'Queda registrada sobre este desarrollo para que la revisen.'
                        : 'Entra como solicitud nueva. Aquí verás su fecha cuando la definan.',
                    timer: 2800,
                    showConfirmButton: false
                });
                cargar();
            })
            .catch(function () {
                boton.disabled = false;
                Swal.fire('Error de conexión', 'No se pudo contactar el servidor.', 'error');
            });
    });

    document.getElementById('modalRadicar').addEventListener('hidden.bs.modal', function () {
        form.reset();
        document.getElementById('reRadicarId').value = '';
        document.getElementById('avisoDevolucion').classList.add('d-none');
        document.getElementById('tituloModalRadicar').innerHTML =
            '<i class="bi bi-lightbulb text-warning me-2"></i>Nueva solicitud de desarrollo';
        document.getElementById('btnEnviarSolicitud').innerHTML =
            '<i class="bi bi-send me-2"></i>Radicar solicitud';
    });

    form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var id = document.getElementById('reRadicarId').value;
        var cuerpo = {
            titulo: document.getElementById('titulo').value.trim(),
            descripcion: document.getElementById('descripcion').value.trim(),
            urgencia_propuesta: document.getElementById('urgencia').value,
            fecha_deseada: document.getElementById('fechaDeseada').value || null
        };
        if (!cuerpo.titulo) return;

        var url = id ? '/api/solicitudes/' + id + '/re-radicar' : '/api/solicitudes';
        var metodo = id ? 'PUT' : 'POST';
        var boton = document.getElementById('btnEnviarSolicitud');
        boton.disabled = true;

        fetch(url, {
            method: metodo,
            headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
            body: JSON.stringify(cuerpo)
        })
            .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
            .then(function (res) {
                boton.disabled = false;
                if (!res.ok) {
                    Swal.fire('No se pudo enviar', (res.d && res.d.message) || 'Intenta de nuevo.', 'error');
                    return;
                }
                modalRadicar.hide();
                Swal.fire({
                    icon: 'success',
                    title: id ? 'Solicitud reenviada' : 'Solicitud radicada',
                    text: 'Queda en revisión. Aquí verás la fecha comprometida cuando la definan.',
                    timer: 2600,
                    showConfirmButton: false
                });
                cargar();
            })
            .catch(function () {
                boton.disabled = false;
                Swal.fire('Error de conexión', 'No se pudo contactar el servidor.', 'error');
            });
    });

    // --- interruptor de correos -------------------------------------------
    var switchCorreos = document.getElementById('switchCorreos');
    if (switchCorreos) {
        fetch('/api/solicitudes/preferencias-correo', {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
            .then(function (r) { return r.json(); })
            .then(function (d) { switchCorreos.checked = !!(d && d.activo); })
            .catch(function () { });

        switchCorreos.addEventListener('change', function () {
            fetch('/api/solicitudes/preferencias-correo', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                body: JSON.stringify({ activo: switchCorreos.checked })
            }).then(function () {
                Swal.fire({
                    icon: 'success',
                    title: switchCorreos.checked ? 'Avisos activados' : 'Avisos desactivados',
                    text: switchCorreos.checked
                        ? 'Te llegará correo cuando acepten tu solicitud y cuando quede entregada.'
                        : 'No te llegarán más correos. Puedes seguir consultando el avance aquí.',
                    timer: 2600,
                    showConfirmButton: false
                });
            });
        });
    }

    cargar();
})();
