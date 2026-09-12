"""Agent-side composition root.

Nothing here is merchant-side. The merchant serves; this consumes.
"""

from bondlayer.agent.composition import BENEFIT_EXT, DEFAULT_POLICY, run_request
from bondlayer.agent.trace import AgentRun, Outcome, Phase, Ranked, Step

__all__ = [
    "BENEFIT_EXT", "DEFAULT_POLICY", "run_request",
    "AgentRun", "Outcome", "Phase", "Ranked", "Step",
]
