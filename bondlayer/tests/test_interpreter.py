"""Run: python -m pytest -o pythonpath=src tests/test_interpreter.py -q"""

import json
from pathlib import Path

from bondlayer.interpreter import ConstraintInterpreter, parse
from bondlayer.types import ConstraintInterpreter as InterpreterProtocol, ConstraintKind


def test_r01_four_typed_constraints():
    request = json.loads((Path(__file__).parents[1] / "data/eval/requests.json").read_text())["requests"][0]
    constraints = parse(request["utterance"])
    assert len(constraints) == 4
    assert {item.kind for item in constraints} == set(ConstraintKind)
    assert all(item.text in request["utterance"] for item in constraints)
    assert any("laptop" in item.text and "$1,500" in item.text for item in constraints)


def test_protocol_stub_is_importable_and_explicitly_empty():
    interpreter: InterpreterProtocol = ConstraintInterpreter()
    assert interpreter.parse("laptop")
    assert interpreter.resolve(interpreter.parse("laptop"), [], []) == []
