from datetime import date
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from services.meal_service import MealService
from tests.support import DatabaseTest, resolved_food


def button(app, label):
    return next(item for item in app.button if item.label == label)


class AppFlowTests(DatabaseTest):
    def app(self, username="alice"):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15)
        app.session_state["active_username"] = username
        app.run()
        self.assertEqual([error.message for error in app.exception], [])
        return app

    def test_profile_page_and_manual_logging_work_without_api_key(self):
        _, profile = self.profile()
        app = self.app()
        next(item for item in app.text_input if item.label == "Food / meal").set_value("Manual egg")
        next(item for item in app.number_input if item.label == "Calories").set_value(75)
        button(app, "Add to log").click().run()
        self.assertEqual([error.message for error in app.exception], [])
        self.assertEqual(MealService(user_id=profile.id).logs()[0].food_name, "Manual egg")

    def test_new_workspace_can_render_profile_without_key(self):
        app = self.app("new-user")
        self.assertTrue(any(item.label == "Age" for item in app.number_input))
        next(item for item in app.checkbox if item.label == "I understand these are estimates and not medical advice.").check()
        button(app, "Save profile").click().run()
        self.assertEqual([error.message for error in app.exception], [])
        from services.nutrition_service import NutritionService
        self.assertIsNotNone(NutritionService(username="new-user").get_profile())

    def test_custom_targets_can_be_entered_before_submitting_profile(self):
        self.profile()
        app = self.app()
        next(item for item in app.checkbox if item.label == "Use custom daily calorie and macro targets").check().run()
        self.assertTrue(any(item.label == "Calories (kcal)" for item in app.number_input))
        self.assertEqual([error.message for error in app.exception], [])

    def test_partial_chat_result_requires_acknowledging_missing_foods(self):
        _, profile = self.profile()
        app = self.app()
        app.text_area(key="assistant_message").set_value("I ate an egg and something unknown")
        items = [resolved_food(review_confirmed=False), {"input_food":"Unknown food", "resolved":False, "reason":"No evidence"}]
        with patch("services.food_analysis_service.FoodAnalysisService.analyze", return_value=items):
            button(app, "Send message").click().run()
        next(item for item in app.checkbox if item.label.startswith("I confirm the food")).check()
        button(app, "Confirm and save food").click().run()
        self.assertEqual(MealService(user_id=profile.id).logs(), [])
        next(item for item in app.checkbox if item.label.startswith("Save only the resolved")).check()
        button(app, "Confirm and save food").click().run()
        self.assertEqual(len(MealService(user_id=profile.id).logs()), 1)
        self.assertEqual([error.message for error in app.exception], [])

    def test_switching_users_clears_advice_pending_food_and_progress(self):
        self.profile("alice")
        self.profile("bob")
        app = self.app()
        app.session_state["assistant_response"] = {"message":"PRIVATE_ALICE", "data":{}}
        app.session_state["pending_food_draft"] = {"user_id":1,"origin":"unused"}
        app.session_state["progress_analysis"] = "PRIVATE_TREND"
        button(app, "Switch user").click().run()
        next(item for item in app.text_input if item.label == "Username").set_value("bob")
        button(app, "Open my workspace").click().run()
        self.assertEqual(app.session_state["active_username"], "bob")
        for key in ("assistant_response", "pending_food_draft", "progress_analysis"):
            self.assertNotIn(key, app.session_state)
        self.assertEqual([error.message for error in app.exception], [])

    def test_chat_uses_confirmation_form_before_saving(self):
        _, profile = self.profile()
        app = self.app()
        app.text_area(key="assistant_message").set_value("I ate an egg for lunch")
        with patch("services.food_analysis_service.FoodAnalysisService.analyze", return_value=[resolved_food(review_confirmed=False)]):
            button(app, "Send message").click().run()
        self.assertEqual(MealService(user_id=profile.id).logs(), [])
        self.assertEqual([error.message for error in app.exception], [])
        button(app, "Confirm and save food").click().run()
        self.assertEqual(MealService(user_id=profile.id).logs(), [])
        next(item for item in app.checkbox if item.label.startswith("I confirm the food")).check()
        button(app, "Confirm and save food").click().run()
        self.assertEqual([error.message for error in app.exception], [])
        self.assertEqual(len(MealService(user_id=profile.id).logs()), 1)
        self.assertNotIn("pending_food_draft", app.session_state)

    def test_lookup_preserves_original_description_until_confirmation(self):
        _, profile = self.profile()
        app = self.app()
        app.text_area(key="log_food_description").set_value("Original egg")
        with patch("services.food_analysis_service.FoodAnalysisService.analyze", return_value=[resolved_food(review_confirmed=False)]):
            button(app, "Find nutrition").click().run()
        app.text_area(key="log_food_description").set_value("Unanalysed new text").run()
        next(item for item in app.checkbox if item.label.startswith("I confirm the food")).check()
        button(app, "Confirm and save food").click().run()
        self.assertEqual([error.message for error in app.exception], [])
        self.assertEqual(MealService(user_id=profile.id).logs()[0].original_input, "Original egg")
