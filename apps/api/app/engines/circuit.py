"""
circuit.py — Netlist representation + Modified Nodal Analysis (MNA) solver.

Phase 1-2 of the AnalogSim roadmap: this module gives the project an actual
circuit-solving core. Node 0 is always ground (0V, not a real unknown).

Currently supports linear elements only:
    - Resistor
    - VoltageSource (independent DC source)

Nonlinear elements (diodes, MOSFETs using the existing engine functions)
plug in later via Newton-Raphson (Phase 3-4) — this module is the
foundation that phase will stamp companion models into.
"""

from dataclasses import dataclass
from typing import Dict, List

import numpy as np


# ---------------------------------------------------------------------------
# Element definitions
# ---------------------------------------------------------------------------

@dataclass
class Resistor:
    """A resistor between two nodes. node values are ints; 0 = ground."""
    node_p: int
    node_n: int
    resistance: float
    name: str = ""

    def stamp(self, A: np.ndarray, z: np.ndarray, node_index: Dict[int, int], extra_index: Dict[str, int]) -> None:
        g = 1.0 / self.resistance
        p = node_index.get(self.node_p)
        n = node_index.get(self.node_n)

        if p is not None:
            A[p, p] += g
        if n is not None:
            A[n, n] += g
        if p is not None and n is not None:
            A[p, n] -= g
            A[n, p] -= g


@dataclass
class VoltageSource:
    """
    An independent DC voltage source between node_p (+) and node_n (-).
    Voltage sources need an extra unknown (the current flowing through
    them), which is why MNA is "modified" nodal analysis rather than
    plain nodal analysis — plain KCL alone can't represent a fixed
    voltage constraint between two nodes.
    """
    node_p: int
    node_n: int
    voltage: float
    name: str = "V1"

    def stamp(self, A: np.ndarray, z: np.ndarray, node_index: Dict[int, int], extra_index: Dict[str, int]) -> None:
        k = extra_index[self.name]
        p = node_index.get(self.node_p)
        n = node_index.get(self.node_n)

        if p is not None:
            A[p, k] += 1.0
            A[k, p] += 1.0
        if n is not None:
            A[n, k] -= 1.0
            A[k, n] -= 1.0

        z[k] += self.voltage


# ---------------------------------------------------------------------------
# Circuit container + MNA assembly/solve
# ---------------------------------------------------------------------------

class Circuit:
    def __init__(self):
        self.elements: List = []

    def add(self, element) -> None:
        self.elements.append(element)

    def _collect_nodes_and_sources(self):
        nodes = set()
        source_names = []

        for el in self.elements:
            nodes.add(el.node_p)
            nodes.add(el.node_n)
            if isinstance(el, VoltageSource):
                source_names.append(el.name)

        nodes.discard(0)  # ground is not an unknown
        sorted_nodes = sorted(nodes)

        node_index = {node: i for i, node in enumerate(sorted_nodes)}
        extra_index = {
            name: len(sorted_nodes) + i for i, name in enumerate(source_names)
        }
        return sorted_nodes, node_index, extra_index

    def solve(self) -> Dict[str, float]:
        """
        Assemble and solve the linear MNA system A.x = z.

        Returns a dict mapping:
            "V(<node>)"  -> node voltage
            "I(<source>)" -> current through each voltage source
        """
        sorted_nodes, node_index, extra_index = self._collect_nodes_and_sources()
        size = len(sorted_nodes) + len(extra_index)

        if size == 0:
            return {}

        A = np.zeros((size, size))
        z = np.zeros(size)

        for el in self.elements:
            el.stamp(A, z, node_index, extra_index)

        x = np.linalg.solve(A, z)

        result: Dict[str, float] = {}
        for node, i in node_index.items():
            result[f"V({node})"] = float(x[i])
        for name, i in extra_index.items():
            result[f"I({name})"] = float(x[i])

        return result
