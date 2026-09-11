"""Create a safe, realistic demo history for an otherwise empty user space."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from services.meal_service import MealService
from services.nutrition_service import NutritionService


class DemoDataError(ValueError):
    """Raised when demo data could overwrite a real user space."""


class DemoDataService:
    def __init__(self, nutrition: NutritionService, meals: MealService) -> None:
        self.nutrition = nutrition
        self.meals = meals

    def load(self) -> dict[str, Any]:
        if self.nutrition.get_profile() is not None:
            raise DemoDataError("这个用户名已有资料；为避免覆盖真实记录，不能加载演示数据。")
        profile = self.nutrition.save_profile(
            age=30, gender="Female", height_cm=165, weight_kg=64.0,
            activity_level="Lightly Active", goal="Weight Loss", health_notice_acknowledged=True,
        )
        # The MealService supplied by the caller must be tied to the profile just created.
        if self.meals.user_id != profile.id:
            self.meals = MealService(self.meals.session_factory, user_id=profile.id)
        meals_added, weights_added = 0, 0
        today = date.today()
        templates = (
            (("Greek yogurt with berries", "Breakfast", 310, 20, 42, 8),
             ("Chicken rice bowl", "Lunch", 620, 42, 68, 18),
             ("Salmon, rice and vegetables", "Dinner", 590, 38, 55, 22)),
            (("Oatmeal and banana", "Breakfast", 360, 13, 63, 8),
             ("Turkey wholegrain sandwich", "Lunch", 510, 35, 56, 16),
             ("Tofu stir-fry with rice", "Dinner", 540, 28, 67, 17)),
            (("Eggs and toast", "Breakfast", 390, 25, 34, 18),
             ("Tuna quinoa salad", "Lunch", 480, 37, 45, 15),
             ("Chicken noodle soup", "Dinner", 520, 36, 61, 13)),
        )
        for offset in range(13, -1, -1):
            day = today - timedelta(days=offset)
            for food_name, meal_type, calories, protein, carbs, fat in templates[offset % len(templates)]:
                self.meals.add_log(food_name=food_name, meal_type=meal_type, calories=calories,
                                   protein_g=protein, carbs_g=carbs, fat_g=fat, log_date=day,
                                   source_type="demo", validation_status="demo_data",
                                   confidence="high", notes="Sample data loaded for product demonstration.")
                meals_added += 1
            if offset % 3 == 1:
                self.meals.add_weight(round(64.0 - (13 - offset) * 0.04, 1), day,
                                      "Sample progress entry")
                weights_added += 1
        return {"profile_id": profile.id, "meals_added": meals_added, "weights_added": weights_added}
