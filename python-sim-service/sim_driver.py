# -*- coding: utf-8 -*-
"""main_app.py

This module contains the core simulation driver for the Sentinel X Satellite model, 
integrating orbital mechanics, FSM, and sensor models.
"""

#---importing libraries---
#---01---Orbital mechanics layer---
import numpy as np
from typing import Dict, Callable
from numpy.polynomial.hermite import hermval
from scipy.stats import norm
from astropy import units as u
from astropy.time import Time
from poliastro.bodies import Earth
from poliastro.twobody import Orbit
from poliastro.maneuver import Maneuver
from poliastro.iod import izzo
import numpy as np
import matplotlib.pyplot as plt
from tabulate import tabulate
import pandas as pd
#---02---Sensor Suite---
import torch
import torch.nn as nn
from scipy.spatial.transform import Rotation as R
import random
#---03---Satellite State Machine---
import json

#---04---Ephemeris Parsing
from sgp4.api import Satrec
from sgp4.api import jday

#---05---Real Time Execution
import time # Kept for structure, but its sleep call is disabled below

# --- NEW IMPORTS (Assumed available from the provided context) ---
# Import the FSM class from its file
from satellite_fsm import SatelliteFSM 

# Import the core simulator and all sensor classes from their file
from simulator_models import (
    OrbitSimulator, UncertaintyPropagator,
    GPSML, StarTrackerML, 
    MagnetometerML, SunSensorML, 
    IRSensorML, CommunicationSubsystem, 
    PowerSubsystem
)

# --- FSM Configuration ---
FSM_CONFIG = '''
{
    "states": ["NOMINAL", "SAFE_MODE", "LOW_POWER", "COMM_LOSS", "ANOMALY"],
    "initial_state": "NOMINAL",
    "subsystems": {
        "Power": {"status": "OK"}, "Thermal": {"status": "OK"},
        "Communication": {"status": "OK"}, "ADCS": {"status": "OK"},
        "Payload": {"status": "IDLE"}, "Propulsion": {"status": "READY"}
    },
    "transitions": [
        {"from": "NOMINAL", "to": "LOW_POWER", "conditions": ["Power.status == 'LOW'"]},
        {"from": "NOMINAL", "to": "SAFE_MODE", "conditions": ["Thermal.status == 'CRITICAL'"]},
        {"from": "LOW_POWER", "to": "NOMINAL", "conditions": ["Power.status == 'OK'"]},
        {"from": "ANY", "to": "ANOMALY", "conditions": ["ADCS.status == 'ANOMALY'"]}
    ]
}
'''

# --- Initialization Constants ---
sensor_suite = {
    "gps": GPSML(noise_std_m=5.0),
    "star_tracker": StarTrackerML(noise_std_deg=0.005),
    "magnetometer": MagnetometerML(),
    "sun_sensor": SunSensorML(),
    "ir_sensor": IRSensorML(),
    "comms": CommunicationSubsystem(),
    "power": PowerSubsystem(),
}

DURATION_SECONDS = 86400
REALTIME_STEP = 1

