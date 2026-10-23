from django.contrib import admin, messages
from django.utils.html import format_html

from .models import (
    ARM,
    AuditLog,
    Challenge,
    Expense,
    ExpenseCategory,
    OtherFinancialMovement,
    RevenueCategory,
    RevenueTransaction,
)
from .services import money, revenue_total


admin.site.site_header = "Xonovate Challenge Tracker"
admin.site.site_title = "Xonovate Challenge Tracker Admin"
admin.site.index_title = "Financial records and maintenance"


@admin.register(Challenge)
class ChallengeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "start_date",
        "end_date",
        "duration_display",
        "target_display",
        "status",
        "is_public_featured",
        "revenue_display",
    )
    list_filter = ("status", "currency", "start_date")
    search_fields = ("name", "description", "notes")
    date_hierarchy = "start_date"
    ordering = ("-start_date",)
    readonly_fields = ("created_at", "updated_at", "duration_display", "revenue_display")
    fieldsets = (
        ("Challenge", {"fields": ("name", "description", "status")}),
        ("Dates and duration", {"fields": ("start_date", "end_date", "duration_display")}),
        ("Financial target", {"fields": ("target_amount", "currency", "revenue_display")}),
        ("Notes", {"fields": ("notes",)}),
        ("Record information", {"classes": ("collapse",), "fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="Duration")
    def duration_display(self, obj):
        return f"{obj.duration_days} days"

    @admin.display(description="Target")
    def target_display(self, obj):
        return f"{obj.currency} {money(obj.target_amount):,.2f}"

    @admin.display(description="Qualifying revenue")
    def revenue_display(self, obj):
        return format_html("<strong>{} {}</strong>", obj.currency, f"{revenue_total(obj):,.2f}")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ARM)
class ARMAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "description", "notes")
    ordering = ("name",)
    fieldsets = (
        (None, {"fields": ("name", "description", "is_active")}),
        ("Notes", {"fields": ("notes",)}),
        ("Record information", {"classes": ("collapse",), "fields": ("created_at", "updated_at")}),
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(RevenueCategory)
class RevenueCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    ordering = ("name",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    ordering = ("name",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(RevenueTransaction)
class RevenueTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "transaction_date",
        "arm",
        "category",
        "amount_display",
        "eligible_display",
        "status",
        "public_visibility",
        "challenge",
    )
    list_filter = (
        "status",
        "public_visibility",
        "arm",
        "category",
        "payment_method",
        "challenge",
        "transaction_date",
    )
    search_fields = (
        "description",
        "public_description",
        "customer_name",
        "reference",
        "internal_notes",
        "arm__name",
    )
    date_hierarchy = "transaction_date"
    ordering = ("-transaction_date", "-id")
    list_select_related = ("arm", "category", "challenge")
    readonly_fields = ("created_at", "updated_at", "eligible_display")
    fieldsets = (
        ("Challenge and classification", {"fields": ("challenge", "transaction_date", "arm", "category")}),
        ("Money received", {"fields": ("amount", "currency", "payment_method", "reference", "customer_name")}),
        ("Descriptions", {"fields": ("description", "public_visibility", "public_description", "internal_notes")}),
        ("Status and corrections", {"fields": ("status", "refunded_amount", "eligible_display")}),
        ("Record information", {"classes": ("collapse",), "fields": ("created_at", "updated_at")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("arm", "category", "challenge")

    @admin.display(description="Received", ordering="amount")
    def amount_display(self, obj):
        return f"{obj.currency} {obj.amount:,.2f}"

    @admin.display(description="Qualifying")
    def eligible_display(self, obj):
        return format_html("<strong>{} {}</strong>", obj.currency, f"{obj.eligible_amount:,.2f}")

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Void selected revenue transactions")
    def void_transactions(self, request, queryset):
        changed = 0
        for txn in queryset:
            txn.status = RevenueTransaction.Status.VOIDED
            txn.refunded_amount = 0
            txn.full_clean()
            txn.save()
            changed += 1
        self.message_user(request, f"{changed} transaction(s) voided.", messages.SUCCESS)

    @admin.action(description="Mark selected revenue transactions fully refunded")
    def refund_transactions(self, request, queryset):
        changed = 0
        for txn in queryset:
            txn.status = RevenueTransaction.Status.REFUNDED
            txn.refunded_amount = txn.amount
            txn.full_clean()
            txn.save()
            changed += 1
        self.message_user(request, f"{changed} transaction(s) marked refunded.", messages.SUCCESS)

    actions = ["void_transactions", "refund_transactions"]


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = (
        "expense_date",
        "category",
        "arm",
        "amount_display",
        "payment_status",
        "is_voided",
        "payee",
        "challenge",
    )
    list_filter = (
        "payment_status",
        "is_voided",
        "category",
        "arm",
        "payment_method",
        "challenge",
        "expense_date",
    )
    search_fields = ("description", "payee", "internal_notes", "category__name")
    date_hierarchy = "expense_date"
    ordering = ("-expense_date", "-id")
    list_select_related = ("arm", "category", "challenge")
    readonly_fields = ("created_at", "updated_at", "status_label")
    fieldsets = (
        ("Challenge and classification", {"fields": ("challenge", "expense_date", "category", "arm")}),
        ("Payment", {"fields": ("amount", "currency", "payment_method", "payment_status", "payee")}),
        ("Description and evidence", {"fields": ("description", "receipt", "internal_notes")}),
        ("Correction", {"fields": ("is_voided", "void_reason", "status_label")}),
        ("Record information", {"classes": ("collapse",), "fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="Amount", ordering="amount")
    def amount_display(self, obj):
        return f"{obj.currency} {obj.amount:,.2f}"

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Void selected expenses")
    def void_expenses(self, request, queryset):
        changed = 0
        for expense in queryset:
            expense.is_voided = True
            expense.save(update_fields=["is_voided", "updated_at"])
            changed += 1
        self.message_user(request, f"{changed} expense(s) voided.", messages.SUCCESS)

    actions = ["void_expenses"]


@admin.register(OtherFinancialMovement)
class OtherFinancialMovementAdmin(admin.ModelAdmin):
    list_display = (
        "movement_date",
        "movement_type",
        "amount_display",
        "arm",
        "is_voided",
        "challenge",
    )
    list_filter = ("movement_type", "is_voided", "arm", "challenge", "movement_date")
    search_fields = ("description", "reference", "notes", "arm__name")
    date_hierarchy = "movement_date"
    ordering = ("-movement_date", "-id")
    list_select_related = ("arm", "challenge")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Challenge and classification", {"fields": ("challenge", "movement_type", "movement_date", "arm")}),
        ("Amount", {"fields": ("amount", "currency", "reference")}),
        ("Description", {"fields": ("description", "notes")}),
        ("Correction", {"fields": ("is_voided", "void_reason")}),
        ("Record information", {"classes": ("collapse",), "fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="Amount", ordering="amount")
    def amount_display(self, obj):
        return f"{obj.currency} {obj.amount:,.2f}"

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "model_name", "object_id", "action", "summary")
    list_filter = ("model_name", "action", "created_at")
    search_fields = ("summary", "model_name")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


