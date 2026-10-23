from decimal import Decimal

from django import forms
from django.db.models import Q
from django.utils import timezone

from .models import (
    ARM,
    Challenge,
    Expense,
    ExpenseCategory,
    OtherFinancialMovement,
    RevenueCategory,
    RevenueTransaction,
)


class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = "form-check-input"
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", "form-select")
            elif isinstance(widget, forms.FileInput):
                widget.attrs.setdefault("class", "form-control")
            else:
                widget.attrs.setdefault("class", "form-control")
            if widget.attrs.get("class") == "form-control" and name not in (
                "description",
                "public_description",
                "internal_notes",
                "notes",
                "void_reason",
            ):
                widget.attrs.setdefault("placeholder", field.label or name.replace("_", " ").title())
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs.setdefault("rows", 3)


class ChallengeSettingsForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Challenge
        fields = ["description", "start_date", "end_date", "target_amount", "status"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "target_amount": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["description"].help_text = "Shown on the public challenge page."
        self.fields["target_amount"].help_text = (
            "Gross revenue target. Expenses are tracked separately."
        )

class RevenueCategoryForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = RevenueCategory
        fields = ["name", "description", "is_active"]


class ExpenseCategoryForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ExpenseCategory
        fields = ["name", "description", "is_active"]


class RevenueTransactionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = RevenueTransaction
        fields = [
            "transaction_date",
            "amount",
            "currency",
            "arm",
            "category",
            "description",
            "customer_name",
            "payment_method",
            "reference",
            "public_visibility",
            "public_description",
            "internal_notes",
            "status",
            "refunded_amount",
        ]
        widgets = {
            "transaction_date": forms.DateInput(attrs={"type": "date"}),
            "amount": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "currency": forms.TextInput(attrs={"maxlength": 3}),
            "description": forms.Textarea(attrs={"rows": 3}),
            "public_description": forms.Textarea(attrs={"rows": 3}),
            "internal_notes": forms.Textarea(attrs={"rows": 2}),
            "refunded_amount": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }
        help_texts = {
            "amount": "Amount received.",
            "description": "Private workspace description.",
            "public_description": "Approved text for the public page.",
            "refunded_amount": "For partially refunded or refunded revenue.",
        }

    def __init__(self, *args, **kwargs):
        challenge = kwargs.pop("challenge", None)
        super().__init__(*args, **kwargs)
        self.challenge = challenge or (self.instance.challenge if self.instance.pk else None)
        if self.challenge and not self.instance.pk:
            self.instance.challenge = self.challenge
        self.fields["transaction_date"].initial = timezone.localdate()
        self.fields["currency"].initial = "GHS"
        self.fields["refunded_amount"].initial = Decimal("0.00")
        arm_qs = ARM.objects.all()
        category_qs = RevenueCategory.objects.all()
        if self.instance and self.instance.pk:
            arm_qs = ARM.objects.filter(
                Q(is_active=True) | Q(pk=self.instance.arm_id)
            )
            category_qs = RevenueCategory.objects.filter(
                Q(is_active=True) | Q(pk=self.instance.category_id)
            )
        else:
            arm_qs = arm_qs.filter(is_active=True)
            category_qs = category_qs.filter(is_active=True)
        self.fields["arm"].label = "Business unit"
        self.fields["arm"].queryset = arm_qs
        self.fields["category"].queryset = category_qs

    def clean_reference(self):
        return (self.cleaned_data.get("reference") or "").strip()

    def clean_currency(self):
        value = (self.cleaned_data.get("currency") or "GHS").upper()
        if len(value) != 3:
            raise forms.ValidationError("Enter a three-letter currency code, such as GHS.")
        return value

    def clean(self):
        cleaned = super().clean()
        challenge = self.challenge
        date = cleaned.get("transaction_date")
        amount = cleaned.get("amount")
        arm = cleaned.get("arm")
        category = cleaned.get("category")
        description = (cleaned.get("description") or "").strip()
        if challenge and date and not (challenge.start_date <= date <= challenge.end_date):
            self.add_error(
                "transaction_date",
                "This date is outside the selected challenge period and will not count toward the target.",
            )
        if challenge and date and amount and arm and category and description:
            duplicates = RevenueTransaction.objects.filter(
                challenge=challenge,
                transaction_date=date,
                amount=amount,
                arm=arm,
                category=category,
                description__iexact=description,
                status=RevenueTransaction.Status.RECEIVED,
            )
            if self.instance.pk:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                self.add_error(
                    "description",
                    "A matching revenue transaction already exists. Edit the existing record or change the description if this is genuinely a different payment.",
                )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.challenge and not instance.challenge_id:
            instance.challenge = self.challenge
        instance.currency = (instance.currency or "GHS").upper()
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class ExpenseForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Expense
        fields = [
            "expense_date",
            "amount",
            "currency",
            "category",
            "arm",
            "description",
            "payee",
            "payment_method",
            "payment_status",
            "receipt",
            "internal_notes",
        ]
        widgets = {
            "expense_date": forms.DateInput(attrs={"type": "date"}),
            "amount": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "currency": forms.TextInput(attrs={"maxlength": 3}),
            "description": forms.Textarea(attrs={"rows": 3}),
            "internal_notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        challenge = kwargs.pop("challenge", None)
        super().__init__(*args, **kwargs)
        self.challenge = challenge or (self.instance.challenge if self.instance.pk else None)
        if self.challenge and not self.instance.pk:
            self.instance.challenge = self.challenge
        self.fields["expense_date"].initial = timezone.localdate()
        self.fields["currency"].initial = "GHS"
        arm_qs = ARM.objects.all()
        cat_qs = ExpenseCategory.objects.all()
        if self.instance and self.instance.pk:
            if self.instance.arm_id:
                arm_qs = ARM.objects.filter(
                    Q(is_active=True) | Q(pk=self.instance.arm_id)
                )
            cat_qs = ExpenseCategory.objects.filter(
                Q(is_active=True) | Q(pk=self.instance.category_id)
            )
        else:
            arm_qs = arm_qs.filter(is_active=True)
            cat_qs = cat_qs.filter(is_active=True)
        self.fields["arm"].label = "Business unit"
        self.fields["arm"].queryset = arm_qs
        self.fields["arm"].empty_label = "Shared / group-level expense"
        self.fields["arm"].help_text = "Leave blank for group-wide costs."
        self.fields["receipt"].help_text = "PDF, JPG, or PNG up to 5 MB."
        self.fields["category"].queryset = cat_qs

    def clean_currency(self):
        value = (self.cleaned_data.get("currency") or "GHS").upper()
        if len(value) != 3:
            raise forms.ValidationError("Enter a three-letter currency code, such as GHS.")
        return value

    def clean(self):
        cleaned = super().clean()
        challenge = self.challenge
        date = cleaned.get("expense_date")
        if challenge and date and not (challenge.start_date <= date <= challenge.end_date):
            self.add_error(
                "expense_date",
                "This date is outside the selected challenge period.",
            )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.challenge and not instance.challenge_id:
            instance.challenge = self.challenge
        instance.currency = (instance.currency or "GHS").upper()
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class OtherFinancialMovementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = OtherFinancialMovement
        fields = [
            "movement_type",
            "movement_date",
            "amount",
            "currency",
            "arm",
            "description",
            "reference",
            "notes",
        ]
        widgets = {
            "movement_date": forms.DateInput(attrs={"type": "date"}),
            "amount": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "currency": forms.TextInput(attrs={"maxlength": 3}),
            "description": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        challenge = kwargs.pop("challenge", None)
        super().__init__(*args, **kwargs)
        self.challenge = challenge or (self.instance.challenge if self.instance.pk else None)
        if self.challenge and not self.instance.pk:
            self.instance.challenge = self.challenge
        self.fields["movement_date"].initial = timezone.localdate()
        self.fields["currency"].initial = "GHS"
        arm_qs = ARM.objects.all()
        if self.instance and self.instance.pk and self.instance.arm_id:
            arm_qs = ARM.objects.filter(
                Q(is_active=True) | Q(pk=self.instance.arm_id)
            )
        else:
            arm_qs = arm_qs.filter(is_active=True)
        self.fields["arm"].label = "Business unit"
        self.fields["arm"].queryset = arm_qs
        self.fields["arm"].empty_label = "Shared / group-level"
        self.fields["notes"].help_text = "Non-revenue records do not count toward the target."

    def clean_currency(self):
        value = (self.cleaned_data.get("currency") or "GHS").upper()
        if len(value) != 3:
            raise forms.ValidationError("Enter a three-letter currency code, such as GHS.")
        return value

    def clean(self):
        cleaned = super().clean()
        challenge = self.challenge
        date = cleaned.get("movement_date")
        if challenge and date and not (challenge.start_date <= date <= challenge.end_date):
            self.add_error("movement_date", "This date is outside the selected challenge period.")
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.challenge and not instance.challenge_id:
            instance.challenge = self.challenge
        instance.currency = (instance.currency or "GHS").upper()
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class SimulatorForm(BootstrapFormMixin, forms.Form):
    target = forms.DecimalField(
        label="Target amount",
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("1.00"),
        initial=Decimal("200000.00"),
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "1"}),
    )
    days = forms.IntegerField(label="Number of days", min_value=1, initial=100)
    average_sale_price = forms.DecimalField(
        label="Average sale price",
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        initial=Decimal("2000.00"),
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
    )
    sales_per_day = forms.DecimalField(
        label="Expected sales per working day",
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.00"),
        initial=Decimal("1.00"),
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
    )
    working_days_per_week = forms.IntegerField(
        label="Working days per week",
        min_value=1,
        max_value=7,
        initial=7,
    )
    delivery_cost_per_sale = forms.DecimalField(
        label="Direct delivery cost per sale (optional)",
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=False,
        initial=Decimal("0.00"),
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
    )
    collection_delay_days = forms.IntegerField(
        label="Collection delay after a sale (days, optional)",
        min_value=0,
        max_value=365,
        required=False,
        initial=0,
    )
    save_scenario = forms.BooleanField(
        label="Add this scenario to the comparison list",
        required=False,
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("delivery_cost_per_sale") is None:
            cleaned["delivery_cost_per_sale"] = Decimal("0.00")
        if cleaned.get("collection_delay_days") is None:
            cleaned["collection_delay_days"] = 0
        return cleaned

