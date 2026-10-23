from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from .models import (
    ARM,
    Challenge,
    Expense,
    ExpenseCategory,
    OtherFinancialMovement,
    RevenueCategory,
    RevenueTransaction,
)
from .services import (
    baseline_scenarios,
    calculate_scenario,
    challenge_progress,
    challenge_totals,
    revenue_total,
)


class TrackerTestBase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user("founder", password="test-pass-123")
        self.client.force_login(self.user)
        self.challenge = Challenge.objects.get(
            name="Building Xonovate: 100 Days to GH\u20b5200,000"
        )
        self.tech = ARM.objects.get(name="Xonovate Technologies")
        self.code = ARM.objects.get(name="Xonovate Code Champions")
        self.revenue_category = RevenueCategory.objects.get(name="Website development")
        self.expense_category = ExpenseCategory.objects.get(name="Software subscriptions")

    def make_revenue(self, amount="1000.00", arm=None, day=None, **kwargs):
        return RevenueTransaction.objects.create(
            challenge=kwargs.pop("challenge", self.challenge),
            transaction_date=day or self.challenge.start_date,
            amount=Decimal(amount),
            currency="GHS",
            arm=arm or self.tech,
            category=kwargs.pop("category", self.revenue_category),
            description=kwargs.pop("description", "Website development payment received from a business customer."),
            payment_method="mobile_money",
            **kwargs,
        )

    def make_expense(self, amount="200.00", **kwargs):
        return Expense.objects.create(
            challenge=kwargs.pop("challenge", self.challenge),
            expense_date=kwargs.pop("expense_date", self.challenge.start_date),
            amount=Decimal(amount),
            currency="GHS",
            category=kwargs.pop("category", self.expense_category),
            description=kwargs.pop("description", "Monthly software subscription."),
            payment_status=kwargs.pop("payment_status", "paid"),
            **kwargs,
        )


class InitialChallengeTests(TrackerTestBase):
    def test_initial_challenge_dates_and_target(self):
        self.assertEqual(self.challenge.start_date, date(2026, 10, 24))
        self.assertEqual(self.challenge.end_date, date(2027, 1, 31))
        self.assertEqual(self.challenge.target_amount, Decimal("200000.00"))
        self.assertEqual(self.challenge.currency, "GHS")

    def test_challenge_duration_is_inclusive_100_days(self):
        self.assertEqual(self.challenge.duration_days, 100)

    def test_initial_challenge_is_featured_on_public_page(self):
        self.assertTrue(self.challenge.is_public_featured)

    def test_only_two_business_units_are_active(self):
        self.assertEqual(ARM.objects.filter(is_active=True).count(), 2)
        self.assertEqual(
            set(ARM.objects.filter(is_active=True).values_list("name", flat=True)),
            {"Xonovate Technologies", "Xonovate Code Champions"},
        )
        self.assertFalse(ARM.objects.get(name="Other Xonovate Business Activities").is_active)
        self.assertTrue(RevenueCategory.objects.filter(name="Code Champions school engagements").exists())
        self.assertTrue(ExpenseCategory.objects.filter(name="Internet and mobile data").exists())


