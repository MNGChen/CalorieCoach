"""One review contract for lookup and chat, with a stable submission identity."""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat


class ReviewedFood(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    quantity: FiniteFloat | None = Field(default=None, gt=0)
    unit: str | None = None
    calories: FiniteFloat = Field(ge=0)
    protein_g: FiniteFloat = Field(ge=0)
    carbs_g: FiniteFloat = Field(ge=0)
    fat_g: FiniteFloat = Field(ge=0)


def new_draft(user_id: int, message: str, items: list[dict[str, Any]],
              day: date | None = None, meal_type: str = "Unknown", follow_up: str | None = None) -> dict[str, Any]:
    if user_id <= 0:
        raise ValueError("Complete your profile before preparing a food log.")
    return {"user_id": user_id, "request_id": str(uuid4()), "original_input": message.strip(),
            "items": deepcopy(items), "day": day or date.today(), "meal_type": meal_type,
            "follow_up_request": follow_up}


def review_items(draft: dict[str, Any], rows: list[dict[str, Any]], user_id: int) -> list[dict[str, Any]]:
    if draft["user_id"] != user_id:
        raise ValueError("This food draft belongs to another workspace.")
    originals = [item for item in draft["items"] if item.get("resolved")]
    if len(rows) != len(originals):
        raise ValueError("The food list changed. Review the current list again.")
    reviewed = []
    for item, row in zip(originals, rows):
        values = ReviewedFood(name=str(row["Food"]).strip(), quantity=row["Quantity"] or None,
                              unit=str(row["Unit"]).strip() or None, calories=row["Calories"],
                              protein_g=row["Protein (g)"], carbs_g=row["Carbs (g)"], fat_g=row["Fat (g)"])
        updated = deepcopy(item)
        updated["original_estimate"] = deepcopy(item["matched_food"])
        updated.update(quantity=values.quantity, unit=values.unit, validation_status="user_reviewed",
                       review_confirmed=True, review_note="User confirmed the food, portion and nutrition before saving.")
        updated["matched_food"].update(values.model_dump(exclude={"quantity", "unit"}))
        reviewed.append(updated)
    return reviewed
