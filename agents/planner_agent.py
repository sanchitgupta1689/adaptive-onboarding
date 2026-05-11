from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from graph.state import (
    OnboardingState, PlannerOutput, OnboardingStep, ComplexityCap
)
from config.settings import get_settings

settings = get_settings()

# Gemini Pro for the Planner — this is the most complex reasoning task.
# It must weigh multiple conflicting signals and make a nuanced decision.
# Pro's longer context window also helps when the user profile is rich.
_llm = ChatGoogleGenerativeAI(
    model=settings.gemini_pro_model,
    temperature=settings.planner_temperature,
    google_api_key=settings.google_api_key,
)

_parser = JsonOutputParser()

# All possible onboarding steps the Planner can choose from
_all_steps = [s.value for s in OnboardingStep]

_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are the strategic brain of an adaptive onboarding system for a health
ecommerce app. Your job is to decide the single best next onboarding step for this
specific user, given everything you know about them.

You must balance three sources of intelligence:
  1. Contextual Bandit recommendation (what converts best for users like this)
  2. Cross-user Pattern Store (what worked for this user's cohort historically)
  3. Your own reasoning (what makes sense given the user's current state)

Respond with valid JSON only."""
    ),
    (
        "human",
        """Decide the next onboarding step for this user.

USER PROFILE:
- Persona: {dominant_persona} (scores: {persona_scores})
- Health goals: {health_goals}
- Trust level: {trust_level} (0=no trust, 1=full trust)
- Purchase readiness: {purchase_readiness}
- Content preference: {content_preference}
- Budget sensitivity: {price_sensitivity}
- Completed steps: {completed_steps}
- Skipped steps: {skipped_steps}
- Current step: {current_step}

CURRENT SESSION STATE:
- Emotional state: {emotional_state} (confidence: {empathy_confidence})
- Engagement score: {engagement_score}
- Intent signal: {intent_signal}
- Complexity cap: {complexity_cap} (do NOT recommend a step that exceeds this)
- Risk action requested: {risk_action}
- Time of day: {time_of_day}

INTELLIGENCE SOURCES:
- Bandit recommendation: {bandit_recommendation} (confidence: {bandit_confidence}, samples: {bandit_samples})
- Pattern Store recommendation: {pattern_recommendation} (confidence: {pattern_confidence})

AVAILABLE STEPS: {available_steps}

RULES:
1. Never recommend a step already in completed_steps
2. If complexity_cap is "low", only recommend steps: welcome, health_goals, product_match, purchase_cta
3. If trust_level < 0.4, trust_signals must come before product_match
4. If intent_signal is "ready_to_buy", prioritize purchase_cta or product_match
5. If risk_action is "inject_trust_signal", next step should build trust
6. Resolve bandit vs pattern store conflicts using this priority:
   - If bandit_samples < {bandit_min_samples}: trust pattern store more
   - If both confident and conflicting: prefer pattern store and note it as micro-explore

Respond with:
{{
  "next_step": "<step value>",
  "reasoning": "<which source won, why, and what override rules applied>",
  "content_variant": "<default | trust_first | social_proof_heavy | minimal>",
  "personalization_hints": {{
    "headline_focus": "<what to emphasize in copy>",
    "show_price": <true | false>,
    "review_persona_filter": "<persona to filter reviews by, or null>"
  }}
}}
"""
    )
])

_chain = _prompt | _llm | _parser


def planner_agent_node(state: OnboardingState) -> OnboardingState:
    """
    The Planner runs after Risk Agent confirms no hard override.
    It receives enriched state from both Empathy and Risk agents and
    produces a single next_step decision with personalization hints.

    The bandit + pattern store values are stubs here — in production
    these come from the Intelligence Layer (intelligence/bandit.py).
    """
    signal  = state["signal_output"]
    profile = state["user_profile"]
    empathy = state["empathy_output"]
    risk    = state["risk_output"]

    # Steps not yet completed = still available
    available = [
        s.value for s in OnboardingStep
        if s not in profile.completed_steps
    ]

    # Determine effective complexity cap:
    # Take the more restrictive of Signal Processor's cap and Empathy Agent's cap.
    # "low" < "medium" < "high"
    cap_order = {ComplexityCap.LOW: 0, ComplexityCap.MEDIUM: 1, ComplexityCap.HIGH: 2}
    effective_cap = (
        signal.complexity_cap
        if cap_order[signal.complexity_cap] <= cap_order[empathy.recommended_cap]
        else empathy.recommended_cap
    ) if empathy else signal.complexity_cap

    raw = _chain.invoke({
        "dominant_persona":    profile.persona_scores.dominant(),
        "persona_scores":      profile.persona_scores.model_dump(),
        "health_goals":        [g.value for g in profile.health_goals],
        "trust_level":         profile.trust_level,
        "purchase_readiness":  profile.purchase_readiness,
        "content_preference":  profile.content_preference,
        "price_sensitivity":   profile.price_sensitivity,
        "completed_steps":     [s.value for s in profile.completed_steps],
        "skipped_steps":       [s.value for s in profile.skipped_steps],
        "current_step":        profile.current_step.value,
        "emotional_state":     empathy.state.value if empathy else "neutral",
        "empathy_confidence":  empathy.confidence if empathy else 0.5,
        "engagement_score":    signal.engagement_score,
        "intent_signal":       signal.intent_signal,
        "complexity_cap":      effective_cap.value,
        "risk_action":         risk.risk_action.value if risk else "none",
        "time_of_day":         signal.time_of_day,
        # Stub bandit + pattern store values — replaced by Intelligence Layer later
        "bandit_recommendation": "social_proof",
        "bandit_confidence":     0.65,
        "bandit_samples":        120,
        "pattern_recommendation": "trust_signals",
        "pattern_confidence":     0.78,
        "available_steps":        available,
        "bandit_min_samples":     settings.bandit_min_samples,
    })

    planner_output = PlannerOutput(
        next_step             = OnboardingStep(raw["next_step"]),
        reasoning             = raw["reasoning"],
        content_variant       = raw.get("content_variant", "default"),
        personalization_hints = raw.get("personalization_hints", {}),
    )

    return {"planner_output": planner_output}
