import unittest
from services.nutrition_router import NutritionRouter
class RouterTests(unittest.TestCase):
    def setUp(self): self.router=NutritionRouter(chain=object())
    def test_deterministic_intents(self):
        cases={"I ate chicken rice":"log_food","How many calories left today?":"daily_progress","Do I need more protein?":"nutrition_question","What should I eat for dinner?":"meal_recommendation"}
        for message,intent in cases.items(): self.assertEqual(self.router.route(message).intent,intent)
if __name__=="__main__": unittest.main()
