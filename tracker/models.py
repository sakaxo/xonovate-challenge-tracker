from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


PAYMENT_METHOD_CHOICES = [
    ("cash", "Cash"),
    ("mobile_money", "Mobile money"),
    ("bank_transfer", "Bank transfer"),
    ("card", "Card"),
    ("cheque", "Cheque"),
    ("other", "Other"),
]


def validate_receipt_size(value):
    limit = 5 * 1024 * 1024
    if value.size > limit:
        raise ValidationError("Receipt files must be 5 MB or smaller.")


class Challenge(models.Model):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        COMPLETED = "completed", "Completed"
        ARCHIVED = "archived", "Archived"

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    target_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    currency = models.CharField(max_length=3, default="GHS")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PLANNED, db_index=True
    )
    is_public_featured = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Feature this challenge on the public landing page.",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_date", "-created_at"]
        verbose_name = "Challenge"
        verbose_name_plural = "Challenges"

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date cannot be earlier than the start date."})
        if self.target_amount is not None and self.target_amount < 0:
            raise ValidationError({"target_amount": "Target amount cannot be negative."})

    def save(self, *args, **kwargs):
        self.currency = (self.currency or "GHS").upper()
        if self.is_public_featured:
            Challenge.objects.filter(is_public_featured=True).exclude(
                pk=self.pk
            ).update(is_public_featured=False)
        super().save(*args, **kwargs)

    @property
    def duration_days(self):
        if not self.start_date or not self.end_date or self.end_date < self.start_date:
            return 0
        return (self.end_date - self.start_date).days + 1

    def day_number(self, on_date=None):
        on_date = on_date or timezone.localdate()
        if not self.start_date or not self.end_date or on_date < self.start_date:
            return 0
        if on_date > self.end_date:
            return self.duration_days
        return (on_date - self.start_date).days + 1

    def days_elapsed(self, on_date=None):
        return self.day_number(on_date)

    def days_remaining(self, on_date=None):
        return max(self.duration_days - self.days_elapsed(on_date), 0)

    @property
    def status_badge_class(self):
        return {
            self.Status.PLANNED: "text-bg-secondary",
            self.Status.ACTIVE: "text-bg-success",
            self.Status.PAUSED: "text-bg-warning",
            self.Status.COMPLETED: "text-bg-primary",
            self.Status.ARCHIVED: "text-bg-dark",
        }.get(self.status, "text-bg-secondary")


class ARM(models.Model):
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "ARM"
        verbose_name_plural = "ARMs"

    def __str__(self):
        return self.name

    @property
    def status_label(self):
        return "Active" if self.is_active else "Inactive"


class RevenueCategory(models.Model):
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Revenue category"
        verbose_name_plural = "Revenue categories"

    def __str__(self):
        return self.name


class ExpenseCategory(models.Model):
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Expense category"
        verbose_name_plural = "Expense categories"

    def __str__(self):
        return self.name


