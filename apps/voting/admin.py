from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from .models import ActaCierreProceso, RegistroParticipacion, Voto


@admin.register(Voto)
class VotoAdmin(admin.ModelAdmin):
    list_display = ("proceso", "tipo_eleccion", "lista", "boleta_id")
    list_filter = ("proceso", "tipo_eleccion")
    search_fields = ("boleta_id", "lista__nombre")


@admin.register(RegistroParticipacion)
class RegistroParticipacionAdmin(admin.ModelAdmin):
    list_display = ("proceso", "estudiante", "hash_integridad", "boleta_cifrada")
    list_filter = ("proceso",)
    search_fields = ("estudiante__numero_documento", "hash_integridad")


@admin.register(ActaCierreProceso)
class ActaCierreProcesoAdmin(admin.ModelAdmin):
    list_display = (
        "proceso",
        "total_electores_habiles",
        "total_votos_emitidos",
        "total_ausentes",
        "fecha_cierre_oficial",
        "descargar_pdf",
    )
    list_filter = ("proceso",)
    search_fields = ("proceso__nombre",)

    @admin.display(description="PDF")
    def descargar_pdf(self, obj):
        url = reverse("acta_pdf", args=[obj.id])
        return format_html(
            '<a class="button" href="{}" target="_blank">📥 Descargar</a>',
            url,
        )