import numpy as np

class Capacitor:
    def __init__(self, name, node1, node2, capacitance):
        self.name = name
        self.node1 = node1
        self.node2 = node2
        self.capacitance = capacitance

    def stamp_ac(self, Y, nodes, omega):
        val = 1j * omega * self.capacitance
        n1 = nodes.get(self.node1)
        n2 = nodes.get(self.node2)

        if n1 is not None:
            Y[n1, n1] += val
        if n2 is not None:
            Y[n2, n2] += val
        if n1 is not None and n2 is not None:
            Y[n1, n2] -= val
            Y[n2, n1] -= val

def extract_small_signal_conductances(mosfet, dc_op):
    gm = mosfet.gm(dc_op)
    gds = mosfet.gds(dc_op)
    return gm, gds

def solve_ac(circuit, dc_operating_point, f_start, f_stop, points):
    nodes = circuit.get_node_map()
    num_nodes = len(nodes)
    frequencies = np.logspace(np.log10(f_start), np.log10(f_stop), points)
    
    results = {}
    
    for f in frequencies:
        omega = 2 * np.pi * f
        Y_ac = np.zeros((num_nodes, num_nodes), dtype=np.complex128)
        J_ac = np.zeros(num_nodes, dtype=np.complex128)
        
        for element in circuit.elements:
            if isinstance(element, Capacitor):
                element.stamp_ac(Y_ac, nodes, omega)
                
        for mosfet in circuit.mosfets:
            gm, gds = extract_small_signal_conductances(mosfet, dc_operating_point)
            
        V_ac = np.linalg.solve(Y_ac, J_ac)
        results[f] = V_ac
        
    return frequencies, results

def main():
    pass
    # 1. Parse .ac directive from netlist
    # 2. Run standard .op to get dc_operating_point
    # 3. Pass dc_operating_point to solve_ac()
    # 4. Return magnitude and phase arrays to frontend