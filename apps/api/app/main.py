from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import database, models
from app.engines.circuit import Circuit, ConvergenceError
from app.engines.empirical_engine import run_empirical_engine
from app.engines.ideal_engine import run_ideal_engine
from app.engines.netlist_parser import AcSweep, DcSweep, NetlistError, parse_netlist_full
from app.engines.non_ideal_engine import run_non_ideal_engine

# Automatically create database tables
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="AnalogSim Multi-Engine API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CircuitSolveRequest(BaseModel):
    netlist: str


class SimulationRequest(BaseModel):
    sweep_param: str = "vds"
    engine_type: str = "ideal"
    gate_length_nm: float = 180.0
    gate_width_um: float = 1.0
    tox_nm: float = 4.0
    vth0: float = 0.4
    gamma: float = 0.4
    lambda_param: float = 0.05
    enable_body_effect: bool = True
    enable_clm: bool = True
    enable_velocity_saturation: bool = False
    # Bias points held constant while the chosen sweep variable runs
    fixed_vgs: float = 1.8
    fixed_vds: float = 1.2
    fixed_vsb: float = 0.0
    temp_c: float = 27.0


@app.post("/api/v1/simulate")
def route_simulation(
    request: SimulationRequest, db: Session = Depends(database.get_db)
):
    if request.engine_type == "empirical":
        results = run_empirical_engine(
            db_session=db,
            gate_length_nm=request.gate_length_nm,
            gate_width_um=request.gate_width_um,
        )
    elif request.engine_type == "non_ideal":
        # Temperature is swept over a realistic range; the voltage sweeps use 0 - 1.8 V
        is_temp_sweep = request.sweep_param == "temp"
        results = run_non_ideal_engine(
            sweep_param=request.sweep_param,
            sweep_start=-40.0 if is_temp_sweep else 0.0,
            sweep_end=125.0 if is_temp_sweep else 1.8,
            fixed_vgs=request.fixed_vgs,
            fixed_vds=request.fixed_vds,
            fixed_vsb=request.fixed_vsb,
            temp_c=request.temp_c,
            gate_length_nm=request.gate_length_nm,
            gate_width_um=request.gate_width_um,
            tox_nm=request.tox_nm,
            vth0=request.vth0,
            gamma=request.gamma,
            lambda_param=request.lambda_param,
            enable_body_effect=request.enable_body_effect,
            enable_clm=request.enable_clm,
            enable_velocity_saturation=request.enable_velocity_saturation,
        )
    else:
        results = run_ideal_engine(
            sweep_param=request.sweep_param,
            fixed_vgs=request.fixed_vgs,
            fixed_vds=request.fixed_vds,
            gate_length_nm=request.gate_length_nm,
            gate_width_um=request.gate_width_um,
            tox_nm=request.tox_nm,
            vth0=request.vth0,
        )

    # Persist simulation run into database
    sim_record = models.SimulationRun(
        engine_type=request.engine_type,
        gate_length_nm=request.gate_length_nm,
        gate_width_um=request.gate_width_um,
        results_json=results,
    )
    db.add(sim_record)
    db.commit()
    db.refresh(sim_record)

    return {"simulation_id": sim_record.id, "data": results}


def _operating_point_response(circuit: Circuit) -> dict:
    result = circuit.solve()
    return {
        "status": "ok",
        "mode": "op",
        "results": result,
        "iterations": circuit.last_iterations,
    }


def _dc_sweep_response(circuit: Circuit, dc: DcSweep) -> dict:
    values = dc.values()
    series, iterations = circuit.dc_sweep(dc.source, values)
    return {
        "status": "ok",
        "mode": "dc_sweep",
        "sweep": {
            "source": dc.source,
            "start": dc.start,
            "stop": dc.stop,
            "step": dc.step,
            "values": values,
        },
        "series": series,
        "iterations_per_point": iterations,
        "max_iterations": max(iterations),
    }


def _ac_response(circuit: Circuit, ac: AcSweep) -> dict:
    freqs = ac.values()
    series = circuit.ac_analysis(freqs)
    return {
        "status": "ok",
        "mode": "ac",
        "sweep": {"kind": ac.kind, "points": ac.points, "start": ac.start, "stop": ac.stop, "freqs": freqs},
        "series": series,
        "operating_point": circuit.last_op,
    }


@app.post("/api/v1/solve_circuit")
def solve_circuit(request: CircuitSolveRequest):
    try:
        parsed = parse_netlist_full(request.netlist)
    except NetlistError as e:
        raise HTTPException(status_code=400, detail=str(e))

    circuit = Circuit()
    for el in parsed.elements:
        circuit.add(el)

    try:
        if parsed.ac is not None:
            return _ac_response(circuit, parsed.ac)
        if parsed.dc is None:
            return _operating_point_response(circuit)
        return _dc_sweep_response(circuit, parsed.dc)
    except ConvergenceError as e:
        raise HTTPException(
            status_code=400,
            detail=f"{e}. Check that every MOSFET has a DC path to its supplies, "
            f"or try smaller source voltages.",
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Circuit could not be solved: {e}. "
            f"Check for disconnected nodes or conflicting sources.",
        )