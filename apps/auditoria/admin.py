from django.contrib import admin

from .models import AccionAdministrativa


@admin.register(AccionAdministrativa)
class AccionAdministrativaAdmin(admin.ModelAdmin):
    list_display = ("accion", "usuario", "entidad", "entidad_id", "creado_en")
    list_filter = ("accion", "usuario")
    search_fields = ("accion", "entidad", "usuario__username")
    readonly_fields = ("creado_en", "actualizado_en")
