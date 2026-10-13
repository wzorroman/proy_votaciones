import csv
import os
import tempfile
from datetime import timedelta

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.candidates.models import ListaCandidatura, TipoEleccion
from apps.voters.models import Estudiante, GradoSeccion, ProcesoElectoral
from apps.auditoria.models import AccionAdministrativa
from apps.core.crypto import cifrar_boleta, nueva_boleta
from apps.voters.selectors import EstadoElector, listar_padron, validar_dni
from apps.voting.models import ActaCierreProceso, RegistroParticipacion, Voto
from apps.voting.selectors import (
    desglose_grado_seccion_por_mesa,
    estudiantes_sin_mesa,
    filtros_padron,
    metricas_generales,
    padron_por_mesas,
    participacion_por_grado_seccion,
    participacion_por_mesa,
    resumen_asignacion_mesas,
)
from apps.voting.services.cerrar_proceso import cerrar_proceso
from apps.voting.services.emitir_voto import ErrorVoto, emitir_voto
from apps.voting.services.asignar_mesa import (
    ErrorAsignacion,
    asignar_mesa_a_grado_seccion,
)
from apps.voting.services.iniciar_votacion import (
    ErrorInicio,
    iniciar_votacion_proceso,
    pausar_votacion_proceso,
    reanudar_votacion_proceso,
)
from apps.voting.services.reiniciar_voto import ErrorAccion, reiniciar_voto
from apps.voting.services.toggle_estudiante import habilitar_estudiante, inhabilitar_estudiante


class ImportarPadronCommandTests(TestCase):
    def test_importar_padron_crea_estudiantes_y_ignora_dnis_invalidos(self):
        proceso = ProcesoElectoral.objects.create(nombre="Proceso prueba", activo=True)

        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="", encoding="utf-8") as f:
            csv_path = f.name
            writer = csv.writer(f)
            writer.writerow([
                "item",
                "dni",
                "apellido_paterno",
                "apellido_materno",
                "nombres",
                "nivel",
                "grado",
                "seccion",
                "mesa",
            ])
            writer.writerow([1, "62950912", "aguilar", "sandoval", "luis dilver", "primaria", "1ro", "C", "Mesa 1"])
            writer.writerow([2, "78123348", "chapoñan", "de la cruz", "luis armando", "primaria", "1ro", "C", "Mesa 1"])
            writer.writerow([3, "ABC12345", "nombres", "apellidos", "otro estudiante", "primaria", "2do", "A", "Mesa 2"])

        self.addCleanup(os.remove, csv_path)
        call_command("importar_padron", file=csv_path, proceso=proceso.pk, crear_mesas=True)

        self.assertEqual(Estudiante.objects.filter(proceso=proceso).count(), 2)
        estudiante = Estudiante.objects.get(numero_documento="62950912")
        self.assertEqual(estudiante.apellido_paterno, "AGUILAR")
        self.assertEqual(estudiante.nombres, "LUIS DILVER")
        self.assertTrue(estudiante.mesa is not None)
        self.assertEqual(estudiante.mesa.numero_mesa, "Mesa 1")
        self.assertIsNotNone(estudiante.grado_seccion)
        self.assertEqual(estudiante.grado_seccion.nivel, "primaria")
        self.assertEqual(estudiante.grado_seccion.seccion, "C")

    def test_importar_padron_sin_columna_mesa(self):
        proceso = ProcesoElectoral.objects.create(nombre="Proceso sin mesa", activo=True)

        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="", encoding="utf-8") as f:
            csv_path = f.name
            writer = csv.writer(f)
            writer.writerow([
                "item", "dni", "apellido_paterno", "apellido_materno",
                "nombres", "nivel", "grado", "seccion",
            ])
            writer.writerow([1, "70000001", "quispe", "mamani", "juan", "secundaria", "3ro", "B"])

        self.addCleanup(os.remove, csv_path)
        call_command("importar_padron", file=csv_path, proceso=proceso.pk)

        estudiante = Estudiante.objects.get(numero_documento="70000001")
        self.assertIsNone(estudiante.mesa)
        self.assertIsNotNone(estudiante.grado_seccion)
        self.assertEqual(estudiante.grado_seccion.grado, "3ro")
        self.assertEqual(estudiante.grado_seccion.orden, 3)


