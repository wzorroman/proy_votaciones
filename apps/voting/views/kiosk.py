from django.shortcuts import redirect, render

from apps.candidates.models import ListaCandidatura, TipoEleccion
from apps.voters.models import Estudiante, ProcesoElectoral
from apps.voters.selectors import proceso_activo
from apps.voting.services.emitir_voto import ErrorVoto, emitir_voto
from apps.voting.services.iniciar_votacion import autopausar_si_sin_votantes
from apps.voting.services.iniciar_voto import ErrorAcceso, iniciar_sesion_voto


def _proceso_activo_kiosk():
    """Devuelve el proceso activo aplicando la pausa automática si no
    tiene votantes asignados. Garantiza que el kiosco nunca habilite la
    votación en un proceso sin padrón cargado.
    """
    proceso = proceso_activo()
    autopausar_si_sin_votantes(proceso)
    return proceso


def _tipos_ordenados(proceso):
    return list(
        TipoEleccion.objects.filter(
            proceso=proceso, es_activo=True
        ).order_by("orden_aparicion")
    )

def _wizard_context(request, proceso, error=None):
    """Contexto listo para renderizar wizard.html. None si no hay pasos."""
    tipos = _tipos_ordenados(proceso)
    idx = request.session.get("voto_tipo_actual", 0)
    if idx >= len(tipos):
        return None

    tipo = tipos[idx]
    listas = (
        ListaCandidatura.objects
        .filter(tipo_eleccion=tipo, es_activo=True)
        .order_by("nombre")
    )

    estudiante = (
        Estudiante.objects
        .select_related("mesa", "grado_seccion")
        .filter(id=request.session.get("voto_estudiante_id"))
        .first()
    )

    return {
        "tipo": tipo,
        "listas": listas,
        "paso": idx + 1,
        "total": len(tipos),
        "es_ultimo_paso": (idx + 1 == len(tipos)),
        "estudiante": estudiante,
        "error": error,
    }


def kiosk_espera(request):
    if request.method == "POST":
        dni = request.POST.get("dni", "").strip()
        try:
            iniciar_sesion_voto(request, dni)
            return redirect("kiosk_wizard")
        except ErrorAcceso as exc:
            return render(
                request,
                "kiosk/espera.html",
                {
                    "error": str(exc),
                    "dni": request.POST.get("dni", ""),
                    "proceso": _proceso_activo_kiosk(),
                },
            )

    return render(
        request,
        "kiosk/espera.html",
        {"proceso": _proceso_activo_kiosk()},
    )


def kiosk_wizard_old(request):
    estudiante_id = request.session.get("voto_estudiante_id")
    if not estudiante_id:
        return redirect("kiosk_espera")

    proceso = ProcesoElectoral.objects.filter(
        pk=request.session.get("voto_proceso_id")
    ).first()
    if not proceso:
        return redirect("kiosk_espera")

    tipos = _tipos_ordenados(proceso)    
    idx = request.session.get("voto_tipo_actual", 0)
    if idx >= len(tipos):
        return redirect("kiosk_espera")

    tipo = tipos[idx]
    return render(
        request,
        "kiosk/wizard.html",
        {
            "tipo": tipo,
            "listas": ListaCandidatura.objects.filter(tipo_eleccion=tipo, es_activo=True),
            "paso": idx + 1,
            "total": len(tipos),
        },
    )

def kiosk_wizard(request):
    estudiante_id = request.session.get("voto_estudiante_id")
    if not estudiante_id:
        return redirect("kiosk_espera")

    proceso = ProcesoElectoral.objects.filter(
        pk=request.session.get("voto_proceso_id")
    ).first()
    if not proceso:
        return redirect("kiosk_espera")

    if not proceso.votacion_iniciada or proceso.votacion_pausada:
        return redirect("kiosk_espera")

    ctx = _wizard_context(request, proceso)
    if ctx is None:
        return redirect("kiosk_espera")
    return render(request, "kiosk/wizard.html", ctx)

