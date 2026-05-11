from graph.state import UserProfile, OnboardingStep, PersonaScores
from signal_processor.processor import RawEvent


# How much each signal shifts persona scores and trust level.
# Small increments ensure one action doesn't dominate — the model
# converges gradually over many actions, like a learning rate in ML.
PERSONA_SHIFT = 0.05
TRUST_SHIFT   = 0.04
READINESS_SHIFT = 0.06


def update_on_event(profile: UserProfile, event: RawEvent) -> UserProfile:
    """
    Updates the UserProfile based on a new raw event.
    Called by the Execution Agent after every user action.

    Returns a new UserProfile (immutable update pattern — we never
    mutate the object in place, we return a modified copy).
    """
    data = profile.model_dump()

    scores = data["persona_scores"]

    # --- Persona score updates ---
    # Each step gives us evidence about which persona this user is.

    if event.event_type == "step_completed":
        step = event.step

        if step == "health_goals":
            # Completing the goals quiz = engaged, likely wellness_explorer
            scores["wellness_explorer"] = min(1.0, scores["wellness_explorer"] + PERSONA_SHIFT)

        elif step == "health_profile":
            # Completing the full profile = detail-oriented, likely chronic_condition or athlete
            scores["performance_athlete"] = min(1.0, scores["performance_athlete"] + PERSONA_SHIFT * 0.5)
            scores["chronic_condition"]   = min(1.0, scores["chronic_condition"] + PERSONA_SHIFT * 0.5)

        elif step == "product_match":
            # Engaging with products = some purchase intent
            scores["weight_loss_seeker"]  = min(1.0, scores["weight_loss_seeker"] + PERSONA_SHIFT)
            data["purchase_readiness"]    = min(1.0, data["purchase_readiness"] + READINESS_SHIFT)

        elif step == "trust_signals":
            # Reading trust content = was skeptical, now building trust
            data["trust_level"] = min(1.0, data["trust_level"] + TRUST_SHIFT)

        elif step == "purchase_cta":
            data["purchase_readiness"] = min(1.0, data["purchase_readiness"] + READINESS_SHIFT * 2)

        # Mark step as completed
        completed = data["completed_steps"]
        if step not in completed:
            completed.append(step)

    elif event.event_type == "step_skipped":
        step = event.step

        # Skipping trust signals = already trusts or doesn't care
        if step == "trust_signals":
            data["trust_level"] = min(1.0, data["trust_level"] + TRUST_SHIFT)

        # Skipping product = price sensitivity or low readiness
        if step == "product_match":
            data["price_sensitivity"] = "high"
            data["purchase_readiness"] = max(0.0, data["purchase_readiness"] - READINESS_SHIFT)

        skipped = data["skipped_steps"]
        if step not in skipped:
            skipped.append(step)

    elif event.event_type == "product_tapped":
        # Tapping a product is a strong purchase intent signal
        data["purchase_readiness"] = min(1.0, data["purchase_readiness"] + READINESS_SHIFT * 1.5)

    # --- Engagement-based trust update ---
    # High engagement on any step slowly builds trust
    if event.dwell_time_seconds > 20 and event.scroll_depth > 0.7:
        data["trust_level"] = min(1.0, data["trust_level"] + TRUST_SHIFT * 0.5)

    # --- Content preference inference ---
    # Slow reading of long content = text_deep preference
    if event.scroll_velocity < 80 and event.dwell_time_seconds > 25:
        data["content_preference"] = "text_deep"
    # Fast scroll but high completion = visual_brief preference
    elif event.scroll_velocity > 300 and event.event_type == "step_completed":
        data["content_preference"] = "visual_brief"

    # Renormalize persona scores so they sum to 1.0
    total = sum(scores.values())
    if total > 0:
        for k in scores:
            scores[k] = round(scores[k] / total, 4)

    data["persona_scores"] = scores
    return UserProfile(**data)


def update_current_step(profile: UserProfile, next_step: OnboardingStep) -> UserProfile:
    """Updates current_step after the agent decides the next step to show."""
    data = profile.model_dump()
    data["current_step"] = next_step.value
    return UserProfile(**data)
