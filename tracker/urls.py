from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.public_progress, name="public_progress"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("revenue/", views.revenue_list, name="revenue_list"),
    path("revenue/new/", views.revenue_create, name="revenue_create"),
    path("revenue/<int:pk>/", views.revenue_detail, name="revenue_detail"),
    path("revenue/<int:pk>/edit/", views.revenue_edit, name="revenue_edit"),
    path("revenue/<int:pk>/action/<str:action>/", views.revenue_action, name="revenue_action"),
    path("expenses/", views.expense_list, name="expense_list"),
    path("expenses/new/", views.expense_create, name="expense_create"),
    path("expenses/<int:pk>/", views.expense_detail, name="expense_detail"),
    path("expenses/<int:pk>/edit/", views.expense_edit, name="expense_edit"),
    path("expenses/<int:pk>/action/<str:action>/", views.expense_action, name="expense_action"),
    path("expenses/<int:pk>/receipt/", views.expense_receipt, name="expense_receipt"),
    path("finance/new/", views.movement_create, name="movement_create"),
    path("finance/<int:pk>/", views.movement_detail, name="movement_detail"),
    path("finance/<int:pk>/edit/", views.movement_edit, name="movement_edit"),
    path("finance/<int:pk>/action/<str:action>/", views.movement_action, name="movement_action"),
    path("transactions/", views.transaction_list, name="transactions"),
    path("reports/", views.reports, name="reports"),
    path("reports/export/", views.export_csv, name="export_csv"),
    path("simulator/", views.simulator, name="simulator"),
    path("settings/", views.workspace_settings, name="settings"),
    path("settings/revenue-categories/new/", views.revenue_category_create, name="revenue_category_create"),
    path("settings/revenue-categories/<int:pk>/edit/", views.revenue_category_edit, name="revenue_category_edit"),
    path("settings/expense-categories/new/", views.expense_category_create, name="expense_category_create"),
    path("settings/expense-categories/<int:pk>/edit/", views.expense_category_edit, name="expense_category_edit"),
]
