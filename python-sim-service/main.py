from fastapi import FastAPI
from pydantic import BaseModel
from typing import Dict, Any, List
from datetime import datetime

# Import the core simulation function from the sibling file
from sim_driver import run_realtime_simulation

# --- Pydantic Data Models ---

# 1. Defines the structure of the JSON payload we expect to RECEIVE (UPDATED)
class RunSimulationRequest(BaseModel):
    altitude_km: float = 600.0        # Default LEO orbit altitude (changed from 550.0 to match sim_driver default)
    inclination_deg: float = 51.6   # NEW: Orbital inclination in degrees (e.g., ISS)
    duration_s: int = 86400         # Default simulation duration

# 2. Defines the structure of the JSON payload we will RETURN
class SimulationResponse(BaseModel):
    status: str
    telemetry: List[Dict[str, Any]] # List of time-stamped telemetry logs
    message: str = None

# --- FastAPI Initialization ---
app = FastAPI(
    title = "Sentinode Python Simulation Core",
    description = "Provides real time telemetry logs via the orbital simulation",
    version = "1.0.0",
)


# --- Health Check Endpoint ---
@app.get("/status", response_model=Dict[str, str])
def get_status():
    """Returns the service status for health checks."""
    return {
        "status": "up",
        "service": "Python Simulation Core",
        # FIX: Changed utcnot() to utcnOW()
        "time_utc": datetime.utcnow().isoformat() + "Z" 
    }

# --- Main Simulation Endpoint ---
@app.post("/run-simulation", response_model = SimulationResponse)
def run_simulation(request: RunSimulationRequest):
    """Triggers the real-time orbital simulation with specified parameters."""

    # 1. Logging the incoming request
    print(f"Received request to run simulation: Alt={request.altitude_km}km, Inc={request.inclination_deg}deg, Duration={request.duration_s}s")
    
    try:
        # 2. CALL THE CORE LOGIC - NOW PASSING INCLINATION
        telemetry_log = run_realtime_simulation(
            altitude_km=request.altitude_km,
            inclination_deg=request.inclination_deg, # <-- NEW PARAMETER PASSED
            duration=request.duration_s,
            verbose=False # Crucial for API use, prevents console spam and delays
        )

        # 3. Return a successful response
        return SimulationResponse(
            status="success",
            telemetry=telemetry_log,
            message=f"Simulation complete for {request.duration_s} seconds."
        )

    except Exception as e:
        # 4. Handle any exceptions
        print(f"Simulation Error: {e}")
        return SimulationResponse(
            status="error",
            telemetry=[],
            message=f"Simulation failed: {str(e)}"
        )
