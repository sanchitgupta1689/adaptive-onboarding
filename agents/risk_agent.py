from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from graph.state import (
    OnboardingState, RiskOutput, RiskAction, OnboardingStep
)
from config.settings import get_settings

settings = get_settings()

# Flash again — risk scoring is a structured classification,
# not open-ended reasoning. Speed matters here.
_llm = ChatGoogleGenerativeAI(
    model=settings.gemini_flash_model,
    temperature=settings.risk_temperature,
    google_api_key=settings.google_api_key,
)

_parser = JsonOutputParser()

_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are a churn prevention specialist for a health ecommerce app.
Your job is to assess whether a user is at risk of abandoning the onboarding flow
and recommend the least intrusive intervention that would keep them engaged.

Respond with valid JSON only."""
    ),
    (
        "human",
        """Assess churn risk and recommend an intervention.

RISK SIGNALS:
- Computed churn risk score: {churn_risk_score} (0=safe, 1=certain churn)
- Emotional state: {emotional_state} (confidence: {empathy_confidence})
- Hesitation flag: {hesitation_flag}
- Session gap: {session_gap_days} days
- Skipped steps so far: {skipped_steps}
- Current step: {current_step}
- Trust level: {trust_level}
- Purchase readiness: {purchase_readiness}

INTERVENTION OPTIONS (use the least intrusive one that fits):
  - "none":                 risk is low, no intervention needed
  - "inject_trust_signal":  show a certification / review / guarantee badge inline
  - "simplify_step":        reduce choices or copy length on the current step
  - "offer_discount":       surface a time-limited discount (use sparingly, risk of devaluing)
  - "human_handoff":        offer live chat or callback (high churn risk only)
  - "exit_intent":          full-screen intervention if user is about to close the app

HARD OVERRIDE RULE:
  If churn_risk_score > {hard_override_threshold}, set hard_override to true.
  In this case, pick the override_step that gives the best chance of recovery
  based on the user's current trust level and emotional state.

Respond with:
{{
  "churn_risk": <float, your refined risk estimate>,
  "risk_action": "<one of the 6 options above>",
  "hard_override": <true | false>,
  "override_step": "<OnboardingStep value or null>",
  "reasoning": "<one sentence>"
}}
"""
    )
])

_chain = _prompt | _llm | _parser


def risk_agent_node(state: OnboardingState) -> OnboardingState:
    """
    Runs after the Empathy Agent. Has access to both signal data and
    the emotional state classified by the Empathy Agent.

    Key responsibility: decide whether to let the Planner run normally
    or hard-override it with an emergency intervention step.
    """
    signal  = state["signal_output"]
    profile = state["user_profile"]
    empathy = state["empathy_output"]

    raw = _chain.invoke({
        "churn_risk_score":       signal.churn_risk_score,
        "emotional_state":        empathy.state.value if empathy else "neutral",
        "empathy_confidence":     empathy.confidence if empathy else 0.5,
        "hesitation_flag":        signal.hesitation_flag,
        "session_gap_days":       signal.session_gap_days,
        "skipped_steps":          [s.value for s in profile.skipped_steps],
        "current_step":           profile.current_step.value,
        "trust_level":            profile.trust_level,
        "purchase_readiness":     profile.purchase_readiness,
        "hard_override_threshold": settings.churn_hard_override_threshold,
    })

    # override_step comes back as a string or null from the LLM
    override_step = None
    if raw.get("override_step"):
        try:
            override_step = OnboardingStep(raw["override_step"])
        except ValueError:
            override_step = None

    risk_output = RiskOutput(
        churn_risk    = float(raw["churn_risk"]),
        risk_action   = RiskAction(raw["risk_action"]),
        hard_override = bool(raw["hard_override"]),
        override_step = override_step,
    )

    return {"risk_output": risk_output}
