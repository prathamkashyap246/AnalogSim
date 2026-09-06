from app.engines.circuit import Circuit
from app.engines.netlist_parser import parse_netlist, NetlistError
from fastapi import HTTPException
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import database, models
from app.engines.empirical_engine import run_empirical_engine
from app.engines.ideal_engine import run_ideal_engine
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
        results = run_non_ideal_engine(
            sweep_param=request.sweep_param,
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
            gate_length_nm=request.gate_length_nm,
            gate_width_um=request.gate_width_um,
            tox_nm=request.tox_nm,
            vth0=request.vth0,
        )

@app.post("/api/v1/solve_circuit")
def solve_circuit(request: CircuitSolveRequest):
    try:
        elements = parse_netlist(request.netlist)
    except NetlistError as e:
        raise HTTPException(status_code=400, detail=str(e))

    circuit = Circuit()
    for el in elements:
        circuit.add(el)

    try:
        result = circuit.solve()
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Circuit could not be solved: {e}. "
            f"Check for disconnected nodes or conflicting sources.",
        )

    return {"status": "ok", "results": result}

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