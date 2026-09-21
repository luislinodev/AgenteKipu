(function () {
    const root = document.querySelector("[data-live-url]");
    if (!root) {
        return;
    }

    const url = root.dataset.liveUrl;
    const kind = root.dataset.liveKind;
    const intervalMs = Number(root.dataset.liveInterval || 3000);
    let lastPayload = "";
    let timer = null;

    function dash(value) {
        if (value === null || value === undefined || value === "") {
            return "—";
        }
        return String(value);
    }

    function flash(el) {
        if (!el) {
            return;
        }
        el.classList.remove("live-flash");
        void el.offsetWidth;
        el.classList.add("live-flash");
    }

    function setText(el, value) {
        const next = dash(value);
        if (!el || el.textContent === next) {
            return;
        }
        el.textContent = next;
        flash(el);
    }

    function setEstado(el, estado, display) {
        if (!el) {
            return;
        }
        const next = display || dash(estado);
        const className = "estado estado-" + estado;
        if (el.textContent === next && el.className === className) {
            return;
        }
        el.textContent = next;
        el.className = className;
        flash(el);
    }

    function setLinkCell(td, urlConfirmacion) {
        if (!td) {
            return;
        }
        const input = td.querySelector("input.link-copiar");
        if (urlConfirmacion) {
            if (input) {
                if (input.value !== urlConfirmacion) {
                    input.value = urlConfirmacion;
                    flash(td);
                }
                return;
            }
            td.replaceChildren();
            const field = document.createElement("input");
            field.className = "link-copiar";
            field.type = "text";
            field.readOnly = true;
            field.value = urlConfirmacion;
            field.addEventListener("click", function () {
                field.select();
            });
            td.appendChild(field);
            flash(td);
            return;
        }
        if (!input && td.querySelector(".muted")) {
            return;
        }
        td.replaceChildren();
        const span = document.createElement("span");
        span.className = "muted";
        span.textContent = "Todavía no hay foto; el link se genera al subirla.";
        td.appendChild(span);
        flash(td);
    }

    function renderRutaRow(punto) {
        const tr = document.createElement("tr");
        tr.dataset.puntoId = String(punto.id);

        const tdLocal = document.createElement("td");
        const link = document.createElement("a");
        link.href = punto.detalle_url;
        link.textContent = punto.nombre_local;
        tdLocal.appendChild(link);

        const tdEstado = document.createElement("td");
        const estado = document.createElement("span");
        estado.dataset.live = "estado";
        setEstado(estado, punto.estado, punto.estado_display);
        tdEstado.appendChild(estado);

        const tdReportado = document.createElement("td");
        tdReportado.dataset.live = "reportado";
        tdReportado.textContent = dash(punto.cantidad_baldes);

        const tdGemini = document.createElement("td");
        tdGemini.dataset.live = "gemini";
        tdGemini.textContent = dash(punto.gemini);

        const tdConf = document.createElement("td");
        tdConf.dataset.live = "confirmacion";
        tdConf.textContent = dash(punto.confirmacion_display);

        const tdMotivo = document.createElement("td");
        tdMotivo.dataset.live = "motivo";
        tdMotivo.textContent = punto.motivo_no_pago ? punto.motivo_no_pago : "—";

        const tdLink = document.createElement("td");
        tdLink.dataset.live = "link";
        setLinkCell(tdLink, punto.url_confirmacion);

        tr.append(tdLocal, tdEstado, tdReportado, tdGemini, tdConf, tdMotivo, tdLink);
        return tr;
    }

    function applyRuta(data) {
        const tbody = root.querySelector("tbody");
        if (!tbody || !Array.isArray(data.puntos)) {
            return;
        }
        const ids = data.puntos.map((punto) => String(punto.id)).join(",");
        const existing = Array.from(tbody.querySelectorAll("tr[data-punto-id]"))
            .map((tr) => tr.dataset.puntoId)
            .join(",");
        if (ids !== existing) {
            tbody.replaceChildren(...data.puntos.map(renderRutaRow));
            return;
        }
        data.puntos.forEach((punto) => {
            const tr = tbody.querySelector('tr[data-punto-id="' + punto.id + '"]');
            if (!tr) {
                return;
            }
            setEstado(
                tr.querySelector('[data-live="estado"]'),
                punto.estado,
                punto.estado_display
            );
            setText(tr.querySelector('[data-live="reportado"]'), punto.cantidad_baldes);
            setText(tr.querySelector('[data-live="gemini"]'), punto.gemini);
            setText(
                tr.querySelector('[data-live="confirmacion"]'),
                punto.confirmacion_display
            );
            setText(
                tr.querySelector('[data-live="motivo"]'),
                punto.motivo_no_pago || "—"
            );
            setLinkCell(tr.querySelector('[data-live="link"]'), punto.url_confirmacion);
        });
    }

    function applyPunto(data) {
        setEstado(
            root.querySelector('[data-live="estado"]'),
            data.estado,
            data.estado_display
        );
        setText(root.querySelector('[data-live="cantidad"]'), data.cantidad_baldes);
        setText(root.querySelector('[data-live="gemini"]'), data.gemini);
        setText(
            root.querySelector('[data-live="confirmacion"]'),
            data.confirmacion_display
        );

        const motivoWrap = root.querySelector("[data-live-motivo-wrap]");
        const motivo = root.querySelector('[data-live="motivo"]');
        if (motivoWrap && motivo) {
            if (data.motivo_no_pago) {
                motivoWrap.hidden = false;
                setText(motivo, data.motivo_no_pago);
            } else {
                motivoWrap.hidden = true;
                motivo.textContent = "";
            }
        }

        const conLink = root.querySelector("[data-live-con-link]");
        const sinLink = root.querySelector("[data-live-sin-link]");
        const input = root.querySelector("input.link-copiar");
        if (data.url_confirmacion) {
            if (conLink) {
                conLink.hidden = false;
            }
            if (sinLink) {
                sinLink.hidden = true;
            }
            if (input && input.value !== data.url_confirmacion) {
                input.value = data.url_confirmacion;
                flash(input);
            }
        } else {
            if (conLink) {
                conLink.hidden = true;
            }
            if (sinLink) {
                sinLink.hidden = false;
            }
        }
    }

    function renderRecolectorRow(punto) {
        const tr = document.createElement("tr");
        tr.dataset.puntoId = String(punto.id);

        const tdLocal = document.createElement("td");
        tdLocal.textContent = punto.nombre_local;

        const tdRuta = document.createElement("td");
        tdRuta.textContent = punto.ruta;

        const tdEstado = document.createElement("td");
        const estado = document.createElement("span");
        estado.dataset.live = "estado";
        setEstado(estado, punto.estado, punto.estado_display);
        tdEstado.appendChild(estado);

        const tdAcciones = document.createElement("td");
        tdAcciones.className = "acciones";
        tdAcciones.dataset.live = "acciones";
        fillRecolectorAcciones(tdAcciones, punto);

        tr.append(tdLocal, tdRuta, tdEstado, tdAcciones);
        return tr;
    }

    function fillRecolectorAcciones(td, punto) {
        td.replaceChildren();
        if (punto.tiene_foto) {
            const span = document.createElement("span");
            span.className = "muted";
            span.textContent = "Foto cargada";
            td.appendChild(span);
            return;
        }
        if (punto.puede_subir && punto.subir_url) {
            const link = document.createElement("a");
            link.href = punto.subir_url;
            link.textContent = "Subir foto";
            td.appendChild(link);
        }
    }

    function applyRecolector(data) {
        const tbody = root.querySelector("tbody");
        if (!tbody || !Array.isArray(data.puntos)) {
            return;
        }
        const ids = data.puntos.map((punto) => String(punto.id)).join(",");
        const existing = Array.from(tbody.querySelectorAll("tr[data-punto-id]"))
            .map((tr) => tr.dataset.puntoId)
            .join(",");
        if (ids !== existing) {
            tbody.replaceChildren(...data.puntos.map(renderRecolectorRow));
            return;
        }
        data.puntos.forEach((punto) => {
            const tr = tbody.querySelector('tr[data-punto-id="' + punto.id + '"]');
            if (!tr) {
                return;
            }
            setEstado(
                tr.querySelector('[data-live="estado"]'),
                punto.estado,
                punto.estado_display
            );
            if (acciones) {
                const hasFoto = Boolean(acciones.querySelector(".muted"));
                const hasLink = Boolean(acciones.querySelector("a"));
                const wantFoto = Boolean(punto.tiene_foto);
                const wantLink = Boolean(punto.puede_subir && punto.subir_url);
                if (hasFoto !== wantFoto || hasLink !== wantLink) {
                    fillRecolectorAcciones(acciones, punto);
                    flash(acciones);
                }
            }
        });
    }

    function renderOperadorRuta(ruta) {
        const tr = document.createElement("tr");
        tr.dataset.rutaId = String(ruta.id);
        const tdNombre = document.createElement("td");
        const link = document.createElement("a");
        link.href = ruta.url;
        link.textContent = ruta.nombre;
        tdNombre.appendChild(link);
        const tdFecha = document.createElement("td");
        tdFecha.dataset.live = "fecha";
        tdFecha.textContent = ruta.fecha;
        const tdRec = document.createElement("td");
        tdRec.dataset.live = "recolector";
        tdRec.textContent = ruta.recolector;
        const tdPuntos = document.createElement("td");
        tdPuntos.dataset.live = "puntos";
        tdPuntos.textContent = String(ruta.puntos);
        tr.append(tdNombre, tdFecha, tdRec, tdPuntos);
        return tr;
    }

    function applyOperador(data) {
        const tbody = root.querySelector("tbody");
        if (!tbody || !Array.isArray(data.rutas)) {
            return;
        }
        const ids = data.rutas.map((ruta) => String(ruta.id)).join(",");
        const existing = Array.from(tbody.querySelectorAll("tr[data-ruta-id]"))
            .map((tr) => tr.dataset.rutaId)
            .join(",");
        if (ids !== existing) {
            tbody.replaceChildren(...data.rutas.map(renderOperadorRuta));
            return;
        }
        data.rutas.forEach((ruta) => {
            const tr = tbody.querySelector('tr[data-ruta-id="' + ruta.id + '"]');
            if (!tr) {
                return;
            }
            setText(tr.querySelector('[data-live="fecha"]'), ruta.fecha);
            setText(tr.querySelector('[data-live="recolector"]'), ruta.recolector);
            setText(tr.querySelector('[data-live="puntos"]'), ruta.puntos);
        });
    }

    function applyConfirmar(data) {
        if (data.formulario_abierto) {
            return;
        }
        const form = root.querySelector("form");
        const pregunta = form ? form.previousElementSibling : null;
        if (form) {
            form.remove();
        }
        if (pregunta && pregunta.tagName === "P") {
            pregunta.remove();
        }
        const card = root.querySelector(".card");
        if (card && data.confirmacion_display && !card.querySelector("[data-live-respuesta]")) {
            const p = document.createElement("p");
            p.dataset.liveRespuesta = "1";
            const strong = document.createElement("strong");
            strong.textContent = "Tu respuesta:";
            p.append(strong, " " + data.confirmacion_display);
            card.appendChild(p);
        }
        const avisoExistente = root.querySelector("[data-live-cerrado]");
        if (avisoExistente) {
            stop();
            return;
        }
        const aviso = document.createElement("p");
        aviso.className = "muted";
        aviso.dataset.liveCerrado = "1";
        aviso.textContent = "Este punto ya fue respondido. El link ya no puede cambiar la decisión.";
        root.querySelector("main").appendChild(aviso);
        stop();
    }

    function apply(data) {
        if (kind === "ruta-operador") {
            applyRuta(data);
        } else if (kind === "punto-operador") {
            applyPunto(data);
        } else if (kind === "panel-recolector") {
            applyRecolector(data);
        } else if (kind === "panel-operador") {
            applyOperador(data);
        } else if (kind === "confirmar") {
            applyConfirmar(data);
        }
    }

    async function tick() {
        if (document.hidden) {
            return;
        }
        try {
            const response = await fetch(url, {
                headers: { Accept: "application/json" },
                credentials: "same-origin",
            });
            const tipo = response.headers.get("content-type") || "";
            if (!response.ok || !tipo.includes("application/json")) {
                return;
            }
            const data = await response.json();
            const payload = JSON.stringify(data);
            if (payload === lastPayload) {
                return;
            }
            lastPayload = payload;
            apply(data);
        } catch (_error) {
            // La pantalla sigue; el próximo intervalo reintenta.
        }
    }

    function stop() {
        if (timer) {
            clearInterval(timer);
            timer = null;
        }
    }

    timer = setInterval(tick, intervalMs);
    document.addEventListener("visibilitychange", function () {
        if (!document.hidden) {
            tick();
        }
    });
    tick();
})();
