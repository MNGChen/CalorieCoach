# CalorieCoach

A local nutrition-tracking application built with Streamlit. It helps users log meals, estimate calories and macronutrients, review food and weight trends, and receive AI guidance grounded in the day's actual intake.

> CalorieCoach provides general adult nutrition estimates and habit support. It does not diagnose, treat, or replace professional medical advice.

## Features

- **Username workspaces**: Each username has its own profile, food logs, weight entries, and AI context. No password is required, making this suitable for local household or classroom demos.
- **Personal targets**: Calculates BMR, TDEE, calories, and macro targets from a user's profile, with support for complete custom targets.
- **Food logging**: Add meals manually, review AI results before saving, and edit or delete saved records.
- **Nutrition lookup**: Searches the bundled food catalogue first, then falls back to web evidence extraction and validation when necessary.
- **Explainable estimates**: Source URLs, validation status, confidence, and user-review markers remain attached to saved logs.
- **Daily progress and AI coaching**: Database services calculate daily totals; the AI receives those deterministic totals as context for guidance.
- **Progress page**: Shows 7-, 30-, and 90-day calorie, protein, and weight trends.
- **AI meal recommendations**: The homepage assistant suggests a next meal from today's remaining nutrition budget. Suggestions are never logged automatically.
- **Demo data**: A new username can load a 14-day sample history containing 42 meal logs and 5 weight entries.

## Quick start

### 1. Install dependencies

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure AI (optional)

```powershell
Copy-Item .env.example .env
```

Add a Gemini API key to `.env`:

```env
GEMINI_API_KEY=your_google_gemini_api_key
GEMINI_MODEL=gemini-2.0-flash
```

Without an API key, manual logging, the local food catalogue, progress tracking, and demo data remain available. AI parsing, coaching, web nutrition extraction, and meal recommendations require a valid key and network connection.

### 3. Run the app

```powershell
streamlit run app.py
```

On first launch, the application creates `caloriecoach.db` locally and seeds the food catalogue from `data/food_300.xlsx`.

## User flow

```text
Enter a username
    ↓
New user: complete a profile or load demo data
Existing user: load that username's profile and history
    ↓
Log food manually or use AI lookup → review/edit the estimate → save
    ↓
Calculate user-scoped daily totals → dashboard, progress page, and AI coach
```

### Loading demo data

1. Enter an unused username in the sidebar, such as `demo-user`.
2. Select **Load demo data**.
3. Open the Progress page to inspect two weeks of food and weight history.

Demo data can only be loaded into a username without a profile. This prevents repeated loads from duplicating or overwriting real records. Use a different username to create another demo workspace.

## Project structure

```text
CalorieCoach/
├── app.py                         # Main dashboard, username workspace, logs, coach, assistant
├── pages/
│   ├── Progress.py                 # Food/weight trends and history
├── database/
│   ├── models.py                   # UserProfile, FoodLog, WeightEntry, Food ORM models
│   ├── database.py                 # SQLite engine, transactions, additive migrations
│   └── food_seed.py                # Imports the bundled Excel food catalogue
├── mcp_server/
│   └── nutrition_server.py          # Read-only MCP entry point for the shared food catalogue
├── services/
│   ├── nutrition_service.py        # Profile, targets, and user-scoped daily totals
│   ├── meal_service.py             # User-scoped food/weight CRUD and progress queries
│   ├── meal_logging_service.py     # Atomic persistence of validated food estimates
│   ├── demo_data_service.py        # Safe two-week demo-history generator
│   ├── nutrition_mcp_tools.py       # Read-only tool implementations used by the MCP server
│   ├── food_* / web_*              # Food parsing, search, and web nutrition evidence extraction
│   ├── nutrition_*                 # Routing, validation, statistics, coaching, orchestration
│   ├── portion_calculator.py       # Deterministic serving calculations
│   └── meal_planning_*.py          # Local candidate selection and meal recommendation
├── ai/
│   ├── prompts.py                  # Auditable AI prompts
│   └── nutrition_ai.py             # Gemini REST client
├── utils/
│   ├── helpers.py                  # Dashboard metrics and progress bars
│   └── ui.py                       # Shared visual theme, headers, and empty states
├── data/food_300.xlsx              # Initial local food catalogue
└── tests/                          # Pipeline, logging, coaching, and router tests
```

## Architecture

## Agent orchestration flow

The V1 Assistant sends each free-text request through `NutritionOrchestrator`. Purple nodes are AI agents; green nodes are deterministic services that calculate, validate, retrieve, or persist data.

