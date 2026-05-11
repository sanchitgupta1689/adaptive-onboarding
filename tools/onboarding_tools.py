import json
from pathlib import Path
from graph.state import UserProfile
from intelligence.embeddings import find_top_matches, build_user_query

# Load product catalog once at module import time — not on every request
_PRODUCTS_PATH = Path(__file__).parent.parent / "data" / "products.json"
_PRODUCTS: list[dict] = json.loads(_PRODUCTS_PATH.read_text())

# Static review bank — in production this comes from a database
_REVIEWS = [
    {
        "id": "r001",
        "author": "Priya, 31",
        "goal": "weight_loss",
        "persona": "busy_professional",
        "product_id": "p001",
        "text": "Lost 4kg in 6 weeks. Perfect for my desk job lifestyle.",
        "rating": 5,
        "description": "A busy professional who lost weight with LeanBurn Pro despite a sedentary desk job"
    },
    {
        "id": "r002",
        "author": "Rahul, 28",
        "goal": "muscle_gain",
        "persona": "performance_athlete",
        "product_id": "p003",
        "text": "Noticeably stronger in 3 weeks. Recovery time cut in half.",
        "rating": 5,
        "description": "A performance athlete who gained muscle and reduced recovery time with PerformanceStack"
    },
    {
        "id": "r003",
        "author": "Ananya, 35",
        "goal": "better_sleep",
        "persona": "busy_professional",
        "product_id": "p002",
        "text": "Finally sleeping through the night. No grogginess in the morning.",
        "rating": 5,
        "description": "A busy professional who fixed sleep issues and wakes up refreshed with DeepSleep Formula"
    },
    {
        "id": "r004",
        "author": "Vikram, 42",
        "goal": "gut_health",
        "persona": "chronic_condition",
        "product_id": "p004",
        "text": "Bloating gone in 2 weeks. My gastro actually recommended this brand.",
        "rating": 5,
        "description": "A person with digestive issues who eliminated bloating with GutShield Daily, doctor-recommended"
    },
    {
        "id": "r005",
        "author": "Meera, 29",
        "goal": "stress_relief",
        "persona": "busy_professional",
        "product_id": "p006",
        "text": "Calmer at work, sharper focus. The afternoon slump is gone.",
        "rating": 5,
        "description": "A busy professional who reduced work stress and improved focus with CalmMind Adapt"
    },
    {
        "id": "r006",
        "author": "Karan, 33",
        "goal": "immunity",
        "persona": "wellness_explorer",
        "product_id": "p005",
        "text": "Haven't fallen sick this entire winter. Worth every rupee.",
        "rating": 5,
        "description": "A wellness enthusiast who stayed healthy all winter with ImmunityShield"
    },
    {
        "id": "r007",
        "author": "Sunita, 38",
        "goal": "more_energy",
        "persona": "busy_professional",
        "product_id": "p008",
        "text": "No more 3pm crashes. Consistent energy without caffeine jitters.",
        "rating": 5,
        "description": "A busy professional who eliminated afternoon energy crashes with EnergyFlow B-Complex"
    }
]


def get_product_recommendations(profile: UserProfile, top_k: int = 3) -> list[dict]:
    """
    Returns the top_k products most relevant to the user's goals and persona.

    Uses embedding similarity: the user's profile is converted to a natural
    language query, then compared against each product's description vector.
    Products whose descriptions are semantically closest to the user's goals
    are ranked highest.

    Falls back to goal-based filtering if no health goals are set yet.
    """
    if not profile.health_goals:
        # No goals yet — return top 3 by popularity (first 3 in catalog)
        return _PRODUCTS[:top_k]

    user_query = build_user_query(profile)
    return find_top_matches(
        query_text=user_query,
        candidates=_PRODUCTS,
        text_field="description",
        top_k=top_k,
    )


def get_social_proof(profile: UserProfile, top_k: int = 3) -> list[dict]:
    """
    Returns reviews from users with the same goals and persona.

    Embedding similarity over review descriptions means we match on
    semantic content — "a busy professional who lost weight" will match
    a user who is a busy professional with weight loss goals, even if
    the exact words differ.
    """
    if not profile.health_goals:
        return _REVIEWS[:top_k]

    user_query = build_user_query(profile)
    return find_top_matches(
        query_text=user_query,
        candidates=_REVIEWS,
        text_field="description",
        top_k=top_k,
    )


def get_trust_signals(profile: UserProfile) -> dict:
    """
    Returns trust content tailored to the user's dominant persona.
    Called when the risk_action is inject_trust_signal or step is trust_signals.
    """
    persona = profile.persona_scores.dominant()

    trust_content = {
        "busy_professional": {
            "headline": "Trusted by 50,000+ working professionals",
            "badges": ["Doctor Recommended", "GMP Certified", "30-Day Guarantee"],
            "stat": "9 out of 10 customers reorder within 60 days"
        },
        "performance_athlete": {
            "headline": "NSF Certified for Sport — safe for competition",
            "badges": ["NSF Certified", "Informed Sport", "No banned substances"],
            "stat": "Used by 2,000+ competitive athletes"
        },
        "weight_loss_seeker": {
            "headline": "Clinically studied. Real results.",
            "badges": ["Third-party tested", "GMP Certified", "Money-back guarantee"],
            "stat": "Average 3.2kg lost in the first 30 days"
        },
        "chronic_condition": {
            "headline": "Formulated with medical-grade standards",
            "badges": ["Doctor formulated", "Third-party tested", "Allergen-free options"],
            "stat": "Recommended by 1,200+ healthcare providers"
        },
        "wellness_explorer": {
            "headline": "Clean ingredients. Transparent sourcing.",
            "badges": ["Non-GMO", "Vegan certified", "Sustainably sourced"],
            "stat": "4.8/5 average rating from 15,000+ reviews"
        },
    }

    return trust_content.get(persona, trust_content["busy_professional"])
