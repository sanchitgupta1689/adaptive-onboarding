from typing import TypedDict, Optional
from pydantic import BaseModel, Field
from enum import Enum


# ---------------------------------------------------------------------------
# Enums — fixed vocabularies used across the system
# ---------------------------------------------------------------------------

class HealthGoal(str, Enum):
    WEIGHT_LOSS   = "weight_loss"
    MUSCLE_GAIN   = "muscle_gain"
    BETTER_SLEEP  = "better_sleep"
    MORE_ENERGY   = "more_energy"
    IMMUNITY      = "immunity"
    GUT_HEALTH    = "gut_health"
    STRESS_RELIEF = "stress_relief"


class Persona(str, Enum):
    BUSY_PROFESSIONAL  = "busy_professional"
    PERFORMANCE_ATHLETE = "performance_athlete"
    CHRONIC_CONDITION  = "chronic_condition"
    WEIGHT_LOSS_SEEKER = "weight_loss_seeker"
    WELLNESS_EXPLORER  = "wellness_explorer"


class EmotionalState(str, Enum):
    MOTIVATED   = "motivated"
    SKEPTICAL   = "skeptical"
    CONFUSED    = "confused"
    OVERWHELMED = "overwhelmed"
    NEUTRAL     = "neutral"


class ComplexityCap(str, Enum):
    LOW    = "low"     # max 4 steps, simple copy, single CTA
    MEDIUM = "medium"  # standard flow
    HIGH   = "high"    # full flow, detailed content ok


class OnboardingStep(str, Enum):
    WELCOME          = "welcome"
    HEALTH_GOALS     = "health_goals"
    HEALTH_PROFILE   = "health_profile"
    PERSONA_REVEAL   = "persona_reveal"
    TRUST_SIGNALS    = "trust_signals"
    PRODUCT_MATCH    = "product_match"
    SOCIAL_PROOF     = "social_proof"
    PURCHASE_CTA     = "purchase_cta"
    COMMITMENT       = "commitment"


class RiskAction(str, Enum):
    NONE                = "none"
    INJECT_TRUST_SIGNAL = "inject_trust_signal"
    SIMPLIFY_STEP       = "simplify_step"
    OFFER_DISCOUNT      = "offer_discount"
    HUMAN_HANDOFF       = "human_handoff"
    EXIT_INTENT         = "exit_intent"


# ---------------------------------------------------------------------------
# UserProfile — the living model of who this user is.
# Updated after every action. Persisted in DB between sessions.
# ---------------------------------------------------------------------------

class PersonaScores(BaseModel):
    busy_professional:   float = 0.2
    performance_athlete: float = 0.2
    chronic_condition:   float = 0.2
    weight_loss_seeker:  float = 0.2
    wellness_explorer:   float = 0.2

    def dominant(self) -> str:
        return max(self.model_dump(), key=self.model_dump().get)


class UserProfile(BaseModel):
    user_id:            str
    email:              Optional[str] = None

    # Set explicitly by user during quiz
    health_goals:       list[HealthGoal] = Field(default_factory=list)
    age_range:          Optional[str] = None          # "25-34", "35-44" etc.
    activity_level:     Optional[str] = None          # "sedentary", "moderate", "active"
    diet_type:          Optional[str] = None          # "vegan", "keto", "no preference"
    known_conditions:   list[str] = Field(default_factory=list)
    budget_range:       Optional[str] = None          # "low", "medium", "high"

    # Continuously inferred from behavior — never set by user
    persona_scores:     PersonaScores = Field(default_factory=PersonaScores)
    trust_level:        float = 0.5                   # 0=no trust, 1=full trust
    purchase_readiness: float = 0.3                   # 0=not ready, 1=ready to buy
    engagement_score:   float = 0.5
    price_sensitivity:  str = "medium"                # "low", "medium", "high"
    content_preference: str = "visual_brief"          # "visual_brief", "text_deep"

    # Session tracking
    current_step:       OnboardingStep = OnboardingStep.WELCOME
    completed_steps:    list[OnboardingStep] = Field(default_factory=list)
    skipped_steps:      list[OnboardingStep] = Field(default_factory=list)
    session_count:      int = 1


# ---------------------------------------------------------------------------
# SignalOutput — output of the Signal Processor.
# Computed from raw events BEFORE agents see anything.
# ---------------------------------------------------------------------------

class SignalOutput(BaseModel):
    engagement_score:   float                         # 0-1, how engaged is the user right now
    intent_signal:      str                           # "browsing", "deciding", "ready_to_buy"
    churn_risk_score:   float                         # 0-1, probability of drop-off
    hesitation_flag:    bool                          # True if re-reads or long dwell + no action
    complexity_cap:     ComplexityCap                 # derived from hesitation + scroll pattern
    session_gap_days:   float = 0.0                   # days since last session
    time_of_day:        str = "unknown"               # "morning", "afternoon", "evening", "night"


# ---------------------------------------------------------------------------
# EmpathyOutput — output of the Empathy Agent.
# A Gemini Flash call that reads SignalOutput + recent actions and
# classifies the user's current emotional state.
# ---------------------------------------------------------------------------

class EmpathyOutput(BaseModel):
    state:              EmotionalState
    confidence:         float                         # 0-1
    reasoning:          str                           # why the agent chose this state
    recommended_cap:    ComplexityCap                 # empathy agent's complexity suggestion


# ---------------------------------------------------------------------------
# RiskOutput — output of the Risk Agent.
# Decides if and how to intervene before the Planner runs.
# ---------------------------------------------------------------------------

class RiskOutput(BaseModel):
    churn_risk:         float
    risk_action:        RiskAction
    hard_override:      bool                          # True = skip Planner entirely
    override_step:      Optional[OnboardingStep] = None  # step to show if hard_override


# ---------------------------------------------------------------------------
# PlannerOutput — output of the Planner Agent.
# The Planner resolves Bandit + Pattern Store + its own reasoning
# into a single next step decision.
# ---------------------------------------------------------------------------

class PlannerOutput(BaseModel):
    next_step:          OnboardingStep
    reasoning:          str                           # which source won and why
    content_variant:    str = "default"               # which A/B variant to show
    personalization_hints: dict = Field(default_factory=dict)  # passed to Execution Agent


# ---------------------------------------------------------------------------
# OnboardingState — the single object passed between all LangGraph nodes.
# Every agent reads from it and writes its output back into it.
# Think of it as the shared whiteboard for the entire agent team.
# ---------------------------------------------------------------------------

class OnboardingState(TypedDict):
    user_profile:    UserProfile
    signal_output:   SignalOutput
    empathy_output:  Optional[EmpathyOutput]   # None until Empathy Agent runs
    risk_output:     Optional[RiskOutput]      # None until Risk Agent runs
    planner_output:  Optional[PlannerOutput]   # None until Planner Agent runs
    final_action:    Optional[dict]            # filled by Execution Agent, sent to client
