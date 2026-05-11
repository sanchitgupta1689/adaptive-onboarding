from langgraph.graph import StateGraph, END
from graph.state import OnboardingState
from agents.empathy_agent import empathy_agent_node
from agents.risk_agent import risk_agent_node
from agents.planner_agent import planner_agent_node
from agents.execution_agent import execution_agent_node
from config.settings import get_settings

settings = get_settings()


def route_after_risk(state: OnboardingState) -> str:
    """
    Routing function called after the Risk Agent completes.
    This is a conditional edge in the LangGraph — it decides
    which node to go to next based on the Risk Agent's output.

    If hard_override is True, the Planner is skipped entirely
    and we go straight to Execution with the override step.
    If not, normal flow continues through the Planner.
    """
    risk = state.get("risk_output")
    if risk and risk.hard_override:
        return "execution_agent"   # skip planner — emergency intervention
    return "planner_agent"         # normal flow


def build_graph() -> StateGraph:
    """
    Constructs and compiles the LangGraph StateGraph.

    Node execution order:
      empathy_agent → risk_agent → (conditional) → planner_agent → execution_agent
                                                 ↘ execution_agent (hard override)

    Each node is a Python function that receives OnboardingState and returns
    a partial dict of updated fields. LangGraph merges the partial dict into
    the full state automatically — nodes only need to return what changed.
    """
    graph = StateGraph(OnboardingState)

    # Register nodes — each node is an agent function
    graph.add_node("empathy_agent",   empathy_agent_node)
    graph.add_node("risk_agent",      risk_agent_node)
    graph.add_node("planner_agent",   planner_agent_node)
    graph.add_node("execution_agent", execution_agent_node)

    # Entry point — first node to run on every invocation
    graph.set_entry_point("empathy_agent")

    # Fixed edges — always run in this order
    graph.add_edge("empathy_agent", "risk_agent")

    # Conditional edge — route_after_risk decides the next node
    graph.add_conditional_edges(
        "risk_agent",
        route_after_risk,
        {
            "planner_agent":   "planner_agent",
            "execution_agent": "execution_agent",   # hard override path
        }
    )

    graph.add_edge("planner_agent",   "execution_agent")
    graph.add_edge("execution_agent", END)

    # compile() validates the graph structure and returns a runnable.
    # After this, the graph can be invoked like a function.
    return graph.compile()


# Module-level compiled graph — created once, reused for every request.
# Building the graph is cheap but we avoid doing it per-request.
onboarding_graph = build_graph()
