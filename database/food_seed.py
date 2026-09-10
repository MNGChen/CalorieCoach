"""Load the bundled food workbook into the application's SQLite database."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
from sqlalchemy import func, select

from config import BASE_DIR
from database.models import Food


def normalize_food_name(name: str) -> str:
    """Produce a comparable food name without changing the displayed name."""
    cleaned = re.sub(r"[^a-z0-9]+", " ", name.casefold())
    return " ".join(cleaned.split())


def seed_food_database(session: object, workbook: Path | None = None) -> None:
    """Seed once from the bundled workbook; never overwrite existing food rows."""
    if session.scalar(select(func.count(Food.id))) > 0:  # type: ignore[attr-defined]
        return

    source = workbook or BASE_DIR / "data" / "food_300.xlsx"
    frame = _read_food_sheet(source)
    for _, row in frame.iterrows():
        name = str(row["Food Item"]).strip()
        if not name or name.lower() == "nan":
            continue
        session.add(Food(  # type: ignore[attr-defined]
            id=int(row["No."]),
            name=name,
            normalized_name=normalize_food_name(name),
            category=_optional_text(row.get("Category")),
            serving_quantity=_number(row.get("Typical Serving (g/ml)")),
            serving_unit="g",
            calories=_number(row.get("Energy (kcal)")) or 0,
            protein_g=_number(row.get("Protein (g)")) or 0,
            carbs_g=_number(row.get("Carbohydrates (g)")) or 0,
            fat_g=_number(row.get("Total Fat (g)")) or 0,
        ))


def _number(value: object) -> float | None:
    return None if pd.isna(value) else float(value)


def _optional_text(value: object) -> str | None:
    return None if pd.isna(value) else str(value).strip() or None


def _read_food_sheet(source: Path) -> pd.DataFrame:
    """Find the real header row instead of assuming a fixed number of title rows."""
    raw = pd.read_excel(source, sheet_name=0, header=None)
    header_rows = raw.index[raw.apply(
        lambda row: row.astype(str).str.strip().eq("Food Item").any(), axis=1
    )]
    if header_rows.empty:
        raise ValueError("The food workbook does not contain a 'Food Item' header.")
    header_row = int(header_rows[0])
    frame = raw.iloc[header_row + 1:].copy()
    frame.columns = raw.iloc[header_row].astype(str).str.strip()
    return frame.dropna(how="all")
