# apps/voting/context_processors.py
from apps.voters.models import ProcesoElectoral

def proceso_activo(request):
    proceso = ProcesoElectoral.objects.filter(activo=True, cerrado=False).first()
    return {"proceso": proceso}
