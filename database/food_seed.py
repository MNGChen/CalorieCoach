"""Load the bundled food workbook into the application's SQLite database."""
from __future__ import annotations

import re
import hashlib
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
    source = workbook or BASE_DIR / "data" / "food_300.xlsx"
    populated = session.scalar(select(func.count(Food.id))) > 0
    if populated and not session.scalar(select(Food.id).where(Food.source_label.is_(None)).limit(1)):
        return
    frame = _read_food_sheet(source)
    version = hashlib.sha256(source.read_bytes()).hexdigest()
    for _, row in frame.iterrows():
        name = str(row["Food Item"]).strip()
        if not name or name.lower() == "nan":
            continue
        if populated:
            existing = session.get(Food, int(row["No."]))
            if existing is not None and existing.name == name and existing.source_label is None:
                existing.source_label = source.name
                existing.source_version = version
                existing.source_quality = "unverified_catalogue"
                existing.serving_unit = _optional_text(row.get("Serving Unit"))
            continue
        session.add(Food(  # type: ignore[attr-defined]
            id=int(row["No."]),
            name=name,
            normalized_name=normalize_food_name(name),
            category=_optional_text(row.get("Category")),
            serving_quantity=_number(row.get("Typical Serving (g/ml)")),
            # The bundled mixed g/ml header does not identify each row's unit.
            serving_unit=_optional_text(row.get("Serving Unit")),
            source_label=source.name, source_version=version, source_quality="unverified_catalogue",
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