def kiosk_wizard_paso_old(request):
    if request.method != "POST":
        return redirect("kiosk_wizard")

    estudiante_id = request.session.get("voto_estudiante_id")
    proceso_id = request.session.get("voto_proceso_id")
    if not estudiante_id or not proceso_id:
        return redirect("kiosk_espera")

    proceso = ProcesoElectoral.objects.get(pk=proceso_id)
    tipos = _tipos_ordenados(proceso)
    idx = request.session.get("voto_tipo_actual", 0)
    if idx >= len(tipos):
        return redirect("kiosk_espera")

    tipo = tipos[idx]
    lista_id = int(request.POST.get("lista_id"))
    if not ListaCandidatura.objects.filter(id=lista_id, tipo_eleccion=tipo, es_activo=True).exists():
        return render(request, "kiosk/wizard.html", {"error": "Lista no válida"})

    selecciones = request.session.get("voto_selecciones", {})
    selecciones[str(tipo.id)] = lista_id
    request.session["voto_selecciones"] = selecciones
    request.session["voto_tipo_actual"] = idx + 1

    if idx + 1 < len(tipos):
        return redirect("kiosk_wizard")

    try:
        emitir_voto(
            estudiante_id=estudiante_id,
            proceso=proceso,
            selecciones={int(k): v for k, v in selecciones.items()},
        )
    except ErrorVoto as exc:
        return render(request, "kiosk/wizard.html", {"error": str(exc)})

    for key in ["voto_estudiante_id", "voto_proceso_id", "voto_tipo_actual", "voto_selecciones"]:
        request.session.pop(key, None)
    return redirect("kiosk_exito")

def kiosk_wizard_paso(request):
    if request.method != "POST":
        return redirect("kiosk_wizard")

    estudiante_id = request.session.get("voto_estudiante_id")
    proceso_id = request.session.get("voto_proceso_id")
    if not estudiante_id or not proceso_id:
        return redirect("kiosk_espera")

    proceso = ProcesoElectoral.objects.filter(pk=proceso_id).first()
    if not proceso:
        return redirect("kiosk_espera")

    if not proceso.votacion_iniciada or proceso.votacion_pausada:
        return redirect("kiosk_espera")

    tipos = _tipos_ordenados(proceso)
    idx = request.session.get("voto_tipo_actual", 0)
    if idx >= len(tipos):
        return redirect("kiosk_espera")

    tipo = tipos[idx]
    es_ultimo_paso = (idx + 1 == len(tipos))

    # ---------- Validación del lista_id ----------
    raw = request.POST.get("lista_id")
    try:
        lista_id = int(raw)
    except (TypeError, ValueError):
        ctx = _wizard_context(request, proceso, error="Selección no válida")
        return render(request, "kiosk/wizard.html", ctx) if ctx else redirect("kiosk_espera")

    if not ListaCandidatura.objects.filter(
        id=lista_id, tipo_eleccion=tipo, es_activo=True
    ).exists():
        ctx = _wizard_context(
            request, proceso,
            error="La lista seleccionada ya no está disponible.",
        )
        return render(request, "kiosk/wizard.html", ctx) if ctx else redirect("kiosk_espera")

    # ---------- Validación del DNI en el último paso ----------
    if es_ultimo_paso:
        estudiante = (
            Estudiante.objects
            .filter(id=estudiante_id, proceso=proceso)
            .first()
        )
        if not estudiante:
            return redirect("kiosk_espera")

        dni_confirmacion = (request.POST.get("dni_confirmacion") or "").strip()
        if not dni_confirmacion:
            ctx = _wizard_context(
                request, proceso,
                error="Debe ingresar su DNI para confirmar el voto.",
            )
            return render(request, "kiosk/wizard.html", ctx) if ctx else redirect("kiosk_espera")

        if dni_confirmacion != estudiante.numero_documento:
            ctx = _wizard_context(
                request, proceso,
                error="El DNI ingresado no coincide con el registrado. Verifique e intente nuevamente.",
            )
            return render(request, "kiosk/wizard.html", ctx) if ctx else redirect("kiosk_espera")

    # ---------- Persistir selección y avanzar ----------
    selecciones = request.session.get("voto_selecciones", {})
    selecciones[str(tipo.id)] = lista_id
    request.session["voto_selecciones"] = selecciones
    request.session["voto_tipo_actual"] = idx + 1

    if not es_ultimo_paso:
        return redirect("kiosk_wizard")

    # ---------- Último paso: emitir voto atómico ----------
    try:
        emitir_voto(
            estudiante_id=estudiante_id,
            proceso=proceso,
            selecciones={int(k): v for k, v in selecciones.items()},
        )
    except ErrorVoto as exc:
        ctx = _wizard_context(request, proceso, error=str(exc))
        return render(request, "kiosk/wizard.html", ctx) if ctx else redirect("kiosk_espera")

    for key in ["voto_estudiante_id", "voto_proceso_id",
                "voto_tipo_actual", "voto_selecciones"]:
        request.session.pop(key, None)
    return redirect("kiosk_exito")

def kiosk_exito(request):
    return render(request, "kiosk/exito.html")
