from django.db import migrations


BUSINESS_UNIT_NAMES = [
    "Xonovate Technologies",
    "Xonovate Code Champions",
]


def restrict_business_units(apps, schema_editor):
    ARM = apps.get_model("tracker", "ARM")
    ARM.objects.exclude(name__in=BUSINESS_UNIT_NAMES).update(is_active=False)
    ARM.objects.filter(name__in=BUSINESS_UNIT_NAMES).update(is_active=True)


def restore_business_units(apps, schema_editor):
    ARM = apps.get_model("tracker", "ARM")
    ARM.objects.filter(name="Other Xonovate Business Activities").update(is_active=True)


class Migration(migrations.Migration):
    dependencies = [
        ("tracker", "0003_challenge_is_public_featured"),
    ]

    operations = [
        migrations.RunPython(restrict_business_units, restore_business_units),
    ]
