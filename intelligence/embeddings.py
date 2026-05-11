from langchain_google_genai import GoogleGenerativeAIEmbeddings
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from config.settings import get_settings

settings = get_settings()

# GoogleGenerativeAIEmbeddings wraps Google's text-embedding-004 model.
# It converts any text string into a 768-dimension float vector.
# Similar texts produce vectors that are close together in this space.
_embeddings = GoogleGenerativeAIEmbeddings(
    model=settings.gemini_embedding_model,
    google_api_key=settings.google_api_key,
)


def embed_text(text: str) -> list[float]:
    """Embed a single text string into a vector."""
    return _embeddings.embed_query(text)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of strings in a single batch API call — more efficient."""
    return _embeddings.embed_documents(texts)


def find_top_matches(
    query_text: str,
    candidates: list[dict],
    text_field: str,
    top_k: int = 3,
) -> list[dict]:
    """
    Given a query (e.g. user's health goal as a sentence) and a list of
    candidate dicts (e.g. products or reviews), return the top_k candidates
    whose `text_field` is most semantically similar to the query.

    This is how we match products and reviews to the user's profile
    without needing a vector database — we compute similarity on the fly.

    Example:
        query_text = "I want to lose weight and have more energy"
        candidates = [{"id": "p1", "description": "Fat burner with green tea"}, ...]
        find_top_matches(query_text, candidates, "description", top_k=3)

    How cosine_similarity works:
        Two vectors are compared by the angle between them (not magnitude).
        Score of 1.0 = identical direction = very similar meaning.
        Score of 0.0 = perpendicular = unrelated.
        Score of -1.0 = opposite = contradictory (rare in practice).
    """
    # Embed the query
    query_vector = np.array(embed_text(query_text)).reshape(1, -1)

    # Embed all candidate texts in one batch call
    candidate_texts = [c[text_field] for c in candidates]
    candidate_vectors = np.array(embed_texts(candidate_texts))

    # Compute similarity between query and every candidate
    # Returns shape (1, N) — one score per candidate
    scores = cosine_similarity(query_vector, candidate_vectors)[0]

    # Attach score to each candidate and sort descending
    scored = sorted(
        zip(scores, candidates),
        key=lambda x: x[0],
        reverse=True
    )

    # Return the top_k candidates (without the score, just the original dict)
    return [candidate for _, candidate in scored[:top_k]]


def build_user_query(profile) -> str:
    """
    Converts a UserProfile into a natural language query string
    for embedding-based similarity search.

    We describe the user in plain English so the embedding model
    can find semantically similar products/reviews.
    """
    goals = ", ".join([g.value.replace("_", " ") for g in profile.health_goals])
    persona = profile.persona_scores.dominant().replace("_", " ")
    diet = profile.diet_type or "no specific diet"

    return (
        f"A {persona} looking to achieve: {goals}. "
        f"Diet preference: {diet}. "
        f"Activity level: {profile.activity_level or 'moderate'}."
    )
