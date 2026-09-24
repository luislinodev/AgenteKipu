from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from stellar_sdk import Keypair
from django.urls import reverse

from .admin import RutaAdmin
from .formato import fecha_hora
from .models import Operador, Payment, Punto, Recolector, Ruta

User = get_user_model()


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class CatalogoYRutaTests(TestCase):
    def setUp(self):
        self.op_user = User.objects.create_user("jose", password="x")
        self.rec_user = User.objects.create_user("luis", password="x")
        self.operador = Operador.objects.create(
            user=self.op_user,
            direccion_stellar="G" + "C" * 55,
        )
        self.recolector = Recolector.objects.create(
            user=self.rec_user,
            direccion_stellar="G" + "A" * 55,
        )
        self.punto = Punto.objects.create(
            operador=self.operador,
            nombre="Restaurante Alita",
        )
        self.ruta = Ruta.objects.create(
            operador=self.operador,
            recolector=self.recolector,
            punto=self.punto,
            fecha=date(2026, 9, 21),
            monto=Decimal("1.0000000"),
        )

    def test_formato_fecha_hora(self):
        valor = datetime(2026, 9, 21, 15, 15, 43, tzinfo=ZoneInfo("America/Lima"))
        self.assertEqual(fecha_hora(valor), "21/09/2026 - 03:15:43 pm")

    def test_operador_rechaza_clave_secreta(self):
        self.operador.direccion_stellar = "S" + "A" * 55
        with self.assertRaises(ValidationError):
            self.operador.full_clean()

    def test_operador_acepta_clave_publica(self):
        self.operador.direccion_stellar = Keypair.random().public_key
        self.operador.full_clean()

    def test_ruta_copia_nombre_del_catalogo(self):
        self.ruta.refresh_from_db()
        self.assertEqual(self.ruta.nombre, "Restaurante Alita")

    def test_admin_de_ruta_solo_pide_asignacion(self):
        admin = RutaAdmin(Ruta, None)
        request = type("Req", (), {"user": self.op_user, "is_superuser": False})()
        self.assertEqual(
            admin.get_fields(request),
            ("punto", "recolector", "monto", "fecha"),
        )

    def test_panel_operador_lista_rutas(self):
        self.client.force_login(self.op_user)
        response = self.client.get(reverse("panel_operador"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Restaurante Alita")
        self.assertContains(response, reverse("detalle_ruta_operador", args=[self.ruta.pk]))

    def test_detalle_operador_es_una_visita(self):
        self.client.force_login(self.op_user)
        response = self.client.get(reverse("detalle_ruta_operador", args=[self.ruta.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Restaurante Alita")
        self.assertContains(response, "XLM")
        self.assertContains(response, "Promedio del local")
        self.assertContains(response, "0 baldes")
        self.assertContains(response, 'data-live-kind="detalle-ruta"')
        self.assertContains(response, "Todavía no hay foto.")
        self.assertNotContains(response, 'data-live="foto" src="')

    def test_detalle_operador_muestra_foto(self):
        self.ruta.foto.save(
            "baldes.jpg",
            SimpleUploadedFile("baldes.jpg", b"fake-image", content_type="image/jpeg"),
            save=True,
        )
        self.client.force_login(self.op_user)
        response = self.client.get(reverse("detalle_ruta_operador", args=[self.ruta.pk]))
        self.assertContains(response, self.ruta.foto.url)
        self.assertContains(response, 'data-live="foto"')
        estado = self.client.get(reverse("estado_ruta_operador", args=[self.ruta.pk]))
        self.assertEqual(estado.json()["foto_url"], self.ruta.foto.url)

    def test_panel_recolector_lista_rutas(self):
        self.client.force_login(self.rec_user)
        response = self.client.get(reverse("panel_recolector"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Restaurante Alita")
        self.assertContains(response, reverse("subir_foto", args=[self.ruta.pk]))
        self.assertContains(response, reverse("detalle_ruta_recolector", args=[self.ruta.pk]))
        self.assertContains(response, "Subir foto")
        self.assertContains(response, fecha_hora(self.ruta.creado_en))
        self.assertNotContains(response, "Motivo de no pago")

    def test_panel_recolector_mas_reciente_primero(self):
        reciente = Ruta.objects.create(
            operador=self.operador,
            recolector=self.recolector,
            punto=self.punto,
            fecha=date(2026, 9, 22),
            monto=Decimal("1.0000000"),
        )
        self.client.force_login(self.rec_user)
        response = self.client.get(reverse("estado_panel_recolector"))
        ids = [ruta["id"] for ruta in response.json()["rutas"]]
        self.assertEqual(ids[0], reciente.pk)

    def test_detalle_recolector_explica_rechazo(self):
        self.ruta.estado = Ruta.Estado.RECHAZADO
        self.ruta.motivo_no_pago = "En la foto hay 5, no los 10 de Gemini."
        self.ruta.token_confirmacion = "token-secreto"
        self.ruta.save()
        self.client.force_login(self.rec_user)
        panel = self.client.get(reverse("panel_recolector"))
        self.assertNotContains(panel, "En la foto hay 5, no los 10 de Gemini.")
        detalle = self.client.get(reverse("detalle_ruta_recolector", args=[self.ruta.pk]))
        self.assertContains(detalle, "rechazó el pago")
        self.assertContains(detalle, "En la foto hay 5, no los 10 de Gemini.")
        self.assertNotContains(detalle, "token-secreto")
        self.assertNotContains(detalle, "confirmar/")

    def test_json_recolector_usa_rutas(self):
        self.client.force_login(self.rec_user)
        response = self.client.get(reverse("estado_panel_recolector"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["rutas"]), 1)
        self.assertEqual(data["rutas"][0]["nombre_local"], "Restaurante Alita")
        self.assertIn("subir_url", data["rutas"][0])

    def test_json_operador_no_anida_puntos(self):
        self.client.force_login(self.op_user)
        response = self.client.get(reverse("estado_panel_operador"))
        data = response.json()
        self.assertNotIn("puntos", data)
        self.assertEqual(data["rutas"][0]["nombre"], "Restaurante Alita")

    @patch("core.views.chequear_consistencia")
    def test_subir_foto_una_vez(self, mock_gemini):
        mock_gemini.return_value.cantidad = 3
        mock_gemini.return_value.consistente = True
        mock_gemini.return_value.respuesta = "3"
        mock_gemini.return_value.error = ""
        self.client.force_login(self.rec_user)
        foto = SimpleUploadedFile("baldes.jpg", b"fake-image", content_type="image/jpeg")
        response = self.client.post(
            reverse("subir_foto", args=[self.ruta.pk]),
            {"cantidad_baldes": "3", "foto": foto},
        )
        self.assertRedirects(response, reverse("panel_recolector"))
        self.ruta.refresh_from_db()
        self.assertTrue(self.ruta.foto)
        self.assertEqual(self.ruta.cantidad_baldes, 3)
        self.assertTrue(self.ruta.token_confirmacion)
        self.assertIsNotNone(self.ruta.procesado_en)
        self.assertIsNone(self.ruta.confirmado_en)
        detalle = self.client.get(reverse("detalle_ruta_recolector", args=[self.ruta.pk]))
        self.assertContains(detalle, fecha_hora(self.ruta.creado_en))
        self.assertContains(detalle, fecha_hora(self.ruta.procesado_en))

        otra = SimpleUploadedFile("otra.jpg", b"otra", content_type="image/jpeg")
        bloqueada = self.client.post(
            reverse("subir_foto", args=[self.ruta.pk]),
            {"cantidad_baldes": "4", "foto": otra},
        )
        self.assertRedirects(bloqueada, reverse("panel_recolector"))
        self.ruta.refresh_from_db()
        self.assertEqual(self.ruta.cantidad_baldes, 3)

    @patch("core.signals.procesar_pago", return_value="hash-de-prueba")
    def test_confirmacion_de_una_vez_y_pago(self, _mock_pago):
        self.ruta.gemini_consistente = True
        self.ruta.token_confirmacion = "token-prueba"
        self.ruta.save()

        primera = self.client.post(
            reverse("confirmar_punto", kwargs={"token": "token-prueba"}),
            {"confirmacion": "si"},
        )
        self.assertEqual(primera.status_code, 200)
        self.ruta.refresh_from_db()
        self.assertEqual(self.ruta.confirmacion, Ruta.Confirmacion.SI)
        self.assertEqual(self.ruta.estado, Ruta.Estado.PAGADO)
        pago = Payment.objects.get(ruta=self.ruta, tx_hash="hash-de-prueba")
        self.assertEqual(pago.monto, self.ruta.monto)
        self.assertEqual(pago.comision, Decimal("0"))

        segunda = self.client.post(
            reverse("confirmar_punto", kwargs={"token": "token-prueba"}),
            {"confirmacion": "no"},
        )
        self.assertEqual(segunda.status_code, 200)
        self.ruta.refresh_from_db()
        self.assertEqual(self.ruta.confirmacion, Ruta.Confirmacion.SI)
        self.assertEqual(Payment.objects.filter(ruta=self.ruta).count(), 1)

    def _confirmar_si(self, token):
        return self.client.post(
            reverse("confirmar_punto", kwargs={"token": token}),
            {"confirmacion": "si"},
        )

    @patch("core.signals.procesar_pago", return_value="hash-comision")
    def test_pago_suma_comision_por_excedente(self, mock_pago):
        self.punto.cantidad_promedio = 8
        self.punto.comision_por_balde = Decimal("0.1000000")
        self.punto.save()
        self.ruta.cantidad_baldes = 11
        self.ruta.gemini_consistente = True
        self.ruta.token_confirmacion = "token-comision"
        self.ruta.save()

        self._confirmar_si("token-comision")

        pago = Payment.objects.get(ruta=self.ruta)
        self.assertEqual(pago.comision, Decimal("0.3000000"))
        self.assertEqual(pago.monto, Decimal("1.3000000"))
        self.assertEqual(mock_pago.call_args[0][0].monto, Decimal("1.3000000"))

        self.client.force_login(self.op_user)
        detalle = self.client.get(reverse("detalle_ruta_operador", args=[self.ruta.pk]))
        self.assertContains(detalle, "8 baldes")
        self.assertContains(detalle, "0,3000000 XLM")
        estado = self.client.get(reverse("estado_ruta_operador", args=[self.ruta.pk]))
        self.assertEqual(estado.json()["comision_display"], "0,3000000 XLM")
        self.assertEqual(estado.json()["cantidad_promedio"], 8)
        with patch("core.views.consultar_saldo_xlm", return_value=Decimal("1")):
            pagos = self.client.get(reverse("pagos_operador"))
        self.assertContains(pagos, "Comisión")
        self.assertContains(pagos, "1,3000000 XLM")
        self.assertContains(pagos, "0,3000000 XLM")

        self.punto.cantidad_promedio = 20
        self.punto.comision_por_balde = Decimal("9")
        self.punto.save()
        pago.refresh_from_db()
        self.assertEqual(pago.comision, Decimal("0.3000000"))
        self.assertEqual(pago.monto, Decimal("1.3000000"))

    @patch("core.signals.procesar_pago", return_value="hash-sin-extra")
    def test_pago_sin_excedente_no_suma_comision(self, mock_pago):
        self.punto.cantidad_promedio = 8
        self.punto.comision_por_balde = Decimal("0.1000000")
        self.punto.save()
        self.ruta.cantidad_baldes = 8
        self.ruta.gemini_consistente = True
        self.ruta.token_confirmacion = "token-sin-extra"
        self.ruta.save()

        self._confirmar_si("token-sin-extra")

        pago = Payment.objects.get(ruta=self.ruta)
        self.assertEqual(pago.comision, Decimal("0"))
        self.assertEqual(pago.monto, Decimal("1.0000000"))
        self.assertEqual(mock_pago.call_args[0][0].monto, Decimal("1.0000000"))

    @patch("core.signals.procesar_pago", return_value="hash-forzado")
    def test_operador_procede_si_gemini_se_equivoca(self, mock_pago):
        self.punto.cantidad_promedio = 5
        self.punto.comision_por_balde = Decimal("0.1000000")
        self.punto.save()
        self.ruta.cantidad_baldes = 8
        self.ruta.gemini_cantidad = 10
        self.ruta.gemini_consistente = False
        self.ruta.confirmacion = Ruta.Confirmacion.SI
        self.ruta.estado = Ruta.Estado.EN_REVISION
        self.ruta.motivo_no_pago = "El conteo de Gemini no es consistente con lo reportado."
        self.ruta.save()

        self.client.force_login(self.op_user)
        detalle = self.client.get(reverse("detalle_ruta_operador", args=[self.ruta.pk]))
        self.assertContains(detalle, "¿Proceder con el pago?")
        self.assertContains(detalle, 'name="decision" value="si"')
        estado = self.client.get(reverse("estado_ruta_operador", args=[self.ruta.pk]))
        self.assertTrue(estado.json()["puede_proceder_pago"])

        respuesta = self.client.post(
            reverse("proceder_pago_operador", args=[self.ruta.pk]),
            {"decision": "si"},
        )
        self.assertRedirects(respuesta, reverse("detalle_ruta_operador", args=[self.ruta.pk]))
        self.ruta.refresh_from_db()
        self.assertEqual(self.ruta.estado, Ruta.Estado.PAGADO)
        pago = Payment.objects.get(ruta=self.ruta)
        self.assertEqual(pago.comision, Decimal("0.3000000"))
        self.assertEqual(pago.monto, Decimal("1.3000000"))
        self.assertEqual(mock_pago.call_args[0][0].monto, Decimal("1.3000000"))
        cerrado = self.client.get(reverse("detalle_ruta_operador", args=[self.ruta.pk]))
        self.assertContains(cerrado, 'data-live-proceder hidden')

    def test_operador_rechaza_pago_con_motivo(self):
        self.ruta.cantidad_baldes = 5
        self.ruta.gemini_cantidad = 10
        self.ruta.gemini_consistente = False
        self.ruta.confirmacion = Ruta.Confirmacion.SI
        self.ruta.estado = Ruta.Estado.EN_REVISION
        self.ruta.motivo_no_pago = "El conteo de Gemini no es consistente con lo reportado."
        self.ruta.save()

        self.client.force_login(self.op_user)
        vacio = self.client.post(
            reverse("proceder_pago_operador", args=[self.ruta.pk]),
            {"decision": "no", "motivo": "  "},
        )
        self.assertEqual(vacio.status_code, 200)
        self.assertContains(vacio, "Motivo del no pago")
        self.ruta.refresh_from_db()
        self.assertEqual(self.ruta.estado, Ruta.Estado.EN_REVISION)

        respuesta = self.client.post(
            reverse("proceder_pago_operador", args=[self.ruta.pk]),
            {"decision": "no", "motivo": "En la foto hay 5, no los 10 de Gemini."},
        )
        self.assertRedirects(respuesta, reverse("detalle_ruta_operador", args=[self.ruta.pk]))
        self.ruta.refresh_from_db()
        self.assertEqual(self.ruta.estado, Ruta.Estado.RECHAZADO)
        self.assertEqual(self.ruta.motivo_no_pago, "En la foto hay 5, no los 10 de Gemini.")
        self.assertFalse(Payment.objects.filter(ruta=self.ruta).exists())

    @patch("core.views.consultar_saldo_xlm", return_value=Decimal("12.5000000"))
    def test_pagos_recolector_muestra_ruta_y_fecha(self, _saldo):
        Payment.objects.create(
            ruta=self.ruta,
            tx_hash="abc123",
            monto=self.ruta.monto,
            estado=Payment.Estado.COMPLETADO,
        )
        self.client.force_login(self.rec_user)
        response = self.client.get(reverse("pagos_recolector"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Restaurante Alita")
        self.assertContains(response, "Ver transferencia")
        self.assertContains(response, "Saldo en tu wallet")
        self.assertContains(response, "12,5000000 XLM")
        self.assertContains(response, "Ver wallet")
        self.assertContains(
            response,
            "https://stellar.expert/explorer/testnet/account/"
            + self.recolector.direccion_stellar,
        )
        json_resp = self.client.get(reverse("estado_pagos_recolector"))
        pago = json_resp.json()["pagos"][0]
        self.assertEqual(pago["local"], "Restaurante Alita")
        self.assertEqual(json_resp.json()["saldo_display"], "12,5000000 XLM")
        self.assertNotIn("recolector", pago)
        self.assertNotIn("ruta_url", pago)

    @patch("core.views.consultar_saldo_xlm", return_value=Decimal("99.0000000"))
    def test_pagos_operador_muestra_a_quien(self, _saldo):
        Payment.objects.create(
            ruta=self.ruta,
            tx_hash="abc123",
            monto=self.ruta.monto,
            estado=Payment.Estado.COMPLETADO,
        )
        self.client.force_login(self.op_user)
        response = self.client.get(reverse("pagos_operador"))
        self.assertContains(response, "luis")
        self.assertContains(response, "Restaurante Alita")
        self.assertContains(response, "Saldo en la wallet que paga")
        self.assertContains(response, "99,0000000 XLM")
        self.assertContains(response, "Ver wallet")
        self.assertContains(
            response,
            "https://stellar.expert/explorer/testnet/account/"
            + self.operador.direccion_stellar,
        )
        json_resp = self.client.get(reverse("estado_pagos_operador"))
        pago = json_resp.json()["pagos"][0]
        self.assertEqual(pago["recolector"], "luis")
        self.assertIn("ruta_url", pago)
        self.assertEqual(json_resp.json()["saldo_display"], "99,0000000 XLM")

    @patch("core.views.consultar_saldo_xlm", return_value=None)
    def test_recolector_no_ve_pagos_de_otro(self, _saldo):
        otro_user = User.objects.create_user("otro", password="x")
        otro = Recolector.objects.create(
            user=otro_user,
            direccion_stellar="G" + "B" * 55,
        )
        otra_ruta = Ruta.objects.create(
            operador=self.operador,
            recolector=otro,
            punto=self.punto,
            fecha=date(2026, 9, 22),
            monto=Decimal("2.0000000"),
        )
        Payment.objects.create(
            ruta=otra_ruta,
            tx_hash="otro-hash",
            monto=otra_ruta.monto,
            estado=Payment.Estado.COMPLETADO,
        )
        self.client.force_login(self.rec_user)
        response = self.client.get(reverse("pagos_recolector"))
        self.assertNotContains(response, "otro-hash")
        self.assertContains(response, "Todavía no te pagaron ninguna ruta.")

    def test_panel_con_rutas_ofrece_crear_nueva(self):
        self.client.force_login(self.op_user)
        response = self.client.get(reverse("panel_operador"))
        self.assertContains(response, "Crear nueva ruta")
        self.assertNotContains(response, ">Crear ruta<")

    def test_panel_sin_rutas_ofrece_crear_ruta(self):
        self.ruta.delete()
        self.client.force_login(self.op_user)
        response = self.client.get(reverse("panel_operador"))
        self.assertContains(response, ">Crear ruta<")
        self.assertNotContains(response, "Crear nueva ruta")

    def test_crear_ruta_sin_puntos_manda_al_formulario(self):
        self.ruta.delete()
        self.punto.delete()
        self.client.force_login(self.op_user)
        response = self.client.get(reverse("crear_ruta_operador"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nueva ruta")
        self.assertContains(response, "No hay puntos de recojo.")
        self.assertContains(response, reverse("crear_punto_operador") + "?volver=ruta")
        self.assertContains(response, "Crear uno")

    def test_puntos_vacios_y_con_lista(self):
        self.client.force_login(self.op_user)
        response = self.client.get(reverse("puntos_operador"))
        self.assertContains(response, "Añadir nuevo punto de recojo")
        self.assertContains(response, "Restaurante Alita")
        self.ruta.delete()
        self.punto.delete()
        vacio = self.client.get(reverse("puntos_operador"))
        self.assertContains(vacio, "Crear punto de recojo")
        self.assertNotContains(vacio, "Añadir nuevo punto de recojo")

    def test_operador_crea_punto_y_ruta(self):
        self.client.force_login(self.op_user)
        alta = self.client.post(
            reverse("crear_punto_operador"),
            {
                "nombre": "Café Norte",
                "cantidad_promedio": "4",
                "comision_por_balde": "0.1000000",
            },
        )
        self.assertRedirects(alta, reverse("puntos_operador"))
        punto = Punto.objects.get(nombre="Café Norte")
        self.assertEqual(punto.operador, self.operador)
        alta_ruta = self.client.post(
            reverse("crear_ruta_operador"),
            {
                "punto": punto.pk,
                "recolector": self.recolector.pk,
                "monto": "1.5000000",
                "fecha": "2026-09-23",
            },
        )
        self.assertRedirects(alta_ruta, reverse("panel_operador"))
        ruta = Ruta.objects.get(punto=punto)
        self.assertEqual(ruta.operador, self.operador)
        self.assertEqual(ruta.nombre, "Café Norte")

    def test_recolector_no_crea_rutas(self):
        self.client.force_login(self.rec_user)
        response = self.client.get(reverse("crear_ruta_operador"))
        self.assertEqual(response.status_code, 404)
