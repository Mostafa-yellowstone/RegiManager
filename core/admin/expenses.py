from django.contrib import admin
from ..models import Expense, ExpenseLabel


@admin.register(ExpenseLabel)
class ExpenseLabelAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "created_at")
    list_filter = ("organization",)
    search_fields = ("name", "organization__name")


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("label", "amount", "expense_date", "organization", "created_by", "created_at")
    list_filter = ("organization", "label", "expense_date")
    search_fields = ("label__name", "description", "organization__name")
    date_hierarchy = "expense_date"
