from django import forms
from django.contrib import admin, messages
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.template.loader import get_template
from django.urls import path, reverse
from django.utils.html import format_html

from apps.auditoria.services import registrar
from apps.voting.services.asignar_mesa import (
    ErrorAsignacion,
    asignar_mesa_a_grado_seccion,
)
from apps.voting.services.limpiar_mesa import (
    ErrorLimpiarMesa,
    limpiar_mesa_estudiantes,
)
from apps.voting.services.toggle_estudiante import (
    ErrorAccion,
    habilitar_estudiante,
    inhabilitar_estudiante,
)
from apps.voting.services.reiniciar_votacion import ErrorReinicio, reiniciar_votacion_proceso
from apps.voting.models import ActaCierreProceso
from .models import Estudiante, GradoSeccion, MesaDeVotacion, ProcesoElectoral

try:
    from xhtml2pdf import pisa
except ImportError:  # pragma: no cover
    pisa = None


# ============================================================
#  Formulario para elegir la mesa destino
# ============================================================
class MoverAMesaForm(forms.Form):
    ids = forms.CharField(widget=forms.HiddenInput())

    mesa_destino = forms.ModelChoiceField(
        queryset=MesaDeVotacion.objects.none(),
        label="Mesa destino",
        empty_label="— Seleccione una mesa —",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, proceso=None, **kwargs):
        super().__init__(*args, **kwargs)
        if proceso is not None:
            self.fields["mesa_destino"].queryset = (
                MesaDeVotacion.objects
                .filter(proceso=proceso, es_activo=True)
                .order_by("numero_mesa")
            )

    def clean(self):
        data = super().clean()
        mesa = data.get("mesa_destino")
        if mesa and not mesa.es_activo:
            raise forms.ValidationError("La mesa seleccionada no está activa.")
        return data


class MesaConProcesoChoiceField(forms.ModelChoiceField):
    """Muestra la mesa junto a su proceso para desambiguar entre procesos."""

    def label_from_instance(self, obj):
        return f"{obj.proceso.nombre} · {obj.numero_mesa}"


