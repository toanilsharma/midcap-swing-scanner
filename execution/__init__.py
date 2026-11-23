"""
Midcap Swing Scanner - Execution & Trade Simulation Package (Version 2)
Provides realistic order fill simulation, anti-chase gap logic, broker friction modeling,
and 20-session trade exit management.
"""

from execution.order_simulator import (
    simulate_order_fill,
    compute_broker_friction,
    FillResult,
)
from execution.exit_evaluator import (
    evaluate_position_exit,
    ExitEvent,
)

__all__ = [
    "simulate_order_fill",
    "compute_broker_friction",
    "FillResult",
    "evaluate_position_exit",
    "ExitEvent",
]