```mermaid
flowchart TD
    U[User message] --> R[NutritionRouter<br/>AI agent]
    R --> I{Intent}

    I -- Log food --> FP[FoodInputParser<br/>AI agent]
    FP --> FS[FoodSearchService<br/>Deterministic]
    FS --> LM{Local food match?}
    LM -- Yes --> PC[PortionCalculator<br/>Deterministic]
    LM -- No --> WS[DuckDuckGo food search<br/>Deterministic]
    WS --> WE[WebNutritionExtractor<br/>AI agent]
    WE --> NV[NutritionNormalizer + Statistics<br/>Deterministic]
    NV --> VA[NutritionValidationAgent<br/>AI agent, constrained by evidence]
    PC --> ML[MealLoggingService<br/>Deterministic persistence]
    VA --> ML
    ML --> LD[DailyNutritionService<br/>Deterministic summary]

    I -- Daily progress --> DP[DailyNutritionService<br/>Deterministic summary]

    I -- Nutrition question --> CQ[DailyNutritionService<br/>Deterministic summary]
    CQ --> CA[NutritionCoachAgent<br/>AI agent with calculated context]

    I -- Recommend a meal --> RM[DailyNutritionService<br/>Deterministic summary]
    RM --> CA
    CA --> MC[Local food candidates<br/>Deterministic retrieval]
    MC --> MPA[MealPlanningAgent<br/>AI agent]
    MPA --> MPC[PortionCalculator + target check<br/>Deterministic]

    I -- General question --> GR[General nutrition response<br/>Deterministic]

    LD --> OUT[Structured response]
    DP --> OUT
    CA --> OUT
    MPC --> OUT
    GR --> OUT

    classDef agent fill:#ede9fe,stroke:#7c3aed,color:#2e1065;
    classDef deterministic fill:#dcfce7,stroke:#16a34a,color:#14532d;
    class R,FP,WE,VA,CA,MPA agent;
    class FS,PC,WS,NV,ML,LD,DP,CQ,RM,MC,MPC,GR deterministic;
```

### Local Nutrition MCP Server

CalorieCoach includes a small, read-only MCP server for the shared local food catalogue. It deliberately does not expose personal profiles, food logs, weight entries, or any write operation.

| Tool | Purpose |
| --- | --- |
| `search_local_food(query)` | Find the best catalogue match and its typical-serving nutrition. |
| `lookup_food_nutrition(query, quantity, unit)` | Match a food name and return nutrition in one call; grams scale the portion. |

`lookup_food_nutrition` is the preferred tool for AI agents. It accepts a food name directly, so agents do **not** need to search for or retain an internal `food_id` first.

```text
lookup_food_nutrition(
  query="Hainanese chicken rice",
  quantity=250,
  unit="g"
)
```

The result includes the matched catalogue food, serving size, calories, protein, carbohydrates, fat, source, and whether the quantity was scaled. When no reliable local match exists, it returns `found: false` instead of inventing nutrition data.

Run it over the local stdio transport:

```powershell
.\.venv\Scripts\python.exe mcp_server\nutrition_server.py
```

The server is intentionally independent from the Streamlit UI, so a future `NutritionMcpProvider` can call it as an external fallback without exposing user data.

### User workspaces and data isolation

`UserProfile.username` identifies a local user workspace. `FoodLog.user_id` and `WeightEntry.user_id` reference that profile, so food logs and weight data are queried and modified only within the active workspace.

When an older single-user database is upgraded, its existing records are retained in the `legacy` workspace. `caloriecoach.db` is ignored by Git, so forks and clones do not include any local user data.

**Privacy boundary:** a username is not authentication. Anyone who knows a username can enter that workspace. Do not use this mode for public deployment or sensitive health data; production use requires authentication and proper access control.

### Food analysis and evidence validation

```text
User description
  → FoodInputParser: extracts food items and explicitly stated portions only
  → FoodSearchService: searches the local food catalogue
  → Match found: PortionCalculator scales the nutrition values
  → No match: DuckDuckGo search → Gemini extracts facts from supplied search evidence
  → NutritionNormalizer + NutritionStatistics: normalize servings and exclude outliers
  → NutritionValidationAgent: accepts, marks uncertain, or rejects based on evidence
  → User reviews/edits the result → MealLoggingService saves provenance and status
```

The AI does not perform final aggregation, serving arithmetic, or database writes. Deterministic services handle those responsibilities. User-adjusted estimates are marked as `user_reviewed` while their original source metadata remains available.

### Daily summaries, coaching, and meal recommendations

```text
FoodLog for the active user
  → NutritionService.daily_totals()
  → DailyNutritionService.summary()
  → consumed / target / remaining calories and macros
  ├── Dashboard and Progress page
  ├── NutritionCoachService: AI interprets deterministic context only
  └── MealPlanningService: chooses local Food candidates and calculates nutrition deterministically
```

`NutritionOrchestrator` powers the V1 assistant by routing requests to food logging, daily progress, coaching, meal recommendations, or general guidance. Paths that read or write user data receive the active user's service instances.

## Data model

| Table | Purpose | Ownership |
| --- | --- | --- |
| `user_profiles` | Username, body data, goals, and custom targets | Unique `username` |
| `food_logs` | Individual food entries, nutrients, sources, and validation metadata | `user_id → user_profiles.id` |
| `weight_entries` | Daily weight and notes | Unique `user_id + recorded_on` |
| `foods` | Shared local food catalogue | Not user-owned |
