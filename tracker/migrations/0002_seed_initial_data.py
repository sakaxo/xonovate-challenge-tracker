from datetime import date
from decimal import Decimal

from django.db import migrations


ARMS = [
    (
        "Xonovate Technologies",
        "Websites, software development, and digital solutions for businesses.",
    ),
    (
        "Xonovate Code Champions",
        "Practical technology education, coding, robotics, electronics, AI, technology projects, school partnerships, and related educational engagements.",
    ),
    (
        "Other Xonovate Business Activities",
        "A configurable category for other relevant revenue-generating activities.",
    ),
]

REVENUE_CATEGORIES = [
    "Website development",
    "Website redesign",
    "Software development",
    "Digital solutions",
    "Code Champions school engagements",
    "Training and educational services",
    "Other qualifying customer revenue",
]

EXPENSE_CATEGORIES = [
    "Internet and mobile data",
    "Software subscriptions",
    "Transport and business visits",
    "Marketing and content production",
    "Project materials",
    "Equipment and hardware",
    "Learning and professional development",
    "Administrative costs",
    "Bank and transaction charges",
    "Other operating expenses",
]


def seed_initial_data(apps, schema_editor):
    ARM = apps.get_model("tracker", "ARM")
    RevenueCategory = apps.get_model("tracker", "RevenueCategory")
    ExpenseCategory = apps.get_model("tracker", "ExpenseCategory")
    Challenge = apps.get_model("tracker", "Challenge")

    for name, description in ARMS:
        ARM.objects.get_or_create(
            name=name,
            defaults={"description": description, "is_active": True},
        )
    for name in REVENUE_CATEGORIES:
        RevenueCategory.objects.get_or_create(name=name, defaults={"is_active": True})
    for name in EXPENSE_CATEGORIES:
        ExpenseCategory.objects.get_or_create(name=name, defaults={"is_active": True})

    start_date = date(2026, 10, 24)
    end_date = date(2027, 1, 31)
    today = date.today()
    if today < start_date:
        status = "planned"
    elif today <= end_date:
        status = "active"
    else:
        status = "completed"

    Challenge.objects.get_or_create(
        name="Building Xonovate: 100 Days to GH\u20b5200,000",
        defaults={
            "description": "A 100-day challenge to generate GH\u20b5200,000 in qualifying revenue actually collected across Xonovate's business activities.",
            "start_date": start_date,
            "end_date": end_date,
            "target_amount": Decimal("200000.00"),
            "currency": "GHS",
            "status": status,
        },
    )


def unseed_initial_data(apps, schema_editor):
    # Reversing seed data is intentionally a no-op so financial records are
    # never removed by a schema rollback.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("tracker", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_initial_data, unseed_initial_data),
    ]