# --- Simulation Driver ---
def run_realtime_simulation(altitude_km: float = 600.0, inclination_deg: float = 51.6, duration: int = DURATION_SECONDS, step: int = 1, verbose: bool = False):
    """
    Runs the satellite simulation, stepping through time and logging telemetry.
    
    Args:
        altitude_km (float): Initial orbital altitude in kilometers.
        inclination_deg (float): Orbital inclination in degrees.
        duration (int): Total simulation duration in seconds.
        step (int): Time step per simulation iteration in seconds.
        verbose (bool): If True, prints real-time telemetry updates to the console.

    Returns:
        list: A log of telemetry dictionaries for every step of the simulation.
    """
    
    # Use the altitude_km passed from the API request (or default 600.0)
    sim_altitude = altitude_km

    # Randomization logic for slight initial perturbation
    np.random.seed(None)
    random.seed(None)
    random_alt_perturb = np.random.uniform(-0.01, 0.01)
    sim_altitude = sim_altitude + random_alt_perturb

    # Set Epoch to the current system time
    current_time_epoch = Time.now().utc.iso.replace(" ", "T")

    if verbose: # Conditional printing
        print(f" Initializing OrbitSimulator at {sim_altitude:.3f} km...")
        print(f"  Starting Epoch: {current_time_epoch}")
        print(f"  Inclination: {inclination_deg:.1f}º")

    # Pass the current UTC time string, altitude, and inclination to the OrbitSimulator constructor
    simulator = OrbitSimulator(
        epoch=current_time_epoch, 
        altitude_km=sim_altitude,
        inclination_deg=inclination_deg
    )
    fsm = SatelliteFSM(FSM_CONFIG)

    if verbose:
        print("  Resetting sensor suite state...")
    for sensor in sensor_suite.values():
        if hasattr(sensor, 'reset'):
            sensor.reset()

    injected_failure = False # FSM testing flag

    telemetry_log = []
    num_steps = duration // step

    if verbose: # Conditional printing
        print(f"\n--- SENTINODE X Real-Time Simulation: Starting {duration}s run ({num_steps} steps, {step}s step) ---")
        print("-" * 90)

    # --- Run Loop (Simulation Time) ---
    for i in range(1, num_steps + 1):

        # 1. Simulate the next step seconds
        latest_telemetry = simulator.step_simulation(
            sensor_suite=sensor_suite,
            fsm=fsm,
            steps_s=step
        )
        telemetry_log.append(latest_telemetry)

        current_time_s = latest_telemetry["time_s"]

        # --- Inject FSM Events for Testing ---
        if current_time_s == 60 and fsm.state == "NOMINAL" and not injected_failure:
            if verbose: # Conditional printing
                print(f"  [EVENT] Time {current_time_s}s: Injecting Power LOW event.")
            fsm.update_subsystem_status("Power", "LOW")
            injected_failure = True

        if current_time_s == 180 and fsm.state == "LOW_POWER" and injected_failure:
            if verbose: # Conditional printing
                print(f"  [EVENT] Time {current_time_s}s: Power subsystem recovering.")
            fsm.update_subsystem_status("Power", "OK")
            # Clear the flag or set it to a new state if needed
            injected_failure = "RECOVERED"

        # 2. Conditional Printing (Only runs if verbose=True)
        if verbose:
            # Line 1: Summary and FSM
            print(f"TIME: {current_time_s:03d}s | STATE: {latest_telemetry['fsm_state']:<10} | ALT: {latest_telemetry['altitude_km']:.3f} km | Epoch Time: {latest_telemetry['timestamp_utc'][-10:-5]}")

            # NEW LINE: Geographic Position
            print(f"  | POS | Lat: {latest_telemetry['latitude_deg']:.3f}º | Lon: {latest_telemetry['longitude_deg']:.3f}º")

            # Line 2: Power Summary
            print(f"  | PWR | SOC: {latest_telemetry['soc']:.2%} | Temp: {latest_telemetry['battery_temp']:.2f}ºC | Solar V: {latest_telemetry['solar_voltage']:.2f} V")
            print(f"  | PWR | Batt V: {latest_telemetry['battery_voltage']:.2f} V | Batt I: {latest_telemetry['battery_current']:.2f} A | Solar I: {latest_telemetry['solar_current']:.2f} A")

            # Line 3: ADCS Sensors
            mag_vec_str = ", ".join([f"{x:.2e}" for x in latest_telemetry['mag_vec_measured']])
            st_quat_str = ", ".join([f"{x:.3f}" for x in latest_telemetry['st_quat']])
            print(f"  | ADCS| GPS Error: {latest_telemetry['gps_error_m']:.2f} m | Mag-Vec: [{mag_vec_str}]")
            print(f"  | ADCS| Sun-Vec: [{latest_telemetry['sun_vec_measured'][0]:.2f}, {latest_telemetry['sun_vec_measured'][1]:.2f}, {latest_telemetry['sun_vec_measured'][2]:.2f}] | ST-Quat: [{st_quat_str}]")

            # Line 4: Communication (Using CONFIRMED keys)
            print(f"  | COMM| Loss: {latest_telemetry['PacketLoss']:.2f} | SNR: {latest_telemetry['SNR_dB']:.1f} dB | Freq Offset: {latest_telemetry['FrequencyOffset_Hz']:.1f} Hz")

            # 5. Pause for 1 second to simulate real time
            # CRITICAL UPDATE: Commented out time.sleep(1) for fast execution in non-real-time environments.
            # time.sleep(1) 
            print("-" * 90)
    
    if verbose:
        print("\n[Done] Simulation complete.")

        # --- Final Output Summary (uses the last entry) ---
        final_entry = telemetry_log[-1]

        print("\n--- Final Telemetry Snapshot ---")
        print(f"Mission Time: {final_entry['time_s']} seconds")
        print(f"Final FSM State: {final_entry['fsm_state']}")
        print(f"Final Altitude (Actual): {final_entry['altitude_km']} km")
        # Include new Lat/Lon in final summary
        print(f"Final Geographic Position: {final_entry['latitude_deg']:.3f}º Lat, {final_entry['longitude_deg']:.3f}º Lon")
        print(f"Final Battery SOC: {final_entry['soc']:.2%}")

    return telemetry_log
