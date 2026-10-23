from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import AuditLog, Challenge, Expense, OtherFinancialMovement, RevenueTransaction


@receiver(post_save, sender=RevenueTransaction)
def log_revenue_transaction(sender, instance, created, **kwargs):
    action = "created" if created else "updated"
    AuditLog.objects.create(
        model_name="Revenue transaction",
        object_id=instance.pk,
        action=action,
        summary=(
            f"{instance.transaction_date} · {instance.arm.name} · "
            f"{instance.currency} {instance.amount:,.2f} · status: {instance.get_status_display()}"
        ),
    )


@receiver(post_save, sender=Expense)
def log_expense(sender, instance, created, **kwargs):
    action = "created" if created else "updated"
    AuditLog.objects.create(
        model_name="Expense",
        object_id=instance.pk,
        action=action,
        summary=(
            f"{instance.expense_date} · {instance.category.name} · "
            f"{instance.currency} {instance.amount:,.2f} · {instance.status_label}"
        ),
    )


@receiver(post_save, sender=OtherFinancialMovement)
def log_other_movement(sender, instance, created, **kwargs):
    action = "created" if created else "updated"
    AuditLog.objects.create(
        model_name="Other financial movement",
        object_id=instance.pk,
        action=action,
        summary=(
            f"{instance.movement_date} · {instance.get_movement_type_display()} · "
            f"{instance.currency} {instance.amount:,.2f}"
        ),
    )


@receiver(post_save, sender=Challenge)
def log_challenge(sender, instance, created, **kwargs):
    action = "created" if created else "updated"
    AuditLog.objects.create(
        model_name="Challenge",
        object_id=instance.pk,
        action=action,
        summary=f"{instance.name} · {instance.start_date} to {instance.end_date} · {instance.status}",
    )
