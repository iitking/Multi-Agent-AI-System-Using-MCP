"""Unit tests for analytics calculations."""
import pytest

from backend.database.seed import ensure_seeded
from backend.services.analytics import (
    AnalyticsError,
    calculate_kpis,
    period_comparison,
    revenue_by_dimension,
    run_readonly_query,
    sales_summary,
    top_products,
)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    ensure_seeded()


def test_sales_summary():
    res = sales_summary()
    assert res["total_revenue"] > 10_000_000
    assert res["total_units"] > 40_000
    assert res["month_count"] == 12
    assert len(res["months"]) == 12


def test_sales_summary_range():
    res = sales_summary(start_month="2025-09", end_month="2025-11")
    assert res["month_count"] == 3


def test_revenue_by_dimension():
    res = revenue_by_dimension("region")
    assert res["dimension"] == "region"
    assert len(res["items"]) == 4
    regions = {r["name"] for r in res["items"]}
    assert regions == {"North", "South", "East", "West"}


def test_revenue_by_dimension_invalid():
    with pytest.raises(AnalyticsError, match="Unknown dimension"):
        revenue_by_dimension("invalid_dimension")


def test_top_products():
    res = top_products(limit=3)
    assert len(res["items"]) == 3
    assert res["items"][0]["rank"] == 1
    assert res["items"][0]["name"] == "Aurora Laptop"


def test_period_comparison():
    res = period_comparison(
        dimension="region",
        baseline_start="2025-06",
        baseline_end="2025-08",
        comparison_start="2025-09",
        comparison_end="2025-11",
    )
    assert res["dimension"] == "region"
    assert "rows" in res
    # West region should show the biggest decline
    west = next(r for r in res["rows"] if r["name"] == "West")
    assert west["change"] < 0
    assert west["pct_change"] < -40.0


def test_period_comparison_overlap_error():
    with pytest.raises(AnalyticsError, match="must not overlap"):
        period_comparison(
            dimension="region",
            baseline_start="2025-06",
            baseline_end="2025-09",
            comparison_start="2025-09",
            comparison_end="2025-11",
        )


def test_calculate_kpis():
    kpis = calculate_kpis()
    assert kpis["first_month"] == "2025-01"
    assert kpis["last_month"] == "2025-12"
    assert kpis["total_revenue"] > 0
    assert kpis["avg_selling_price"] > 300
    assert "best_month" in kpis
    assert "worst_month" in kpis
    assert len(kpis["mom_growth"]) == 11


def test_run_readonly_query():
    res = run_readonly_query("SELECT region, SUM(revenue) FROM sales GROUP BY region")
    assert len(res["rows"]) == 4
    assert res["row_count"] == 4
