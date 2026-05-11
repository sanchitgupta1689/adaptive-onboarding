from datetime import datetime
from pydantic import BaseModel
from graph.state import SignalOutput, ComplexityCap


# ---------------------------------------------------------------------------
# RawEvent — the payload the client sends on every user action.
# The mobile/web app fires this after each meaningful interaction.
# ---------------------------------------------------------------------------

class RawEvent(BaseModel):
    user_id:            str
    event_type:         str        # "step_viewed", "step_skipped", "step_completed",
                                   # "product_tapped", "scroll", "field_input", "session_start"
    step:               str        # which onboarding step this event belongs to
    dwell_time_seconds: float = 0  # how long user stayed on the current screen
    scroll_depth:       float = 0  # 0.0 (top) to 1.0 (bottom of screen)
    scroll_velocity:    float = 0  # pixels/second — fast = skimming, slow = reading
    reread_count:       int = 0    # how many times user navigated back to this screen
    session_gap_days:   float = 0  # days since the user's last session
    timestamp:          datetime = datetime.utcnow()


def compute_engagement_score(event: RawEvent) -> float:
    """
    Engagement score is a 0-1 number representing how actively the user
    is reading and interacting — not just tapping through.

    Formula weighs three signals:
      - Dwell time:      normalized against a 30s "ideal" read time
      - Scroll depth:    did they read to the bottom or bail early?
      - Scroll velocity: slow scroll = reading, fast = skimming
    """
    # Normalize dwell time: 30s = 1.0, anything above caps at 1.0
    dwell_score = min(event.dwell_time_seconds / 30.0, 1.0)

    # Scroll depth is already 0-1
    depth_score = event.scroll_depth

    # Velocity score: slow (< 100 px/s) = 1.0, fast (> 500 px/s) = 0.0
    velocity_score = max(0.0, 1.0 - (event.scroll_velocity / 500.0))

    # Weighted average — dwell time carries the most weight
    return round(
        (dwell_score * 0.5) + (depth_score * 0.3) + (velocity_score * 0.2),
        3
    )


def compute_intent_signal(event: RawEvent, engagement: float) -> str:
    """
    Intent signal classifies what mode the user is in:
      - "ready_to_buy":  high engagement on product/CTA steps
      - "deciding":      moderate engagement, product steps
      - "browsing":      low engagement or early steps
    """
    product_steps = {"product_match", "purchase_cta", "social_proof"}

    if event.step in product_steps and engagement > 0.7:
        return "ready_to_buy"
    elif event.step in product_steps and engagement > 0.4:
        return "deciding"
    return "browsing"


def compute_churn_risk(event: RawEvent, engagement: float) -> float:
    """
    Churn risk is a 0-1 score. Multiple signals contribute additively.
    Each signal adds a fixed risk increment — these weights were chosen
    based on typical ecommerce drop-off patterns.

    Real production version: replace this with an XGBoost model trained
    on historical session outcomes. This heuristic is a good starting point.
    """
    risk = 0.0

    if event.event_type == "step_skipped":
        risk += 0.25

    # Session gap: longer gap = higher re-engagement risk
    if event.session_gap_days > 3:
        risk += 0.20
    elif event.session_gap_days > 1:
        risk += 0.10

    # Re-reading the same screen: sign of confusion or hesitation
    if event.reread_count >= 2:
        risk += 0.15

    # Low engagement on a content-heavy step
    if engagement < 0.3 and event.dwell_time_seconds > 5:
        risk += 0.15

    # Very fast scroll: skimming without reading
    if event.scroll_velocity > 400:
        risk += 0.10

    return round(min(risk, 1.0), 3)


def compute_hesitation(event: RawEvent, engagement: float) -> bool:
    """
    Hesitation flag = True when the user is lingering but not acting.
    Pattern: long dwell + low scroll depth + no completion = stuck.
    Also triggered by re-reading the same screen.
    """
    long_dwell_no_action = (
        event.dwell_time_seconds > 15
        and event.scroll_depth < 0.4
        and event.event_type not in ("step_completed", "product_tapped")
    )
    return long_dwell_no_action or event.reread_count >= 2


def compute_complexity_cap(
    hesitation: bool,
    churn_risk: float,
    engagement: float
) -> ComplexityCap:
    """
    Complexity cap limits how much content/choices the Planner can surface.
    Derived purely from behavioral features — no LLM needed.

      LOW:    overwhelmed/hesitant user — short steps, single CTA
      MEDIUM: normal user
      HIGH:   engaged user who can handle more detail
    """
    if hesitation or churn_risk > 0.6 or engagement < 0.3:
        return ComplexityCap.LOW
    elif engagement > 0.7 and churn_risk < 0.3:
        return ComplexityCap.HIGH
    return ComplexityCap.MEDIUM


def get_time_of_day(ts: datetime) -> str:
    hour = ts.hour
    if 5 <= hour < 12:
        return "morning"
    elif 12 <= hour < 17:
        return "afternoon"
    elif 17 <= hour < 21:
        return "evening"
    return "night"


def process_event(event: RawEvent) -> SignalOutput:
    """
    Main entry point. Takes a raw client event and returns a structured
    SignalOutput that all agents consume.

    This runs synchronously and must be fast (< 5ms).
    No LLM calls here — pure math and rules.
    """
    engagement   = compute_engagement_score(event)
    intent       = compute_intent_signal(event, engagement)
    churn_risk   = compute_churn_risk(event, engagement)
    hesitation   = compute_hesitation(event, engagement)
    complexity   = compute_complexity_cap(hesitation, churn_risk, engagement)
    time_of_day  = get_time_of_day(event.timestamp)

    return SignalOutput(
        engagement_score  = engagement,
        intent_signal     = intent,
        churn_risk_score  = churn_risk,
        hesitation_flag   = hesitation,
        complexity_cap    = complexity,
        session_gap_days  = event.session_gap_days,
        time_of_day       = time_of_day,
    )
