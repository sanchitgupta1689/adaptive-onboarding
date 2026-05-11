import json
import random
from pathlib import Path
from typing import Optional
from graph.state import OnboardingStep

# ---------------------------------------------------------------------------
# Contextual Bandit — Epsilon-Greedy implementation
#
# A contextual bandit picks the best "arm" (next onboarding step) for a
# given context (persona + trust level + time of day). It learns by updating
# arm weights every time we observe an outcome (converted / churned).
#
# Why epsilon-greedy?
#   - Simple to implement, easy to debug, no external dependency
#   - Epsilon=0.15 means: 85% of the time exploit the known best arm,
#     15% of the time explore a random arm to keep learning
#   - Production upgrade path: swap for Vowpal Wabbit or a Thompson Sampling
#     model without changing the interface
#
# Persistence: arm weights are saved to bandit_state.json after every update
# so the bandit retains its learning across server restarts.
# ---------------------------------------------------------------------------

EPSILON       = 0.15   # exploration rate — 15% random, 85% exploit
MIN_SAMPLES   = 5      # minimum observations before we trust an arm's rate
BANDIT_STATE_PATH = Path(__file__).parent.parent / "data" / "bandit_state.json"

# All arms the bandit can recommend (a single next step)
ALL_ARMS = [s.value for s in OnboardingStep]


def _context_key(persona: str, trust_bucket: str, time_of_day: str) -> str:
    """
    Compress context into a string key for the state dict.
    trust_bucket buckets trust_level float into low/medium/high
    so similar users share the same context bucket.
    """
    return f"{persona}|{trust_bucket}|{time_of_day}"


def _trust_bucket(trust_level: float) -> str:
    if trust_level < 0.35:
        return "low"
    elif trust_level < 0.65:
        return "medium"
    return "high"


def _load_state() -> dict:
    """Load bandit arm weights from disk. Returns empty dict if file missing."""
    if BANDIT_STATE_PATH.exists():
        return json.loads(BANDIT_STATE_PATH.read_text())
    return {}


def _save_state(state: dict) -> None:
    BANDIT_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BANDIT_STATE_PATH.write_text(json.dumps(state, indent=2))


def _get_arm_stats(state: dict, context_key: str, arm: str) -> dict:
    """Returns stats for a specific arm in a context. Initialises if missing."""
    return state.setdefault(context_key, {}).setdefault(arm, {
        "tries":   0,
        "rewards": 0,
        "rate":    0.0,
    })


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def recommend(
    persona: str,
    trust_level: float,
    time_of_day: str,
    available_steps: list[str],
    exclude_steps: Optional[list[str]] = None,
) -> dict:
    """
    Returns the bandit's recommended next step for this context.

    Output:
        {
          "recommendation": "trust_signals",
          "confidence":     0.71,
          "samples":        134,
          "source":         "exploit"   # or "explore"
        }

    confidence = the arm's observed reward rate (conversions / tries)
    samples    = how many times this arm has been tried in this context
    source     = "exploit" if best known arm, "explore" if random pick
    """
    state       = _load_state()
    bucket      = _trust_bucket(trust_level)
    ctx_key     = _context_key(persona, bucket, time_of_day)
    candidates  = [s for s in available_steps if s not in (exclude_steps or [])]

    if not candidates:
        candidates = available_steps

    # Epsilon-greedy: explore with probability EPSILON
    if random.random() < EPSILON:
        chosen = random.choice(candidates)
        stats  = _get_arm_stats(state, ctx_key, chosen)
        return {
            "recommendation": chosen,
            "confidence":     stats["rate"],
            "samples":        stats["tries"],
            "source":         "explore",
        }

    # Exploit: pick the arm with highest reward rate among candidates
    # Arms with fewer than MIN_SAMPLES tries get a small optimism bonus
    # (Upper Confidence Bound idea — prefer under-explored arms slightly)
    best_arm   = None
    best_score = -1.0

    for arm in candidates:
        stats = _get_arm_stats(state, ctx_key, arm)
        tries = stats["tries"]

        if tries < MIN_SAMPLES:
            # Optimism bonus for under-explored arms
            score = stats["rate"] + (0.3 * (1 - tries / MIN_SAMPLES))
        else:
            score = stats["rate"]

        if score > best_score:
            best_score = score
            best_arm   = arm

    stats = _get_arm_stats(state, ctx_key, best_arm)
    return {
        "recommendation": best_arm,
        "confidence":     round(stats["rate"], 3),
        "samples":        stats["tries"],
        "source":         "exploit",
    }


def update(
    persona: str,
    trust_level: float,
    time_of_day: str,
    arm: str,
    reward: float,
) -> None:
    """
    Called after a session outcome is observed.
    reward = 1.0 if user converted (completed step / purchased)
    reward = 0.0 if user churned or skipped

    Updates the arm's try count and reward rate, then persists to disk.

    The reward rate is a rolling average:
        new_rate = old_rate + (1/tries) * (reward - old_rate)
    This is an incremental mean update — no need to store all past rewards.
    """
    state   = _load_state()
    bucket  = _trust_bucket(trust_level)
    ctx_key = _context_key(persona, bucket, time_of_day)
    stats   = _get_arm_stats(state, ctx_key, arm)

    stats["tries"]   += 1
    # Incremental mean: converges to the true average reward rate over time
    stats["rate"]    += (1 / stats["tries"]) * (reward - stats["rate"])
    stats["rate"]     = round(stats["rate"], 4)
    stats["rewards"] += reward

    _save_state(state)


def get_context_summary(persona: str, trust_level: float, time_of_day: str) -> dict:
    """
    Debug helper — returns all arm stats for a given context.
    Useful for inspecting what the bandit has learned.
    Exposed via a debug API endpoint.
    """
    state   = _load_state()
    bucket  = _trust_bucket(trust_level)
    ctx_key = _context_key(persona, bucket, time_of_day)
    return state.get(ctx_key, {})