class RevenueTransaction(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        PARTIALLY_REFUNDED = "partially_refunded", "Partially refunded"
        REFUNDED = "refunded", "Refunded"
        VOIDED = "voided", "Voided"

    challenge = models.ForeignKey(
        Challenge, on_delete=models.PROTECT, related_name="revenue_transactions"
    )
    transaction_date = models.DateField(default=timezone.localdate, db_index=True)
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="The amount actually received. Partial payments should be recorded as received.",
    )
    currency = models.CharField(max_length=3, default="GHS")
    arm = models.ForeignKey(
        ARM, on_delete=models.PROTECT, related_name="revenue_transactions"
    )
    category = models.ForeignKey(
        RevenueCategory,
        on_delete=models.PROTECT,
        related_name="revenue_transactions",
    )
    description = models.TextField(
        help_text="Internal, factual description of what this payment was for."
    )
    customer_name = models.CharField(max_length=200, blank=True)
    payment_method = models.CharField(
        max_length=30, choices=PAYMENT_METHOD_CHOICES, default="mobile_money"
    )
    reference = models.CharField(max_length=120, blank=True)
    public_visibility = models.BooleanField(default=False, db_index=True)
    public_description = models.TextField(
        blank=True,
        help_text="A deliberately prepared, non-sensitive description for public display.",
    )
    internal_notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=30, choices=Status.choices, default=Status.RECEIVED, db_index=True
    )
    refunded_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-transaction_date", "-id"]
        verbose_name = "Revenue transaction"
        verbose_name_plural = "Revenue transactions"
        constraints = [
            models.UniqueConstraint(
                fields=["challenge", "reference"],
                condition=~Q(reference=""),
                name="unique_revenue_reference_per_challenge",
            )
        ]

    def __str__(self):
        return f"{self.transaction_date} · {self.arm} · {self.currency} {self.amount:,.2f}"

    def clean(self):
        super().clean()
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({"amount": "Amount must be greater than zero."})
        if self.refunded_amount is None:
            self.refunded_amount = Decimal("0.00")
        if self.refunded_amount < 0:
            raise ValidationError({"refunded_amount": "Refunded amount cannot be negative."})
        if self.amount is not None and self.refunded_amount > self.amount:
            raise ValidationError(
                {"refunded_amount": "Refunded amount cannot exceed the amount received."}
            )
        if self.status == self.Status.RECEIVED and self.refunded_amount != 0:
            raise ValidationError(
                {"refunded_amount": "A received transaction cannot have a refunded amount."}
            )
        if self.status == self.Status.PARTIALLY_REFUNDED and not (
            0 < self.refunded_amount < (self.amount or 0)
        ):
            raise ValidationError(
                {
                    "refunded_amount": "A partially refunded transaction needs a refund greater than zero and less than the amount."
                }
            )
        if self.status == self.Status.REFUNDED and self.refunded_amount != self.amount:
            raise ValidationError(
                {"refunded_amount": "A fully refunded transaction must have refunded amount equal to the received amount."}
            )
        if self.status == self.Status.VOIDED and self.refunded_amount != 0:
            raise ValidationError(
                {"refunded_amount": "A voided transaction should not have a refunded amount."}
            )
        if self.public_visibility and not self.public_description.strip():
            # The public view will use a safe category-based summary. This is
            # allowed, but the transaction page warns the founder.
            pass

    def save(self, *args, **kwargs):
        self.currency = (self.currency or "GHS").upper()
        super().save(*args, **kwargs)

    @property
    def eligible_amount(self):
        if self.status in (self.Status.RECEIVED, self.Status.PARTIALLY_REFUNDED):
            return max(self.amount - (self.refunded_amount or Decimal("0.00")), Decimal("0.00"))
        return Decimal("0.00")

    @property
    def status_badge_class(self):
        return {
            self.Status.RECEIVED: "text-bg-success",
            self.Status.PARTIALLY_REFUNDED: "text-bg-warning",
            self.Status.REFUNDED: "text-bg-secondary",
            self.Status.VOIDED: "text-bg-dark",
        }.get(self.status, "text-bg-secondary")

    @property
    def public_display_description(self):
        if self.public_description.strip():
            return self.public_description.strip()
        return f"{self.category.name} revenue received."

    @property
    def has_public_description(self):
        return bool(self.public_description.strip())


