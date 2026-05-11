from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from langsmith import traceable
from graph.state import OnboardingState, UserProfile, OnboardingStep
from graph.orchestrator import onboarding_graph
from signal_processor.processor import RawEvent, process_event
from intelligence.user_model import update_on_event, update_current_step

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

# ---------------------------------------------------------------------------
# In-memory user profile store.
# Replace with Redis or PostgreSQL in production.
# Key: user_id, Value: UserProfile
# ---------------------------------------------------------------------------
_user_store: dict[str, UserProfile] = {}


class StartOnboardingRequest(BaseModel):
    user_id: str
    email: Optional[str] = None


class EventRequest(BaseModel):
    """
    Sent by the client after every meaningful user interaction.
    The client measures timing and scroll signals natively and includes
    them in this payload.
    """
    user_id:            str
    event_type:         str
    step:               str
    dwell_time_seconds: float = 0
    scroll_depth:       float = 0
    scroll_velocity:    float = 0
    reread_count:       int = 0
    session_gap_days:   float = 0


@router.post("/start")
async def start_onboarding(req: StartOnboardingRequest):
    """
    Called when a new user signs up or returns to start onboarding.
    Creates a fresh UserProfile and returns the first step (WELCOME).
    """
    profile = UserProfile(
        user_id=req.user_id,
        email=req.email,
    )
    _user_store[req.user_id] = profile

    return {
        "user_id":      req.user_id,
        "current_step": profile.current_step.value,
        "message":      "Onboarding started. Send events to /event to progress."
    }


@router.post("/event")
async def handle_event(req: EventRequest):
    """
    Main endpoint. Called after every user action on the frontend.

    Flow:
      1. Load user profile from store
      2. Process raw event → SignalOutput (pure math, no LLM)
      3. Update UserProfile based on event (persona scores, trust level etc.)
      4. Run the LangGraph: Empathy → Risk → Planner → Execution
      5. Update user's current step
      6. Return the rendered screen content to the client

    All LangChain and LangSmith tracing is automatic — every LLM call
    inside the graph is recorded in LangSmith with no extra code needed.
    """
    profile = _user_store.get(req.user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found. Call /start first.")

    # Step 1: Build RawEvent from request
    raw_event = RawEvent(
        user_id=req.user_id,
        event_type=req.event_type,
        step=req.step,
        dwell_time_seconds=req.dwell_time_seconds,
        scroll_depth=req.scroll_depth,
        scroll_velocity=req.scroll_velocity,
        reread_count=req.reread_count,
        session_gap_days=req.session_gap_days,
    )

    # Step 2: Signal Processor — pure math, no LLM
    signal_output = process_event(raw_event)

    # Step 3: Update UserProfile based on this event
    profile = update_on_event(profile, raw_event)

    # Step 4: Build state and run the LangGraph.
    # @traceable wraps the invoke call with a named root span in LangSmith,
    # attaching user_id, step, event_type, and key signals as metadata.
    # Every agent node inside the graph becomes a child span of this root,
    # so you can see the full session trace in one place.
    initial_state: OnboardingState = {
        "user_profile":  profile,
        "signal_output": signal_output,
        "empathy_output": None,
        "risk_output":    None,
        "planner_output": None,
        "final_action":   None,
    }

    @traceable(
        name="onboarding_session",
        metadata={
            "user_id":          req.user_id,
            "step":             req.step,
            "event_type":       req.event_type,
            "session_count":    profile.session_count,
            "persona":          profile.persona_scores.dominant(),
            "trust_level":      profile.trust_level,
            "churn_risk":       signal_output.churn_risk_score,
            "engagement_score": signal_output.engagement_score,
            "hesitation_flag":  signal_output.hesitation_flag,
            "emotional_intent": signal_output.intent_signal,
        }
    )
    def run_graph(state: OnboardingState):
        return onboarding_graph.invoke(state)

    result_state = run_graph(initial_state)

    # Step 5: Update user's current step based on what the agent decided
    next_step_value = result_state["final_action"]["next_step_id"]
    profile = update_current_step(profile, OnboardingStep(next_step_value))
    _user_store[req.user_id] = profile

    # Step 6: Return the rendered screen to the client
    return result_state["final_action"]


@router.get("/profile/{user_id}")
async def get_profile(user_id: str):
    """
    Debug endpoint — returns the current UserProfile for a user.
    Useful for inspecting how the Dynamic User Model has evolved.
    """
    profile = _user_store.get(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found.")
    return profile.model_dump()
