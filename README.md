# Adaptive Onboarding Agent

A self-learning, multi-agent onboarding system for a health ecommerce app. The system adapts the onboarding flow in real-time based on user behavior — and gets smarter with every session.

---

## What It Does

Instead of showing every user the same onboarding flow, this system:
- Reads behavioral signals (dwell time, scroll depth, hesitation) in real-time
- Infers the user's emotional state, churn risk, and persona dynamically
- Decides the best next onboarding step for each individual user
- Learns from outcomes across all users to improve decisions over time

---

## Architecture

```
Client (Browser)
      │  events: dwell_time, scroll_depth, step
      ▼
FastAPI Backend
      │
      ▼
Signal Processor          ← pure math, no LLM, < 5ms
(engagement, churn risk, hesitation, complexity cap)
      │
      ▼
LangGraph Orchestrator
      │
      ├── Empathy Agent   ← Gemini Flash — classifies emotional state
      │                      (motivated / skeptical / confused / overwhelmed)
      │
      ├── Risk Agent      ← Gemini Flash — churn risk + intervention
      │                      (none / trust signal / simplify / human handoff)
      │
      ├── Planner Agent   ← Gemini Pro — decides next step
      │                      (resolves Bandit + Pattern Store + own reasoning)
      │
      └── Execution Agent ← Gemini Flash — generates screen content
                             (headline, body, CTAs, product cards, reviews)
      │
      ▼
Intelligence Layer
  ├── Dynamic User Model   ← updates persona scores + trust after every action
  ├── Contextual Bandit    ← epsilon-greedy, learns which steps convert per persona
  ├── Pattern Store        ← cohort wisdom from past users via embedding similarity
  └── Embeddings           ← Gemini text-embedding-004 for product + review matching
```

---

## Onboarding Steps

| Step | Purpose |
|---|---|
| Welcome | Hook + value proposition |
| Health Goals Quiz | Captures primary persona signal |
| Health Profile | Age, activity, diet, budget |
| Persona Reveal | AI-generated archetype (dopamine moment) |
| Trust Signals | Certifications, doctor endorsements |
| Product Match | 3 AI-matched products via embedding similarity |
| Social Proof | Reviews matched to user's persona + goals |
| Purchase CTA | Anchored offer with guarantee |
| Commitment | Notification preferences + health app connect |

The agent reorders, skips, or substitutes steps based on each user's behavioral signals.

---

## Adaptive Paths

```
High trust user:         Welcome → Goals → Profile → Product → CTA
Skeptical user:          Welcome → Goals → Trust → Social Proof → Profile → Product → CTA
Overwhelmed user:        Welcome → Goals → Product → CTA   (4 steps only)
Returning user (gap>2d): Trust reinforcement → resume from last step
```

---

## Self-Learning Mechanisms

### Contextual Bandit
Learns which step sequence converts best for each user context (persona × trust level × time of day). Uses epsilon-greedy exploration (15% explore, 85% exploit). Arm weights persist across restarts in `data/bandit_state.json`.

### Dynamic User Model
Every user action shifts persona probability scores and trust level by small increments — like a learning rate in ML. The model converges over many interactions without any single event dominating.

### Embedding-Based Matching
User goals are converted to a natural language query and compared against product/review description vectors using cosine similarity. Top-K matches are surfaced — no manual tagging needed.

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM | Google Gemini 2.5 Pro (Planner) + Gemini 2.5 Flash (Empathy, Risk, Execution) |
| Embeddings | Google text-embedding-004 |
| Agent Orchestration | LangGraph |
| Observability | LangSmith (auto-traces every LLM call) |
| Backend | FastAPI + Uvicorn |
| Frontend | Vanilla HTML/CSS/JS (no build step) |
| Data Validation | Pydantic v2 |

---

## Project Structure

```
adaptive_onboarding/
├── main.py                        # FastAPI entry point + static file serving
├── requirements.txt
├── .env.example
│
├── config/
│   └── settings.py                # All config via pydantic-settings
│
├── graph/
│   ├── state.py                   # All data models — enums, UserProfile, OnboardingState
│   └── orchestrator.py            # LangGraph StateGraph definition + routing
│
├── signal_processor/
│   └── processor.py               # Raw event → SignalOutput (pure math, no LLM)
│
├── agents/
│   ├── empathy_agent.py           # Gemini Flash — emotional state classification
│   ├── risk_agent.py              # Gemini Flash — churn risk + intervention
│   ├── planner_agent.py           # Gemini Pro — next step decision
│   └── execution_agent.py        # Gemini Flash — screen content generation
│
├── intelligence/
│   ├── user_model.py              # Continuously updates UserProfile from events
│   ├── bandit.py                  # Epsilon-greedy contextual bandit
│   └── embeddings.py             # text-embedding-004 similarity search
│
├── tools/
│   └── onboarding_tools.py        # Product + review retrieval using embeddings
│
├── data/
│   └── products.json              # Product catalog (8 health products)
│
├── api/
│   └── routes.py                  # /start, /event, /profile endpoints
│
└── frontend/
    └── index.html                 # Full-screen responsive web app
```

---

## Getting Started

### 1. Prerequisites

```bash
brew install python
```

### 2. Clone and setup

```bash
git clone https://github.com/sanchitgupta1689/adaptive-onboarding.git
cd adaptive-onboarding
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and add your keys:
```env
GOOGLE_API_KEY=your_gemini_api_key      # aistudio.google.com
LANGSMITH_API_KEY=your_langsmith_key    # smith.langchain.com
```

### 4. Run

```bash
python main.py
```

Open **http://localhost:8000** in your browser.

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Frontend web app |
| `GET` | `/health` | Health check |
| `POST` | `/onboarding/start` | Create a new user session |
| `POST` | `/onboarding/event` | Send a user action, get next screen |
| `GET` | `/onboarding/profile/{user_id}` | Inspect user's dynamic model |
| `GET` | `/docs` | Interactive API explorer |

### Example: Start onboarding
```bash
curl -X POST http://localhost:8000/onboarding/start \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_001", "email": "test@example.com"}'
```

### Example: Send event
```bash
curl -X POST http://localhost:8000/onboarding/event \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_001",
    "event_type": "step_completed",
    "step": "welcome",
    "dwell_time_seconds": 12,
    "scroll_depth": 0.9,
    "scroll_velocity": 80,
    "reread_count": 0,
    "session_gap_days": 0
  }'
```

---

## Observability

Every agent run is fully traced in LangSmith with custom metadata:

```
Trace: onboarding_session
├── user_id, step, event_type
├── persona, trust_level, churn_risk
├── engagement_score, hesitation_flag
│
├── empathy_agent_node    → emotional state + confidence
├── risk_agent_node       → churn risk + intervention
├── planner_agent_node    → next step + reasoning
└── execution_agent_node  → rendered screen content
```

Filter traces in LangSmith by `metadata.user_id`, `metadata.churn_risk > 0.6`, or `error = true` to debug specific sessions.

---

## Conflict Resolution

When Bandit and Pattern Store disagree on the next step:

```
Priority 1: Risk Agent hard override (churn_risk > 0.75)
Priority 2: Empathy gate (filters high-complexity steps for overwhelmed users)
Priority 3: Weighted merge — Bandit (0.4) + Pattern Store (0.35) + Planner (0.25)
Priority 4: Cold start rule — if bandit_samples < 50, trust Pattern Store more
Priority 5: Fallback default flow
```