class ChallengeSettingsTests(TrackerTestBase):
    def test_settings_update_the_single_existing_challenge(self):
        response = self.client.post(
            reverse("settings"),
            {
                "description": "Updated public challenge summary.",
                "start_date": "2026-10-24",
                "end_date": "2027-01-31",
                "target_amount": "250000.00",
                "status": "active",
            },
        )
        self.assertRedirects(response, reverse("settings"))
        self.assertEqual(Challenge.objects.count(), 1)
        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.description, "Updated public challenge summary.")
        self.assertEqual(self.challenge.target_amount, Decimal("250000.00"))
        self.assertEqual(self.challenge.status, Challenge.Status.ACTIVE)

    def test_settings_reject_invalid_date_range(self):
        response = self.client.post(
            reverse("settings"),
            {
                "description": "",
                "start_date": "2027-03-01",
                "end_date": "2027-02-01",
                "target_amount": "1000.00",
                "status": "active",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "end_date",
            "End date cannot be earlier than the start date.",
        )
        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.start_date, date(2026, 10, 24))

    def test_challenge_management_routes_are_not_available(self):
        for name in (
            "challenges",
            "challenge_create",
            "challenge_edit",
            "challenge_action",
            "challenge_detail",
        ):
            with self.subTest(name=name):
                with self.assertRaises(NoReverseMatch):
                    reverse(name, args=[self.challenge.pk])

    def test_feature_flag_does_not_change_public_challenge(self):
        other = Challenge.objects.create(
            name="Ignored featured challenge",
            description="This record must not control the public page.",
            start_date=date(2027, 2, 1),
            end_date=date(2027, 5, 11),
            target_amount=Decimal("75000.00"),
            currency="GHS",
            status="planned",
            is_public_featured=True,
        )
        self.client.logout()
        response = self.client.get(reverse("public_progress"))
        self.assertContains(response, self.challenge.name)
        self.assertNotContains(response, other.name)

    def test_zero_target_progress_has_no_division_error(self):
        self.challenge.target_amount = Decimal("0.00")
        self.challenge.save()
        metrics = challenge_progress(self.challenge)
        self.assertIsNone(metrics["percentage"])
        self.assertEqual(metrics["target"], Decimal("0.00"))
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

class RevenueWorkflowTests(TrackerTestBase):
    def test_progress_updates_when_revenue_recorded(self):
        self.make_revenue("12500.00")
        self.assertEqual(revenue_total(self.challenge), Decimal("12500.00"))
        totals = challenge_totals(self.challenge)
        self.assertEqual(totals["revenue"], Decimal("12500.00"))
        self.assertEqual(totals["remaining_target"], Decimal("187500.00"))
        self.assertEqual(totals["percentage_achieved"], Decimal("6.3"))
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "12,500.00")

    def test_revenue_is_assigned_to_selected_arm(self):
        self.make_revenue("3000.00", arm=self.code)
        self.make_revenue("2000.00", arm=self.tech)
        self.assertEqual(revenue_total(self.challenge, arm=self.code), Decimal("3000.00"))
        self.assertEqual(revenue_total(self.challenge, arm=self.tech), Decimal("2000.00"))

    def test_non_revenue_receipts_do_not_count_toward_target(self):
        self.make_revenue("1000.00")
        OtherFinancialMovement.objects.create(
            challenge=self.challenge,
            movement_type="loan_received",
            movement_date=self.challenge.start_date,
            amount=Decimal("50000.00"),
            currency="GHS",
            description="Loan received for working capital.",
        )
        self.assertEqual(revenue_total(self.challenge), Decimal("1000.00"))
        totals = challenge_totals(self.challenge)
        self.assertEqual(totals["other_inflow"], Decimal("50000.00"))
        self.assertEqual(totals["revenue"], Decimal("1000.00"))

    def test_partial_collection_is_counted_at_amount_received(self):
        self.make_revenue("4000.00", description="Partial deposit for website project.")
        self.assertEqual(revenue_total(self.challenge), Decimal("4000.00"))

    def test_expenses_are_separate_from_revenue_target(self):
        self.make_revenue("10000.00")
        self.make_expense("2500.00")
        totals = challenge_totals(self.challenge)
        self.assertEqual(totals["revenue"], Decimal("10000.00"))
        self.assertEqual(totals["remaining_target"], Decimal("190000.00"))
        self.assertEqual(totals["expenses_paid"], Decimal("2500.00"))
        self.assertEqual(totals["net_cash_movement"], Decimal("7500.00"))

    def test_refunds_voids_and_partial_refunds_update_totals(self):
        txn = self.make_revenue("1000.00")
        txn.status = RevenueTransaction.Status.REFUNDED
        txn.refunded_amount = Decimal("1000.00")
        txn.full_clean()
        txn.save()
        self.assertEqual(revenue_total(self.challenge), Decimal("0.00"))

        txn.status = RevenueTransaction.Status.PARTIALLY_REFUNDED
        txn.refunded_amount = Decimal("300.00")
        txn.full_clean()
        txn.save()
        self.assertEqual(revenue_total(self.challenge), Decimal("700.00"))

        txn.status = RevenueTransaction.Status.VOIDED
        txn.refunded_amount = Decimal("0.00")
        txn.full_clean()
        txn.save()
        self.assertEqual(revenue_total(self.challenge), Decimal("0.00"))

    def test_transaction_is_not_counted_twice_and_reference_is_unique(self):
        self.make_revenue("5000.00", reference="UNIQUE-001")
        self.assertEqual(revenue_total(self.challenge), Decimal("5000.00"))
        duplicate = RevenueTransaction(
            challenge=self.challenge,
            transaction_date=self.challenge.start_date,
            amount=Decimal("5000.00"),
            currency="GHS",
            arm=self.tech,
            category=self.revenue_category,
            description="A second entry with the same reference.",
            payment_method="mobile_money",
            reference="UNIQUE-001",
        )
        with self.assertRaises(Exception):
            duplicate.full_clean()
        self.assertEqual(revenue_total(self.challenge), Decimal("5000.00"))

    def test_revenue_form_records_public_fields(self):
        response = self.client.post(
            reverse("revenue_create"),
            {
                "transaction_date": self.challenge.start_date.isoformat(),
                "amount": "8000.00",
                "currency": "GHS",
                "arm": self.tech.pk,
                "category": self.revenue_category.pk,
                "description": "Internal factual description.",
                "customer_name": "Private Customer Ltd",
                "payment_method": "mobile_money",
                "reference": "PAY-88",
                "public_visibility": "on",
                "public_description": "Website development payment received.",
                "internal_notes": "Sensitive internal note.",
                "status": "received",
                "refunded_amount": "0.00",
            },
        )
        self.assertEqual(response.status_code, 302)
        txn = RevenueTransaction.objects.get(reference="PAY-88")
        self.assertTrue(txn.public_visibility)
        self.assertEqual(txn.public_description, "Website development payment received.")
        self.assertEqual(txn.internal_notes, "Sensitive internal note.")


