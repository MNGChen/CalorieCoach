# CalorieCoach

## 1. Project Title and Description

**CalorieCoach** is an AI-assisted nutrition tracker that helps people monitor calories and macronutrients, plan meals, and receive context-aware nutrition coaching. It is intended for people who want to lose weight, maintain weight, build muscle, or develop healthier eating habits.

## 2. Problem Statement

Estimating food calories and macros, then connecting those choices to a daily goal, is difficult to do consistently. CalorieCoach provides one place to log meals, review progress, estimate food nutrition with AI, and ask practical questions such as “I am hungry—what can I still eat today?”

## 3. Technology Stack

- Python 3.11
- Streamlit
- Google Gemini API through its REST API
- `python-dotenv`
- SQLite and SQLAlchemy ORM
- `requests`
- `pandas`
- `matplotlib`
- Pillow

## 4. Setup Instructions

1. Clone the repository and enter the project folder.

   ```bash
   git clone <your-repository-url>
   cd CalorieCoach
   ```

2. Create and activate a Python 3.11 virtual environment.

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install the project dependencies.

   ```bash
   pip install -r requirements.txt
   ```

4. Copy the environment template to `.env`.

   ```powershell
   Copy-Item .env.example .env
   ```

5. Open `.env` and add your Gemini API key.

   ```env
   GEMINI_API_KEY=your_google_gemini_api_key
   GEMINI_MODEL=gemini-2.0-flash
   ```

6. Run the Streamlit application.

   ```bash
   streamlit run app.py
   ```

7. Open the local URL shown in the terminal. SQLite creates `caloriecoach.db` automatically when the application starts.

## 5. Usage Examples

### Example 1: AI food analysis

**User input**

```text
I ate chicken rice and bubble tea
```

**Application output**

The app displays estimated food items with calories, protein, carbohydrates, fat, and a short explanation of the portion assumptions. Choose a meal type, such as Lunch, then select **Add all estimates to today's log** to save them.

### Example 2: Context-aware AI coaching

**User input**

```text
I am hungry. What can I still eat today?
```

**Application output**

After selecting **Attach today's intake** and **Attach today's target**, the coach receives the current foods, calories, macros, and targets. It responds with a practical food suggestion based on the remaining calorie and macro budget, while avoiding medical diagnosis.

### Example 3: Daily Meal Planner

**User input**

```text
Daily calorie target: 2,000 kcal
Dietary preference: High protein
```

**Application output**

The Meal Planner generates a one-day plan with Breakfast, Lunch, Dinner, and Snack options. Each meal includes estimated calories, protein, carbohydrates, and fat, followed by the total daily calories for the plan.

## 6. Known Limitations

- Food analysis is an estimate: preparation method, restaurant recipe, portion size, sauces, and sugar can substantially change nutrition values.
- A valid Gemini API key and network connection are required for AI food analysis, meal plans, and coaching. When the API is unavailable, the app shows an error rather than inventing an answer.

## 7. Future Improvements

- Add an in-place food-log editing interface and explicit weekly and monthly summary cards.
- Add user authentication, multiple profiles, and optional barcode or image-based food recognition.
