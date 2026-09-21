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

    function applyDetalleRuta(data) {
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

        const conFoto = root.querySelector("[data-live-con-foto]");
        const sinFoto = root.querySelector("[data-live-sin-foto]");
        const img = root.querySelector('[data-live="foto"]');
        if (data.foto_url) {
            if (conFoto) {
                conFoto.hidden = false;
            }
            if (sinFoto) {
                sinFoto.hidden = true;
            }
            if (img && img.getAttribute("src") !== data.foto_url) {
                img.src = data.foto_url;
                img.hidden = false;
                flash(img);
            }
        } else {
            if (conFoto) {
                conFoto.hidden = true;
            }
            if (sinFoto) {
                sinFoto.hidden = false;
            }
            if (img) {
                img.removeAttribute("src");
                img.hidden = true;
            }
        }
    }

    function renderRecolectorRow(ruta) {
        const tr = document.createElement("tr");
        tr.dataset.rutaId = String(ruta.id);

        const tdLocal = document.createElement("td");
        tdLocal.textContent = ruta.nombre_local;

        const tdFecha = document.createElement("td");
        tdFecha.textContent = ruta.fecha;

        const tdEstado = document.createElement("td");
        const estado = document.createElement("span");
        estado.dataset.live = "estado";
        setEstado(estado, ruta.estado, ruta.estado_display);
        tdEstado.appendChild(estado);

        const tdAcciones = document.createElement("td");
        tdAcciones.className = "acciones";
        tdAcciones.dataset.live = "acciones";
        fillRecolectorAcciones(tdAcciones, ruta);

        tr.append(tdLocal, tdFecha, tdEstado, tdAcciones);
        return tr;
    }

    function fillRecolectorAcciones(td, ruta) {
        td.replaceChildren();
        if (ruta.tiene_foto) {
            const span = document.createElement("span");
            span.className = "muted";
            span.textContent = "Foto cargada";
            td.appendChild(span);
            return;
        }
        if (ruta.puede_subir && ruta.subir_url) {
            const link = document.createElement("a");
            link.href = ruta.subir_url;
            link.textContent = "Subir foto";
            td.appendChild(link);
        }
    }

    function applyRecolector(data) {
        const tbody = root.querySelector("tbody");
        if (!tbody || !Array.isArray(data.rutas)) {
            return;
        }
        const ids = data.rutas.map((ruta) => String(ruta.id)).join(",");
        const existing = Array.from(tbody.querySelectorAll("tr[data-ruta-id]"))
            .map((tr) => tr.dataset.rutaId)
            .join(",");
        if (ids !== existing) {
            tbody.replaceChildren(...data.rutas.map(renderRecolectorRow));
            return;
        }
        data.rutas.forEach((ruta) => {
            const tr = tbody.querySelector('tr[data-ruta-id="' + ruta.id + '"]');
            if (!tr) {
                return;
            }
            setEstado(
                tr.querySelector('[data-live="estado"]'),
                ruta.estado,
                ruta.estado_display
            );
            const acciones = tr.querySelector('[data-live="acciones"]');
            if (acciones) {
                const hasFoto = Boolean(acciones.querySelector(".muted"));
                const hasLink = Boolean(acciones.querySelector("a"));
                const wantFoto = Boolean(ruta.tiene_foto);
                const wantLink = Boolean(ruta.puede_subir && ruta.subir_url);
                if (hasFoto !== wantFoto || hasLink !== wantLink) {
                    fillRecolectorAcciones(acciones, ruta);
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
        const tdEstado = document.createElement("td");
        const estado = document.createElement("span");
        estado.dataset.live = "estado";
        setEstado(estado, ruta.estado, ruta.estado_display);
        tdEstado.appendChild(estado);
        tr.append(tdNombre, tdFecha, tdRec, tdEstado);
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
            setEstado(
                tr.querySelector('[data-live="estado"]'),
                ruta.estado,
                ruta.estado_display
            );
        });
    }

    function renderPagoRow(pago, operador) {
        const tr = document.createElement("tr");
        tr.dataset.pagoId = String(pago.id);

        if (operador) {
            const tdQuien = document.createElement("td");
            tdQuien.textContent = pago.recolector;
            tr.appendChild(tdQuien);
        }

        const tdLocal = document.createElement("td");
        if (operador && pago.ruta_url) {
            const link = document.createElement("a");
            link.href = pago.ruta_url;
            link.textContent = pago.local;
            tdLocal.appendChild(link);
        } else {
            tdLocal.textContent = pago.local;
        }

        const tdFecha = document.createElement("td");
        tdFecha.textContent = dash(pago.fecha);

        const tdMonto = document.createElement("td");
        tdMonto.textContent = dash(pago.monto_display);

        const tdTx = document.createElement("td");
        tdTx.className = "acciones";
        if (pago.tx_url) {
            const link = document.createElement("a");
            link.href = pago.tx_url;
            link.target = "_blank";
            link.rel = "noopener noreferrer";
            link.textContent = "Ver transferencia";
            tdTx.appendChild(link);
        } else {
            const span = document.createElement("span");
            span.className = "muted";
            span.textContent = "—";
            tdTx.appendChild(span);
        }

        tr.append(tdLocal, tdFecha, tdMonto, tdTx);
        return tr;
    }

    function applyPagos(data, operador) {
        setText(root.querySelector('[data-live="saldo"]'), data.saldo_display || "—");
        const tbody = root.querySelector("tbody");
        const tabla = root.querySelector("[data-live-tabla]");
        const vacio = root.querySelector("[data-live-vacio]");
        if (!Array.isArray(data.pagos)) {
            return;
        }
        if (tabla) {
            tabla.hidden = data.pagos.length === 0;
        }
        if (vacio) {
            vacio.hidden = data.pagos.length !== 0;
        }
        if (!tbody) {
            return;
        }
        const ids = data.pagos.map(function (pago) {
            return String(pago.id);
        }).join(",");
        const existing = Array.from(tbody.querySelectorAll("tr[data-pago-id]"))
            .map(function (tr) {
                return tr.dataset.pagoId;
            })
            .join(",");
        if (ids !== existing) {
            tbody.replaceChildren(
                ...data.pagos.map(function (pago) {
                    return renderPagoRow(pago, operador);
                })
            );
        }
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
        if (kind === "detalle-ruta") {
            applyDetalleRuta(data);
        } else if (kind === "panel-recolector") {
            applyRecolector(data);
        } else if (kind === "panel-operador") {
            applyOperador(data);
        } else if (kind === "pagos-recolector") {
            applyPagos(data, false);
        } else if (kind === "pagos-operador") {
            applyPagos(data, true);
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
