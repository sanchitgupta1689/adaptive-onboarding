from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from graph.state import OnboardingState, OnboardingStep, RiskAction
from config.settings import get_settings

settings = get_settings()

_llm = ChatGoogleGenerativeAI(
    model=settings.gemini_flash_model,
    temperature=0.4,  # slight creativity ok — this generates UI copy
    google_api_key=settings.google_api_key,
)

_parser = JsonOutputParser()

_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are generating the exact content payload for a specific onboarding screen
in a health ecommerce app. Your output is sent directly to the frontend — it must be
production-ready copy, not placeholders.

Be concise. Health app users are often short on time. Respond with valid JSON only."""
    ),
    (
        "human",
        """Generate the content for this onboarding screen.

SCREEN TO RENDER: {next_step}
CONTENT VARIANT: {content_variant}

USER CONTEXT:
- Dominant persona: {dominant_persona}
- Health goals: {health_goals}
- Emotional state: {emotional_state}
- Trust level: {trust_level}
- Complexity cap: {complexity_cap}
- Personalization hints: {personalization_hints}
- Risk action to apply: {risk_action}

PRODUCT RECOMMENDATIONS (for product_match / purchase_cta steps):
{product_recommendations}

SOCIAL PROOF (for social_proof / trust_signals steps):
{social_proof}

Generate the screen content as:
{{
  "step": "{next_step}",
  "headline": "<main heading — max 8 words>",
  "subheadline": "<supporting line — max 15 words, or null>",
  "body": "<main content — adapt length to complexity_cap: low=1 sentence, medium=2-3, high=4+>",
  "cta_primary": "<primary button label>",
  "cta_secondary": "<secondary option or null>",
  "trust_badge": "<inline trust signal to show if risk_action=inject_trust_signal, else null>",
  "product_cards": [
    {{"id": "<id>", "name": "<name>", "benefit": "<one benefit line>", "price": "<price>"}}
  ],
  "reviews": [
    {{"author": "<first name + age>", "goal": "<their goal>", "text": "<review, max 20 words>"}}
  ],
  "next_step_id": "{next_step}"
}}

Only include product_cards if step is product_match or purchase_cta.
Only include reviews if step is social_proof.
"""
    )
])

_chain = _prompt | _llm | _parser


def execution_agent_node(state: OnboardingState) -> OnboardingState:
    """
    Final node in the graph. Takes the Planner's decision and generates
    the actual screen content payload to send to the frontend.

    Also handles the hard_override case from the Risk Agent —
    if the Risk Agent bypassed the Planner, we still need to render
    the override step with appropriate content.
    """
    profile = state["user_profile"]
    signal  = state["signal_output"]
    empathy = state["empathy_output"]
    risk    = state["risk_output"]
    planner = state["planner_output"]

    # Determine which step to render:
    # Risk hard override takes precedence over Planner decision
    if risk and risk.hard_override and risk.override_step:
        next_step = risk.override_step
        content_variant = "trust_first"
    else:
        next_step = planner.next_step
        content_variant = planner.content_variant if planner else "default"

    personalization_hints = planner.personalization_hints if planner else {}

    raw = _chain.invoke({
        "next_step":               next_step.value,
        "content_variant":         content_variant,
        "dominant_persona":        profile.persona_scores.dominant(),
        "health_goals":            [g.value for g in profile.health_goals],
        "emotional_state":         empathy.state.value if empathy else "neutral",
        "trust_level":             profile.trust_level,
        "complexity_cap":          signal.complexity_cap.value,
        "personalization_hints":   personalization_hints,
        "risk_action":             risk.risk_action.value if risk else "none",
        # These will be populated by tools in the full implementation
        # For now passing empty — Intelligence Layer will inject these
        "product_recommendations": "[]",
        "social_proof":            "[]",
    })

    # Merge rendered step into final_action
    # This dict is what the API route returns to the client
    final_action = {
        "rendered_step":    raw,
        "next_step_id":     next_step.value,
        "risk_action":      risk.risk_action.value if risk else "none",
        "empathy_state":    empathy.state.value if empathy else "neutral",
        "planner_reasoning": planner.reasoning if planner else "risk_override",
    }

    return {"final_action": final_action}