class AsignarMesaGradoSeccionForm(forms.Form):
    ids = forms.CharField(widget=forms.HiddenInput())

    mesa_destino = MesaConProcesoChoiceField(
        queryset=MesaDeVotacion.objects.none(),
        label="Mesa destino",
        empty_label="— Seleccione una mesa —",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["mesa_destino"].queryset = (
            MesaDeVotacion.objects
            .filter(es_activo=True, proceso__cerrado=False)
            .select_related("proceso")
            .order_by("proceso__nombre", "numero_mesa")
        )

    def clean(self):
        data = super().clean()
        mesa = data.get("mesa_destino")
        if mesa and not mesa.es_activo:
            raise forms.ValidationError("La mesa seleccionada no está activa.")
        return data


# ============================================================
#  Admins
# ============================================================

class ProcesoElectoralForm(forms.ModelForm):
    """Formulario con validación extra para el logo."""

    class Meta:
        model = ProcesoElectoral
        fields = "__all__"

    def clean_logo(self):
        logo = self.cleaned_data.get("logo")
        if logo and hasattr(logo, "size"):
            if logo.size > 5 * 1024 * 1024:  # 5 MB
                raise forms.ValidationError(
                    "El logo no puede superar los 5 MB."
                )
        return logo
    
@admin.register(ProcesoElectoral)
class ProcesoElectoralAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "nombre_institucion",
        "activo",
        "cerrado",
        "votacion_iniciada",
        "votacion_pausada",
        "habilitar_voto_nulo",
        "habilitar_voto_invalido",
        "fecha_inicio",
        "fecha_cierre",
    )
    list_filter = ("activo", "cerrado", "votacion_iniciada", "votacion_pausada", "habilitar_voto_nulo", "habilitar_voto_invalido")
    search_fields = ("nombre",)
    actions = ["reiniciar_votacion_action", "descargar_acta_cierre_action"]
    fieldsets = (
        ("Identidad del proceso", {
            "fields": ("nombre", "nombre_institucion", "logo", "logo_preview"),
        }),
        ("Control del proceso", {
            "fields": (
                "activo",
                "cerrado",
                "votacion_iniciada",
                "votacion_pausada",
                "fecha_inicio",
                "fecha_cierre",
            ),
        }),
        ("Opciones de votación", {
            "fields": ("habilitar_voto_nulo", "habilitar_voto_invalido"),
        }),
    )

    readonly_fields = ("logo_preview", "votacion_iniciada", "votacion_pausada")
    # ---------- Vista previa del logo en el formulario ----------
    @admin.display(description="Vista previa")
    def logo_preview(self, obj):
        if not obj or not obj.logo:
            return "—"
        return format_html(
            '<img src="{}" alt="Logo" '
            'style="max-height:120px;max-width:320px;'
            'border:1px solid #ddd;border-radius:8px;padding:6px;background:#fff;" />',
            obj.logo.url,
        )

    # ---------- Miniatura en el listado ----------
    @admin.display(description="Logo")
    def logo_thumb(self, obj):
        if not obj.logo:
            return "—"
        return format_html(
            '<img src="{}" alt="Logo" '
            'style="height:32px;width:auto;'
            'border-radius:4px;border:1px solid #eee;" />',
            obj.logo.url,
        )

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<int:proceso_id>/reiniciar-votacion/",
                self.admin_site.admin_view(self.reiniciar_votacion_view),
                name="voters_procesoelectoral_reiniciar_votacion",
            ),
            path(
                "<int:proceso_id>/acta-pdf/",
                self.admin_site.admin_view(self.acta_pdf_admin_view),
                name="voters_procesoelectoral_acta_pdf",
            ),
        ]
        return custom + urls

    # ---------- Acción desde el changelist ----------
    @admin.action(description="♻️ Reiniciar votación (borra todos los votos)")
    def reiniciar_votacion_action(self, request, queryset):
        # Regla: solo 1 proceso seleccionado
        if queryset.count() != 1:
            self.message_user(
                request,
                "Seleccione exactamente UN proceso electoral.",
                level=messages.ERROR,
            )
            return

        proceso = queryset.first()

        # Regla: solo procesos ACTIVOS y no cerrados
        if proceso.cerrado or not proceso.activo:
            self.message_user(
                request,
                f"⚠ El proceso «{proceso.nombre}» no está activo o ya fue cerrado. "
                f"Solo se puede reiniciar la votación en procesos activos.",
                level=messages.ERROR,
            )
            return

        url = reverse(
            "admin:voters_procesoelectoral_reiniciar_votacion",
            args=[proceso.id],
        )
        return HttpResponseRedirect(url)

    # ---------- Vista intermedia de confirmación ----------
    def reiniciar_votacion_view(self, request, proceso_id):
        proceso = self.get_object(request, proceso_id)
        if proceso is None:
            self.message_user(
                request,
                "El proceso no existe.",
                level=messages.ERROR,
            )
            return HttpResponseRedirect(
                reverse("admin:voters_procesoelectoral_changelist")
            )

        # Revalidar por si el estado cambió entre el listado y esta vista
        if proceso.cerrado or not proceso.activo:
            self.message_user(
                request,
                f"⚠ El proceso «{proceso.nombre}» no está activo o ya fue cerrado.",
                level=messages.ERROR,
            )
            return HttpResponseRedirect(
                reverse("admin:voters_procesoelectoral_changelist")
            )

        # Métricas para mostrar en la confirmación
        votos_actuales = proceso.votos.count()
        participaciones = proceso.participaciones.count()

        if request.method == "POST":
            motivo = (request.POST.get("motivo") or "").strip()
            try:
                resumen = reiniciar_votacion_proceso(
                    proceso,
                    request.user,
                    motivo=motivo,
                )
                extra = " | Acta previa eliminada" if resumen["acta_eliminada"] else ""
                self.message_user(
                    request,
                    f"♻ Votación reiniciada. "
                    f"Votos eliminados: {resumen['votos_eliminados']} | "
                    f"Participaciones: {resumen['participaciones_eliminadas']} | "
                    f"Estudiantes reseteados: {resumen['estudiantes_reseteados']}{extra}.",
                    level=messages.SUCCESS,
                )
            except ErrorReinicio as exc:
                self.message_user(request, f"✖ {exc}", level=messages.ERROR)
            except Exception as exc:  # noqa: BLE001
                self.message_user(
                    request,
                    f"✖ Error inesperado: {exc}",
                    level=messages.ERROR,
                )
            return HttpResponseRedirect(
                reverse("admin:voters_procesoelectoral_changelist")
            )

        tiene_acta = ActaCierreProceso.objects.filter(proceso=proceso).exists()
        context = {
            **self.admin_site.each_context(request),
            "title": "Reiniciar votación del proceso",
            "opts": self.model._meta,
            "proceso": proceso,
            "votos_actuales": votos_actuales,
            "participaciones": participaciones,
            "app_label": self.model._meta.app_label,
            "tiene_acta": tiene_acta,
        }
        return render(
            request,
            "admin/voters/procesoelectoral/reiniciar_votacion.html",
            context,
        )

    # ---------- Acción: Acta de Cierre y Resultados Oficiales (PDF) ----------
    @admin.action(description="📄 Acta de Cierre y Resultados Oficiales (PDF)")
    def descargar_acta_cierre_action(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(
                request,
                "Seleccione exactamente UN proceso electoral.",
                level=messages.ERROR,
            )
            return

        proceso = queryset.first()
        acta = ActaCierreProceso.objects.filter(proceso=proceso).first()
        if not acta:
            self.message_user(
                request,
                f"⚠ El proceso «{proceso.nombre}» aún no tiene un acta de cierre. "
                "Cierre el proceso electoral para generar el acta y luego "
                "puede descargar el PDF desde esta opción.",
                level=messages.ERROR,
            )
            return

        url = reverse(
            "admin:voters_procesoelectoral_acta_pdf",
            args=[proceso.id],
        )
        return HttpResponseRedirect(url)

    def acta_pdf_admin_view(self, request, proceso_id):
        """Genera y devuelve el PDF del acta de cierre del proceso."""
        proceso = self.get_object(request, proceso_id)
        if proceso is None:
            self.message_user(
                request,
                "El proceso no existe.",
                level=messages.ERROR,
            )
            return HttpResponseRedirect(
                reverse("admin:voters_procesoelectoral_changelist")
            )

        acta = ActaCierreProceso.objects.filter(proceso=proceso).first()
        if not acta:
            self.message_user(
                request,
                f"⚠ El proceso «{proceso.nombre}» no tiene un acta de cierre.",
                level=messages.ERROR,
            )
            return HttpResponseRedirect(
                reverse("admin:voters_procesoelectoral_changelist")
            )

        if pisa is None:
            return HttpResponse(
                "Falta la librería xhtml2pdf. Ejecute: pip install xhtml2pdf",
                status=500,
            )

        template = get_template("voting/acta_pdf_template.html")
        html = template.render({"acta": acta, "proceso": proceso})

        response = HttpResponse(content_type="application/pdf")
        filename = f"Acta_Cierre_{proceso.id}_{acta.id}.pdf"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        # Reutiliza el link_callback del módulo de cierre para imágenes/estáticos
        from apps.voting.views.cierre import _link_callback

        pisa_status = pisa.CreatePDF(
            html,
            dest=response,
            encoding="utf-8",
            link_callback=_link_callback,
        )
        if pisa_status.err:
            return HttpResponse(
                f"<h1>Error al generar el PDF</h1><pre>{html}</pre>",
                status=500,
                content_type="text/html",
            )
        return response


@admin.register(MesaDeVotacion)
class MesaDeVotacionAdmin(admin.ModelAdmin):
    list_display = ("proceso", "numero_mesa", "descripcion", "es_activo")
    list_filter = ("proceso", "es_activo")
    search_fields = ("numero_mesa", "descripcion")


@admin.register(GradoSeccion)
class GradoSeccionAdmin(admin.ModelAdmin):
    list_display = (
        "nivel",
        "grado",
        "seccion",
        "orden",
        "es_activo",
        "total_estudiantes",
    )
    list_filter = ("nivel", "grado", "es_activo")
    search_fields = ("nivel", "grado", "seccion")
    list_editable = ("orden", "es_activo")
    ordering = ("nivel", "orden", "grado", "seccion")
    actions = ["asignar_a_mesa_action"]

    @admin.display(description="Estudiantes")
    def total_estudiantes(self, obj):
        return obj.estudiantes.count()

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "asignar-a-mesa/",
                self.admin_site.admin_view(self.asignar_mesa_view),
                name="voters_gradoseccion_asignar_mesa",
            ),
        ]
        return custom + urls

    # ---------- ASIGNAR A MESA ----------
    @admin.action(description="📦 Asignar grado/sección a una mesa")
    def asignar_a_mesa_action(self, request, queryset):
        if not queryset.exists():
            self.message_user(
                request,
                "Seleccione al menos un grado/sección.",
                level=messages.WARNING,
            )
            return

        ids = ",".join(str(i) for i in queryset.values_list("id", flat=True))
        url = reverse("admin:voters_gradoseccion_asignar_mesa") + f"?ids={ids}"
        return HttpResponseRedirect(url)

    def asignar_mesa_view(self, request):
        ids_raw = request.POST.get("ids") or request.GET.get("ids") or ""
        ids = [int(x) for x in ids_raw.split(",") if x.strip().isdigit()]

        grado_secciones = list(
            GradoSeccion.objects.filter(id__in=ids).order_by("nivel", "orden", "grado", "seccion")
        )
        if not grado_secciones:
            self.message_user(
                request,
                "No hay grados/secciones seleccionados para asignar.",
                level=messages.WARNING,
            )
            return HttpResponseRedirect(reverse("admin:voters_gradoseccion_changelist"))

        if not AsignarMesaGradoSeccionForm().fields["mesa_destino"].queryset.exists():
            self.message_user(
                request,
                "No hay mesas activas disponibles. Cree mesas en un proceso abierto primero.",
                level=messages.ERROR,
            )
            return HttpResponseRedirect(reverse("admin:voters_gradoseccion_changelist"))

        # Resumen informativo (global) por grado/sección.
        resumen = []
        hay_votos = False
        for gs in grado_secciones:
            total = gs.estudiantes.count()
            votaron = gs.estudiantes.filter(ha_votado=True).count()
            hay_votos = hay_votos or bool(votaron)
            resumen.append({"gs": gs, "total": total, "votaron": votaron})

        if request.method == "POST":
            form = AsignarMesaGradoSeccionForm(request.POST)
            if form.is_valid():
                mesa_destino = form.cleaned_data["mesa_destino"]
                try:
                    resultado = asignar_mesa_a_grado_seccion(
                        grado_secciones,
                        mesa_destino,
                        request.user,
                        ip=request.META.get("REMOTE_ADDR"),
                    )
                    self.message_user(
                        request,
                        f"✔ {resultado['total']} estudiante(s) del grado/sección "
                        f"movido(s) a {resultado['mesa']} (proceso «{resultado['proceso']}»).",
                        level=messages.SUCCESS,
                    )
                except ErrorAsignacion as exc:
                    self.message_user(request, f"✖ {exc}", level=messages.ERROR)
                return HttpResponseRedirect(reverse("admin:voters_gradoseccion_changelist"))
        else:
            form = AsignarMesaGradoSeccionForm(
                initial={"ids": ",".join(str(gs.id) for gs in grado_secciones)},
            )

        context = {
            **self.admin_site.each_context(request),
            "title": "Asignar grado/sección a una mesa",
            "opts": self.model._meta,
            "form": form,
            "resumen": resumen,
            "hay_votos": hay_votos,
            "app_label": self.model._meta.app_label,
        }
        return render(request, "admin/voters/gradoseccion/asignar_mesa.html", context)


