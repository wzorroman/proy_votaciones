from django.urls import path

from apps.voting.views.cierre import (
    acta_detalle,
    cerrar_proceso_view,
    generar_acta_pdf_view,
    generar_padron_pdf_view,
)
from apps.voting.views.dashboard import (
    dashboard_live_json,
    dashboard_view,
    iniciar_votacion_view,
    pausar_votacion_view,
    reanudar_votacion_view,
)
from apps.voting.views.kiosk import kiosk_espera, kiosk_exito, kiosk_wizard, kiosk_wizard_paso
from apps.voting.views.auditoria import (
    auditoria_padron_view, reiniciar_voto_estudiante, cambiar_estado_habilitacion_estudiante
)
from apps.voting.views.mesas import mesas_lista_view

urlpatterns = [
    path("", kiosk_espera, name="kiosk_espera"),
    path("wizard/", kiosk_wizard, name="kiosk_wizard"),
    path("wizard/paso/", kiosk_wizard_paso, name="kiosk_wizard_paso"),
    path("exito/", kiosk_exito, name="kiosk_exito"),
    path("panel/", dashboard_view, name="dashboard"),
    path("panel/live.json", dashboard_live_json, name="dashboard_live_json"),
    path("panel/iniciar/", iniciar_votacion_view, name="iniciar_votacion"),
    path("panel/pausar/", pausar_votacion_view, name="pausar_votacion"),
    path("panel/reanudar/", reanudar_votacion_view, name="reanudar_votacion"),
    path("panel/cerrar/", cerrar_proceso_view, name="cerrar_proceso"),
    path("panel/acta/<int:acta_id>/", acta_detalle, name="acta_detalle"),
    # Auditoría de padrón
    path("panel/auditoria/", auditoria_padron_view, name="auditoria_padron"),
    path(
        "panel/auditoria/<int:estudiante_id>/reiniciar/",
        reiniciar_voto_estudiante,
        name="reiniciar_voto",
    ),
    path(
        "panel/auditoria/<int:estudiante_id>/toggle/",
        cambiar_estado_habilitacion_estudiante,
        name="toggle_estudiante",
    ),
    path("panel/mesas/", mesas_lista_view, name="mesas_lista"),
    path(
        "panel/acta/<int:acta_id>/pdf/",
        generar_acta_pdf_view,
        name="acta_pdf",   # <-- NUEVO
    ),
    path(
        "panel/padron/pdf/",
        generar_padron_pdf_view,
        name="padron_pdf",
    ),
]
