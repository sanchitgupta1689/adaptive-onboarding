from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from graph.state import OnboardingState, EmpathyOutput, EmotionalState, ComplexityCap
from config.settings import get_settings

settings = get_settings()

# ---------------------------------------------------------------------------
# Gemini Flash for the Empathy Agent.
# Flash is used here (not Pro) because:
#   - This is a classification task with a small, well-defined output
#   - It runs on every single user action — latency and cost matter
#   - Flash handles structured JSON output reliably for simple schemas
# ---------------------------------------------------------------------------
_llm = ChatGoogleGenerativeAI(
    model=settings.gemini_flash_model,
    temperature=settings.empathy_temperature,
    google_api_key=settings.google_api_key,
)

# JsonOutputParser automatically parses the LLM's JSON string response
# into a Python dict — we then validate it into EmpathyOutput (Pydantic)
_parser = JsonOutputParser()

_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are an expert in user psychology and digital behavior analysis.
Your job is to infer a user's current emotional state during a health app onboarding
flow based purely on behavioral signals — not what they say, but how they behave.

Always respond with valid JSON only. No explanation outside the JSON."""
    ),
    (
        "human",
        """Analyze these behavioral signals and classify the user's emotional state.

BEHAVIORAL SIGNALS:
- Dwell time on current screen: {dwell_time}s
- Re-read same screen: {reread_count} times
- Scroll velocity: {scroll_velocity} px/s (< 100 = reading, > 400 = skimming)
- Scroll depth: {scroll_depth} (0=top, 1=bottom)
- Session gap before this session: {session_gap_days} days
- Time of day: {time_of_day}
- Current onboarding step: {current_step}
- Event type: {event_type}
- Hesitation flag (computed): {hesitation_flag}
- Current engagement score: {engagement_score}

USER CONTEXT:
- Trust level: {trust_level} (0=no trust, 1=full trust)
- Session count: {session_count} (returning user = more patient)

Classify the emotional state as exactly one of:
  motivated | skeptical | confused | overwhelmed | neutral

Respond with this JSON structure:
{{
  "state": "<one of the 5 states above>",
  "confidence": <float 0.0 to 1.0>,
  "reasoning": "<one sentence explaining the key signal that drove this classification>",
  "recommended_cap": "<low | medium | high>"
}}

Guidelines for recommended_cap:
  - overwhelmed or confused → always "low"
  - skeptical → "medium" (needs more content, not less)
  - motivated → "high"
  - neutral → "medium"
"""
    )
])

# Chain: prompt → LLM → JSON parser
# This is LangChain's LCEL (LangChain Expression Language) pipe syntax.
# Each | passes the output of the left side as input to the right side.
_chain = _prompt | _llm | _parser


def empathy_agent_node(state: OnboardingState) -> OnboardingState:
    """
    LangGraph node function. Receives the full OnboardingState,
    runs the Empathy Agent, and writes EmpathyOutput back into state.

    LangGraph calls this function with the current state and expects
    a dict back with only the keys that changed.
    """
    signal  = state["signal_output"]
    profile = state["user_profile"]

    raw = _chain.invoke({
        "dwell_time":       signal.engagement_score * 30,  # back-approximate from score
        "reread_count":     int(signal.hesitation_flag) * 2,
        "scroll_velocity":  (1.0 - signal.engagement_score) * 500,
        "scroll_depth":     signal.engagement_score,
        "session_gap_days": signal.session_gap_days,
        "time_of_day":      signal.time_of_day,
        "current_step":     profile.current_step.value,
        "event_type":       "step_viewed",
        "hesitation_flag":  signal.hesitation_flag,
        "engagement_score": signal.engagement_score,
        "trust_level":      profile.trust_level,
        "session_count":    profile.session_count,
    })

    empathy_output = EmpathyOutput(
        state           = EmotionalState(raw["state"]),
        confidence      = float(raw["confidence"]),
        reasoning       = raw["reasoning"],
        recommended_cap = ComplexityCap(raw["recommended_cap"]),
    )

    # LangGraph merges this dict into the existing state —
    # only empathy_output is updated, everything else is untouched
    return {"empathy_output": empathy_output}
