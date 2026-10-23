import csv
import os
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from .forms import (
    ChallengeSettingsForm,
    ExpenseCategoryForm,
    ExpenseForm,
    OtherFinancialMovementForm,
    RevenueCategoryForm,
    RevenueTransactionForm,
    SimulatorForm,
)
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
from .services import (
    CURRENCY_SYMBOL,
    ZERO,
    arm_breakdown,
    baseline_scenarios,
    calculate_scenario,
    challenge_progress,
    challenge_totals,
    default_challenge,
    expense_category_breakdown,
    expense_queryset,
    expense_totals,
    money,
    other_movement_queryset,
    public_challenge,
    qualifying_revenue_queryset,
    recent_activity,
    revenue_category_breakdown,
    revenue_total,
    weekly_revenue,
)


def _parse_date(value, fallback):
    parsed = parse_date(value) if value else None
    return parsed or fallback


def _parse_arm(value):
    if not value:
        return None
    try:
        return ARM.objects.filter(pk=int(value)).first()
    except (TypeError, ValueError):
        return None


def _audit_for(model_name, object_id):
    return AuditLog.objects.filter(model_name=model_name, object_id=object_id)[:20]


@login_required
def dashboard(request):
    challenge = default_challenge()
    if not challenge:
        messages.error(request, "Configure the challenge in Settings to begin.")
        return redirect("settings")

    totals = challenge_totals(challenge)
    progress = challenge_progress(challenge, revenue=totals["revenue"])
    activity = [
        row
        for row in recent_activity(challenge, limit=20)
        if row["kind"] in ("revenue", "expense")
    ][:8]
    return render(
        request,
        "tracker/dashboard.html",
        {
            "challenge": challenge,
            "totals": totals,
            "progress": progress,
            "arm_rows": arm_breakdown(challenge),
            "activity": activity,
            "today": timezone.localdate(),
        },
    )


@login_required
def revenue_list(request):
    challenge = default_challenge()
    if not challenge:
        return render(request, "tracker/revenue_list.html", {"challenge": None})
    start = _parse_date(request.GET.get("start"), challenge.start_date)
    end = _parse_date(request.GET.get("end"), challenge.end_date)
    if end < start:
        start, end = challenge.start_date, challenge.end_date
        messages.error(request, "The date range was invalid and has been reset.")
    arm = _parse_arm(request.GET.get("arm"))
    category_id = request.GET.get("category", "")
    query = (request.GET.get("q") or "").strip()
    rows = RevenueTransaction.objects.filter(
        challenge=challenge,
        transaction_date__gte=start,
        transaction_date__lte=end,
    ).select_related("arm", "category")
    if arm:
        rows = rows.filter(arm=arm)
    if category_id:
        rows = rows.filter(category_id=category_id)
    if query:
        rows = rows.filter(
            Q(description__icontains=query)
            | Q(customer_name__icontains=query)
            | Q(public_description__icontains=query)
            | Q(reference__icontains=query)
        )
    rows = rows.order_by("-transaction_date", "-id")
    paginator = Paginator(rows, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "tracker/revenue_list.html",
        {
            "challenge": challenge,
            "page_obj": page_obj,
            "rows": page_obj.object_list,
            "start": start,
            "end": end,
            "arm": arm,
            "category_id": category_id,
            "query": query,
            "arms": ARM.objects.filter(is_active=True),
            "categories": RevenueCategory.objects.filter(is_active=True),
            "total": revenue_total(challenge, start, end, arm),
            "total_count": paginator.count,
        },
    )


