from django.db import migrations


def clear_note(apps, schema_editor):
    Publication = apps.get_model("catalog", "Publication")
    Publication.objects.using(schema_editor.connection.alias).filter(
        kind="software",
        registration_number__in=["2025SR0462060", "2025SR0462049"],
        source_note='来源：用户提供的成果清单。2026-11-06 按用户要求作为独立软件著作权板块录入。按登记号和名称检索未取得可核对的公开登记记录；名称、登记号、日期及著作权人均保持用户原文，尚未完成公开核验。',
    ).update(source_note="")


class Migration(migrations.Migration):
    dependencies = [("catalog", "0008_publication_registration")]
    operations = [migrations.RunPython(clear_note, migrations.RunPython.noop)]