class KioskValidationTests(TestCase):
    def setUp(self):
        self.proceso = ProcesoElectoral.objects.create(nombre="Proceso prueba", activo=True, cerrado=False)

    def test_validar_dni_cinco_estados(self):
        estado, estudiante = validar_dni("99999999", self.proceso)
        self.assertEqual(estado, EstadoElector.NO_EXISTE)
        self.assertIsNone(estudiante)

        inhabilitado = Estudiante.objects.create(
            proceso=self.proceso,
            numero_documento="11111111",
            apellido_paterno="Pérez",
            apellido_materno="López",
            nombres="Ana",
            es_activo=True,
            inhabilitado=True,
        )
        estado, estudiante = validar_dni("11111111", self.proceso)
        self.assertEqual(estado, EstadoElector.INHABILITADO)
        self.assertEqual(estudiante, inhabilitado)

        ya_voto = Estudiante.objects.create(
            proceso=self.proceso,
            numero_documento="22222222",
            apellido_paterno="García",
            apellido_materno="Mendoza",
            nombres="Luis",
            ha_votado=True,
        )
        estado, estudiante = validar_dni("22222222", self.proceso)
        self.assertEqual(estado, EstadoElector.YA_VOTO)
        self.assertEqual(estudiante, ya_voto)

        ausente = Estudiante.objects.create(
            proceso=self.proceso,
            numero_documento="33333333",
            apellido_paterno="Ruiz",
            apellido_materno="Castro",
            nombres="María",
            fecha_ausentismo=timezone.now() - timedelta(days=1),
        )
        estado, estudiante = validar_dni("33333333", self.proceso)
        self.assertEqual(estado, EstadoElector.AUSENTE)
        self.assertEqual(estudiante, ausente)

        ok = Estudiante.objects.create(
            proceso=self.proceso,
            numero_documento="44444444",
            apellido_paterno="Vargas",
            apellido_materno="Paredes",
            nombres="Sofía",
        )
        estado, estudiante = validar_dni("44444444", self.proceso)
        self.assertEqual(estado, EstadoElector.OK)
        self.assertEqual(estudiante, ok)

    def test_kiosk_post_valida_dni_y_persiste_sesion(self):
        self.proceso.votacion_iniciada = True
        self.proceso.save(update_fields=["votacion_iniciada"])
        Estudiante.objects.create(
            proceso=self.proceso,
            numero_documento="55555555",
            apellido_paterno="Soto",
            apellido_materno="Luna",
            nombres="Pedro",
        )

        response = self.client.post(reverse("kiosk_espera"), {"dni": "55555555"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session["voto_estudiante_id"], 1)
        self.assertEqual(self.client.session["voto_proceso_id"], self.proceso.pk)

    def test_kiosk_post_bloqueado_si_votacion_no_iniciada(self):
        Estudiante.objects.create(
            proceso=self.proceso,
            numero_documento="55555555",
            apellido_paterno="Soto",
            apellido_materno="Luna",
            nombres="Pedro",
        )

        response = self.client.post(reverse("kiosk_espera"), {"dni": "55555555"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "aún no ha comenzado")
        self.assertNotIn("voto_estudiante_id", self.client.session)


class IniciarVotacionTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="inicia", password="secret", is_staff=True)
        self.proceso = ProcesoElectoral.objects.create(nombre="Proceso inicio", activo=True, cerrado=False)
        self.grado_seccion = GradoSeccion.objects.get_or_create(
            nivel="secundaria", grado="1ro", seccion="A", defaults={"orden": 1},
        )[0]

    def test_catalogo_normaliza_nivel_y_seccion(self):
        gs = GradoSeccion.objects.create(nivel="  Primaria ", grado=" 6to ", seccion=" z ")
        self.assertEqual(gs.nivel, "primaria")
        self.assertEqual(gs.grado, "6to")
        self.assertEqual(gs.seccion, "Z")
        self.assertEqual(str(gs), "6to Z")

    def test_iniciar_rechaza_padron_con_estudiantes_sin_mesa(self):
        Estudiante.objects.create(
            proceso=self.proceso,
            grado_seccion=self.grado_seccion,
            numero_documento="10000000",
            apellido_paterno="A",
            nombres="A",
        )

        with self.assertRaises(ErrorInicio):
            iniciar_votacion_proceso(self.proceso, self.usuario)

        self.proceso.refresh_from_db()
        self.assertFalse(self.proceso.votacion_iniciada)

    def test_iniciar_rechaza_estudiantes_sin_grado_seccion(self):
        mesa = self.proceso.mesas.create(numero_mesa="Mesa 1")
        Estudiante.objects.create(
            proceso=self.proceso,
            mesa=mesa,
            numero_documento="10000001",
            apellido_paterno="A",
            nombres="A",
        )

        with self.assertRaises(ErrorInicio):
            iniciar_votacion_proceso(self.proceso, self.usuario)

    def test_iniciar_votacion_ok_marca_proceso_y_audita(self):
        mesa = self.proceso.mesas.create(numero_mesa="Mesa 1")
        Estudiante.objects.create(
            proceso=self.proceso,
            mesa=mesa,
            grado_seccion=self.grado_seccion,
            numero_documento="10000002",
            apellido_paterno="A",
            nombres="A",
        )

        resumen = iniciar_votacion_proceso(self.proceso, self.usuario)

        self.proceso.refresh_from_db()
        self.assertTrue(self.proceso.votacion_iniciada)
        self.assertIsNotNone(self.proceso.fecha_inicio)
        self.assertEqual(resumen["sin_mesa"], 0)
        self.assertTrue(AccionAdministrativa.objects.filter(accion="iniciar_votacion").exists())

    def test_iniciar_votacion_no_se_puede_repetir(self):
        mesa = self.proceso.mesas.create(numero_mesa="Mesa 1")
        Estudiante.objects.create(
            proceso=self.proceso,
            mesa=mesa,
            grado_seccion=self.grado_seccion,
            numero_documento="10000003",
            apellido_paterno="A",
            nombres="A",
        )
        iniciar_votacion_proceso(self.proceso, self.usuario)

        with self.assertRaises(ErrorInicio):
            iniciar_votacion_proceso(self.proceso, self.usuario)

    def _proceso_listo(self):
        mesa = self.proceso.mesas.create(numero_mesa="Mesa 1")
        estudiante = Estudiante.objects.create(
            proceso=self.proceso,
            mesa=mesa,
            grado_seccion=self.grado_seccion,
            numero_documento="19999999",
            apellido_paterno="A",
            apellido_materno="B",
            nombres="A",
        )
        iniciar_votacion_proceso(self.proceso, self.usuario)
        self.proceso.refresh_from_db()
        return mesa, estudiante

    def test_pausar_y_reanudar_votacion(self):
        self._proceso_listo()
        self.assertFalse(self.proceso.votacion_pausada)

        pausar_votacion_proceso(self.proceso, self.usuario)
        self.proceso.refresh_from_db()
        self.assertTrue(self.proceso.votacion_pausada)

        reanudar_votacion_proceso(self.proceso, self.usuario)
        self.proceso.refresh_from_db()
        self.assertFalse(self.proceso.votacion_pausada)

        self.assertTrue(AccionAdministrativa.objects.filter(accion="pausar_votacion").exists())
        self.assertTrue(AccionAdministrativa.objects.filter(accion="reanudar_votacion").exists())

    def test_no_se_puede_pausar_si_no_ha_iniciado(self):
        with self.assertRaises(ErrorInicio):
            pausar_votacion_proceso(self.proceso, self.usuario)

    def test_no_se_puede_reanudar_si_no_esta_pausada(self):
        self._proceso_listo()
        with self.assertRaises(ErrorInicio):
            reanudar_votacion_proceso(self.proceso, self.usuario)

    def test_kiosk_bloquea_mientras_esta_pausada(self):
        _, estudiante = self._proceso_listo()
        pausar_votacion_proceso(self.proceso, self.usuario)

        response = self.client.post(
            reverse("kiosk_espera"), {"dni": estudiante.numero_documento}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Votación pausada")
        self.assertNotIn("voto_estudiante_id", self.client.session)

    def test_kiosk_espera_muestra_mensaje_de_pausa(self):
        self._proceso_listo()
        pausar_votacion_proceso(self.proceso, self.usuario)

        response = self.client.get(reverse("kiosk_espera"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Votación pausada")

    def test_vistas_pausar_y_reanudar_actualizan_estado(self):
        self._proceso_listo()
        self.client.force_login(self.usuario)

        response = self.client.post(reverse("pausar_votacion"))
        self.assertEqual(response.status_code, 302)
        self.proceso.refresh_from_db()
        self.assertTrue(self.proceso.votacion_pausada)

        response = self.client.post(reverse("reanudar_votacion"))
        self.assertEqual(response.status_code, 302)
        self.proceso.refresh_from_db()
        self.assertFalse(self.proceso.votacion_pausada)

    def test_selectores_asignacion_y_filtro_sin_mesa(self):
        mesa = self.proceso.mesas.create(numero_mesa="Mesa 1")
        Estudiante.objects.create(
            proceso=self.proceso,
            mesa=mesa,
            grado_seccion=self.grado_seccion,
            numero_documento="10000004",
            apellido_paterno="A",
            nombres="A",
        )
        sin_mesa = Estudiante.objects.create(
            proceso=self.proceso,
            grado_seccion=self.grado_seccion,
            numero_documento="10000005",
            apellido_paterno="B",
            nombres="B",
        )

        resumen = resumen_asignacion_mesas(self.proceso)
        self.assertEqual(resumen["total"], 2)
        self.assertEqual(resumen["asignados"], 1)
        self.assertEqual(resumen["sin_mesa"], 1)
        self.assertEqual(resumen["porcentaje"], 50.0)

        qs = list(estudiantes_sin_mesa(self.proceso))
        self.assertEqual(qs, [sin_mesa])

        filtrados = list(filtros_padron(self.proceso, estado="sin_mesa"))
        self.assertEqual(filtrados, [sin_mesa])


class AdminCandidatesInlineTests(TestCase):
    def setUp(self):
        self.proceso = ProcesoElectoral.objects.create(nombre="Proceso admin", activo=True, cerrado=False)
        self.tipo = TipoEleccion.objects.create(proceso=self.proceso, nombre="Alcalde", orden_aparicion=1)
        self.user = get_user_model().objects.create_superuser(username="admin", email="admin@example.com", password="admin123")

    def test_admin_inline_crea_lista_con_proceso_del_tipo(self):
        self.client.force_login(self.user)

        payload = {
            "proceso": self.proceso.pk,
            "nombre": self.tipo.nombre,
            "orden_aparicion": self.tipo.orden_aparicion,
            "es_activo": "on",
            "color_fondo": "#EAF3FF",
            "_save": "Guardar",
            "listas-TOTAL_FORMS": "1",
            "listas-INITIAL_FORMS": "0",
            "listas-MIN_NUM_FORMS": "0",
            "listas-MAX_NUM_FORMS": "1000",
            "listas-0-nombre": "Lista Nueva",
            "listas-0-descripcion": "Descripción de prueba",
            "listas-0-es_activo": "on",
        }

        response = self.client.post(reverse("admin:candidates_tipoeleccion_change", args=[self.tipo.pk]), payload)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(ListaCandidatura.objects.filter(proceso=self.proceso, tipo_eleccion=self.tipo, nombre="Lista Nueva").exists())


class VoteEmissionPhase4Tests(TestCase):
    def setUp(self):
        self.proceso = ProcesoElectoral.objects.create(nombre="Proceso fase 4", activo=True, cerrado=False)
        self.proceso.votacion_iniciada = True
        self.proceso.save(update_fields=["votacion_iniciada"])
        self.tipo_a = TipoEleccion.objects.create(proceso=self.proceso, nombre="Alcalde", orden_aparicion=1)
        self.tipo_b = TipoEleccion.objects.create(proceso=self.proceso, nombre="Regidores", orden_aparicion=2)
        self.lista_a = ListaCandidatura.objects.create(proceso=self.proceso, tipo_eleccion=self.tipo_a, nombre="Lista A")
        self.lista_b = ListaCandidatura.objects.create(proceso=self.proceso, tipo_eleccion=self.tipo_a, nombre="Lista B")
        self.lista_c = ListaCandidatura.objects.create(proceso=self.proceso, tipo_eleccion=self.tipo_b, nombre="Lista C")
        self.lista_d = ListaCandidatura.objects.create(proceso=self.proceso, tipo_eleccion=self.tipo_b, nombre="Lista D")
        self.estudiante = Estudiante.objects.create(
            proceso=self.proceso,
            numero_documento="12345678",
            apellido_paterno="Apellido",
            apellido_materno="Materno",
            nombres="Nombre",
        )

    def test_emitir_voto_crea_votos_y_registro(self):
        emitir_voto(
            self.estudiante.id,
            self.proceso,
            {self.tipo_a.id: self.lista_a.id, self.tipo_b.id: self.lista_c.id},
        )

        self.estudiante.refresh_from_db()
        self.assertTrue(self.estudiante.ha_votado)
        self.assertEqual(Voto.objects.filter(proceso=self.proceso).count(), 2)
        self.assertEqual(RegistroParticipacion.objects.filter(proceso=self.proceso).count(), 1)

    def test_emitir_voto_doble_rechaza_y_no_duplca(self):
        emitir_voto(
            self.estudiante.id,
            self.proceso,
            {self.tipo_a.id: self.lista_a.id, self.tipo_b.id: self.lista_c.id},
        )

        with self.assertRaises(ErrorVoto):
            emitir_voto(
                self.estudiante.id,
                self.proceso,
                {self.tipo_a.id: self.lista_b.id, self.tipo_b.id: self.lista_d.id},
            )

        self.assertEqual(Voto.objects.filter(proceso=self.proceso).count(), 2)
        self.assertEqual(RegistroParticipacion.objects.filter(proceso=self.proceso).count(), 1)

    def test_wizard_persiste_selecciones_en_sesion(self):
        session = self.client.session
        session["voto_estudiante_id"] = self.estudiante.id
        session["voto_proceso_id"] = self.proceso.id
        session["voto_tipo_actual"] = 0
        session["voto_selecciones"] = {}
        session.save()

        response = self.client.post(reverse("kiosk_wizard_paso"), {"lista_id": self.lista_a.id})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session["voto_selecciones"][str(self.tipo_a.id)], self.lista_a.id)
        self.assertEqual(self.client.session["voto_tipo_actual"], 1)


class DashboardMetricsTests(TestCase):
    def setUp(self):
        self.proceso = ProcesoElectoral.objects.create(nombre="Proceso dashboard", activo=True, cerrado=False)
        self.mesa_1 = self.proceso.mesas.create(numero_mesa="Mesa 1", descripcion="Aula 1")
        self.mesa_2 = self.proceso.mesas.create(numero_mesa="Mesa 2", descripcion="Aula 2")
        self.tipo = TipoEleccion.objects.create(proceso=self.proceso, nombre="Alcalde", orden_aparicion=1)
        self.lista_1 = ListaCandidatura.objects.create(proceso=self.proceso, tipo_eleccion=self.tipo, nombre="Lista X")
        self.lista_2 = ListaCandidatura.objects.create(proceso=self.proceso, tipo_eleccion=self.tipo, nombre="Lista Y")

    def test_metricas_generales_y_participacion_por_mesa(self):
        Estudiante.objects.create(proceso=self.proceso, mesa=self.mesa_1, numero_documento="10000000", apellido_paterno="A", nombres="A")
        Estudiante.objects.create(proceso=self.proceso, mesa=self.mesa_1, numero_documento="10000001", apellido_paterno="B", nombres="B")
        Estudiante.objects.create(proceso=self.proceso, mesa=self.mesa_2, numero_documento="10000002", apellido_paterno="C", nombres="C", inhabilitado=True)
        votante = Estudiante.objects.create(proceso=self.proceso, mesa=self.mesa_2, numero_documento="10000003", apellido_paterno="D", nombres="D", ha_votado=True)

        metrics = metricas_generales(self.proceso)
        self.assertEqual(metrics["habiles"], 3)
        self.assertEqual(metrics["emitidos"], 1)
        self.assertEqual(metrics["faltantes"], 2)
        self.assertEqual(metrics["porcentaje"], 33.3)

        mesas = participacion_por_mesa(self.proceso)
        self.assertEqual(mesas[0]["numero_mesa"], "Mesa 1")
        self.assertEqual(mesas[1]["numero_mesa"], "Mesa 2")
        self.assertEqual(mesas[0]["habiles"], 2)
        self.assertEqual(mesas[0]["emitidos"], 0)
        self.assertEqual(mesas[1]["habiles"], 1)
        self.assertEqual(mesas[1]["emitidos"], 1)

    def test_dashboard_live_json(self):
        User = get_user_model()
        user = User.objects.create_user(username="admin", password="secret", is_staff=True, is_superuser=True)
        self.client.force_login(user)
        self.proceso.activo = False
        self.proceso.save(update_fields=["activo"])

        response = self.client.get(reverse("dashboard_live_json"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["activo"], False)

    def test_participacion_por_grado_seccion(self):
        gs_a = GradoSeccion.objects.get_or_create(nivel="secundaria", grado="1ro", seccion="A", defaults={"orden": 1})[0]
        gs_b = GradoSeccion.objects.get_or_create(nivel="secundaria", grado="1ro", seccion="B", defaults={"orden": 1})[0]
        gs_c = GradoSeccion.objects.get_or_create(nivel="secundaria", grado="2do", seccion="A", defaults={"orden": 2})[0]
        Estudiante.objects.create(
            proceso=self.proceso, mesa=self.mesa_1, grado_seccion=gs_a,
            numero_documento="30000001", apellido_paterno="A", nombres="A", ha_votado=True,
        )
        Estudiante.objects.create(
            proceso=self.proceso, mesa=self.mesa_1, grado_seccion=gs_a,
            numero_documento="30000002", apellido_paterno="B", nombres="B",
        )
        Estudiante.objects.create(
            proceso=self.proceso, mesa=self.mesa_2, grado_seccion=gs_b,
            numero_documento="30000003", apellido_paterno="C", nombres="C",
        )
        Estudiante.objects.create(
            proceso=self.proceso, mesa=self.mesa_2, grado_seccion=gs_b,
            numero_documento="30000004", apellido_paterno="D", nombres="D", inhabilitado=True,
        )
        Estudiante.objects.create(
            proceso=self.proceso, mesa=self.mesa_2, grado_seccion=gs_c,
            numero_documento="30000005", apellido_paterno="E", nombres="E",
        )

        data = participacion_por_grado_seccion(self.proceso)

        grados = {g["grado"]: g for g in data["grados"]}
        self.assertEqual(set(grados.keys()), {"1ro", "2do"})
        self.assertEqual(grados["1ro"]["habiles"], 3)
        self.assertEqual(grados["1ro"]["emitidos"], 1)
        self.assertEqual(grados["1ro"]["porcentaje"], 33.3)
        self.assertEqual(grados["2do"]["habiles"], 1)
        self.assertEqual(grados["2do"]["emitidos"], 0)

        filas = {(s["grado"], s["seccion"]): s for s in data["secciones"]}
        self.assertEqual(filas[("1ro", "A")]["habiles"], 2)
        self.assertEqual(filas[("1ro", "A")]["emitidos"], 1)
        self.assertEqual(filas[("1ro", "B")]["habiles"], 1)
        self.assertEqual(filas[("2do", "A")]["habiles"], 1)

    def test_desglose_grado_seccion_por_mesa(self):
        gs_a = GradoSeccion.objects.get_or_create(nivel="secundaria", grado="1ro", seccion="A", defaults={"orden": 1})[0]
        gs_b = GradoSeccion.objects.get_or_create(nivel="secundaria", grado="2do", seccion="A", defaults={"orden": 2})[0]
        Estudiante.objects.create(
            proceso=self.proceso, mesa=self.mesa_1, grado_seccion=gs_a,
            numero_documento="30000101", apellido_paterno="A", nombres="A",
        )
        Estudiante.objects.create(
            proceso=self.proceso, mesa=self.mesa_1, grado_seccion=gs_a,
            numero_documento="30000102", apellido_paterno="B", nombres="B",
        )
        Estudiante.objects.create(
            proceso=self.proceso, mesa=self.mesa_1, grado_seccion=gs_b,
            numero_documento="30000103", apellido_paterno="C", nombres="C", inhabilitado=True,
        )
        Estudiante.objects.create(
            proceso=self.proceso, mesa=self.mesa_2, grado_seccion=gs_b,
            numero_documento="30000104", apellido_paterno="D", nombres="D",
        )

        detalle = desglose_grado_seccion_por_mesa(self.proceso)
        by_mesa = {m["numero_mesa"]: m for m in detalle}

        self.assertEqual(set(by_mesa.keys()), {"Mesa 1", "Mesa 2"})
        self.assertEqual(by_mesa["Mesa 1"]["habiles"], 2)
        self.assertEqual(by_mesa["Mesa 1"]["filas"], [
            {"grado": "1ro", "seccion": "A", "cantidad": 2},
        ])
        self.assertEqual(by_mesa["Mesa 2"]["habiles"], 1)
        self.assertEqual(by_mesa["Mesa 2"]["filas"], [
            {"grado": "2do", "seccion": "A", "cantidad": 1},
        ])
        self.assertEqual(sum(m["habiles"] for m in detalle), 3)

    def test_dashboard_render_tiene_graficos_y_modal_grados(self):
        User = get_user_model()
        user = User.objects.create_user(username="admin2", password="secret", is_staff=True, is_superuser=True)
        self.client.force_login(user)
        gs_a = GradoSeccion.objects.get_or_create(nivel="secundaria", grado="1ro", seccion="A", defaults={"orden": 1})[0]
        Estudiante.objects.create(
            proceso=self.proceso, mesa=self.mesa_1, grado_seccion=gs_a,
            numero_documento="30000201", apellido_paterno="A", nombres="A",
        )

        response = self.client.get(reverse("dashboard"))
        content = response.content.decode()

        self.assertContains(response, 'id="chartGrados"')
        self.assertContains(response, 'id="chartSecciones"')
        self.assertContains(response, 'id="modalGradosSeccion"')
        self.assertContains(response, "Participación por Grado (%)")
        self.assertContains(response, "Participación por Sección (%)")
        self.assertContains(response, "TOTAL PADRÓN")
        self.assertContains(response, "Subtotal de hábiles:")
        self.assertIn('data-bs-target="#modalGradosSeccion"', content)
        self.assertIn('class="btn btn-sm btn-primary btn-mas rounded-circle border-0"', content)


class AuditoriaPhase6Tests(TestCase):
    def setUp(self):
        self.proceso = ProcesoElectoral.objects.create(nombre="Proceso auditoría", activo=True, cerrado=False)
        self.mesa = self.proceso.mesas.create(numero_mesa="Mesa 1", descripcion="Aula 1")
        self.tipo_a = TipoEleccion.objects.create(proceso=self.proceso, nombre="Alcalde", orden_aparicion=1)
        self.tipo_b = TipoEleccion.objects.create(proceso=self.proceso, nombre="Regidores", orden_aparicion=2)
        self.lista_1 = ListaCandidatura.objects.create(proceso=self.proceso, tipo_eleccion=self.tipo_a, nombre="Lista A")
        self.lista_2 = ListaCandidatura.objects.create(proceso=self.proceso, tipo_eleccion=self.tipo_a, nombre="Lista B")
        self.lista_3 = ListaCandidatura.objects.create(proceso=self.proceso, tipo_eleccion=self.tipo_b, nombre="Lista C")
        self.lista_4 = ListaCandidatura.objects.create(proceso=self.proceso, tipo_eleccion=self.tipo_b, nombre="Lista D")
        self.estudiante = Estudiante.objects.create(
            proceso=self.proceso,
            mesa=self.mesa,
            numero_documento="90000001",
            apellido_paterno="Pérez",
            apellido_materno="López",
            nombres="Ana",
        )
        self.usuario = get_user_model().objects.create_user(username="admin6", password="secret", is_staff=True)

    def test_listar_padron_y_reiniciar_voto(self):
        emitir_voto(
            self.estudiante.id,
            self.proceso,
            {self.tipo_a.id: self.lista_1.id, self.tipo_b.id: self.lista_3.id},
        )

        page = listar_padron(self.proceso, page=1)
        self.assertEqual(page.object_list.count(), 1)
        self.assertTrue(page.object_list[0].ha_votado)

        reiniciar_voto(self.estudiante.id, self.usuario, motivo="Revisar voto")
        self.estudiante.refresh_from_db()
        self.assertFalse(self.estudiante.ha_votado)
        self.assertEqual(Voto.objects.filter(proceso=self.proceso).count(), 0)
        self.assertEqual(RegistroParticipacion.objects.filter(proceso=self.proceso).count(), 0)
        self.assertTrue(AccionAdministrativa.objects.filter(accion="reiniciar_voto").exists())

    def test_reiniciar_voto_con_clave_invalida_no_cambia_nada(self):
        emitir_voto(
            self.estudiante.id,
            self.proceso,
            {self.tipo_a.id: self.lista_1.id, self.tipo_b.id: self.lista_3.id},
        )
        with self.settings(VOTE_KEY=Fernet.generate_key().decode()):
            with self.assertRaises(Exception):
                reiniciar_voto(self.estudiante.id, self.usuario)

        self.estudiante.refresh_from_db()
        self.assertTrue(self.estudiante.ha_votado)
        self.assertEqual(Voto.objects.filter(proceso=self.proceso).count(), 2)

    def test_inhabilitar_y_habilitar_estudiante(self):
        inhabilitar_estudiante(self.estudiante.id, self.usuario, motivo="Falta de requisitos")
        self.estudiante.refresh_from_db()
        self.assertTrue(self.estudiante.inhabilitado)
        self.assertFalse(self.estudiante.es_activo)

        estado, estudiante = validar_dni(self.estudiante.numero_documento, self.proceso)
        self.assertEqual(estado, EstadoElector.INHABILITADO)

        habilitar_estudiante(self.estudiante.id, self.usuario)
        self.estudiante.refresh_from_db()
        self.assertFalse(self.estudiante.inhabilitado)
        self.assertTrue(self.estudiante.es_activo)


class CierreProcesoPhase7Tests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="cierre7", password="secret", is_staff=True)
        self.proceso = ProcesoElectoral.objects.create(nombre="Proceso cierre", activo=True, cerrado=False)
        self.mesa = self.proceso.mesas.create(numero_mesa="Mesa 1", descripcion="Aula 1")
        self.tipo = TipoEleccion.objects.create(proceso=self.proceso, nombre="Alcalde", orden_aparicion=1)
        self.lista_1 = ListaCandidatura.objects.create(proceso=self.proceso, tipo_eleccion=self.tipo, nombre="Lista X")
        self.lista_2 = ListaCandidatura.objects.create(proceso=self.proceso, tipo_eleccion=self.tipo, nombre="Lista Y")

    def test_cerrar_proceso_marca_ausentes_y_destruye_vinculo(self):
        habil = Estudiante.objects.create(proceso=self.proceso, mesa=self.mesa, numero_documento="10000000", apellido_paterno="A", nombres="A")
        pending = Estudiante.objects.create(proceso=self.proceso, mesa=self.mesa, numero_documento="10000001", apellido_paterno="B", nombres="B")
        inhabil = Estudiante.objects.create(proceso=self.proceso, mesa=self.mesa, numero_documento="10000002", apellido_paterno="C", nombres="C", inhabilitado=True, es_activo=False)
        emitido = Estudiante.objects.create(proceso=self.proceso, mesa=self.mesa, numero_documento="10000003", apellido_paterno="D", nombres="D")
        emitido2 = Estudiante.objects.create(proceso=self.proceso, mesa=self.mesa, numero_documento="10000004", apellido_paterno="E", nombres="E")

        emitir_voto(habil.id, self.proceso, {self.tipo.id: self.lista_1.id})
        emitir_voto(emitido.id, self.proceso, {self.tipo.id: self.lista_2.id})
        emitir_voto(emitido2.id, self.proceso, {self.tipo.id: self.lista_1.id})

        acta = cerrar_proceso(self.proceso, self.usuario)

        self.assertEqual(acta.total_electores_habiles, 4)
        self.assertEqual(acta.total_votos_emitidos, 3)
        self.assertEqual(acta.total_ausentes, 1)
        self.assertTrue(self.proceso.cerrado)
        self.assertFalse(self.proceso.activo)
        self.assertTrue(ActaCierreProceso.objects.filter(proceso=self.proceso).exists())
        self.assertEqual(RegistroParticipacion.objects.filter(proceso=self.proceso).count(), 3)
        self.assertTrue(all(p.boleta_cifrada is None for p in RegistroParticipacion.objects.filter(proceso=self.proceso)))
        self.assertTrue(all(v.boleta_id is None for v in Voto.objects.filter(proceso=self.proceso)))
        self.assertEqual(self.proceso.estudiantes.filter(es_activo=True, inhabilitado=False, ha_votado=False).count(), 1)

    def test_cierre_no_contabiliza_inhabilitados(self):
        habil = Estudiante.objects.create(proceso=self.proceso, mesa=self.mesa, numero_documento="10000004", apellido_paterno="E", nombres="E")
        inhabil = Estudiante.objects.create(proceso=self.proceso, mesa=self.mesa, numero_documento="10000005", apellido_paterno="F", nombres="F", inhabilitado=True, es_activo=False)

        emitir_voto(habil.id, self.proceso, {self.tipo.id: self.lista_1.id})
        acta = cerrar_proceso(self.proceso, self.usuario)

        self.assertEqual(acta.total_electores_habiles, 1)
        self.assertEqual(acta.total_votos_emitidos, 1)
        self.assertEqual(acta.total_ausentes, 0)
        self.assertFalse(self.proceso.estudiantes.filter(numero_documento="10000005").first().es_activo)


class AsignarMesaGradoSeccionAdminTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(
            username="admin_gs", email="gs@example.com", password="secret"
        )
        self.proceso = ProcesoElectoral.objects.create(nombre="Proceso GS", activo=True, cerrado=False)
        self.mesa_a = self.proceso.mesas.create(numero_mesa="Mesa A")
        self.mesa_b = self.proceso.mesas.create(numero_mesa="Mesa B")
        self.gs = GradoSeccion.objects.get_or_create(
            nivel="primaria", grado="6to", seccion="X", defaults={"orden": 6},
        )[0]

    def _crear_estudiante(self, dni, mesa=None, **kwargs):
        return Estudiante.objects.create(
            proceso=self.proceso,
            mesa=mesa,
            grado_seccion=self.gs,
            numero_documento=dni,
            apellido_paterno="Test",
            nombres="Alumno",
            **kwargs,
        )

    def test_asignar_mesa_a_grado_seccion_ok(self):
        self._crear_estudiante("30000001", mesa=self.mesa_a)
        self._crear_estudiante("30000002", mesa=self.mesa_a)

        resultado = asignar_mesa_a_grado_seccion([self.gs], self.mesa_b, self.usuario)

        self.assertEqual(resultado["total"], 2)
        self.assertEqual(
            Estudiante.objects.filter(proceso=self.proceso, mesa=self.mesa_b).count(), 2
        )
        self.assertTrue(
            AccionAdministrativa.objects.filter(accion="asignar_mesa_a_grado_seccion").exists()
        )

    def test_asignar_mesa_bloquea_si_hay_votos(self):
        self._crear_estudiante("30000003", mesa=self.mesa_a)
        votante = self._crear_estudiante("30000004", mesa=self.mesa_a, ha_votado=True)

        with self.assertRaises(ErrorAsignacion):
            asignar_mesa_a_grado_seccion([self.gs], self.mesa_b, self.usuario)

        votante.refresh_from_db()
        self.assertEqual(votante.mesa, self.mesa_a)
        self.assertEqual(
            Estudiante.objects.filter(proceso=self.proceso, mesa=self.mesa_b).count(), 0
        )

    def test_asignar_mesa_solo_afecta_proceso_de_la_mesa(self):
        otro_proceso = ProcesoElectoral.objects.create(
            nombre="Proceso GS 2", activo=True, cerrado=False
        )
        mesa_otro = otro_proceso.mesas.create(numero_mesa="Mesa Z")

        propio = self._crear_estudiante("30000005", mesa=self.mesa_a)
        ajeno = Estudiante.objects.create(
            proceso=otro_proceso,
            mesa=mesa_otro,
            grado_seccion=self.gs,
            numero_documento="30000006",
            apellido_paterno="Ajeno",
            nombres="Alumno",
        )

        asignar_mesa_a_grado_seccion([self.gs], self.mesa_b, self.usuario)

        propio.refresh_from_db()
        ajeno.refresh_from_db()
        self.assertEqual(propio.mesa, self.mesa_b)
        self.assertEqual(ajeno.mesa, mesa_otro)

    def test_accion_y_vista_asignar_mesa(self):
        self.client.force_login(self.usuario)
        self._crear_estudiante("30000007", mesa=self.mesa_a)

        # Acción desde el changelist → redirige a la vista intermedia
        response = self.client.post(
            reverse("admin:voters_gradoseccion_changelist"),
            {
                "action": "asignar_a_mesa_action",
                "_selected_action": [str(self.gs.id)],
                "index": "0",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/asignar-a-mesa/", response.url)

        # GET de la vista intermedia
        response = self.client.get(
            reverse("admin:voters_gradoseccion_asignar_mesa"),
            {"ids": str(self.gs.id)},
        )
        self.assertEqual(response.status_code, 200)

        # POST del formulario → asigna la mesa
        response = self.client.post(
            reverse("admin:voters_gradoseccion_asignar_mesa"),
            {"ids": str(self.gs.id), "mesa_destino": self.mesa_b.id},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            Estudiante.objects.filter(proceso=self.proceso, mesa=self.mesa_b).count(), 1
        )


class PadronPdfTests(TestCase):
    """Reporte de padrón por mesas (PDF): selector + vistas xhtml2pdf."""

    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(
            username="pdfadmin", email="pdf@example.com", password="pdf123"
        )
        self.proceso = ProcesoElectoral.objects.create(nombre="Proceso PDF", activo=True, cerrado=False)
        self.mesa_1 = self.proceso.mesas.create(numero_mesa="Mesa 1", descripcion="Aula 101")
        self.mesa_2 = self.proceso.mesas.create(numero_mesa="Mesa 2", descripcion="Aula 102")
        self.gs_3a = GradoSeccion.objects.get_or_create(
            nivel="secundaria", grado="3ro", seccion="A", defaults={"orden": 3},
        )[0]
        self.gs_1c = GradoSeccion.objects.get_or_create(
            nivel="secundaria", grado="1ro", seccion="C", defaults={"orden": 1},
        )[0]

        # Mesa 1: hábiles ordenados grado→sección→apellidos + un inhabilitado (excluido)
        self.m1_a = Estudiante.objects.create(
            proceso=self.proceso, mesa=self.mesa_1, grado_seccion=self.gs_3a,
            numero_documento="10000001", apellido_paterno="Zeta", apellido_materno="A", nombres="Ana",
        )
        self.m1_b = Estudiante.objects.create(
            proceso=self.proceso, mesa=self.mesa_1, grado_seccion=self.gs_1c,
            numero_documento="10000002", apellido_paterno="Alfa", apellido_materno="B", nombres="Ben",
        )
        Estudiante.objects.create(
            proceso=self.proceso, mesa=self.mesa_1, grado_seccion=self.gs_3a,
            numero_documento="10000003", apellido_paterno="No", apellido_materno="Vota",
            nombres="Descarte", inhabilitado=True,
        )
        # Mesa 2: un hábil
        Estudiante.objects.create(
            proceso=self.proceso, mesa=self.mesa_2, grado_seccion=self.gs_1c,
            numero_documento="10000004", apellido_paterno="Caro", apellido_materno="D", nombres="Dina",
        )
        # Sin mesa: un hábil + un inhabilitado (excluido)
        Estudiante.objects.create(
            proceso=self.proceso, grado_seccion=self.gs_3a,
            numero_documento="10000005", apellido_paterno="Eco", apellido_materno="F", nombres="Eva",
        )
        Estudiante.objects.create(
            proceso=self.proceso, grado_seccion=self.gs_3a,
            numero_documento="10000006", apellido_paterno="Sin", apellido_materno="Mesa",
            nombres="X", inhabilitado=True,
        )
        self.client.force_login(self.usuario)

    def test_selector_agrupa_mesas_filtra_habiles_y_ordena(self):
        datos = padron_por_mesas(self.proceso)

        self.assertEqual(datos["estado"], "todas")
        self.assertEqual(datos["resumen"]["mesas"], 2)
        self.assertEqual(datos["resumen"]["habiles"], 4)
        self.assertEqual(datos["resumen"]["sin_mesa"], 1)

        # Mesa 1 ordenada por grado→sección→apellidos (1ro C antes que 3ro A)
        filas_m1 = [f["dni"] for f in datos["mesas"][0]["filas"]]
        self.assertEqual(filas_m1, ["10000002", "10000001"])
        self.assertEqual(datos["mesas"][0]["habiles"], 2)

        # Mesa 2
        self.assertEqual(datos["mesas"][1]["habiles"], 1)

        # Sin mesa: solo hábiles
        self.assertEqual([f["dni"] for f in datos["sin_mesa"]], ["10000005"])

    def test_selector_solo_una_mesa(self):
        datos = padron_por_mesas(self.proceso, mesa_id=self.mesa_1.id)
        self.assertEqual(datos["estado"], "mesa")
        self.assertEqual(len(datos["mesas"]), 1)
        self.assertEqual(datos["mesas"][0]["numero_mesa"], "Mesa 1")
        self.assertEqual(datos["sin_mesa"], [])

    def test_selector_solo_sin_mesa(self):
        datos = padron_por_mesas(self.proceso, solo_sin_mesa=True)
        self.assertEqual(datos["estado"], "sin_mesa")
        self.assertEqual(datos["mesas"], [])
        self.assertEqual([f["dni"] for f in datos["sin_mesa"]], ["10000005"])

    def test_vista_pdf_todas_y_variantes(self):
        try:
            from xhtml2pdf import pisa  # noqa: F401
        except ImportError:
            self.skipTest("xhtml2pdf no disponible")

        r = self.client.get(reverse("padron_pdf"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertTrue(r.content.startswith(b"%PDF-"))
        self.assertIn("Padron_Por_Mesas", r["Content-Disposition"])

        r = self.client.get(reverse("padron_pdf"), {"mesa": self.mesa_1.id})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertTrue(r.content.startswith(b"%PDF-"))
        self.assertIn("mesa", r["Content-Disposition"])

        r = self.client.get(reverse("padron_pdf"), {"estado": "sin_mesa"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertTrue(r.content.startswith(b"%PDF-"))
        self.assertIn("sin_mesa", r["Content-Disposition"])

    def test_vista_pdf_sin_proceso_activo_devuelve_404(self):
        self.proceso.activo = False
        self.proceso.save(update_fields=["activo"])
        r = self.client.get(reverse("padron_pdf"))
        self.assertEqual(r.status_code, 404)


class ReportesModalRenderTests(TestCase):
    """Las páginas admin que incluyen el popup de reportes deben renderizar."""

    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(
            username="renderadmin", email="r@example.com", password="r123"
        )
        self.proceso = ProcesoElectoral.objects.create(nombre="Proceso render", activo=True, cerrado=False)
        self.mesa = self.proceso.mesas.create(numero_mesa="Mesa 1", descripcion="Aula 101")
        self.tipo = TipoEleccion.objects.create(proceso=self.proceso, nombre="Alcalde", orden_aparicion=1)
        self.lista = ListaCandidatura.objects.create(
            proceso=self.proceso, tipo_eleccion=self.tipo, nombre="Lista A"
        )
        Estudiante.objects.create(
            proceso=self.proceso, mesa=self.mesa, numero_documento="20000001",
            apellido_paterno="A", apellido_materno="B", nombres="C",
        )
        self.client.force_login(self.usuario)

    def test_dashboard_mesas_y_auditoria_muestran_popup(self):
        for url in (reverse("dashboard"), reverse("mesas_lista"), reverse("auditoria_padron")):
            with self.subTest(url=url):
                r = self.client.get(url)
                self.assertEqual(r.status_code, 200)
                self.assertContains(r, "modalReportes")
                self.assertContains(r, "🖨️ Reportes")
