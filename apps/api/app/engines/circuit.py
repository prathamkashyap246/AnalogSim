"""
circuit.py — Netlist representation + Modified Nodal Analysis (MNA) solver.

Node 0 is always ground (0V, not a real unknown).

Elements:
    - Resistor
    - VoltageSource  (independent DC source)
    - CurrentSource  (independent DC source, SPICE convention)
    - Capacitor      (open circuit at DC; jwC admittance in AC analysis)
    - Mosfet         (nonlinear; uses the project's non-ideal square-law model)

Circuits with only linear elements are solved with a single linear solve.
As soon as a Mosfet is present, the solver switches to Newton-Raphson:
every iteration linearizes each MOSFET around the current guess (a
"companion model": conductances + an equivalent current source), stamps
that into the same MNA matrix, and re-solves until the update is tiny.

Small-signal AC analysis (Circuit.ac_analysis) first solves the DC operating
point, then linearizes every MOSFET there (gm, gds, gmb come from the same
finite-difference Jacobian Newton-Raphson uses) and solves the complex
system (G + jwC) x = b once per frequency. Independent sources contribute
only their AC magnitude, so with "AC 1" on the input a node voltage IS the
transfer function.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from app.engines.non_ideal_engine import calculate_non_ideal_current, mosfet_constants


class ConvergenceError(Exception):
    """Raised when Newton-Raphson fails to converge."""
    pass


def _stamp_admittance(Y: np.ndarray, node_index: Dict[int, int], a: int, b: int, y) -> None:
    """Stamp an admittance y between nodes a and b (either may be ground)."""
    ia, ib = node_index.get(a), node_index.get(b)
    if ia is not None:
        Y[ia, ia] += y
    if ib is not None:
        Y[ib, ib] += y
    if ia is not None and ib is not None:
        Y[ia, ib] -= y
        Y[ib, ia] -= y


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

    def stamp_ac(self, Y, z, node_index, extra_index, omega, volts) -> None:
        _stamp_admittance(Y, node_index, self.node_p, self.node_n, 1.0 / self.resistance)


@dataclass
class Capacitor:
    """A capacitor. Open circuit at DC; admittance jwC in AC analysis."""
    node_p: int
    node_n: int
    capacitance: float
    name: str = "C1"

    def terminals(self):
        return (self.node_p, self.node_n)

    def stamp(self, A: np.ndarray, z: np.ndarray, node_index: Dict[int, int], extra_index: Dict[str, int]) -> None:
        pass  # open circuit at DC

    def stamp_ac(self, Y, z, node_index, extra_index, omega, volts) -> None:
        _stamp_admittance(Y, node_index, self.node_p, self.node_n, 1j * omega * self.capacitance)


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
    ac_mag: float = 0.0  # small-signal magnitude used by AC analysis (SPICE "AC 1")

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

    def stamp_ac(self, Y, z, node_index, extra_index, omega, volts) -> None:
        k = extra_index[self.name]
        p = node_index.get(self.node_p)
        n = node_index.get(self.node_n)
        if p is not None:
            Y[p, k] += 1.0
            Y[k, p] += 1.0
        if n is not None:
            Y[n, k] -= 1.0
            Y[k, n] -= 1.0
        z[k] += self.ac_mag


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
    ac_mag: float = 0.0

    def terminals(self):
        return (self.node_p, self.node_n)

    def stamp(self, A: np.ndarray, z: np.ndarray, node_index: Dict[int, int], extra_index: Dict[str, int]) -> None:
        p = node_index.get(self.node_p)
        n = node_index.get(self.node_n)

        if p is not None:
            z[p] -= self.current
        if n is not None:
            z[n] += self.current

    def stamp_ac(self, Y, z, node_index, extra_index, omega, volts) -> None:
        p = node_index.get(self.node_p)
        n = node_index.get(self.node_n)
        if p is not None:
            z[p] -= self.ac_mag
        if n is not None:
            z[n] += self.ac_mag


# ---------------------------------------------------------------------------
# Nonlinear element: MOSFET
# ---------------------------------------------------------------------------

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
    cgs: float = 0.0  # gate-source capacitance (F), used only by AC analysis
    cgd: float = 0.0  # gate-drain capacitance (F), used only by AC analysis

    is_nonlinear = True
    _FD_STEP = 1e-6  # volts, for the central-difference Jacobian

    def __post_init__(self):
        if self.polarity not in ("n", "p"):
            raise ValueError(f"{self.name}: polarity must be 'n' or 'p'")
        self._k, self._mu_temp, self._l_cm = mosfet_constants(
            self.gate_length_nm, self.gate_width_um, self.tox_nm, self.mu_0, self.temp_c
        )

    def terminals(self):
        return (self.node_d, self.node_g, self.node_s, self.node_b)

    # -- current model ------------------------------------------------------
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

    def _gradients(self, v0) -> List[float]:
        """dId/dV for each terminal voltage (d, g, s, b), by central differences.
        Done on the current function itself so the Jacobian is always
        consistent with whatever model flags are on."""
        h = self._FD_STEP
        grads = []
        for k in range(4):
            vp, vm = list(v0), list(v0)
            vp[k] += h
            vm[k] -= h
            grads.append((self.drain_current(*vp) - self.drain_current(*vm)) / (2.0 * h))
        return grads

    # -- Small-signal AC model ---------------------------------------------
    def stamp_ac(self, Y, z, node_index, extra_index, omega, volts) -> None:
        """Linearize at the DC operating point: a voltage-controlled current
        source per terminal (gds on the drain, gm on the gate, gmb on the
        bulk) plus optional Cgs / Cgd."""
        grads = self._gradients([volts[n] for n in self.terminals()])
        row_d = node_index.get(self.node_d)
        row_s = node_index.get(self.node_s)
        for k, node in enumerate(self.terminals()):
            col = node_index.get(node)
            if col is None:
                continue
            if row_d is not None:
                Y[row_d, col] += grads[k]
            if row_s is not None:
                Y[row_s, col] -= grads[k]
        if self.cgs:
            _stamp_admittance(Y, node_index, self.node_g, self.node_s, 1j * omega * self.cgs)
        if self.cgd:
            _stamp_admittance(Y, node_index, self.node_g, self.node_d, 1j * omega * self.cgd)

    # -- Newton-Raphson companion model ------------------------------------
    def stamp_newton(self, A: np.ndarray, z: np.ndarray, volts: Dict[int, float], node_index: Dict[int, int]) -> None:
        nodes = self.terminals()
        v0 = [volts[n] for n in nodes]
        i0 = self.drain_current(*v0)
        grads = self._gradients(v0)

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


# ---------------------------------------------------------------------------
# Circuit container + MNA assembly/solve
# ---------------------------------------------------------------------------

class Circuit:
    # Newton-Raphson settings (SPICE-like defaults)
    MAX_ITER: int = 100
    VNTOL: float = 1e-9      # absolute voltage tolerance (V)
    ABSTOL: float = 1e-12    # absolute current tolerance (A)
    RELTOL: float = 1e-6
    V_STEP_LIMIT: float = 0.5  # max node-voltage change per iteration (V)
    GMIN: float = 1e-12        # tiny conductance node->ground so cut-off devices never leave a node floating

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

        nodes.discard(0)  # ground is not an unknown
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
        return self._solve_full()[0]

    def _solve_full(self, x0: Optional[np.ndarray] = None):
        """Like solve(), but also returns the raw solution vector and accepts
        a starting guess x0 for Newton-Raphson (ignored for linear circuits)."""
        sorted_nodes, node_index, extra_index = self._collect_nodes_and_sources()
        size = len(sorted_nodes) + len(extra_index)

        if size == 0:
            return {}, np.zeros(0)

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
            x = self._newton(size, n_nodes, node_index, extra_index, sorted_nodes, x0)

        result: Dict[str, float] = {}
        for node, i in node_index.items():
            result[f"V({node})"] = float(x[i])
        for name, i in extra_index.items():
            result[f"I({name})"] = float(x[i])

        volts = self._volts(x, sorted_nodes)
        for el in nonlinear:
            result[f"Id({el.name})"] = float(el.drain_current(*[volts[n] for n in el.terminals()]))

        return result, x

    def dc_sweep(self, source_name: str, values: List[float]):
        """
        Solve the operating point once per value of the named V/I source.

        Each point starts Newton-Raphson from the previous point's solution
        (continuation), which is both faster and more robust than starting
        from zero every time. If a warm start fails to converge it is retried
        from zero before giving up. The source's original value is restored
        afterwards.

        Returns (series, iterations): series maps each result name (e.g. "V(3)")
        to a list with one entry per sweep value; iterations is a list of the
        Newton iteration counts per point.
        """
        src = next(
            (e for e in self.elements
             if isinstance(e, (VoltageSource, CurrentSource)) and e.name.upper() == source_name.upper()),
            None,
        )
        if src is None:
            raise ValueError(f"No voltage or current source named '{source_name}'")
        attr = "voltage" if isinstance(src, VoltageSource) else "current"
        original = getattr(src, attr)

        series: Dict[str, List[float]] = {}
        iterations: List[int] = []
        x_prev: Optional[np.ndarray] = None
        try:
            for val in values:
                setattr(src, attr, val)
                try:
                    result, x = self._solve_full(x_prev)
                except ConvergenceError:
                    if x_prev is None:
                        raise ConvergenceError(
                            f"Newton-Raphson did not converge at {src.name} = {val:g}"
                        ) from None
                    try:
                        result, x = self._solve_full(None)
                    except ConvergenceError:
                        raise ConvergenceError(
                            f"Newton-Raphson did not converge at {src.name} = {val:g}"
                        ) from None
                x_prev = x
                iterations.append(self.last_iterations)
                for key, v in result.items():
                    series.setdefault(key, []).append(v)
        finally:
            setattr(src, attr, original)

        return series, iterations

    def ac_analysis(self, freqs: List[float]) -> Dict[str, Dict[str, List[float]]]:
        """
        Small-signal frequency response around the DC operating point.

        At least one source needs a non-zero AC magnitude (SPICE "AC 1").
        Returns {"V(<node>)" or "I(<source>)": {"mag": [...], "db": [...],
        "phase_deg": [...]}}, one entry per frequency. The DC operating
        point used is left in self.last_op.
        """
        if not any(getattr(e, "ac_mag", 0.0) for e in self.elements):
            raise ValueError("AC analysis needs a source with an AC magnitude, e.g. 'Vin 1 0 0 AC 1'")
        if any(f <= 0 for f in freqs):
            raise ValueError("AC frequencies must be positive")

        self.last_op, x = self._solve_full()
        sorted_nodes, node_index, extra_index = self._collect_nodes_and_sources()
        n_nodes = len(sorted_nodes)
        size = n_nodes + len(extra_index)
        volts = self._volts(x, sorted_nodes)

        labels = [f"V({n})" for n in sorted_nodes] + [f"I({name})" for name in extra_index]
        rows: List[np.ndarray] = []
        for f in freqs:
            omega = 2.0 * np.pi * f
            Y = np.zeros((size, size), dtype=complex)
            z = np.zeros(size, dtype=complex)
            for el in self.elements:
                el.stamp_ac(Y, z, node_index, extra_index, omega, volts)
            for i in range(n_nodes):
                Y[i, i] += self.GMIN
            rows.append(np.linalg.solve(Y, z))

        sol = np.array(rows)  # shape (n_freqs, size)
        out: Dict[str, Dict[str, List[float]]] = {}
        for col, label in enumerate(labels):
            mag = np.abs(sol[:, col])
            out[label] = {
                "mag": mag.tolist(),
                "db": (20.0 * np.log10(np.maximum(mag, 1e-300))).tolist(),
                "phase_deg": np.degrees(np.angle(sol[:, col])).tolist(),
            }
        return out

    @staticmethod
    def _volts(x: np.ndarray, sorted_nodes) -> Dict[int, float]:
        volts = {0: 0.0}
        for i, node in enumerate(sorted_nodes):
            volts[node] = float(x[i])
        return volts

    def _newton(self, size, n_nodes, node_index, extra_index, sorted_nodes, x0=None) -> np.ndarray:
        x = np.zeros(size) if x0 is None else np.array(x0, dtype=float)
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

            # Limit how far any node voltage may move in one step; the
            # square-law curve is only locally linear, so a huge jump
            # (e.g. from a cut-off device) would overshoot badly.
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