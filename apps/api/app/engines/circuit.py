"""
circuit.py — Netlist representation + Modified Nodal Analysis (MNA) solver.

Node 0 is always ground (0V, not a real unknown).

Elements:
    - Resistor
    - VoltageSource  (independent DC source)
    - CurrentSource  (independent DC source, SPICE convention)
    - Mosfet         (nonlinear; uses the project's non-ideal square-law model)

Circuits with only linear elements are solved with a single linear solve.
As soon as a Mosfet is present, the solver switches to Newton-Raphson:
every iteration linearizes each MOSFET around the current guess (a
"companion model": conductances + an equivalent current source), stamps
that into the same MNA matrix, and re-solves until the update is tiny.
"""

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np

from app.engines.non_ideal_engine import calculate_non_ideal_current, mosfet_constants
class ConvergenceError(Exception):
    """Raised when Newton-Raphson fails to converge."""
    pass


# ---------------------------------------------------------------------------
# Linear element definitions
# ---------------------------------------------------------------------------

@dataclass
class Resistor:
    """A resistor between two nodes. node values are ints; 0 = ground."""
    node_p: int
    node_n: int
    resistance: float
    name: str = ""

    def terminals(self):
        return (self.node_p, self.node_n)

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

    def terminals(self):
        return (self.node_p, self.node_n)

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


@dataclass
class CurrentSource:
    """
    An independent DC current source. SPICE convention: positive current
    flows from node_p, THROUGH the source, to node_n. So "I1 0 1 1m"
    pushes 1 mA into node 1.
    """
    node_p: int
    node_n: int
    current: float
    name: str = "I1"

    def terminals(self):
        return (self.node_p, self.node_n)

    def stamp(self, A: np.ndarray, z: np.ndarray, node_index: Dict[int, int], extra_index: Dict[str, int]) -> None:
        p = node_index.get(self.node_p)
        n = node_index.get(self.node_n)

        if p is not None:
            z[p] -= self.current
        if n is not None:
            z[n] += self.current

@dataclass
class Mosfet:
    """
    4-terminal MOSFET using calculate_non_ideal_current() from
    non_ideal_engine.py (square-law + body effect + CLM + optional velocity
    saturation). The same model that drives the sweep plots is what the
    circuit solver sees.

    polarity: "n" or "p". PMOS reuses the NMOS equations with every terminal
    voltage negated (vth0 is a magnitude, as usual); k is the same for both
    polarities, i.e. a mobility-matched complementary pair.
    """
    node_d: int
    node_g: int
    node_s: int
    node_b: int
    polarity: str = "n"
    name: str = "M1"
    gate_width_um: float = 1.0
    gate_length_nm: float = 180.0
    tox_nm: float = 4.0
    vth0: float = 0.4
    gamma: float = 0.4
    lambda_param: float = 0.05
    mu_0: float = 450.0
    phi2f: float = 0.6
    temp_c: float = 27.0
    enable_body_effect: bool = True
    enable_clm: bool = True
    enable_velocity_saturation: bool = False

    is_nonlinear = True
    _FD_STEP = 1e-6  

    def __post_init__(self):
        if self.polarity not in ("n", "p"):
            raise ValueError(f"{self.name}: polarity must be 'n' or 'p'")
        self._k, self._mu_temp, self._l_cm = mosfet_constants(
            self.gate_length_nm, self.gate_width_um, self.tox_nm, self.mu_0, self.temp_c
        )

    def terminals(self):
        return (self.node_d, self.node_g, self.node_s, self.node_b)
    def _id_forward(self, vgs: float, vds: float, vsb: float) -> float:
        i, _, _, _ = calculate_non_ideal_current(
            vgs, vds, vsb, self.temp_c, self.vth0, self._k, self._mu_temp,
            self._l_cm, self.lambda_param, self.gamma, self.phi2f,
            self.enable_body_effect, self.enable_clm, self.enable_velocity_saturation,
        )
        return i
    def _id_nmos(self, vd: float, vg: float, vs: float, vb: float) -> float:
        # The model assumes vds >= 0. If the "drain" is below the "source"
        # the terminals swap roles (a MOSFET is symmetric) -- same trick SPICE uses.
        if vd >= vs:
            return self._id_forward(vg - vs, vd - vs, vs - vb)
        return -self._id_forward(vg - vd, vs - vd, vd - vb)
    def drain_current(self, vd: float, vg: float, vs: float, vb: float) -> float:
        """Current flowing INTO the drain terminal (through the device to the source)."""
        if self.polarity == "p":
            return -self._id_nmos(-vd, -vg, -vs, -vb)
        return self._id_nmos(vd, vg, vs, vb)
    def stamp_newton(self, A: np.ndarray, z: np.ndarray, volts: Dict[int, float], node_index: Dict[int, int]) -> None:
        nodes = self.terminals()
        v0 = [volts[n] for n in nodes]
        i0 = self.drain_current(*v0)

        h = self._FD_STEP
        grads = []
        for k in range(4):
            vp, vm = list(v0), list(v0)
            vp[k] += h
            vm[k] -= h
            grads.append((self.drain_current(*vp) - self.drain_current(*vm)) / (2.0 * h))

        i_eq = i0 - sum(g * v for g, v in zip(grads, v0))

        row_d = node_index.get(self.node_d)
        row_s = node_index.get(self.node_s)
        for k, node in enumerate(nodes):
            col = node_index.get(node)
            if col is None:
                continue
            if row_d is not None:
                A[row_d, col] += grads[k]
            if row_s is not None:
                A[row_s, col] -= grads[k]
        if row_d is not None:
            z[row_d] -= i_eq
        if row_s is not None:
            z[row_s] += i_eq

