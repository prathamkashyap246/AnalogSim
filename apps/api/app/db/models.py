from sqlalchemy import Column, DateTime, Float, Integer, JSON, String
from sqlalchemy.sql import func

from app.db.database import Base


class MeasurementData(Base):
    __tablename__ = "measurement_data"

    id = Column(Integer, primary_key=True, index=True)
    chip_name = Column(String, index=True)
    vgs = Column(Float)
    vds = Column(Float)
    id_measured = Column(Float)


class SimulationRun(Base):
    __tablename__ = "simulation_runs"

    id = Column(Integer, primary_key=True, index=True)
    engine_type = Column(String, index=True)
    gate_length_nm = Column(Float)
    gate_width_um = Column(Float)
    results_json = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())