@login_required
def expense_list(request):
    challenge = default_challenge()
    if not challenge:
        return render(request, "tracker/expense_list.html", {"challenge": None})
    start = _parse_date(request.GET.get("start"), challenge.start_date)
    end = _parse_date(request.GET.get("end"), challenge.end_date)
    if end < start:
        start, end = challenge.start_date, challenge.end_date
        messages.error(request, "The date range was invalid and has been reset.")
    arm = _parse_arm(request.GET.get("arm"))
    category_id = request.GET.get("category", "")
    payment_status = request.GET.get("payment_status", "")
    query = (request.GET.get("q") or "").strip()
    rows = Expense.objects.filter(
        challenge=challenge,
        expense_date__gte=start,
        expense_date__lte=end,
    ).select_related("arm", "category")
    if arm:
        rows = rows.filter(arm=arm)
    if category_id:
        rows = rows.filter(category_id=category_id)
    if payment_status in (
        Expense.PaymentStatus.PAID,
        Expense.PaymentStatus.UNPAID,
    ):
        rows = rows.filter(payment_status=payment_status)
    if query:
        rows = rows.filter(
            Q(description__icontains=query)
            | Q(payee__icontains=query)
            | Q(internal_notes__icontains=query)
        )
    rows = rows.order_by("-expense_date", "-id")
    paginator = Paginator(rows, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    totals = expense_totals(challenge, start, end, arm)
    return render(
        request,
        "tracker/expense_list.html",
        {
            "challenge": challenge,
            "page_obj": page_obj,
            "rows": page_obj.object_list,
            "start": start,
            "end": end,
            "arm": arm,
            "category_id": category_id,
            "payment_status": payment_status,
            "query": query,
            "arms": ARM.objects.filter(is_active=True),
            "categories": ExpenseCategory.objects.filter(is_active=True),
            "totals": totals,
            "total_count": paginator.count,
        },
    )


@login_required
def revenue_create(request):
    challenge = default_challenge()
    if not challenge:
        messages.error(request, "The challenge is not configured.")
        return redirect("dashboard")
    if request.method == "POST":
        form = RevenueTransactionForm(request.POST, challenge=challenge)
        if form.is_valid():
            txn = form.save()
            if txn.public_visibility and not txn.has_public_description:
                messages.warning(
                    request,
                    "This transaction is public but has no public description. A safe category-based summary will be shown until you add one.",
                )
            messages.success(request, "Revenue recorded and challenge totals recalculated.")
            return redirect("revenue_detail", pk=txn.pk)
    else:
        form = RevenueTransactionForm(challenge=challenge, initial={"challenge": challenge})
    return render(
        request,
        "tracker/revenue_form.html",
        {"form": form, "challenge": challenge, "title": "Record revenue"},
    )


@login_required
def revenue_edit(request, pk):
    txn = get_object_or_404(RevenueTransaction, pk=pk)
    form = RevenueTransactionForm(request.POST or None, instance=txn, challenge=txn.challenge)
    if request.method == "POST" and form.is_valid():
        txn = form.save()
        messages.success(request, "Revenue transaction updated. All affected totals were recalculated.")
        return redirect("revenue_detail", pk=txn.pk)
    return render(
        request,
        "tracker/revenue_form.html",
        {
            "form": form,
            "challenge": txn.challenge,

            "transaction": txn,
            "title": "Edit revenue transaction",
        },
    )


@login_required
def revenue_detail(request, pk):
    txn = get_object_or_404(RevenueTransaction.objects.select_related("challenge", "arm", "category"), pk=pk)
    return render(
        request,
        "tracker/revenue_detail.html",
        {
            "transaction": txn,
            "challenge": txn.challenge,

            "audit_entries": _audit_for("Revenue transaction", txn.pk),
        },
    )


@login_required
@require_POST
def revenue_action(request, pk, action):
    txn = get_object_or_404(RevenueTransaction, pk=pk)
    reason = (request.POST.get("reason") or "").strip()
    before = txn.get_status_display()
    if action == "void":
        txn.status = RevenueTransaction.Status.VOIDED
        txn.refunded_amount = Decimal("0.00")
        note = f"[Voided {timezone.localdate():%Y-%m-%d}] {reason}".strip()
    elif action == "refund":
        txn.status = RevenueTransaction.Status.REFUNDED
        txn.refunded_amount = txn.amount
        note = f"[Refunded {timezone.localdate():%Y-%m-%d}] {reason}".strip()
    elif action == "restore":
        txn.status = RevenueTransaction.Status.RECEIVED
        txn.refunded_amount = Decimal("0.00")
        note = f"[Restored {timezone.localdate():%Y-%m-%d}] {reason}".strip()
    else:
        messages.error(request, "Unknown transaction action.")
        return redirect("revenue_detail", pk=txn.pk)
    if note:
        txn.internal_notes = f"{txn.internal_notes}\n{note}".strip()
    try:
        txn.full_clean()
        txn.save()
    except Exception as exc:
        messages.error(request, f"The transaction could not be updated: {exc}")
        return redirect("revenue_detail", pk=txn.pk)
    messages.success(request, f"Revenue transaction changed from {before} to {txn.get_status_display()}. Totals recalculated.")
    return redirect("revenue_detail", pk=txn.pk)


@login_required
def expense_create(request):
    challenge = default_challenge()
    if not challenge:
        messages.error(request, "Configure the challenge in Settings before recording expenses.")
        return redirect("settings")
    if request.method == "POST":
        form = ExpenseForm(request.POST, request.FILES, challenge=challenge)
        if form.is_valid():
            expense = form.save()
            messages.success(request, "Expense recorded.")
            return redirect("expense_detail", pk=expense.pk)
    else:
        form = ExpenseForm(challenge=challenge, initial={"challenge": challenge})
    return render(
        request,
        "tracker/expense_form.html",
        {"form": form, "challenge": challenge, "title": "Record expense"},
    )


@login_required
def expense_edit(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    form = ExpenseForm(
        request.POST or None, request.FILES or None, instance=expense, challenge=expense.challenge
    )
    if request.method == "POST" and form.is_valid():
        expense = form.save()
        messages.success(request, "Expense updated.")
        return redirect("expense_detail", pk=expense.pk)
    return render(
        request,
        "tracker/expense_form.html",
        {
            "form": form,
            "challenge": expense.challenge,

            "expense": expense,
            "title": "Edit expense",
        },
    )


@login_required
def expense_detail(request, pk):
    expense = get_object_or_404(Expense.objects.select_related("challenge", "arm", "category"), pk=pk)
    return render(
        request,
        "tracker/expense_detail.html",
        {
            "expense": expense,
            "challenge": expense.challenge,

            "audit_entries": _audit_for("Expense", expense.pk),
        },
    )


@login_required
@require_POST
def expense_action(request, pk, action):
    expense = get_object_or_404(Expense, pk=pk)
    if action == "void":
        expense.is_voided = True
        expense.void_reason = (request.POST.get("reason") or "").strip()
        expense.save(update_fields=["is_voided", "void_reason", "updated_at"])
        messages.success(request, "Expense voided. It no longer affects dashboard expense totals.")
    elif action == "restore":
        expense.is_voided = False
        expense.void_reason = ""
        expense.save(update_fields=["is_voided", "void_reason", "updated_at"])
        messages.success(request, "Expense restored.")
    else:
        messages.error(request, "Unknown expense action.")
    return redirect("expense_detail", pk=expense.pk)


@login_required
def expense_receipt(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if not expense.receipt:
        raise Http404("No receipt attached.")
    file_path = os.path.abspath(expense.receipt.path)
    media_root = os.path.abspath(settings.MEDIA_ROOT)
    if not file_path.startswith(media_root + os.sep) or not os.path.exists(file_path):
        raise Http404("Receipt not found.")
    return FileResponse(open(file_path, "rb"), as_attachment=True, filename=os.path.basename(file_path))


@login_required
def movement_create(request):
    challenge = default_challenge()
    if not challenge:
        messages.error(request, "Configure the challenge in Settings before recording financial movements.")
        return redirect("settings")
    if request.method == "POST":
        form = OtherFinancialMovementForm(request.POST, challenge=challenge)
        if form.is_valid():
            movement = form.save()
            messages.success(
                request,
                "Other financial movement recorded. It does not count toward the revenue target.",
            )
            return redirect("movement_detail", pk=movement.pk)
    else:
        form = OtherFinancialMovementForm(challenge=challenge, initial={"challenge": challenge})
    return render(
        request,
        "tracker/movement_form.html",
        {
            "form": form,
            "challenge": challenge,
            "title": "Record other financial movement",
        },
    )


@login_required
def movement_edit(request, pk):
    movement = get_object_or_404(OtherFinancialMovement, pk=pk)
    form = OtherFinancialMovementForm(
        request.POST or None, instance=movement, challenge=movement.challenge
    )
    if request.method == "POST" and form.is_valid():
        movement = form.save()
        messages.success(request, "Financial movement updated.")
        return redirect("movement_detail", pk=movement.pk)
    return render(
        request,
        "tracker/movement_form.html",
        {
            "form": form,
            "challenge": movement.challenge,

            "movement": movement,
            "title": "Edit other financial movement",
        },
    )


@login_required
def movement_detail(request, pk):
    movement = get_object_or_404(
        OtherFinancialMovement.objects.select_related("challenge", "arm"), pk=pk
    )
    return render(
        request,
        "tracker/movement_detail.html",
        {
            "movement": movement,
            "challenge": movement.challenge,

            "audit_entries": _audit_for("Other financial movement", movement.pk),
        },
    )


@login_required
@require_POST
def movement_action(request, pk, action):
    movement = get_object_or_404(OtherFinancialMovement, pk=pk)
    if action == "void":
        movement.is_voided = True
        movement.void_reason = (request.POST.get("reason") or "").strip()
        movement.save(update_fields=["is_voided", "void_reason", "updated_at"])
        messages.success(request, "Financial movement voided.")
    elif action == "restore":
        movement.is_voided = False
        movement.void_reason = ""
        movement.save(update_fields=["is_voided", "void_reason", "updated_at"])
        messages.success(request, "Financial movement restored.")
    else:
        messages.error(request, "Unknown movement action.")
    return redirect("movement_detail", pk=movement.pk)


@login_required
def transaction_list(request):
    challenge = default_challenge()
    if not challenge:
        return render(
            request,
            "tracker/transactions.html",
            {"challenge": None, "page_obj": None, "transaction_rows": []},
        )
    start = _parse_date(request.GET.get("start"), challenge.start_date)
    end = _parse_date(request.GET.get("end"), challenge.end_date)
    if end < start:
        start, end = challenge.start_date, challenge.end_date
        messages.error(request, "The date range was invalid and has been reset.")
    arm = _parse_arm(request.GET.get("arm"))
    txn_type = request.GET.get("type", "all")
    public_filter = request.GET.get("public", "")
    query = (request.GET.get("q") or "").strip()
    category_filter = request.GET.get("category", "")

    rows = []
    if txn_type in ("all", "revenue"):
        qs = RevenueTransaction.objects.filter(
            challenge=challenge, transaction_date__gte=start, transaction_date__lte=end
        ).select_related("arm", "category")
        if arm:
            qs = qs.filter(arm=arm)
        if query:
            qs = qs.filter(
                Q(description__icontains=query)
                | Q(public_description__icontains=query)
                | Q(customer_name__icontains=query)
                | Q(reference__icontains=query)
                | Q(internal_notes__icontains=query)
            )
        if public_filter == "yes":
            qs = qs.filter(public_visibility=True)
        elif public_filter == "no":
            qs = qs.filter(public_visibility=False)
        if category_filter.startswith("revenue:"):
            qs = qs.filter(category_id=category_filter.split(":", 1)[1])
        for txn in qs:
            rows.append(
                {
                    "date": txn.transaction_date,
                    "type": "Revenue",
                    "kind": "revenue",
                    "arm": txn.arm.name,
                    "category": txn.category.name,
                    "description": txn.description,
                    "amount": txn.eligible_amount,
                    "currency": txn.currency,
                    "status": txn.get_status_display(),
                    "badge": txn.status_badge_class,
                    "public": txn.public_visibility,
                    "url": reverse("revenue_detail", args=[txn.pk]),
                    "edit_url": reverse("revenue_edit", args=[txn.pk]),
                    "is_voided": txn.status == RevenueTransaction.Status.VOIDED,
                }
            )
    if txn_type in ("all", "expense") and not category_filter.startswith("revenue:"):
        qs = Expense.objects.filter(
            challenge=challenge, expense_date__gte=start, expense_date__lte=end
        ).select_related("arm", "category")
        if arm:
            qs = qs.filter(arm=arm)
        if query:
            qs = qs.filter(
                Q(description__icontains=query)
                | Q(payee__icontains=query)
                | Q(internal_notes__icontains=query)
            )
        if category_filter.startswith("expense:"):
            qs = qs.filter(category_id=category_filter.split(":", 1)[1])
        if public_filter == "yes":
            qs = qs.none()
        for expense in qs:
            rows.append(
                {
                    "date": expense.expense_date,
                    "type": "Expense",
                    "kind": "expense",
                    "arm": expense.arm.name if expense.arm else "Shared / group",
                    "category": expense.category.name,
                    "description": expense.description,
                    "amount": expense.amount,
                    "currency": expense.currency,
                    "status": expense.status_label,
                    "badge": expense.status_badge_class,
                    "public": False,
                    "url": reverse("expense_detail", args=[expense.pk]),
                    "edit_url": reverse("expense_edit", args=[expense.pk]),
                    "is_voided": expense.is_voided,
                }
            )
    if txn_type in ("all", "other") and not category_filter.startswith("expense:"):
        qs = OtherFinancialMovement.objects.filter(
            challenge=challenge, movement_date__gte=start, movement_date__lte=end
        ).select_related("arm")
        if arm:
            qs = qs.filter(arm=arm)
        if query:
            qs = qs.filter(
                Q(description__icontains=query)
                | Q(reference__icontains=query)
                | Q(notes__icontains=query)
            )
        if public_filter == "yes":
            qs = qs.none()
        for movement in qs:
            rows.append(
                {
                    "date": movement.movement_date,
                    "type": "Other movement",
                    "kind": "movement",
                    "arm": movement.arm.name if movement.arm else "Shared / group",
                    "category": movement.get_movement_type_display(),
                    "description": movement.description,
                    "amount": movement.amount,
                    "currency": movement.currency,
                    "status": "Voided" if movement.is_voided else movement.get_movement_type_display(),
                    "badge": "text-bg-dark" if movement.is_voided else "text-bg-info",
                    "public": False,
                    "url": reverse("movement_detail", args=[movement.pk]),
                    "edit_url": reverse("movement_edit", args=[movement.pk]),
                    "is_voided": movement.is_voided,
                }
            )
    rows.sort(key=lambda row: (row["date"], row["amount"]), reverse=True)
    paginator = Paginator(rows, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    categories = []
    for item in RevenueCategory.objects.all():
        categories.append((f"revenue:{item.pk}", f"Revenue · {item.name}"))
    for item in ExpenseCategory.objects.all():
        categories.append((f"expense:{item.pk}", f"Expense · {item.name}"))
    return render(
        request,
        "tracker/transactions.html",
        {
            "challenge": challenge,
            "page_obj": page_obj,
            "transaction_rows": page_obj.object_list,
            "start": start,
            "end": end,
            "arm": arm,
            "arms": ARM.objects.filter(is_active=True),
            "txn_type": txn_type,
            "public_filter": public_filter,
            "query": query,
            "category_filter": category_filter,
            "categories": categories,
            "total_count": len(rows),
        },
    )


@login_required
def reports(request):
    challenge = default_challenge()
    if not challenge:
        return render(request, "tracker/reports.html", {"challenge": None})
    start = _parse_date(request.GET.get("start"), challenge.start_date)
    end = _parse_date(request.GET.get("end"), challenge.end_date)
    if end < start:
        start, end = challenge.start_date, challenge.end_date
        messages.error(request, "The report date range was invalid and has been reset.")
    arm = _parse_arm(request.GET.get("arm"))
    totals = challenge_totals(challenge, start=start, end=end, arm=arm)
    return render(
        request,
        "tracker/reports.html",
        {
            "challenge": challenge,
            "start": start,
            "end": end,
            "arm": arm,
            "arms": ARM.objects.filter(is_active=True),
            "totals": totals,
            "arm_rows": arm_breakdown(challenge, start, end, arm),
        },
    )


def _csv_safe(value):
    if value is None:
        return ""
    text = str(value)
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _csv_money(value):
    return f"{money(value):.2f}"


@login_required
def export_csv(request):
    challenge = default_challenge()
    if not challenge:
        messages.error(request, "Configure the challenge in Settings before exporting reports.")
        return redirect("settings")
    report = request.GET.get("report", "revenue")
    start = _parse_date(request.GET.get("start"), challenge.start_date)
    end = _parse_date(request.GET.get("end"), challenge.end_date)
    arm = _parse_arm(request.GET.get("arm"))
    revenue = qualifying_revenue_queryset(challenge, start, end, arm).select_related("arm", "category")
    expenses = expense_queryset(challenge, start, end, arm).select_related("arm", "category")
    movements = other_movement_queryset(challenge, start, end, arm).select_related("arm")
    totals = challenge_totals(challenge, start=start, end=end, arm=arm)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    filename = f"xonovate_{report}_{timezone.localdate():%Y%m%d}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")
    writer = csv.writer(response)

    if report == "overall":
        writer.writerow(["Xonovate Challenge Tracker — Overall challenge report"])
        writer.writerow(["Challenge", challenge.name])
        writer.writerow(["Period", f"{start.isoformat()} to {end.isoformat()}"])
        writer.writerow(["Currency", challenge.currency])
        writer.writerow(["Basis", "Target is measured using qualifying revenue actually collected during the challenge period."])
        writer.writerow([])
        writer.writerow(["Metric", "Value"])
        writer.writerow(["Target amount", _csv_money(challenge.target_amount)])
        writer.writerow(["Qualifying revenue collected", _csv_money(totals["revenue"])])
        writer.writerow(["Remaining target", _csv_money(totals["remaining_target"])])
        writer.writerow(["Percentage achieved", "" if totals["percentage_achieved"] is None else f"{totals['percentage_achieved']}%"])
        writer.writerow(["Expenses paid", _csv_money(totals["expenses_paid"])])
        writer.writerow(["Unpaid expense obligations", _csv_money(totals["expenses_unpaid"])])
        writer.writerow(["Other non-revenue inflows", _csv_money(totals["other_inflow"])])
        writer.writerow(["Other refunds paid", _csv_money(totals["other_refunds"])])
        writer.writerow(["Net cash movement (not accounting profit)", _csv_money(totals["net_cash_movement"])])
        writer.writerow(["Revenue transaction count", totals["revenue_transaction_count"]])
    elif report == "revenue":
        writer.writerow(["Date", "ARM", "Category", "Description", "Customer / payer", "Payment method", "Reference", "Amount", "Currency", "Status", "Public visibility", "Public description"])
        for txn in revenue:
            writer.writerow([
                txn.transaction_date.isoformat(),
                _csv_safe(txn.arm.name),
                _csv_safe(txn.category.name),
                _csv_safe(txn.description),
                _csv_safe(txn.customer_name),
                _csv_safe(txn.get_payment_method_display()),
                _csv_safe(txn.reference),
                _csv_money(txn.eligible_amount),
                txn.currency,
                txn.get_status_display(),
                "Yes" if txn.public_visibility else "No",
                _csv_safe(txn.public_description),
            ])
        writer.writerow([])
        writer.writerow(["Total qualifying revenue", _csv_money(revenue_total(challenge, start, end, arm))])
    elif report == "revenue_by_arm":
        writer.writerow(["ARM", "Qualifying revenue", "Currency"])
        for row in arm_breakdown(challenge, start, end, arm):
            writer.writerow([_csv_safe(row["name"]), _csv_money(row["total"]), challenge.currency])
        writer.writerow(["Total", _csv_money(revenue_total(challenge, start, end, arm)), challenge.currency])
    elif report == "revenue_by_category":
        writer.writerow(["Revenue category", "Qualifying revenue", "Currency"])
        for row in revenue_category_breakdown(challenge, start, end, arm):
            writer.writerow([_csv_safe(row["name"]), _csv_money(row["total"]), challenge.currency])
        writer.writerow(["Total", _csv_money(revenue_total(challenge, start, end, arm)), challenge.currency])
    elif report == "expenses":
        writer.writerow(["Date", "Category", "ARM / group", "Description", "Payee / vendor", "Payment method", "Payment status", "Amount", "Currency"])
        for expense in expenses:
            writer.writerow([
                expense.expense_date.isoformat(),
                _csv_safe(expense.category.name),
                _csv_safe(expense.arm.name if expense.arm else "Shared / group"),
                _csv_safe(expense.description),
                _csv_safe(expense.payee),
                _csv_safe(expense.get_payment_method_display()),
                expense.get_payment_status_display(),
                _csv_money(expense.amount),
                expense.currency,
            ])
        exp_totals = expense_totals(challenge, start, end, arm)
        writer.writerow([])
        writer.writerow(["Expenses paid", _csv_money(exp_totals["paid"])])
        writer.writerow(["Unpaid obligations", _csv_money(exp_totals["unpaid"])])
    elif report == "expense_by_category":
        writer.writerow(["Expense category", "Amount", "Currency"])
        for row in expense_category_breakdown(challenge, start, end, arm):
            writer.writerow([_csv_safe(row["name"]), _csv_money(row["total"]), challenge.currency])
        writer.writerow(["Total", _csv_money(expense_totals(challenge, start, end, arm)["paid"]), challenge.currency])
    elif report == "weekly":
        writer.writerow(["Week", "Week start", "Week end", "Weekly qualifying revenue", "Cumulative", "Currency"])
        for row in weekly_revenue(challenge, start, end, arm):
            writer.writerow([
                row["week"],
                row["start"].isoformat(),
                row["end"].isoformat(),
                _csv_money(row["total"]),
                _csv_money(row["cumulative"]),
                challenge.currency,
            ])
    elif report == "public":
        writer.writerow(["Date", "Public description", "ARM", "Revenue category", "Amount", "Currency"])
        for txn in revenue.filter(public_visibility=True):
            writer.writerow([
                txn.transaction_date.isoformat(),
                _csv_safe(txn.public_display_description),
                _csv_safe(txn.arm.name),
                _csv_safe(txn.category.name),
                _csv_money(txn.eligible_amount),
                txn.currency,
            ])
    elif report == "transactions":
        writer.writerow(["Date", "Type", "ARM / group", "Category", "Description", "Amount", "Currency", "Status", "Public", "Reference"])
        for txn in revenue:
            writer.writerow([
                txn.transaction_date.isoformat(), "Revenue", _csv_safe(txn.arm.name), _csv_safe(txn.category.name),
                _csv_safe(txn.description), _csv_money(txn.eligible_amount), txn.currency,
                txn.get_status_display(), "Yes" if txn.public_visibility else "No", _csv_safe(txn.reference),
            ])
        for expense in expenses:
            writer.writerow([
                expense.expense_date.isoformat(), "Expense", _csv_safe(expense.arm.name if expense.arm else "Shared / group"),
                _csv_safe(expense.category.name), _csv_safe(expense.description), _csv_money(expense.amount),
                expense.currency, expense.get_payment_status_display(), "No", "",
            ])
        for movement in movements:
            writer.writerow([
                movement.movement_date.isoformat(), "Other movement", _csv_safe(movement.arm.name if movement.arm else "Shared / group"),
                _csv_safe(movement.get_movement_type_display()), _csv_safe(movement.description), _csv_money(movement.amount),
                movement.currency, "Voided" if movement.is_voided else movement.get_movement_type_display(), "No", _csv_safe(movement.reference),
            ])
    else:
        messages.error(request, "Unknown report type.")
        return redirect("reports")
    return response


def _scenario_from_form(cleaned):
    result = calculate_scenario(
        target=cleaned["target"],
        days=cleaned["days"],
        average_sale_price=cleaned["average_sale_price"],
        sales_per_day=cleaned["sales_per_day"],
        working_days_per_week=cleaned["working_days_per_week"],
        delivery_cost_per_sale=cleaned.get("delivery_cost_per_sale") or ZERO,
        collection_delay_days=cleaned.get("collection_delay_days") or 0,
    )
    return result


def _scenario_comparison_row(result):
    return {
        "label": f"{result['days']} days · {result['sales_per_day']} sales/day · {CURRENCY_SYMBOL}{result['average_sale_price']:,.2f}",
        "expected_sales": f"{result['expected_sales']:,.2f}",
        "gross_projected": f"{result['gross_projected']:,.2f}",
        "expected_collections": f"{result['expected_collections']:,.2f}",
        "delivery_costs": f"{result['delivery_costs']:,.2f}",
        "contribution": f"{result['contribution']:,.2f}",
        "remaining_required": f"{result['remaining_required']:,.2f}",
        "target_achieved": result["target_achieved"],
    }


@login_required
def simulator(request):
    scenarios = request.session.get("simulator_scenarios", [])
    if request.method == "POST" and request.POST.get("action") == "clear":
        request.session["simulator_scenarios"] = []
        messages.success(request, "Saved scenario comparisons cleared.")
        return redirect("simulator")

    scenario = None
    form = SimulatorForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            scenario = _scenario_from_form(form.cleaned_data)
            if form.cleaned_data.get("save_scenario"):
                row = _scenario_comparison_row(scenario)
                scenarios.append(row)
                request.session["simulator_scenarios"] = scenarios[-5:]
                scenarios = request.session["simulator_scenarios"]
                messages.success(request, "Scenario added to the comparison list. It remains simulated only.")
            else:
                scenarios = request.session.get("simulator_scenarios", [])
    return render(
        request,
        "tracker/simulator.html",
        {
            "form": form,
            "scenario": scenario,
            "baseline_rows": baseline_scenarios(),
            "scenarios": scenarios,
        },
    )


def _public_challenge_data(challenge, today):
    if today < challenge.start_date:
        phase = "upcoming"
        status_label = "Upcoming"
        current_day = 0
        days_remaining = challenge.duration_days
        days_until_start = (challenge.start_date - today).days
    elif today > challenge.end_date:
        phase = "completed"
        status_label = "Completed"
        current_day = challenge.duration_days
        days_remaining = 0
        days_until_start = 0
    elif challenge.status == Challenge.Status.PAUSED:
        phase = "paused"
        status_label = "Paused"
        current_day = challenge.day_number(today)
        days_remaining = challenge.days_remaining(today)
        days_until_start = 0
    elif challenge.status == Challenge.Status.COMPLETED:
        phase = "completed"
        status_label = "Completed"
        current_day = challenge.day_number(today)
        days_remaining = challenge.days_remaining(today)
        days_until_start = 0
    else:
        phase = "active"
        status_label = "Active"
        current_day = challenge.day_number(today)
        days_remaining = challenge.days_remaining(today)
        days_until_start = 0
    return {
        "name": challenge.name,
        "description": challenge.description,
        "start_date": challenge.start_date,
        "end_date": challenge.end_date,
        "duration": challenge.duration_days,
        "currency": challenge.currency,
        "phase": phase,
        "status_label": status_label,
        "current_day": current_day,
        "days_remaining": days_remaining,
        "days_until_start": days_until_start,
    }


def _public_transaction_rows(challenge, limit=30):
    qs = (
        qualifying_revenue_queryset(challenge)
        .filter(public_visibility=True)
        .select_related("arm")
        .order_by("-transaction_date", "-id")
    )
    total_count = qs.count()
    rows = [
        {
            "date": txn.transaction_date,
            "arm": txn.arm.name,
            "description": txn.public_display_description,
            "amount": txn.eligible_amount,
        }
        for txn in qs[:limit]
    ]
    return rows, total_count


def public_progress(request):
    challenge = public_challenge()
    if not challenge:
        return render(request, "tracker/public_empty.html")
    today = timezone.localdate()
    totals = challenge_totals(challenge)
    progress = challenge_progress(challenge, revenue=totals["revenue"])
    transactions, public_count = _public_transaction_rows(challenge)
    weeks = weekly_revenue(challenge)
    elapsed_weeks = [week for week in weeks if week["start"] <= today]
    current_week = next(
        (week for week in elapsed_weeks if week["end"] >= today),
        elapsed_weeks[-1] if elapsed_weeks else None,
    )
    month_start = max(today.replace(day=1), challenge.start_date)
    next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
    month_end = min(next_month - timedelta(days=1), challenge.end_date)
    month_revenue = (
        revenue_total(challenge, month_start, month_end)
        if month_start <= month_end
        else ZERO
    )
    return render(
        request,
        "tracker/public_progress.html",
        {
            "public_challenge": _public_challenge_data(challenge, today),
            "progress": progress,
            "arm_rows": arm_breakdown(challenge),
            "public_transactions": transactions,
            "recent_weeks": list(reversed(elapsed_weeks[-6:])),
            "current_week": current_week,
            "month_revenue": month_revenue,
            "public_count": public_count,
            "today": today,
        },
    )


@login_required
def workspace_settings(request):
    challenge = default_challenge()
    form = ChallengeSettingsForm(request.POST or None, instance=challenge)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Challenge settings updated.")
        return redirect("settings")
    return render(
        request,
        "tracker/settings.html",
        {
            "challenge": challenge,
            "form": form,
            "arms": ARM.objects.filter(is_active=True),
            "revenue_categories": RevenueCategory.objects.all(),
            "expense_categories": ExpenseCategory.objects.all(),
        },
    )


@login_required
def revenue_category_create(request):
    form = RevenueCategoryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Revenue category created.")
        return redirect("settings")
    return render(
        request,
        "tracker/simple_form.html",
        {"form": form, "title": "Create revenue category"},
    )


@login_required
def revenue_category_edit(request, pk):
    category = get_object_or_404(RevenueCategory, pk=pk)
    form = RevenueCategoryForm(request.POST or None, instance=category)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Revenue category updated.")
        return redirect("settings")
    return render(
        request,
        "tracker/simple_form.html",
        {"form": form, "title": f"Edit {category.name}"},
    )


@login_required
def expense_category_create(request):
    form = ExpenseCategoryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Expense category created.")
        return redirect("settings")
    return render(
        request,
        "tracker/simple_form.html",
        {"form": form, "title": "Create expense category"},
    )


@login_required
def expense_category_edit(request, pk):
    category = get_object_or_404(ExpenseCategory, pk=pk)
    form = ExpenseCategoryForm(request.POST or None, instance=category)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Expense category updated.")
        return redirect("settings")
    return render(
        request,
        "tracker/simple_form.html",
        {"form": form, "title": f"Edit {category.name}"},
    )