class PublicPrivacyTests(TrackerTestBase):
    def test_public_visibility_and_internal_notes_are_respected(self):
        self.make_revenue(
            "1500.00",
            public_visibility=True,
            public_description="Approved public website payment.",
            internal_notes="CONFIDENTIAL-INTERNAL-NOTE",
            customer_name="Secret Customer",
            reference="SECRET-REFERENCE",
            description="Private internal description only.",
        )
        self.make_revenue(
            "999.00",
            public_visibility=False,
            public_description="SHOULD NOT APPEAR PRIVATE.",
            description="Private revenue description.",
        )
        response = self.client.get(reverse("public_progress"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Approved public website payment.")
        self.assertNotContains(response, "CONFIDENTIAL-INTERNAL-NOTE")
        self.assertNotContains(response, "Secret Customer")
        self.assertNotContains(response, "SECRET-REFERENCE")
        self.assertNotContains(response, "Private internal description only.")
        self.assertNotContains(response, "SHOULD NOT APPEAR PRIVATE.")
        self.assertContains(response, "approved transaction", count=1)

    def test_public_description_fallback_is_safe(self):
        self.make_revenue(
            "1200.00",
            public_visibility=True,
            public_description="",
            customer_name="Do Not Show",
            reference="HIDDEN-REF",
        )
        response = self.client.get(reverse("public_progress"))
        self.assertContains(response, "Website development revenue received.")
        self.assertNotContains(response, "Do Not Show")
        self.assertNotContains(response, "HIDDEN-REF")

    def test_public_landing_is_available_without_authentication(self):
        self.client.logout()
        response = self.client.get(reverse("public_progress"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.challenge.name)
        self.assertContains(response, "Sign in")
        self.assertNotContains(response, "Django Admin")
        self.assertNotContains(response, "PLC")

    def test_private_dashboard_requires_authentication(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_public_context_contains_only_safe_presentation_data(self):
        self.make_revenue(
            "1500.00",
            public_visibility=True,
            public_description="Approved public website payment.",
            internal_notes="PRIVATE-CONTEXT-NOTE",
            customer_name="Private Context Customer",
        )
        self.challenge.notes = "PRIVATE-CHALLENGE-NOTE"
        self.challenge.save(update_fields=["notes", "updated_at"])
        self.client.logout()
        response = self.client.get(reverse("public_progress"))
        self.assertNotIn("challenge", response.context)
        self.assertIn("public_challenge", response.context)
        self.assertEqual(response.context["public_transactions"][0]["description"], "Approved public website payment.")
        self.assertNotIn("customer_name", response.context["public_transactions"][0])
        self.assertNotContains(response, "PRIVATE-CONTEXT-NOTE")
        self.assertNotContains(response, "Private Context Customer")
        self.assertNotContains(response, "PRIVATE-CHALLENGE-NOTE")

    def test_public_empty_state_is_available_without_authentication(self):
        Challenge.objects.all().delete()
        self.client.logout()
        response = self.client.get(reverse("public_progress"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "being prepared")
        self.assertNotContains(response, "Django Admin")

    def test_login_redirects_to_private_dashboard(self):
        self.client.logout()
        response = self.client.post(
            reverse("login"),
            {"username": "founder", "password": "test-pass-123"},
        )
        self.assertRedirects(response, reverse("dashboard"))
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)


class FilteringAndExportTests(TrackerTestBase):
    def test_revenue_list_date_and_business_unit_filters_work(self):
        self.make_revenue("1000.00", arm=self.tech, day=self.challenge.start_date)
        self.make_revenue("2000.00", arm=self.code, day=self.challenge.start_date + timedelta(days=10))
        response = self.client.get(
            reverse("revenue_list"),
            {
                "start": (self.challenge.start_date + timedelta(days=5)).isoformat(),
                "end": self.challenge.end_date.isoformat(),
                "arm": self.code.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total"], Decimal("2000.00"))
        self.assertEqual(response.context["total_count"], 1)

    def test_csv_exports_contain_correct_records(self):
        self.make_revenue(
            "4321.00",
            public_visibility=True,
            public_description="Exported public description.",
            description="Exported internal revenue description.",
            reference="EXP-001",
        )
        self.make_expense("321.00", description="Exported expense description.")
        response = self.client.get(
            reverse("export_csv"),
            {
                "report": "revenue",
                "start": self.challenge.start_date.isoformat(),
                "end": self.challenge.end_date.isoformat(),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        content = response.content.decode("utf-8-sig")
        self.assertIn("4321.00", content)
        self.assertIn("Exported internal revenue description.", content)
        self.assertNotIn("Exported expense description.", content)

        response = self.client.get(
            reverse("export_csv"),
            {
                "report": "expenses",
                "start": self.challenge.start_date.isoformat(),
                "end": self.challenge.end_date.isoformat(),
            },
        )
        content = response.content.decode("utf-8-sig")
        self.assertIn("Exported expense description.", content)
        self.assertIn("321.00", content)

    def test_public_csv_excludes_private_records(self):
        self.make_revenue(
            "1000.00",
            public_visibility=True,
            public_description="Public record for export.",
        )
        self.make_revenue(
            "5000.00",
            public_visibility=False,
            public_description="Private record for export.",
        )
        response = self.client.get(
            reverse("export_csv"),
            {
                "report": "public",
                "start": self.challenge.start_date.isoformat(),
                "end": self.challenge.end_date.isoformat(),
            },
        )
        content = response.content.decode("utf-8-sig")
        self.assertIn("Public record for export.", content)
        self.assertNotIn("Private record for export.", content)


class SimulatorTests(TrackerTestBase):
    def test_scenario_calculations_are_correct(self):
        result = calculate_scenario(
            target=Decimal("200000.00"),
            days=100,
            average_sale_price=Decimal("2000.00"),
            sales_per_day=Decimal("1.00"),
            working_days_per_week=7,
            delivery_cost_per_sale=Decimal("100.00"),
            collection_delay_days=0,
        )
        self.assertEqual(result["expected_sales"], Decimal("100.00"))
        self.assertEqual(result["gross_projected"], Decimal("200000.00"))
        self.assertEqual(result["expected_collections"], Decimal("200000.00"))
        self.assertEqual(result["delivery_costs"], Decimal("10000.00"))
        self.assertEqual(result["contribution"], Decimal("190000.00"))
        self.assertEqual(result["sales_needed"], 100)
        self.assertTrue(result["target_achieved"])
        self.assertEqual(result["remaining_required"], Decimal("0.00"))

    def test_collection_delay_reduces_expected_collections(self):
        result = calculate_scenario(
            target=Decimal("200000.00"),
            days=100,
            average_sale_price=Decimal("2000.00"),
            sales_per_day=Decimal("1.00"),
            working_days_per_week=7,
            delivery_cost_per_sale=Decimal("0.00"),
            collection_delay_days=10,
        )
        self.assertEqual(result["gross_projected"], Decimal("200000.00"))
        self.assertEqual(result["expected_collections"], Decimal("180000.00"))

    def test_baseline_scenarios_include_required_reference_cases(self):
        rows = baseline_scenarios()
        self.assertTrue(any(row["count"] == 134 and row["price"] == Decimal("1500.00") for row in rows))
        self.assertTrue(any(row["count"] == 80 and row["price"] == Decimal("2500.00") for row in rows))
        self.assertEqual(
            next(row for row in rows if row["count"] == 100 and row["price"] == Decimal("1500.00"))["total"],
            Decimal("150000.00"),
        )

    def test_simulation_never_alters_actual_results(self):
        self.make_revenue("2000.00")
        before = revenue_total(self.challenge)
        response = self.client.post(
            reverse("simulator"),
            {
                "target": "200000.00",
                "days": "100",
                "average_sale_price": "2500.00",
                "sales_per_day": "1.00",
                "working_days_per_week": "7",
                "delivery_cost_per_sale": "100.00",
                "collection_delay_days": "0",
                "save_scenario": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["scenario"]["target_achieved"])
        self.assertEqual(revenue_total(self.challenge), before)
        self.assertEqual(response.context["scenario"]["target"], Decimal("200000.00"))


class DailyRecordWorkflowTests(TrackerTestBase):
    def test_expense_create_void_and_restore(self):
        response = self.client.get(reverse("expense_create"))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse("expense_create"),
            {
                "expense_date": self.challenge.start_date.isoformat(),
                "amount": "450.00",
                "currency": "GHS",
                "category": self.expense_category.pk,
                "arm": self.tech.pk,
                "description": "Domain renewal expense.",
                "payee": "Registrar",
                "payment_method": "card",
                "payment_status": "paid",
                "internal_notes": "Receipt to be filed.",
            },
        )
        self.assertEqual(response.status_code, 302)
        expense = Expense.objects.get(description="Domain renewal expense.")
        self.assertEqual(challenge_totals(self.challenge)["expenses_paid"], Decimal("450.00"))

        response = self.client.post(reverse("expense_action", args=[expense.pk, "void"]), {"reason": "Duplicate"})
        self.assertEqual(response.status_code, 302)
        expense.refresh_from_db()
        self.assertTrue(expense.is_voided)
        self.assertEqual(challenge_totals(self.challenge)["expenses_paid"], Decimal("0.00"))

        self.client.post(reverse("expense_action", args=[expense.pk, "restore"]))
        expense.refresh_from_db()
        self.assertFalse(expense.is_voided)
        self.assertEqual(challenge_totals(self.challenge)["expenses_paid"], Decimal("450.00"))

    def test_movement_create_and_void_never_changes_revenue(self):
        response = self.client.get(reverse("movement_create"))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse("movement_create"),
            {
                "movement_type": "owner_contribution",
                "movement_date": self.challenge.start_date.isoformat(),
                "amount": "15000.00",
                "currency": "GHS",
                "arm": "",
                "description": "Owner working capital contribution.",
                "reference": "CONTRIB-1",
                "notes": "Not customer revenue.",
            },
        )
        self.assertEqual(response.status_code, 302)
        movement = OtherFinancialMovement.objects.get(reference="CONTRIB-1")
        self.assertEqual(revenue_total(self.challenge), Decimal("0.00"))
        self.assertEqual(challenge_totals(self.challenge)["other_inflow"], Decimal("15000.00"))

        self.client.post(reverse("movement_action", args=[movement.pk, "void"]), {"reason": "Reclassified"})
        movement.refresh_from_db()
        self.assertTrue(movement.is_voided)
        self.assertEqual(challenge_totals(self.challenge)["other_inflow"], Decimal("0.00"))

    def test_settings_manages_reference_data_and_fixed_business_units(self):
        response = self.client.get(reverse("settings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Revenue categories")
        self.assertContains(response, "Expense categories")
        self.assertContains(response, "Xonovate Technologies")
        self.assertContains(response, "Xonovate Code Champions")
        self.assertNotContains(response, "Other Xonovate Business Activities")

        response = self.client.post(
            reverse("revenue_category_create"),
            {"name": "Training workshops", "description": "Workshop fees.", "is_active": "on"},
        )
        self.assertRedirects(response, reverse("settings"))
        self.assertTrue(RevenueCategory.objects.filter(name="Training workshops").exists())

        response = self.client.post(
            reverse("expense_category_create"),
            {"name": "Travel", "description": "Local travel.", "is_active": "on"},
        )
        self.assertRedirects(response, reverse("settings"))
        self.assertTrue(ExpenseCategory.objects.filter(name="Travel").exists())

    def test_revenue_form_only_offers_active_business_units(self):
        other = ARM.objects.get(name="Other Xonovate Business Activities")
        self.make_revenue("1000.00", arm=other)
        response = self.client.get(reverse("revenue_create"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(other, response.context["form"].fields["arm"].queryset)
    def test_authenticated_primary_pages_render(self):
        revenue = self.make_revenue("1000.00")
        expense = self.make_expense("100.00")
        movement = OtherFinancialMovement.objects.create(
            challenge=self.challenge,
            movement_type="owner_contribution",
            movement_date=self.challenge.start_date,
            amount=Decimal("500.00"),
            currency="GHS",
            description="Owner contribution.",
        )
        routes = [
            reverse("dashboard"),
            reverse("revenue_list"),
            reverse("expense_list"),
            reverse("revenue_create"),
            reverse("expense_create"),
            reverse("movement_create"),
            reverse("revenue_detail", args=[revenue.pk]),
            reverse("expense_detail", args=[expense.pk]),
            reverse("movement_detail", args=[movement.pk]),
            reverse("transactions"),
            reverse("reports"),
            reverse("simulator"),
            reverse("public_progress"),
            reverse("settings"),
        ]
        for url in routes:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)


class AdminAndEmptyStateTests(TrackerTestBase):
    def setUp(self):
        super().setUp()
        self.admin = get_user_model().objects.create_superuser(
            "admin", "admin@example.com", "admin-test-pass-123"
        )

    def test_admin_challenge_change_appears_on_frontend(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("admin:tracker_challenge_change", args=[self.challenge.pk]),
            {
                "name": self.challenge.name,
                "description": self.challenge.description,
                "status": "active",
                "start_date": self.challenge.start_date.isoformat(),
                "end_date": self.challenge.end_date.isoformat(),
                "target_amount": "210000.00",
                "currency": "GHS",
                "notes": "Changed in admin",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.target_amount, Decimal("210000.00"))
        dashboard = self.client.get(reverse("dashboard"))
        self.assertContains(dashboard, "210,000.00")

    def test_empty_datasets_do_not_error(self):
        urls = [
            reverse("dashboard"),
            reverse("revenue_list"),
            reverse("expense_list"),
            reverse("transactions"),
            reverse("reports"),
            reverse("public_progress"),
            reverse("export_csv") + "?report=overall",
            reverse("settings"),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    def test_transaction_edit_recalculates(self):
        txn = self.make_revenue("1000.00")
        response = self.client.post(
            reverse("revenue_edit", args=[txn.pk]),
            {
                "transaction_date": self.challenge.start_date.isoformat(),
                "amount": "2500.00",
                "currency": "GHS",
                "arm": self.code.pk,
                "category": self.revenue_category.pk,
                "description": "Corrected revenue description.",
                "customer_name": "",
                "payment_method": "bank_transfer",
                "reference": "",
                "public_visibility": "",
                "public_description": "",
                "internal_notes": "",
                "status": "received",
                "refunded_amount": "0.00",
            },
        )
        self.assertEqual(response.status_code, 302)
        txn.refresh_from_db()
        self.assertEqual(txn.amount, Decimal("2500.00"))
        self.assertEqual(txn.arm, self.code)
        self.assertEqual(revenue_total(self.challenge), Decimal("2500.00"))




