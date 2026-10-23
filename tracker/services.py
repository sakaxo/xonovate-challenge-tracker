from datetime import timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from django.db.models import DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce
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

ZERO = Decimal("0.00")
HUNDRED = Decimal("100")
CURRENCY_SYMBOL = "GH\u20b5"
DEFAULT_CHALLENGE_NAME = "Building Xonovate: 100 Days to GH\u20b5" + "200,000"
CHART_COLORS = [
    "#0f766e",
    "#2563eb",
    "#d97706",
    "#7c3aed",
    "#dc2626",
    "#0891b2",
    "#65a30d",
    "#db2777",
    "#475569",
    "#ea580c",
]


def money(value):
    if value is None:
        return ZERO
    return Decimal(value).quantize(Decimal("0.01"))


def percentage(value, target):
    if not target or target <= 0:
        return None
    return (Decimal(value) / Decimal(target) * HUNDRED).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def default_challenge():
    qs = Challenge.objects.exclude(status=Challenge.Status.ARCHIVED)
    challenge = qs.filter(name=DEFAULT_CHALLENGE_NAME).first()
    if challenge:
        return challenge
    return qs.order_by("start_date", "pk").first()


def public_challenge():
    return default_challenge()


def qualifying_revenue_queryset(challenge, start=None, end=None, arm=None):
    """Revenue that counts toward the target, constrained to the challenge period."""
    qs = RevenueTransaction.objects.filter(
        challenge=challenge,
        status__in=[
            RevenueTransaction.Status.RECEIVED,
            RevenueTransaction.Status.PARTIALLY_REFUNDED,
        ],
        transaction_date__gte=challenge.start_date,
        transaction_date__lte=challenge.end_date,
    )
    if start:
        qs = qs.filter(transaction_date__gte=start)
    if end:
        qs = qs.filter(transaction_date__lte=end)
    if arm:
        qs = qs.filter(arm=arm)
    return qs.annotate(
        eligible_amount_value=Coalesce(
            F("amount") - F("refunded_amount"),
            Value(ZERO),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
    )


def revenue_total(challenge, start=None, end=None, arm=None):
    qs = qualifying_revenue_queryset(challenge, start, end, arm)
    result = qs.aggregate(total=Coalesce(Sum("eligible_amount_value"), Value(ZERO)))
    return money(result["total"])


def expense_queryset(challenge, start=None, end=None, arm=None, include_voided=False):
    qs = Expense.objects.filter(
        challenge=challenge,
        expense_date__gte=challenge.start_date,
        expense_date__lte=challenge.end_date,
    )
    if not include_voided:
        qs = qs.filter(is_voided=False)
    if start:
        qs = qs.filter(expense_date__gte=start)
    if end:
        qs = qs.filter(expense_date__lte=end)
    if arm:
        qs = qs.filter(arm=arm)
    return qs


def expense_totals(challenge, start=None, end=None, arm=None):
    qs = expense_queryset(challenge, start, end, arm)
    paid = qs.filter(payment_status=Expense.PaymentStatus.PAID).aggregate(
        total=Coalesce(Sum("amount"), Value(ZERO))
    )["total"]
    unpaid = qs.filter(payment_status=Expense.PaymentStatus.UNPAID).aggregate(
        total=Coalesce(Sum("amount"), Value(ZERO))
    )["total"]
    return {"paid": money(paid), "unpaid": money(unpaid)}


def other_movement_queryset(challenge, start=None, end=None, arm=None):
    qs = OtherFinancialMovement.objects.filter(
        challenge=challenge,
        is_voided=False,
        movement_date__gte=challenge.start_date,
        movement_date__lte=challenge.end_date,
    )
    if start:
        qs = qs.filter(movement_date__gte=start)
    if end:
        qs = qs.filter(movement_date__lte=end)
    if arm:
        qs = qs.filter(arm=arm)
    return qs


def other_movement_totals(challenge, start=None, end=None, arm=None):
    qs = other_movement_queryset(challenge, start, end, arm)
    inflow_types = OtherFinancialMovement.INFLOW_TYPES
    inflow = qs.filter(movement_type__in=inflow_types).aggregate(
        total=Coalesce(Sum("amount"), Value(ZERO))
    )["total"]
    refunds = qs.filter(movement_type=OtherFinancialMovement.MovementType.REFUND_PAID).aggregate(
        total=Coalesce(Sum("amount"), Value(ZERO))
    )["total"]
    transfers = qs.filter(
        movement_type=OtherFinancialMovement.MovementType.INTERNAL_TRANSFER
    ).aggregate(total=Coalesce(Sum("amount"), Value(ZERO)))["total"]
    return {
        "inflow": money(inflow),
        "refunds_paid": money(refunds),
        "transfers": money(transfers),
        "net_cash_effect": money(inflow - refunds),
    }


def challenge_totals(challenge, as_of=None, start=None, end=None, arm=None):
    revenue = revenue_total(challenge, start, end, arm)
    expenses = expense_totals(challenge, start, end, arm)
    others = other_movement_totals(challenge, start, end, arm)
    revenue_qs = qualifying_revenue_queryset(challenge, start, end, arm)
    txn_count = revenue_qs.count()
    net_cash = revenue + others["net_cash_effect"] - expenses["paid"]
    return {
        "revenue": revenue,
        "expenses_paid": expenses["paid"],
        "expenses_unpaid": expenses["unpaid"],
        "other_inflow": others["inflow"],
        "other_refunds": others["refunds_paid"],
        "other_transfers": others["transfers"],
        "other_net_effect": others["net_cash_effect"],
        "net_cash_movement": money(net_cash),
        "revenue_transaction_count": txn_count,
        "target": money(challenge.target_amount),
        "remaining_target": money(max(challenge.target_amount - revenue, ZERO)),
        "percentage_achieved": percentage(revenue, challenge.target_amount),
    }


def challenge_progress(challenge, as_of=None, revenue=None):
    as_of = as_of or timezone.localdate()
    revenue = challenge_totals(challenge)["revenue"] if revenue is None else money(revenue)
    target = money(challenge.target_amount)
    elapsed = challenge.days_elapsed(as_of)
    remaining_days = challenge.days_remaining(as_of)
    remaining_target = money(max(target - revenue, ZERO))
    avg_daily_achieved = money(revenue / elapsed) if elapsed > 0 else ZERO
    avg_daily_required = None
    if target > 0 and remaining_target > 0 and remaining_days > 0:
        avg_daily_required = money(remaining_target / remaining_days)
    elif target > 0 and remaining_target == 0:
        avg_daily_required = ZERO
    return {
        "as_of": as_of,
        "revenue": revenue,
        "target": target,
        "remaining_target": remaining_target,
        "percentage": percentage(revenue, target),
        "duration": challenge.duration_days,
        "current_day": challenge.day_number(as_of),
        "days_elapsed": elapsed,
        "days_remaining": remaining_days,
        "average_daily_achieved": avg_daily_achieved,
        "average_daily_required": avg_daily_required,
    }


def _grouped_revenue(challenge, start=None, end=None, arm=None):
    qs = qualifying_revenue_queryset(challenge, start, end, arm)
    return {
        row["transaction_date"]: money(row["total"])
        for row in qs.values("transaction_date")
        .annotate(total=Coalesce(Sum("eligible_amount_value"), Value(ZERO)))
        .order_by("transaction_date")
    }


def weekly_revenue(challenge, start=None, end=None, arm=None):
    start = start or challenge.start_date
    end = end or challenge.end_date
    if end < start:
        return []
    grouped = _grouped_revenue(challenge, start, end, arm)
    weeks = []
    cursor = start
    index = 1
    running = ZERO
    while cursor <= end:
        week_end = min(cursor + timedelta(days=6), end)
        total = sum(
            (amount for day, amount in grouped.items() if cursor <= day <= week_end),
            ZERO,
        )
        running += total
        weeks.append(
            {
                "week": index,
                "start": cursor,
                "end": week_end,
                "label": f"{cursor.strftime('%d %b')} – {week_end.strftime('%d %b')}",
                "total": money(total),
                "cumulative": money(running),
            }
        )
        cursor = week_end + timedelta(days=1)
        index += 1
    return weeks


def arm_breakdown(challenge, start=None, end=None, arm=None):
    qs = qualifying_revenue_queryset(challenge, start, end, arm)
    totals = {
        row["arm_id"]: money(row["total"])
        for row in qs.values("arm_id")
        .annotate(total=Coalesce(Sum("eligible_amount_value"), Value(ZERO)))
    }
    rows = []
    for index, item in enumerate(ARM.objects.all()):
        total = totals.get(item.id, ZERO)
        if total > 0 or item.is_active:
            rows.append(
                {
                    "name": item.name,
                    "total": total,
                    "color": CHART_COLORS[index % len(CHART_COLORS)],
                    "is_active": item.is_active,
                }
            )
    return sorted(rows, key=lambda row: row["total"], reverse=True)


def revenue_category_breakdown(challenge, start=None, end=None, arm=None):
    qs = qualifying_revenue_queryset(challenge, start, end, arm)
    totals = {
        row["category_id"]: money(row["total"])
        for row in qs.values("category_id")
        .annotate(total=Coalesce(Sum("eligible_amount_value"), Value(ZERO)))
    }
    rows = []
    for index, item in enumerate(RevenueCategory.objects.all()):
        total = totals.get(item.id, ZERO)
        if total > 0:
            rows.append(
                {
                    "name": item.name,
                    "total": total,
                    "color": CHART_COLORS[index % len(CHART_COLORS)],
                }
            )
    return sorted(rows, key=lambda row: row["total"], reverse=True)


def expense_category_breakdown(challenge, start=None, end=None, arm=None):
    qs = expense_queryset(challenge, start, end, arm)
    totals = {
        row["category_id"]: money(row["total"])
        for row in qs.values("category_id").annotate(
            total=Coalesce(Sum("amount"), Value(ZERO))
        )
    }
    rows = []
    for index, item in enumerate(ExpenseCategory.objects.all()):
        total = totals.get(item.id, ZERO)
        if total > 0:
            rows.append(
                {
                    "name": item.name,
                    "total": total,
                    "color": CHART_COLORS[index % len(CHART_COLORS)],
                }
            )
    return sorted(rows, key=lambda row: row["total"], reverse=True)


def recent_activity(challenge, start=None, end=None, arm=None, limit=12):
    revenue = qualifying_revenue_queryset(challenge, start, end, arm)
    expenses = expense_queryset(challenge, start, end, arm)
    movements = other_movement_queryset(challenge, start, end, arm)
    if arm:
        movements = movements.filter(arm=arm)
    items = []
    for txn in revenue.order_by("-transaction_date", "-id")[:limit]:
        items.append(
            {
                "date": txn.transaction_date,
                "type": "Revenue",
                "arm": txn.arm.name,
                "category": txn.category.name,
                "description": txn.description,
                "amount": txn.eligible_amount,
                "status": txn.get_status_display(),
                "public": txn.public_visibility,
                "url": f"/revenue/{txn.pk}/",
                "kind": "revenue",
            }
        )
    for expense in expenses.order_by("-expense_date", "-id")[:limit]:
        items.append(
            {
                "date": expense.expense_date,
                "type": "Expense",
                "arm": expense.arm.name if expense.arm else "Shared / group",
                "category": expense.category.name,
                "description": expense.description,
                "amount": expense.amount,
                "status": expense.status_label,
                "public": False,
                "url": f"/expenses/{expense.pk}/",
                "kind": "expense",
            }
        )
    for movement in movements.order_by("-movement_date", "-id")[:limit]:
        items.append(
            {
                "date": movement.movement_date,
                "type": "Other movement",
                "arm": movement.arm.name if movement.arm else "Shared / group",
                "category": movement.get_movement_type_display(),
                "description": movement.description,
                "amount": movement.amount,
                "status": "Voided" if movement.is_voided else movement.get_movement_type_display(),
                "public": False,
                "url": f"/finance/{movement.pk}/",
                "kind": "movement",
            }
        )
    items.sort(key=lambda item: (item["date"], item["amount"]), reverse=True)
    return items[:limit]


def _working_days_in(days, working_days_per_week):
    if days <= 0:
        return 0
    weeks, extra = divmod(days, 7)
    return weeks * working_days_per_week + min(extra, working_days_per_week)


def calculate_scenario(
    target,
    days,
    average_sale_price,
    sales_per_day,
    working_days_per_week=7,
    delivery_cost_per_sale=ZERO,
    collection_delay_days=0,
):
    target = Decimal(target)
    days = int(days)
    average_sale_price = Decimal(average_sale_price)
    sales_per_day = Decimal(sales_per_day)
    working_days_per_week = int(working_days_per_week)
    delivery_cost_per_sale = Decimal(delivery_cost_per_sale or 0)
    collection_delay_days = int(collection_delay_days)

    available_working_days = _working_days_in(days, working_days_per_week)
    expected_sales = sales_per_day * available_working_days
    gross_projected = expected_sales * average_sale_price

    collectible_days = max(days - collection_delay_days, 0)
    collectible_working_days = _working_days_in(collectible_days, working_days_per_week)
    collectible_sales = sales_per_day * collectible_working_days
    expected_collections = collectible_sales * average_sale_price

    delivery_costs = expected_sales * delivery_cost_per_sale
    contribution = gross_projected - delivery_costs

    remaining = max(target - gross_projected, ZERO)
    if average_sale_price > 0:
        sales_needed = int((target / average_sale_price).to_integral_value(rounding=ROUND_CEILING))
    else:
        sales_needed = 0

    return {
        "target": money(target),
        "days": days,
        "average_sale_price": money(average_sale_price),
        "sales_per_day": sales_per_day.quantize(Decimal("0.01")),
        "working_days_per_week": working_days_per_week,
        "delivery_cost_per_sale": money(delivery_cost_per_sale),
        "collection_delay_days": collection_delay_days,
        "available_working_days": available_working_days,
        "expected_sales": expected_sales.quantize(Decimal("0.01")),
        "gross_projected": money(gross_projected),
        "expected_collections": money(expected_collections),
        "delivery_costs": money(delivery_costs),
        "contribution": money(contribution),
        "remaining_required": money(remaining),
        "sales_needed": sales_needed,
        "target_achieved": gross_projected >= target,
    }


def baseline_scenarios():
    target = Decimal("200000.00")
    rows = []
    for count, price in [(100, "1500"), (100, "2000"), (100, "2500"), (134, "1500"), (80, "2500")]:
        total = Decimal(count) * Decimal(price)
        rows.append(
            {
                "count": count,
                "price": Decimal(price),
                "total": money(total),
                "target": money(target),
                "surplus": money(total - target),
                "shortfall": money(max(target - total, ZERO)),
                "reaches_target": total >= target,
            }
        )
    return rows


