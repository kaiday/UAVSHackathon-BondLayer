"""Interpreter seam for catalogue integration; resolution not implemented yet."""

from bondlayer.types import Constraint, Proposal, SignedRecord, Sku

from .parser import parse


def resolve(
    constraints: list[Constraint], skus: list[Sku], records: list[SignedRecord],
) -> list[Proposal]:
    # ponytail: integration stub only; replace with attribute/evidence resolution.
    return []


class ConstraintInterpreter:
    """Implements bondlayer.types.ConstraintInterpreter without changing it."""

    parse = staticmethod(parse)
    resolve = staticmethod(resolve)
