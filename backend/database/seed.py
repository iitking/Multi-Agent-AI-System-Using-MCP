"""Deterministic sample sales dataset used for development, tests and evaluation.

The data contains a *planted* revenue drop so analyses have a known answer:

* Sep-Nov 2025: the **West** region loses ~55% of its volume (distribution-centre outage).
* Sep-Nov 2025: **Aurora Laptop** loses ~30% of volume everywhere else (promo ended, competitor launch).
* December recovers.
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

from sqlalchemy import Column, Float, Integer, MetaData, String, Table, func, insert, select

from backend.database.db import get_analytics_write_engine

metadata = MetaData()

sales = Table(
    "sales",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("order_date", String(10), nullable=False),
    Column("month", String(7), nullable=False, index=True),  # YYYY-MM
    Column("region", String(32), nullable=False),
    Column("product", String(64), nullable=False),
    Column("category", String(32), nullable=False),
    Column("units", Integer, nullable=False),
    Column("unit_price", Float, nullable=False),
    Column("discount_pct", Float, nullable=False),
    Column("revenue", Float, nullable=False),
)

REGIONS = [("North", 1.00), ("South", 0.85), ("East", 1.10), ("West", 1.05)]

# name, category, list price, base units per region-month
PRODUCTS = [
    ("Aurora Laptop", "Electronics", 1200.0, 95),
    ("Nimbus Phone", "Electronics", 800.0, 120),
    ("Pulse Tablet", "Electronics", 450.0, 110),
    ("Orbit Smartwatch", "Wearables", 250.0, 150),
    ("Zephyr Headphones", "Accessories", 150.0, 260),
    ("Echo Speaker", "Accessories", 120.0, 230),
]

SEASONALITY = [0.92, 0.90, 0.98, 1.00, 1.02, 1.00, 0.98, 1.00, 1.02, 1.05, 1.10, 1.15]


def generate_rows(seed: int = 42, year: int = 2025) -> list[dict]:
    rng = random.Random(seed)
    rows: list[dict] = []
    row_id = 1
    for month_number in range(1, 13):
        month = f"{year}-{month_number:02d}"
        for region, region_weight in REGIONS:
            for name, category, price, base_units in PRODUCTS:
                multiplier = SEASONALITY[month_number - 1] * region_weight * rng.uniform(0.95, 1.05)
                discount = 0.10 if (name == "Aurora Laptop" and month_number <= 8) else 0.0
                if month_number in (9, 10, 11):
                    if region == "West":
                        multiplier *= 0.45
                    elif name == "Aurora Laptop":
                        multiplier *= 0.70
                units = max(1, int(round(base_units * multiplier)))
                rows.append(
                    {
                        "id": row_id,
                        "order_date": f"{month}-15",
                        "month": month,
                        "region": region,
                        "product": name,
                        "category": category,
                        "units": units,
                        "unit_price": price,
                        "discount_pct": discount * 100,
                        "revenue": round(units * price * (1 - discount), 2),
                    }
                )
                row_id += 1
    return rows


def ensure_seeded(reset: bool = False) -> int:
    """Create the table and load sample data if empty. Returns the row count."""
    engine = get_analytics_write_engine()
    if engine.url.get_backend_name() == "sqlite" and engine.url.database:
        Path(engine.url.database).parent.mkdir(parents=True, exist_ok=True)
    if reset:
        metadata.drop_all(engine, tables=[sales])
    metadata.create_all(engine, tables=[sales])
    with engine.begin() as conn:
        count = conn.execute(select(func.count()).select_from(sales)).scalar_one()
        if count == 0:
            conn.execute(insert(sales), generate_rows())
            count = conn.execute(select(func.count()).select_from(sales)).scalar_one()
    return int(count)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the sample sales database.")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate the sales table.")
    args = parser.parse_args()
    print(f"sales table ready with {ensure_seeded(reset=args.reset)} rows")


if __name__ == "__main__":
    main()
