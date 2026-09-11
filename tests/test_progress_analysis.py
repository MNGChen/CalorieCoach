from __future__ import annotations

import unittest

import pandas as pd

from services.progress_analysis_service import ProgressAnalysisSchema, ProgressAnalysisService


class _Chain:
    def __init__(self) -> None: self.context = None
    def invoke(self, values):
        self.context = values["context"]
        return {"summary": "A steady review.", "insight": "Protein is consistent.",
                "next_step": "Keep logging meals.", "watch_out": "Avoid judging one day alone."}


class ProgressAnalysisServiceTests(unittest.TestCase):
    def test_supplies_aggregated_trend_context(self) -> None:
        chain = _Chain()
        food = pd.DataFrame({"Calories": [1800, 2200], "Protein (g)": [90, 110]})
        weights = pd.DataFrame({"Weight (kg)": [70.0, 69.4]})
        result = ProgressAnalysisService(chain).analyze(food, weights, {"calories": 2000.0}, "Weight Loss", 7)
        self.assertIsInstance(result, ProgressAnalysisSchema)
        self.assertIn('"average_calories": 2000.0', chain.context)
        self.assertIn('"change_kg": -0.6', chain.context)

    def test_handles_missing_trend_data(self) -> None:
        chain = _Chain()
        ProgressAnalysisService(chain).analyze(pd.DataFrame(), pd.DataFrame(), {"calories": 2000.0}, "Maintain", 30)
        self.assertIn('"days_logged": 0', chain.context)
        self.assertIn('"measurements": 0', chain.context)


if __name__ == "__main__":
    unittest.main()
