from django.db import migrations


GRADOS = [
    ("1ro", 1),
    ("2do", 2),
    ("3ro", 3),
    ("4to", 4),
    ("5to", 5),
]
SECCIONES = ["A", "B", "C"]


def crear_catalogo(apps, schema_editor):
    GradoSeccion = apps.get_model("voters", "GradoSeccion")
    for grado, orden in GRADOS:
        for seccion in SECCIONES:
            # No existe 5to C en el padrón base
            if grado == "5to" and seccion == "C":
                continue
            GradoSeccion.objects.get_or_create(
                nivel="secundaria",
                grado=grado,
                seccion=seccion,
                defaults={"orden": orden, "es_activo": True},
            )


def borrar_catalogo(apps, schema_editor):
    GradoSeccion = apps.get_model("voters", "GradoSeccion")
    GradoSeccion.objects.filter(nivel="secundaria").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("voters", "0003_gradoseccion_remove_estudiante_grado_and_more"),
    ]

    operations = [
        migrations.RunPython(crear_catalogo, borrar_catalogo),
    ]
