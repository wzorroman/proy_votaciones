from apps.voters.selectors import EstadoElector, proceso_activo, validar_dni


class ErrorAcceso(Exception):
    pass


def iniciar_sesion_voto(request, dni: str):
    proceso = proceso_activo()
    if not proceso:
        raise ErrorAcceso("El proceso electoral no está disponible")

    if not proceso.votacion_iniciada:
        raise ErrorAcceso("La votación aún no ha comenzado")

    if proceso.votacion_pausada:
        raise ErrorAcceso("La votación está pausada")

    estado, estudiante = validar_dni(dni, proceso)
    mensajes = {
        EstadoElector.NO_EXISTE: "DNI no encontrado en el padrón",
        EstadoElector.INHABILITADO: "Su DNI se encuentra inhabilitado para votar",
        EstadoElector.YA_VOTO: "Este DNI ya registró un sufragio",
        EstadoElector.AUSENTE: "Su DNI figura como ausente",
    }

    if estado != EstadoElector.OK:
        raise ErrorAcceso(mensajes.get(estado, "Acceso denegado"))

    request.session["voto_estudiante_id"] = estudiante.id
    request.session["voto_proceso_id"] = proceso.id
    request.session["voto_selecciones"] = {}
    request.session["voto_tipo_actual"] = 0
    return estudiante