@admin.register(Estudiante)
class EstudianteAdmin(admin.ModelAdmin):
    list_display = (
        "numero_documento",
        "apellido_paterno",
        "apellido_materno",
        "nombres",
        "proceso",
        "mesa",
        "grado_seccion",
        "es_activo",
        "inhabilitado",
        "ha_votado",
    )
    list_filter = ("proceso", "mesa", "grado_seccion__grado", "grado_seccion__seccion", "es_activo", "inhabilitado", "ha_votado")
    search_fields = ("numero_documento", "apellido_paterno")
    list_select_related = ("proceso", "mesa", "grado_seccion")
    fields = (
        "proceso",
        "mesa",
        "grado_seccion",
        "numero_documento",
        "apellido_paterno",
        "apellido_materno",
        "nombres",
        "es_activo",
        "inhabilitado",
        "ha_votado",
        "fecha_ausentismo",
        "fecha_inhabilitacion",
    )

    # ----------------- Acciones -----------------
    actions = [
        "mover_a_mesa_action",
        "inhabilitar_action",
        "habilitar_action",
        "limpiar_mesa_action",
    ]

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "mover-a-mesa/",
                self.admin_site.admin_view(self.mover_a_mesa_view),
                name="voters_estudiante_mover_a_mesa",
            ),
        ]
        return custom + urls

    # ---------- MOVER A MESA ----------
    @admin.action(description="📦 Mover seleccionados a otra mesa")
    def mover_a_mesa_action(self, request, queryset):
        procesos = set(queryset.values_list("proceso_id", flat=True))
        if len(procesos) != 1:
            self.message_user(
                request,
                "Seleccione estudiantes de un mismo proceso electoral.",
                level=messages.ERROR,
            )
            return

        votaron = queryset.filter(ha_votado=True).count()
        if votaron:
            self.message_user(
                request,
                f"No se puede mover a {votaron} estudiante(s) que ya emitieron su voto.",
                level=messages.ERROR,
            )
            return

        ids = ",".join(str(i) for i in queryset.values_list("id", flat=True))
        url = reverse("admin:voters_estudiante_mover_a_mesa") + f"?ids={ids}"
        return HttpResponseRedirect(url)

    def mover_a_mesa_view(self, request):
        ids_raw = request.POST.get("ids") or request.GET.get("ids") or ""
        ids = [int(x) for x in ids_raw.split(",") if x.strip().isdigit()]
        if not ids:
            self.message_user(
                request,
                "No hay estudiantes seleccionados para mover.",
                level=messages.WARNING,
            )
            return HttpResponseRedirect(reverse("admin:voters_estudiante_changelist"))

        queryset = (
            Estudiante.objects
            .filter(id__in=ids)
            .select_related("proceso", "mesa", "grado_seccion")
        )
        if not queryset.exists():
            self.message_user(
                request,
                "Los estudiantes seleccionados ya no existen.",
                level=messages.WARNING,
            )
            return HttpResponseRedirect(reverse("admin:voters_estudiante_changelist"))

        proceso = queryset.first().proceso

        if request.method == "POST":
            form = MoverAMesaForm(request.POST, proceso=proceso)
            if form.is_valid():
                mesa_destino = form.cleaned_data["mesa_destino"]
                total = queryset.update(mesa=mesa_destino)

                registrar(
                    request.user,
                    "mover_estudiantes_mesa",
                    detalle={
                        "total": total,
                        "mesa_destino_id": mesa_destino.id,
                        "mesa_destino": str(mesa_destino),
                        "estudiantes_ids": ids,
                    },
                    entidad="MesaDeVotacion",
                    entidad_id=mesa_destino.id,
                    ip=request.META.get("REMOTE_ADDR"),
                )

                self.message_user(
                    request,
                    f"✔ {total} estudiante(s) movido(s) a {mesa_destino}.",
                    level=messages.SUCCESS,
                )
                return HttpResponseRedirect(reverse("admin:voters_estudiante_changelist"))
        else:
            form = MoverAMesaForm(
                initial={"ids": ",".join(str(i) for i in ids)},
                proceso=proceso,
            )

        context = {
            **self.admin_site.each_context(request),
            "title": "Mover estudiantes a otra mesa",
            "opts": self.model._meta,
            "form": form,
            "queryset": queryset,
            "proceso": proceso,
            "app_label": self.model._meta.app_label,
        }
        return render(request, "admin/voters/estudiante/mover_a_mesa.html", context)

    # ---------- INHABILITAR ----------
    @admin.action(description="🚫 Inhabilitar seleccionados")
    def inhabilitar_action(self, request, queryset):
        ok, fallidos = 0, 0
        for est in queryset:
            try:
                inhabilitar_estudiante(
                    est.id,
                    request.user,
                    motivo="Inhabilitación masiva desde el admin",
                )
                ok += 1
            except ErrorAccion:
                fallidos += 1

        if ok:
            self.message_user(
                request,
                f"✔ {ok} estudiante(s) inhabilitado(s).",
                level=messages.SUCCESS,
            )
        if fallidos:
            self.message_user(
                request,
                f"⚠ {fallidos} estudiante(s) no pudieron inhabilitarse "
                f"(ya votaron o tienen ausentismo registrado).",
                level=messages.WARNING,
            )

    # ---------- HABILITAR ----------
    @admin.action(description="✅ Habilitar seleccionados")
    def habilitar_action(self, request, queryset):
        ok, fallidos = 0, 0
        for est in queryset:
            try:
                habilitar_estudiante(est.id, request.user)
                ok += 1
            except ErrorAccion:
                fallidos += 1

        if ok:
            self.message_user(
                request,
                f"✔ {ok} estudiante(s) habilitado(s).",
                level=messages.SUCCESS,
            )
        if fallidos:
            self.message_user(
                request,
                f"⚠ {fallidos} estudiante(s) no estaban inhabilitados "
                f"o no pudieron reactivarse.",
                level=messages.WARNING,
            )

    # ---------- LIMPIAR MESA ----------
    @admin.action(description="🧹 Limpiar Mesa de votación")
    def limpiar_mesa_action(self, request, queryset):
        """Quita la asignación de mesa a los estudiantes seleccionados.

        - No afecta a quienes ya emitieron su voto (serán omitidos).
        - Registra la acción en la auditoría del proceso de cada afectado.
        """
        try:
            resumen = limpiar_mesa_estudiantes(
                queryset,
                request.user,
                motivo="Limpieza masiva desde el admin",
                ip=request.META.get("REMOTE_ADDR"),
            )
        except ErrorLimpiarMesa as exc:
            self.message_user(request, str(exc), level=messages.ERROR)
            return

        if resumen["omitidos_por_voto"]:
            self.message_user(
                request,
                f"⚠ {resumen['omitidos_por_voto']} estudiante(s) omitido(s) "
                f"porque ya emitieron su voto; no se les puede limpiar la mesa.",
                level=messages.WARNING,
            )
        if resumen["actualizados"]:
            self.message_user(
                request,
                f"✔ Mesa limpiada a {resumen['actualizados']} estudiante(s).",
                level=messages.SUCCESS,
            )
        elif not resumen["ya_sin_mesa"]:
            self.message_user(
                request,
                "No se limpió ninguna mesa (selección vacía).",
                level=messages.INFO,
            )
        elif not resumen["omitidos_por_voto"]:
            self.message_user(
                request,
                "Los estudiantes seleccionados ya no tenían mesa asignada.",
                level=messages.INFO,
            )
