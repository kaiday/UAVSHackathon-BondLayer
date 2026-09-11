"""Store adapters: the seam between AgentBridge and a real commerce backend."""

from agentbridge.adapters.base import StoreAdapter
from agentbridge.adapters.mock import MockStoreAdapter

__all__ = ["StoreAdapter", "MockStoreAdapter"]
