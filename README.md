# CalorieCoach

CalorieCoach is a production-minded Streamlit nutrition companion for calorie awareness, meal logging, progress tracking, and supportive AI nutrition guidance. It is not a general-purpose chatbot and does not provide medical diagnosis or treatment.

## Features

- Personalized BMI, BMR, TDEE, calorie, and macro estimates using Mifflin–St Jeor
- SQLite food and weight tracking with SQLAlchemy ORM
- AI food analysis that estimates calories and macros from natural-language meals
- AI meal plans for high-protein, vegetarian, keto, low-carb, and budget preferences
- Daily dashboard, progress charts, and history views
- Gemini API integration with a useful local fallback when no key is configured

## Quick start

1. Create and activate a Python 3.11 virtual environment.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env`, then add a Gemini API key if you want live AI generation.
4. Start the application:

   ```bash
   streamlit run app.py
   ```

The SQLite database (`caloriecoach.db`) is created automatically in the project folder.

## Architecture

```text
app.py / pages/       Streamlit UI
services/             Calculation, profile, food-log, and reporting use cases
ai/                   Central prompts and Gemini REST integration
database/             SQLAlchemy models and session lifecycle
utils/                Shared UI helpers
```

## Privacy and safety

Food estimates are approximate and vary with recipe and portion. CalorieCoach offers educational guidance only; it must not be used to diagnose or treat health conditions. Users with medical conditions, pregnancy, eating-disorder concerns, or special nutritional needs should work with a qualified clinician or dietitian.
