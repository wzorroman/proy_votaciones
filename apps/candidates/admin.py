from django import forms
from django.contrib import admin
from django.utils.html import format_html

from .models import ListaCandidatura, TipoEleccion


# ============================================================
#  Formulario con validación de tamaño
# ============================================================
class ListaCandidaturaForm(forms.ModelForm):
    class Meta:
        model = ListaCandidatura
        fields = "__all__"

    def clean_foto(self):
        foto = self.cleaned_data.get("foto")
        if foto and hasattr(foto, "size"):
            if foto.size > 3 * 1024 * 1024:  # 3 MB
                raise forms.ValidationError(
                    "La imagen no puede superar los 3 MB."
                )
        return foto


# ============================================================
#  Inline de listas dentro del TipoEleccion
# ============================================================
class ListaCandidaturaInline(admin.TabularInline):
    model = ListaCandidatura
    form = ListaCandidaturaForm
    extra = 1
    fields = ("nombre", "descripcion", "foto", "foto_thumb_inline", "es_activo")
    readonly_fields = ("foto_thumb_inline",)
    exclude = ("proceso",)

    @admin.display(description="Vista previa")
    def foto_thumb_inline(self, obj):
        if not obj or not obj.foto:
            return "—"
        return format_html(
            '<img src="{}" alt="Foto" '
            'style="height:48px;width:48px;object-fit:cover;'
            'border-radius:6px;border:1px solid #eee;" />',
            obj.foto.url,
        )


# ============================================================
#  Admin: TipoEleccion
# ============================================================
@admin.register(TipoEleccion)
class TipoEleccionAdmin(admin.ModelAdmin):
    list_display = ("proceso", "nombre", "orden_aparicion", "es_activo")
    list_filter = ("proceso", "es_activo")
    search_fields = ("nombre",)
    inlines = [ListaCandidaturaInline]

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for obj in instances:
            if not obj.proceso_id:
                obj.proceso = form.instance.proceso
            obj.save()
        formset.save_m2m()


# ============================================================
#  Admin: ListaCandidatura (vista directa)
# ============================================================
@admin.register(ListaCandidatura)
class ListaCandidaturaAdmin(admin.ModelAdmin):
    form = ListaCandidaturaForm

    list_display = (
        "id",
        "proceso",
        "tipo_eleccion",
        "nombre",
        "foto_thumb",
        "es_activo",
    )
    list_filter = ("proceso", "tipo_eleccion", "es_activo")
    search_fields = ("nombre", "descripcion")

    fieldsets = (
        ("Identificación", {
            "fields": ("proceso", "tipo_eleccion", "nombre", "descripcion"),
        }),
        ("Imagen", {
            "fields": ("foto", "foto_preview"),
        }),
        ("Estado", {
            "fields": ("es_activo",),
        }),
    )
    readonly_fields = ("foto_preview",)

    @admin.display(description="Foto")
    def foto_thumb(self, obj):
        if not obj.foto:
            return "—"
        return format_html(
            '<img src="{}" alt="Foto" '
            'style="height:36px;width:36px;object-fit:cover;'
            'border-radius:6px;border:1px solid #eee;" />',
            obj.foto.url,
        )

    @admin.display(description="Vista previa")
    def foto_preview(self, obj):
        if not obj or not obj.foto:
            return "—"
        return format_html(
            '<img src="{}" alt="Foto" '
            'style="max-height:180px;max-width:180px;object-fit:cover;'
            'border-radius:12px;border:1px solid #ddd;padding:4px;'
            'background:#fff;" />',
            obj.foto.url,
        )
    