class Expense(models.Model):
    class PaymentStatus(models.TextChoices):
        PAID = "paid", "Paid"
        UNPAID = "unpaid", "Unpaid obligation"

    challenge = models.ForeignKey(
        Challenge, on_delete=models.PROTECT, related_name="expenses"
    )
    expense_date = models.DateField(default=timezone.localdate, db_index=True)
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    currency = models.CharField(max_length=3, default="GHS")
    category = models.ForeignKey(
        ExpenseCategory, on_delete=models.PROTECT, related_name="expenses"
    )
    arm = models.ForeignKey(
        ARM,
        on_delete=models.PROTECT,
        related_name="expenses",
        null=True,
        blank=True,
        help_text="Leave blank for a shared or group-level expense.",
    )
    description = models.TextField()
    payee = models.CharField(max_length=200, blank=True)
    payment_method = models.CharField(
        max_length=30, choices=PAYMENT_METHOD_CHOICES, default="mobile_money"
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PAID,
        db_index=True,
    )
    receipt = models.FileField(
        upload_to="receipts/%Y/%m/",
        blank=True,
        validators=[
            FileExtensionValidator(allowed_extensions=["pdf", "jpg", "jpeg", "png"]),
            validate_receipt_size,
        ],
        help_text="Optional PDF, JPG or PNG receipt (maximum 5 MB).",
    )
    internal_notes = models.TextField(blank=True)
    is_voided = models.BooleanField(default=False, db_index=True)
    void_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-expense_date", "-id"]
        verbose_name = "Expense"
        verbose_name_plural = "Expenses"

    def __str__(self):
        return f"{self.expense_date} · {self.category} · {self.currency} {self.amount:,.2f}"

    def clean(self):
        super().clean()
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({"amount": "Amount must be greater than zero."})

    def save(self, *args, **kwargs):
        self.currency = (self.currency or "GHS").upper()
        super().save(*args, **kwargs)

    @property
    def status_label(self):
        if self.is_voided:
            return "Voided"
        return self.get_payment_status_display()

    @property
    def status_badge_class(self):
        if self.is_voided:
            return "text-bg-dark"
        return "text-bg-success" if self.payment_status == self.PaymentStatus.PAID else "text-bg-warning"


class OtherFinancialMovement(models.Model):
    class MovementType(models.TextChoices):
        LOAN_RECEIVED = "loan_received", "Loan received"
        OWNER_CONTRIBUTION = "owner_contribution", "Owner contribution"
        INVESTMENT = "investment", "Investment"
        GRANT = "grant", "Grant"
        REFUND_PAID = "refund_paid", "Refund paid"
        INTERNAL_TRANSFER = "internal_transfer", "Internal transfer"
        OTHER_RECEIPT = "other_receipt", "Other non-revenue receipt"

    INFLOW_TYPES = {
        MovementType.LOAN_RECEIVED,
        MovementType.OWNER_CONTRIBUTION,
        MovementType.INVESTMENT,
        MovementType.GRANT,
        MovementType.OTHER_RECEIPT,
    }

    challenge = models.ForeignKey(
        Challenge, on_delete=models.PROTECT, related_name="other_movements"
    )
    movement_type = models.CharField(
        max_length=40, choices=MovementType.choices, db_index=True
    )
    movement_date = models.DateField(default=timezone.localdate, db_index=True)
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    currency = models.CharField(max_length=3, default="GHS")
    arm = models.ForeignKey(
        ARM,
        on_delete=models.PROTECT,
        related_name="other_movements",
        null=True,
        blank=True,
    )
    description = models.TextField()
    reference = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    is_voided = models.BooleanField(default=False, db_index=True)
    void_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-movement_date", "-id"]
        verbose_name = "Other financial movement"
        verbose_name_plural = "Other financial movements"

    def __str__(self):
        return f"{self.movement_date} · {self.get_movement_type_display()} · {self.currency} {self.amount:,.2f}"

    def clean(self):
        super().clean()
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({"amount": "Amount must be greater than zero."})

    def save(self, *args, **kwargs):
        self.currency = (self.currency or "GHS").upper()
        super().save(*args, **kwargs)

class AuditLog(models.Model):
    model_name = models.CharField(max_length=80)
    object_id = models.PositiveBigIntegerField()
    action = models.CharField(max_length=30)
    summary = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Audit log entry"
        verbose_name_plural = "Audit log"

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} · {self.model_name} #{self.object_id} · {self.action}"
