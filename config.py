"""Configuration values for the CNC setup-time optimization MVP."""
from __future__ import annotations

from typing import Dict, List

RANDOM_SEED = 42
ANNUAL_SETUP_VOLUME = 4200
DEFAULT_NOISE_LEVEL = 0.18
HISTORICAL_JOBS = 650
HISTORICAL_TRANSITIONS = 1400
QUEUE_MIN_JOBS = 4
QUEUE_MAX_JOBS = 7

MACHINE_CAPABILITIES: List[Dict[str, object]] = [
    {
        "machine_id": "LATHE_01",
        "machine_name": "Mazak Quick Turn 250",
        "machine_type": "lathe",
        "supported_materials": ["aluminum", "mild_steel", "stainless_steel", "brass"],
        "supported_size_classes": ["small", "medium"],
        "default_tool_family": "turning_tools",
        "setup_hourly_rate": 115.0,
        "utilization_target": 0.82,
    },
    {
        "machine_id": "LATHE_02",
        "machine_name": "Okuma Genos L300",
        "machine_type": "lathe",
        "supported_materials": ["aluminum", "mild_steel", "stainless_steel", "titanium"],
        "supported_size_classes": ["small", "medium", "large"],
        "default_tool_family": "turning_tools",
        "setup_hourly_rate": 122.0,
        "utilization_target": 0.85,
    },
    {
        "machine_id": "MILL_01",
        "machine_name": "Haas VF-4",
        "machine_type": "mill",
        "supported_materials": ["aluminum", "mild_steel", "stainless_steel", "brass"],
        "supported_size_classes": ["small", "medium", "large"],
        "default_tool_family": "end_mills",
        "setup_hourly_rate": 118.0,
        "utilization_target": 0.84,
    },
    {
        "machine_id": "MILL_02",
        "machine_name": "DMG Mori CMX 1100",
        "machine_type": "mill",
        "supported_materials": ["aluminum", "mild_steel", "stainless_steel", "titanium"],
        "supported_size_classes": ["small", "medium", "large"],
        "default_tool_family": "end_mills",
        "setup_hourly_rate": 126.0,
        "utilization_target": 0.86,
    },
    {
        "machine_id": "AXIS5_01",
        "machine_name": "Hermle C 400",
        "machine_type": "5_axis",
        "supported_materials": ["aluminum", "stainless_steel", "titanium", "inconel"],
        "supported_size_classes": ["small", "medium"],
        "default_tool_family": "multi_axis_tools",
        "setup_hourly_rate": 175.0,
        "utilization_target": 0.88,
    },
    {
        "machine_id": "MTURN_01",
        "machine_name": "Mazak Integrex i-200",
        "machine_type": "mill_turn",
        "supported_materials": ["aluminum", "stainless_steel", "titanium", "inconel"],
        "supported_size_classes": ["small", "medium", "large"],
        "default_tool_family": "multi_axis_tools",
        "setup_hourly_rate": 168.0,
        "utilization_target": 0.87,
    },
    {
        "machine_id": "FIN_01",
        "machine_name": "Okamoto Finishing Cell",
        "machine_type": "secondary",
        "supported_materials": ["aluminum", "mild_steel", "stainless_steel", "brass", "titanium"],
        "supported_size_classes": ["small", "medium"],
        "default_tool_family": "boring_tools",
        "setup_hourly_rate": 92.0,
        "utilization_target": 0.8,
    },
]

MACHINE_TYPE_COMPATIBILITY = {
    "turning": ["lathe", "mill_turn"],
    "milling": ["mill", "5_axis", "mill_turn"],
    "drilling": ["mill", "5_axis", "mill_turn", "secondary"],
    "tapping": ["mill", "5_axis", "mill_turn", "secondary"],
    "boring": ["mill", "5_axis", "mill_turn", "secondary"],
    "finishing": ["secondary", "mill", "5_axis"],
    "multi_op": ["5_axis", "mill_turn", "mill"],
}

PART_FAMILIES = [
    "shaft",
    "flange",
    "housing",
    "bracket",
    "sleeve",
    "custom_precision",
    "valve_body",
]

OPERATION_TYPES = ["turning", "milling", "drilling", "tapping", "boring", "finishing", "multi_op"]
MATERIALS = ["aluminum", "stainless_steel", "mild_steel", "brass", "titanium", "inconel"]
SIZE_CLASSES = ["small", "medium", "large"]
TOLERANCE_CLASSES = ["standard", "tight", "ultra_tight"]
FIXTURE_TYPES = ["standard_vise", "soft_jaw", "collet", "chuck", "custom_fixture", "palletized"]
TOOL_FAMILIES = ["turning_tools", "end_mills", "drills", "taps", "boring_tools", "multi_axis_tools"]
DUE_DATE_PRIORITIES = ["low", "normal", "high", "critical"]

BASE_SETUP_MINUTES = {
    "lathe": 45,
    "mill": 52,
    "5_axis": 78,
    "mill_turn": 72,
    "secondary": 30,
}

DEFAULT_WEIGHTS = {
    "material_change": 14.0,
    "fixture_change": 18.0,
    "part_family_change": 11.0,
    "tool_mismatch": 20.0,
    "tolerance_increase": 8.0,
    "operation_change": 10.0,
    "complexity_change": 2.2,
    "size_change": 7.0,
    "rush_penalty": 6.0,
    "tooling_overlap_credit": 16.0,
    "same_family_credit": 7.0,
    "same_fixture_credit": 8.0,
}

MATERIAL_CHANGE_PENALTY = {
    ("aluminum", "stainless_steel"): 10,
    ("aluminum", "mild_steel"): 8,
    ("aluminum", "brass"): 5,
    ("aluminum", "titanium"): 18,
    ("aluminum", "inconel"): 22,
    ("stainless_steel", "mild_steel"): 6,
    ("stainless_steel", "brass"): 9,
    ("stainless_steel", "titanium"): 11,
    ("stainless_steel", "inconel"): 16,
    ("mild_steel", "brass"): 7,
    ("mild_steel", "titanium"): 15,
    ("mild_steel", "inconel"): 19,
    ("brass", "titanium"): 16,
    ("brass", "inconel"): 20,
    ("titanium", "inconel"): 10,
}

SIZE_CLASS_ORDER = {"small": 0, "medium": 1, "large": 2}
TOLERANCE_ORDER = {"standard": 0, "tight": 1, "ultra_tight": 2}
PRIORITY_ORDER = {"low": 0, "normal": 1, "high": 2, "critical": 3}

EXPLANATION_TEMPLATE = {
    "summary": (
        "The optimizer evaluates every feasible machine and insertion point, then compares the extra setup burden "
        "created by inserting the new job against the transition it replaces."
    )
}