class Circuit:
    MAX_ITER = 100
    VNTOL = 1e-9      
    ABSTOL = 1e-12   
    RELTOL = 1e-6
    V_STEP_LIMIT = 0.5 
    GMIN = 1e-12        
    def __init__(self):
        self.elements: List = []
        self.last_iterations: int = 0

    def add(self, element) -> None:
        self.elements.append(element)

    def _collect_nodes_and_sources(self):
        nodes = set()
        source_names = []

        for el in self.elements:
            nodes.update(el.terminals())
            if isinstance(el, VoltageSource):
                source_names.append(el.name)

        nodes.discard(0)  
        sorted_nodes = sorted(nodes)

        node_index = {node: i for i, node in enumerate(sorted_nodes)}
        extra_index = {
            name: len(sorted_nodes) + i for i, name in enumerate(source_names)
        }
        return sorted_nodes, node_index, extra_index

    def solve(self) -> Dict[str, float]:
        """
        Solve the DC operating point.

        Returns a dict mapping:
            "V(<node>)"   -> node voltage
            "I(<source>)" -> current through each voltage source
            "Id(<mosfet>)" -> drain current of each MOSFET (into the drain)
        The number of Newton iterations used is left in self.last_iterations.
        """
        sorted_nodes, node_index, extra_index = self._collect_nodes_and_sources()
        size = len(sorted_nodes) + len(extra_index)

        if size == 0:
            return {}

        nonlinear = [el for el in self.elements if getattr(el, "is_nonlinear", False)]
        n_nodes = len(sorted_nodes)

        if not nonlinear:
            A = np.zeros((size, size))
            z = np.zeros(size)
            for el in self.elements:
                el.stamp(A, z, node_index, extra_index)
            x = np.linalg.solve(A, z)
            self.last_iterations = 1
        else:
            x = self._newton(size, n_nodes, node_index, extra_index, sorted_nodes)

        result: Dict[str, float] = {}
        for node, i in node_index.items():
            result[f"V({node})"] = float(x[i])
        for name, i in extra_index.items():
            result[f"I({name})"] = float(x[i])

        volts = self._volts(x, sorted_nodes)
        for el in nonlinear:
            result[f"Id({el.name})"] = float(el.drain_current(*[volts[n] for n in el.terminals()]))

        return result

    @staticmethod
    def _volts(x: np.ndarray, sorted_nodes) -> Dict[int, float]:
        volts = {0: 0.0}
        for i, node in enumerate(sorted_nodes):
            volts[node] = float(x[i])
        return volts

    def _newton(self, size, n_nodes, node_index, extra_index, sorted_nodes) -> np.ndarray:
        x = np.zeros(size)
        abs_tol = np.concatenate([np.full(n_nodes, self.VNTOL), np.full(size - n_nodes, self.ABSTOL)])

        for iteration in range(1, self.MAX_ITER + 1):
            A = np.zeros((size, size))
            z = np.zeros(size)
            volts = self._volts(x, sorted_nodes)

            for el in self.elements:
                if getattr(el, "is_nonlinear", False):
                    el.stamp_newton(A, z, volts, node_index)
                else:
                    el.stamp(A, z, node_index, extra_index)
            for i in range(n_nodes):
                A[i, i] += self.GMIN

            x_solved = np.linalg.solve(A, z)
            dx = x_solved - x
            limited = np.abs(dx[:n_nodes]) > self.V_STEP_LIMIT
            if limited.any():
                dx[:n_nodes] = np.clip(dx[:n_nodes], -self.V_STEP_LIMIT, self.V_STEP_LIMIT)

            x_new = x + dx
            tol = abs_tol + self.RELTOL * np.abs(x_new)
            converged = (not limited.any()) and bool(np.all(np.abs(dx) <= tol))
            x = x_new

            if converged:
                self.last_iterations = iteration
                return x

        raise ConvergenceError(
            f"Newton-Raphson did not converge within {self.MAX_ITER} iterations"
        )