import json
from pathlib import Path
from typing import Tuple, Mapping, Dict, Any, Optional

from core.types import (
    Item, Fixture, Actor, GridPlacement, Edge, NodeVitals, Node,
    Companion, Exposure, PlayerCharacter, TreeNode, GameState,
    ItemCategory, FixtureState, Environment
)

DEFAULT_ITEMS = [
  {
    "id": "fitting_copper",
    "name": "Copper Pipe Fitting",
    "category": "utility",
    "tags": ["seal_fitting", "conductive"],
    "integrity": 1,
    "max_integrity": 1,
    "description": "Standard threaded pipe collar with a clean silicone ring."
  },
  {
    "id": "pass_work",
    "name": "Stamped Work Pass",
    "category": "credential",
    "tags": ["dock_clearance", "id_verified"],
    "integrity": 0,
    "max_integrity": 0,
    "description": "Laminated shift card signed by the transit stevedore office."
  },
  {
    "id": "dice_steel",
    "name": "Steel Dice",
    "category": "record",
    "tags": ["morale", "barter_token"],
    "integrity": 0,
    "max_integrity": 0,
    "description": "Two milled steel cubes, pips worn flat from rolling on deck plate."
  },
  {
    "id": "chit_transit",
    "name": "Transit Token",
    "category": "credential",
    "tags": ["transit_clearance"],
    "integrity": 1,
    "max_integrity": 1,
    "description": "Stamped metal token granting single-hop shuttle boarding."
  },
  {
    "id": "tool_prybar",
    "name": "Thermal Pry-Bar",
    "category": "utility",
    "tags": ["force_lever", "heavy_duty"],
    "integrity": 4,
    "max_integrity": 4,
    "description": "Flat-nosed iron lever rated for stuck latches and warped plates."
  },
  {
    "id": "flask_water",
    "name": "Insulated Canteen",
    "category": "sustenance",
    "tags": ["hydration", "refillable"],
    "integrity": 3,
    "max_integrity": 3,
    "description": "Metal drinking flask fitted with a screw seal."
  },
  {
    "id": "ration_dry",
    "name": "Compressed Ration",
    "category": "sustenance",
    "tags": ["nutrition"],
    "integrity": 3,
    "max_integrity": 3,
    "description": "Dense calorie block in foil wrap. Tastes like salted chalk."
  },
  {
    "id": "tool_spanner",
    "name": "Filter Spanner",
    "category": "utility",
    "tags": ["bio_filter", "wrench"],
    "integrity": 3,
    "max_integrity": 3,
    "description": "Offset ring spanner sized for standard filtration cartridge bolts."
  },
  {
    "id": "slate_tally",
    "name": "Chalk Slate",
    "category": "record",
    "tags": ["record", "marking"],
    "integrity": 0,
    "max_integrity": 0,
    "description": "Flat stone slab with a nub of calcium carbonate chalk."
  }
]

DEFAULT_NODES = [
  {
    "id": "stn_a_bunkroom",
    "name": "Deck 4 - Shared Bunkroom",
    "cluster": "station_alpha",
    "size": 5,
    "depth": 0,
    "environment": "pressurized",
    "base_vitals": {"pressure_kpa": 101.3, "radiation_msv": 0.1, "temperature_c": 20},
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "hatch_berth": {
        "id": "hatch_berth",
        "glyph": "=",
        "name": "Transit Hatch",
        "state": "open",
        "required_tag": None,
        "grants_edge": "to_berth",
        "on_use_effect": None,
        "description": "Standard oval pressure seal leading to the primary berths."
      },
      "spigot_01": {
        "id": "spigot_01",
        "glyph": "⌸",
        "name": "Water Spigot",
        "state": "active",
        "required_tag": "refillable",
        "grants_edge": None,
        "on_use_effect": "refill",
        "description": "Push-valve tap metering gray-line recycled water."
      }
    },
    "actors": {},
    "placements": [
      {"entity_id": "hatch_berth", "row": 0, "col": 2},
      {"entity_id": "spigot_01", "row": 3, "col": 1}
    ],
    "edges": {
      "to_berth": {
        "id": "to_berth",
        "target_node_id": "stn_a_berth",
        "label": "Berth 04",
        "gated_by_fixture": None,
        "requires_capability": None
      }
    },
    "description": "Narrow compartment lined with fold-down bunks. Recycled air tastes of copper and cleaning solvent."
  },
  {
    "id": "stn_a_berth",
    "name": "Berth 04 - Transfer Platform",
    "cluster": "station_alpha",
    "size": 7,
    "depth": 0,
    "environment": "pressurized",
    "base_vitals": {"pressure_kpa": 101.3, "radiation_msv": 0.2, "temperature_c": 18},
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "hatch_bunks": {
        "id": "hatch_bunks",
        "glyph": "◆",
        "name": "Bunkroom Hatch",
        "state": "open",
        "required_tag": None,
        "grants_edge": "to_bunks",
        "on_use_effect": None,
        "description": "Hatch back to the shared sleeping quarters."
      },
      "cargo_hoist": {
        "id": "cargo_hoist",
        "glyph": "⎅",
        "name": "Cargo Hoist Platform",
        "state": "locked",
        "required_tag": "dock_clearance",
        "grants_edge": "to_subdeck",
        "on_use_effect": "unlock",
        "description": "Chain-driven freight platform descending into the lower conduit well."
      },
      "shuttle_gate": {
        "id": "shuttle_gate",
        "glyph": "=",
        "name": "Shuttle Boarding Gate",
        "state": "sealed",
        "required_tag": "transit_clearance",
        "grants_edge": "to_shuttle",
        "on_use_effect": "unlock",
        "description": "Flexible boarding seal clamped to the exterior hopper vessel."
      },
      "freight_skid": {
        "id": "freight_skid",
        "glyph": "▓",
        "name": "Lashed Freight Skid",
        "state": "active",
        "required_tag": None,
        "grants_edge": None,
        "on_use_effect": None,
        "description": "Heavy cargo skid lashed down with tension clamps. Manifest reads: machine parts, Luna-bound."
      },
      "hab_hatch": {
        "id": "hab_hatch",
        "glyph": "≡",
        "name": "Hab Ring Corridor",
        "state": "open",
        "required_tag": None,
        "grants_edge": "to_hab",
        "on_use_effect": None,
        "description": "Wide corridor hatch leading up to the hab ring common gallery."
      }
    },
    "actors": {
      "npc_kael": {
        "id": "npc_kael",
        "glyph": "K",
        "name": "Kael",
        "title": "Dock Stevedore",
        "status": "Checking tension clamps on freight skid",
        "trade_offered_id": "pass_work",
        "trade_required_tag": "seal_fitting",
        "trade_completed": False,
        "dialogue_idle": "Hopper to the moon pad is spooling. Need a replacement collar for this hydraulic line before I can endorse any passes.",
        "dialogue_post_trade": "Collar's seated. Here — shift pass, endorsed. Radek down on the sub-deck could use a hand with the cargo platform.",
        "companion_unlock": None
      }
    },
    "placements": [
      {"entity_id": "hatch_bunks", "row": 0, "col": 3},
      {"entity_id": "freight_skid", "row": 2, "col": 2},
      {"entity_id": "npc_kael", "row": 2, "col": 4},
      {"entity_id": "hab_hatch", "row": 3, "col": 0},
      {"entity_id": "shuttle_gate", "row": 3, "col": 6},
      {"entity_id": "cargo_hoist", "row": 5, "col": 3}
    ],
    "edges": {
      "to_bunks": {
        "id": "to_bunks",
        "target_node_id": "stn_a_bunkroom",
        "label": "Bunkroom",
        "gated_by_fixture": None,
        "requires_capability": None
      },
      "to_hab": {
        "id": "to_hab",
        "target_node_id": "stn_a_hab",
        "label": "Hab Ring",
        "gated_by_fixture": None,
        "requires_capability": None
      },
      "to_shuttle": {
        "id": "to_shuttle",
        "target_node_id": "shuttle_ab",
        "label": "Shuttle Hopper",
        "gated_by_fixture": "shuttle_gate",
        "requires_capability": None
      },
      "to_subdeck": {
        "id": "to_subdeck",
        "target_node_id": "stn_a_sub",
        "label": "Sub-Deck",
        "gated_by_fixture": "cargo_hoist",
        "requires_capability": None
      }
    },
    "description": "Open transfer bay smelling of hydraulic fluid and ozone. Cargo skids line the deck under industrial lighting."
  },
  {
    "id": "stn_a_sub",
    "name": "Sub-Deck - Conduit Well",
    "cluster": "station_alpha",
    "size": 6,
    "depth": 1,
    "environment": "depressurizing",
    "base_vitals": {"pressure_kpa": 65.0, "radiation_msv": 2.0, "temperature_c": -25},
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "hoist_up": {
        "id": "hoist_up",
        "glyph": "⎅",
        "name": "Cargo Hoist (Up)",
        "state": "open",
        "required_tag": None,
        "grants_edge": "to_berth",
        "on_use_effect": None,
        "description": "Chain platform ascending back to Berth 04."
      },
      "jammed_valve": {
        "id": "jammed_valve",
        "glyph": "■",
        "name": "Jammed Pressure Valve",
        "state": "disabled",
        "required_tag": "force_lever",
        "grants_edge": None,
        "on_use_effect": "repair",
        "description": "Manual shutoff valve seized by thermal contraction. Frozen in the closed position."
      }
    },
    "actors": {
      "npc_radek": {
        "id": "npc_radek",
        "glyph": "R",
        "name": "Radek",
        "title": "Cargo Rigger",
        "status": "Crouched by a frozen conduit junction",
        "trade_offered_id": "ration_dry",
        "trade_required_tag": "force_lever",
        "trade_completed": False,
        "dialogue_idle": "Valve's seized. Can't move freight until someone levers it open. Got a bar?",
        "dialogue_post_trade": "That did it. Pressure's equalizing. Take this ration — I packed extra. I'll stick around if you're heading deeper.",
        "companion_unlock": "comp_radek"
      }
    },
    "placements": [
      {"entity_id": "hoist_up", "row": 0, "col": 3},
      {"entity_id": "jammed_valve", "row": 3, "col": 1},
      {"entity_id": "npc_radek", "row": 3, "col": 4}
    ],
    "edges": {
      "to_berth": {
        "id": "to_berth",
        "target_node_id": "stn_a_berth",
        "label": "Berth 04 (Up)",
        "gated_by_fixture": None,
        "requires_capability": None
      }
    },
    "description": "Low-ceilinged conduit passage. Frost crusts the pipe manifolds. The air is thin and bites cold."
  },
  {
    "id": "stn_a_hab",
    "name": "Hab Ring - Common Gallery",
    "cluster": "station_alpha",
    "size": 6,
    "depth": 0,
    "environment": "pressurized",
    "base_vitals": {"pressure_kpa": 101.3, "radiation_msv": 0.1, "temperature_c": 21},
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "hatch_to_berth": {
        "id": "hatch_to_berth",
        "glyph": "=",
        "name": "Berth Access Hatch",
        "state": "open",
        "required_tag": None,
        "grants_edge": "to_berth",
        "on_use_effect": None,
        "description": "Wide corridor hatch leading down to the transfer berths."
      },
      "notice_board": {
        "id": "notice_board",
        "glyph": "≡",
        "name": "Station Notice Board",
        "state": "active",
        "required_tag": None,
        "grants_edge": None,
        "on_use_effect": None,
        "description": "Laminated postings: shift rosters, water ration schedules, a missing-persons notice dated three cycles back."
      }
    },
    "actors": {},
    "placements": [
      {"entity_id": "hatch_to_berth", "row": 5, "col": 3},
      {"entity_id": "notice_board", "row": 2, "col": 2}
    ],
    "edges": {
      "to_berth": {
        "id": "to_berth",
        "target_node_id": "stn_a_berth",
        "label": "Berth 04",
        "gated_by_fixture": None,
        "requires_capability": None
      }
    },
    "description": "Curved corridor segment with brushed-metal walls. Handrails run at waist height. Faint hum of air recyclers."
  },
  {
    "id": "shuttle_ab",
    "name": "Inter-Station Shuttle",
    "cluster": "transit",
    "size": 4,
    "depth": 0,
    "environment": "pressurized",
    "base_vitals": {"pressure_kpa": 98.0, "radiation_msv": 1.5, "temperature_c": 16},
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "gate_alpha": {
        "id": "gate_alpha",
        "glyph": "◆",
        "name": "Station Alpha Umbilical",
        "state": "open",
        "required_tag": None,
        "grants_edge": "to_stn_a",
        "on_use_effect": None,
        "description": "Docking collar sealed to Station Alpha's Berth 04."
      },
      "gate_beta": {
        "id": "gate_beta",
        "glyph": "=",
        "name": "Station Beta Umbilical",
        "state": "sealed",
        "required_tag": "transit_clearance",
        "grants_edge": "to_stn_b",
        "on_use_effect": "unlock",
        "description": "Docking collar to Station Beta's Dock Ring. Requires transit token."
      },
      "gate_luna": {
        "id": "gate_luna",
        "glyph": "▲",
        "name": "Lunar Descent Hatch",
        "state": "sealed",
        "required_tag": "transit_clearance",
        "grants_edge": "to_luna",
        "on_use_effect": "unlock",
        "description": "Descent module hatch for the surface run to Lunar Pad."
      }
    },
    "actors": {},
    "placements": [
      {"entity_id": "gate_alpha", "row": 0, "col": 1},
      {"entity_id": "gate_beta", "row": 0, "col": 2},
      {"entity_id": "gate_luna", "row": 3, "col": 1}
    ],
    "edges": {
      "to_stn_a": {
        "id": "to_stn_a",
        "target_node_id": "stn_a_berth",
        "label": "Station Alpha",
        "gated_by_fixture": None,
        "requires_capability": None
      },
      "to_stn_b": {
        "id": "to_stn_b",
        "target_node_id": "stn_b_dock",
        "label": "Station Beta",
        "gated_by_fixture": "gate_beta",
        "requires_capability": None
      },
      "to_luna": {
        "id": "to_luna",
        "target_node_id": "luna_pad",
        "label": "Lunar Surface",
        "gated_by_fixture": "gate_luna",
        "requires_capability": None
      }
    },
    "description": "Cramped shuttle cabin with four acceleration couches. Viewport shows the slow rotation of station superstructure."
  },
  {
    "id": "stn_b_dock",
    "name": "Dock Ring - Bay 7",
    "cluster": "station_beta",
    "size": 6,
    "depth": 0,
    "environment": "pressurized",
    "base_vitals": {"pressure_kpa": 100.5, "radiation_msv": 0.3, "temperature_c": 19},
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "shuttle_return": {
        "id": "shuttle_return",
        "glyph": "◆",
        "name": "Shuttle Docking Port",
        "state": "open",
        "required_tag": None,
        "grants_edge": "to_shuttle",
        "on_use_effect": None,
        "description": "Umbilical back to the inter-station shuttle."
      },
      "hatch_array": {
        "id": "hatch_array",
        "glyph": "=",
        "name": "Array Corridor Hatch",
        "state": "open",
        "required_tag": None,
        "grants_edge": "to_array",
        "on_use_effect": None,
        "description": "Pressure hatch leading to the communications array hub."
      },
      "hatch_fuel": {
        "id": "hatch_fuel",
        "glyph": "▲",
        "name": "Fuel Spur Access",
        "state": "sealed",
        "required_tag": "id_verified",
        "grants_edge": "to_fuel",
        "on_use_effect": "unlock",
        "description": "Heavy blast door to the fuel processing spur. ID verification required."
      }
    },
    "actors": {},
    "placements": [
      {"entity_id": "shuttle_return", "row": 0, "col": 3},
      {"entity_id": "hatch_array", "row": 3, "col": 0},
      {"entity_id": "hatch_fuel", "row": 3, "col": 5}
    ],
    "edges": {
      "to_shuttle": {
        "id": "to_shuttle",
        "target_node_id": "shuttle_ab",
        "label": "Shuttle",
        "gated_by_fixture": None,
        "requires_capability": None
      },
      "to_array": {
        "id": "to_array",
        "target_node_id": "stn_b_array",
        "label": "Array Hub",
        "gated_by_fixture": None,
        "requires_capability": None
      },
      "to_fuel": {
        "id": "to_fuel",
        "target_node_id": "stn_b_fuel",
        "label": "Fuel Spur",
        "gated_by_fixture": "hatch_fuel",
        "requires_capability": None
      }
    },
    "description": "Wide docking bay with magnetic clamp rails and loading gantries. The air smells of fuel volatiles and sealant."
  },
  {
    "id": "stn_b_array",
    "name": "Array Hub - Comms Center",
    "cluster": "station_beta",
    "size": 5,
    "depth": 0,
    "environment": "pressurized",
    "base_vitals": {"pressure_kpa": 101.0, "radiation_msv": 0.2, "temperature_c": 20},
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "hatch_dock": {
        "id": "hatch_dock",
        "glyph": "◆",
        "name": "Dock Ring Hatch",
        "state": "open",
        "required_tag": None,
        "grants_edge": "to_dock",
        "on_use_effect": None,
        "description": "Corridor back to Dock Ring Bay 7."
      }
    },
    "actors": {},
    "placements": [
      {"entity_id": "hatch_dock", "row": 4, "col": 2}
    ],
    "edges": {
      "to_dock": {
        "id": "to_dock",
        "target_node_id": "stn_b_dock",
        "label": "Dock Ring",
        "gated_by_fixture": None,
        "requires_capability": None
      }
    },
    "description": "Hexagonal chamber packed with signal processing racks. Status LEDs blink in steady patterns. Quiet."
  },
  {
    "id": "stn_b_fuel",
    "name": "Fuel Spur - Processing Bay",
    "cluster": "station_beta",
    "size": 5,
    "depth": 0,
    "environment": "pressurized",
    "base_vitals": {"pressure_kpa": 99.0, "radiation_msv": 1.0, "temperature_c": 22},
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "hatch_dock_fuel": {
        "id": "hatch_dock_fuel",
        "glyph": "◆",
        "name": "Dock Ring Hatch",
        "state": "open",
        "required_tag": None,
        "grants_edge": "to_dock",
        "on_use_effect": None,
        "description": "Blast door back to Dock Ring."
      }
    },
    "actors": {},
    "placements": [
      {"entity_id": "hatch_dock_fuel", "row": 4, "col": 2}
    ],
    "edges": {
      "to_dock": {
        "id": "to_dock",
        "target_node_id": "stn_b_dock",
        "label": "Dock Ring",
        "gated_by_fixture": None,
        "requires_capability": None
      }
    },
    "description": "Processing bay with pressurized fuel lines running floor to ceiling. Warning placards on every surface."
  },
  {
    "id": "luna_pad",
    "name": "Lunar Surface Pad",
    "cluster": "lunar_base",
    "size": 7,
    "depth": 0,
    "environment": "vacuum",
    "base_vitals": {"pressure_kpa": 0.0, "radiation_msv": 25.0, "temperature_c": -80},
    "grid_floor": "~",
    "grid_wall": "░",
    "fixtures": {
      "lander_hatch": {
        "id": "lander_hatch",
        "glyph": "▲",
        "name": "Lander Ascent Hatch",
        "state": "open",
        "required_tag": None,
        "grants_edge": "to_shuttle",
        "on_use_effect": None,
        "description": "Ascent module hatch back to the shuttle."
      },
      "dome_airlock": {
        "id": "dome_airlock",
        "glyph": "=",
        "name": "Habitat Dome Airlock",
        "state": "open",
        "required_tag": None,
        "grants_edge": "to_dome",
        "on_use_effect": None,
        "description": "Reinforced airlock cylinder leading into the pressurized dome."
      }
    },
    "actors": {},
    "placements": [
      {"entity_id": "lander_hatch", "row": 0, "col": 3},
      {"entity_id": "dome_airlock", "row": 6, "col": 3}
    ],
    "edges": {
      "to_shuttle": {
        "id": "to_shuttle",
        "target_node_id": "shuttle_ab",
        "label": "Shuttle (Ascent)",
        "gated_by_fixture": None,
        "requires_capability": "vacuum_traverse"
      },
      "to_dome": {
        "id": "to_dome",
        "target_node_id": "luna_dome",
        "label": "Habitat Dome",
        "gated_by_fixture": None,
        "requires_capability": "vacuum_traverse"
      }
    },
    "description": "Flat regolith landing apron under unfiltered starlight. Boot prints fade into gray dust. Silence."
  },
  {
    "id": "luna_dome",
    "name": "Habitat Dome - Central Bay",
    "cluster": "lunar_base",
    "size": 7,
    "depth": 0,
    "environment": "pressurized",
    "base_vitals": {"pressure_kpa": 95.0, "radiation_msv": 3.0, "temperature_c": 17},
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "airlock_pad": {
        "id": "airlock_pad",
        "glyph": "=",
        "name": "Surface Pad Airlock",
        "state": "open",
        "required_tag": None,
        "grants_edge": "to_pad",
        "on_use_effect": None,
        "description": "Airlock back to the open surface pad."
      },
      "hatch_smelter": {
        "id": "hatch_smelter",
        "glyph": "◆",
        "name": "Smelter Corridor",
        "state": "open",
        "required_tag": None,
        "grants_edge": "to_smelter",
        "on_use_effect": None,
        "description": "Heated corridor leading to the smelting facility."
      },
      "hatch_crater": {
        "id": "hatch_crater",
        "glyph": "▲",
        "name": "Crater Rim Access",
        "state": "sealed",
        "required_tag": "heavy_duty",
        "grants_edge": "to_crater",
        "on_use_effect": "unlock",
        "description": "Heavy exterior hatch to the crater rim observation path."
      }
    },
    "actors": {},
    "placements": [
      {"entity_id": "airlock_pad", "row": 0, "col": 3},
      {"entity_id": "hatch_smelter", "row": 3, "col": 0},
      {"entity_id": "hatch_crater", "row": 3, "col": 6}
    ],
    "edges": {
      "to_pad": {
        "id": "to_pad",
        "target_node_id": "luna_pad",
        "label": "Surface Pad",
        "gated_by_fixture": None,
        "requires_capability": None
      },
      "to_smelter": {
        "id": "to_smelter",
        "target_node_id": "luna_smelter",
        "label": "Smelter Flat",
        "gated_by_fixture": None,
        "requires_capability": None
      },
      "to_crater": {
        "id": "to_crater",
        "target_node_id": "luna_crater",
        "label": "Crater Rim",
        "gated_by_fixture": "hatch_crater",
        "requires_capability": None
      }
    },
    "description": "Geodesic dome interior with hydroponic trays and water recyclers. Artificial daylight panels overhead."
  },
  {
    "id": "luna_smelter",
    "name": "Smelter Flat - Processing Floor",
    "cluster": "lunar_base",
    "size": 6,
    "depth": 0,
    "environment": "pressurized",
    "base_vitals": {"pressure_kpa": 93.0, "radiation_msv": 5.0, "temperature_c": 35},
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "hatch_dome_smelter": {
        "id": "hatch_dome_smelter",
        "glyph": "◆",
        "name": "Dome Corridor",
        "state": "open",
        "required_tag": None,
        "grants_edge": "to_dome",
        "on_use_effect": None,
        "description": "Corridor back to the habitat dome."
      },
      "mine_shaft": {
        "id": "mine_shaft",
        "glyph": "⎅",
        "name": "Mine Shaft Cage",
        "state": "locked",
        "required_tag": "two_person_lift",
        "grants_edge": "to_mine",
        "on_use_effect": "unlock",
        "description": "Two-person cage lift descending into the deep mine. Requires two operators."
      }
    },
    "actors": {},
    "placements": [
      {"entity_id": "hatch_dome_smelter", "row": 0, "col": 3},
      {"entity_id": "mine_shaft", "row": 5, "col": 3}
    ],
    "edges": {
      "to_dome": {
        "id": "to_dome",
        "target_node_id": "luna_dome",
        "label": "Habitat Dome",
        "gated_by_fixture": None,
        "requires_capability": None
      },
      "to_mine": {
        "id": "to_mine",
        "target_node_id": "luna_mine",
        "label": "Deep Mine",
        "gated_by_fixture": "mine_shaft",
        "requires_capability": None
      }
    },
    "description": "Industrial floor vibrating with furnace resonance. Ore dust coats every surface. Heat radiates from smelting crucibles."
  },
  {
    "id": "luna_crater",
    "name": "Crater Rim - Observation Path",
    "cluster": "lunar_base",
    "size": 6,
    "depth": 0,
    "environment": "vacuum",
    "base_vitals": {"pressure_kpa": 0.0, "radiation_msv": 30.0, "temperature_c": -120},
    "grid_floor": "~",
    "grid_wall": "░",
    "fixtures": {
      "hatch_dome_crater": {
        "id": "hatch_dome_crater",
        "glyph": "◆",
        "name": "Dome Access",
        "state": "open",
        "required_tag": None,
        "grants_edge": "to_dome",
        "on_use_effect": None,
        "description": "Hatch back to the habitat dome."
      },
      "tube_entrance": {
        "id": "tube_entrance",
        "glyph": "⎅",
        "name": "Lava Tube Descent",
        "state": "sealed",
        "required_tag": "force_lever",
        "grants_edge": "to_tube",
        "on_use_effect": "unlock",
        "description": "Bolted hatch covering a natural lava tube opening. Pry marks around the rim."
      }
    },
    "actors": {},
    "placements": [
      {"entity_id": "hatch_dome_crater", "row": 0, "col": 3},
      {"entity_id": "tube_entrance", "row": 5, "col": 3}
    ],
    "edges": {
      "to_dome": {
        "id": "to_dome",
        "target_node_id": "luna_dome",
        "label": "Habitat Dome",
        "gated_by_fixture": None,
        "requires_capability": "vacuum_traverse"
      },
      "to_tube": {
        "id": "to_tube",
        "target_node_id": "luna_tube",
        "label": "Lava Tube",
        "gated_by_fixture": "tube_entrance",
        "requires_capability": None
      }
    },
    "description": "Narrow path carved into the crater wall. Earth hangs above the horizon line. No sound at all."
  },
  {
    "id": "luna_mine",
    "name": "Deep Mine - Primary Shaft",
    "cluster": "lunar_base",
    "size": 5,
    "depth": 1,
    "environment": "depressurizing",
    "base_vitals": {"pressure_kpa": 50.0, "radiation_msv": 15.0, "temperature_c": -30},
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "cage_up": {
        "id": "cage_up",
        "glyph": "⎅",
        "name": "Mine Cage (Up)",
        "state": "open",
        "required_tag": None,
        "grants_edge": "to_smelter",
        "on_use_effect": None,
        "description": "Cage lift back to the smelter floor."
      }
    },
    "actors": {},
    "placements": [
      {"entity_id": "cage_up", "row": 0, "col": 2}
    ],
    "edges": {
      "to_smelter": {
        "id": "to_smelter",
        "target_node_id": "luna_smelter",
        "label": "Smelter Flat (Up)",
        "gated_by_fixture": None,
        "requires_capability": None
      }
    },
    "description": "Rough-hewn shaft descending into basalt. Drill marks line the walls. Cold seeps from the rock."
  },
  {
    "id": "luna_tube",
    "name": "Lava Tube - Natural Chamber",
    "cluster": "lunar_base",
    "size": 6,
    "depth": 1,
    "environment": "low_temp",
    "base_vitals": {"pressure_kpa": 40.0, "radiation_msv": 8.0, "temperature_c": -45},
    "grid_floor": "·",
    "grid_wall": "░",
    "fixtures": {
      "ascent_hatch": {
        "id": "ascent_hatch",
        "glyph": "⎅",
        "name": "Crater Rim Ascent",
        "state": "open",
        "required_tag": None,
        "grants_edge": "to_crater",
        "on_use_effect": None,
        "description": "Ladder and hatch back up to the crater rim."
      }
    },
    "actors": {},
    "placements": [
      {"entity_id": "ascent_hatch", "row": 0, "col": 3}
    ],
    "edges": {
      "to_crater": {
        "id": "to_crater",
        "target_node_id": "luna_crater",
        "label": "Crater Rim (Up)",
        "gated_by_fixture": None,
        "requires_capability": None
      }
    },
    "description": "Vast natural tube of frozen basalt. The ceiling vanishes into darkness. Something drips in the distance."
  }
]

DEFAULT_COMPANIONS = [
  {
    "id": "comp_radek",
    "name": "Radek",
    "title": "Cargo Rigger",
    "status": "Ready to work",
    "capability_tag": "two_person_lift"
  }
]

DEFAULT_TREE = [
  {
    "id": "seam_discipline",
    "name": "Seam Discipline",
    "description": "Inspect sealed fixtures to reveal leak state and required tool tags.",
    "prerequisite": None,
    "unlock_condition": "use_fixture",
    "unlock_parameter": "spigot_01",
    "attuned": False
  },
  {
    "id": "bulkhead_ear",
    "name": "Bulkhead Ear",
    "description": "Inspect sealed edge fixtures to reveal destination pressure before opening.",
    "prerequisite": "seam_discipline",
    "unlock_condition": "visit_node",
    "unlock_parameter": "stn_a_sub",
    "attuned": False
  },
  {
    "id": "cold_bypass",
    "name": "Cold-Line Bypass",
    "description": "Halves temperature exposure accumulation rate.",
    "prerequisite": None,
    "unlock_condition": "survive_depth",
    "unlock_parameter": "1",
    "attuned": False
  },
  {
    "id": "vacuum_walk",
    "name": "Vacuum Walk",
    "description": "Halves pressure exposure accumulation. Grants vacuum_traverse capability.",
    "prerequisite": "cold_bypass",
    "unlock_condition": "complete_trade",
    "unlock_parameter": "npc_kael",
    "attuned": False
  },
  {
    "id": "deep_well",
    "name": "Deep-Well Attunement",
    "description": "Halves radiation exposure accumulation rate.",
    "prerequisite": "bulkhead_ear",
    "unlock_condition": "survive_depth",
    "unlock_parameter": "2",
    "attuned": False
  },
  {
    "id": "trench_hardened",
    "name": "Trench Hardened",
    "description": "All exposure thresholds increased by 5.0 (stressed at 10, critical at 15, incapacitated at 20).",
    "prerequisite": "vacuum_walk",
    "unlock_condition": "visit_node",
    "unlock_parameter": "luna_mine",
    "attuned": False
  }
]


def ensure_presets(presets_dir: Path) -> None:
    """Creates the presets directory and writes default JSON assets if missing."""
    presets_dir.mkdir(parents=True, exist_ok=True)
    files_to_write = [
        (presets_dir / "items.json", DEFAULT_ITEMS),
        (presets_dir / "nodes.json", DEFAULT_NODES),
        (presets_dir / "companions.json", DEFAULT_COMPANIONS),
        (presets_dir / "tree.json", DEFAULT_TREE),
    ]
    for path, data in files_to_write:
        if not path.exists():
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)


def load_items(path: Path) -> Tuple[Item, ...]:
    """Pure deserializer for items.json."""
    if not path.exists():
        raise FileNotFoundError(f"Items preset not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("items.json root must be a list")

    items = []
    required_keys = {"id", "name", "category", "tags", "integrity", "max_integrity", "description"}
    for idx, raw in enumerate(data):
        missing = required_keys - set(raw.keys())
        if missing:
            raise ValueError(f"Item #{idx} missing required fields: {missing}")
        items.append(
            Item(
                id=str(raw["id"]),
                name=str(raw["name"]),
                category=str(raw["category"]),
                tags=tuple(str(t) for t in raw["tags"]),
                integrity=int(raw["integrity"]),
                max_integrity=int(raw["max_integrity"]),
                description=str(raw["description"]),
            )
        )
    return tuple(items)


def load_companions(path: Path) -> Tuple[Companion, ...]:
    """Pure deserializer for companions.json."""
    if not path.exists():
        raise FileNotFoundError(f"Companions preset not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("companions.json root must be a list")

    companions = []
    required_keys = {"id", "name", "title", "status"}
    for idx, raw in enumerate(data):
        missing = required_keys - set(raw.keys())
        if missing:
            raise ValueError(f"Companion #{idx} missing required fields: {missing}")
        companions.append(
            Companion(
                id=str(raw["id"]),
                name=str(raw["name"]),
                title=str(raw["title"]),
                status=str(raw["status"]),
                capability_tag=raw.get("capability_tag"),
            )
        )
    return tuple(companions)


def load_tree(path: Path) -> Tuple[TreeNode, ...]:
    """Pure deserializer for tree.json."""
    if not path.exists():
        raise FileNotFoundError(f"Tree preset not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("tree.json root must be a list")

    tree_nodes = []
    required_keys = {"id", "name", "description", "prerequisite", "unlock_condition", "unlock_parameter", "attuned"}
    for idx, raw in enumerate(data):
        missing = required_keys - set(raw.keys())
        if missing:
            raise ValueError(f"TreeNode #{idx} missing required fields: {missing}")
        tree_nodes.append(
            TreeNode(
                id=str(raw["id"]),
                name=str(raw["name"]),
                description=str(raw["description"]),
                prerequisite=raw["prerequisite"],
                unlock_condition=str(raw["unlock_condition"]),
                unlock_parameter=str(raw["unlock_parameter"]),
                attuned=bool(raw["attuned"]),
            )
        )
    return tuple(tree_nodes)


def load_nodes(path: Path) -> Mapping[str, Node]:
    """Pure deserializer for nodes.json."""
    if not path.exists():
        raise FileNotFoundError(f"Nodes preset not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("nodes.json root must be a list")

    nodes_map: Dict[str, Node] = {}
    required_keys = {
        "id", "name", "cluster", "size", "depth", "environment", "base_vitals",
        "grid_floor", "grid_wall", "fixtures", "actors", "placements", "edges", "description"
    }

    for idx, raw in enumerate(data):
        missing = required_keys - set(raw.keys())
        if missing:
            raise ValueError(f"Node #{idx} missing required fields: {missing}")

        raw_vitals = raw["base_vitals"]
        vitals = NodeVitals(
            pressure_kpa=float(raw_vitals["pressure_kpa"]),
            radiation_msv=float(raw_vitals["radiation_msv"]),
            temperature_c=int(raw_vitals["temperature_c"]),
        )

        fixtures_dict: Dict[str, Fixture] = {}
        for fid, fraw in raw["fixtures"].items():
            fixtures_dict[fid] = Fixture(
                id=str(fraw["id"]),
                glyph=str(fraw["glyph"]),
                name=str(fraw["name"]),
                state=str(fraw["state"]),
                required_tag=fraw.get("required_tag"),
                grants_edge=fraw.get("grants_edge"),
                on_use_effect=fraw.get("on_use_effect"),
                description=str(fraw["description"]),
            )

        actors_dict: Dict[str, Actor] = {}
        for aid, araw in raw["actors"].items():
            actors_dict[aid] = Actor(
                id=str(araw["id"]),
                glyph=str(araw["glyph"]),
                name=str(araw["name"]),
                title=str(araw["title"]),
                status=str(araw["status"]),
                trade_offered_id=araw.get("trade_offered_id"),
                trade_required_tag=araw.get("trade_required_tag"),
                trade_completed=bool(araw.get("trade_completed", False)),
                dialogue_idle=str(araw["dialogue_idle"]),
                dialogue_post_trade=araw.get("dialogue_post_trade"),
                companion_unlock=araw.get("companion_unlock"),
            )

        placements_list = []
        for p in raw["placements"]:
            placements_list.append(
                GridPlacement(
                    entity_id=str(p["entity_id"]),
                    row=int(p["row"]),
                    col=int(p["col"]),
                )
            )

        edges_dict: Dict[str, Edge] = {}
        for eid, eraw in raw["edges"].items():
            edges_dict[eid] = Edge(
                id=str(eraw["id"]),
                target_node_id=str(eraw["target_node_id"]),
                label=str(eraw["label"]),
                gated_by_fixture=eraw.get("gated_by_fixture"),
                requires_capability=eraw.get("requires_capability"),
            )

        node = Node(
            id=str(raw["id"]),
            name=str(raw["name"]),
            cluster=str(raw["cluster"]),
            size=int(raw["size"]),
            depth=int(raw["depth"]),
            environment=str(raw["environment"]),
            base_vitals=vitals,
            grid_floor=str(raw["grid_floor"]),
            grid_wall=str(raw["grid_wall"]),
            fixtures=fixtures_dict,
            actors=actors_dict,
            placements=tuple(placements_list),
            edges=edges_dict,
            description=str(raw["description"]),
        )
        nodes_map[node.id] = node

    return nodes_map


def init_game_state(
    presets_dir: Path,
    character_name: str,
    anchor_choice: int,
    routine_choice: int,
) -> GameState:
    """Constructs a fresh initial GameState from loaded presets and character creation choices."""
    ensure_presets(presets_dir)
    items = load_items(presets_dir / "items.json")
    nodes = load_nodes(presets_dir / "nodes.json")
    tree = load_tree(presets_dir / "tree.json")

    items_by_id = {item.id: item for item in items}

    # Step 2: Personal Anchor
    anchor_map = {
        1: "fitting_copper",
        2: "pass_work",
        3: "dice_steel",
    }
    anchor_id = anchor_map.get(anchor_choice, "fitting_copper")
    anchor_item = items_by_id[anchor_id]

    # Step 3: Survival Context / Routine
    routine_map = {
        1: ("seam_scraper", "seal_fitting"),
        2: ("algae_tender", "bio_filter"),
        3: ("cargo_handler", "heavy_lift"),
    }
    past_work, initial_capability = routine_map.get(
        routine_choice, ("seam_scraper", "seal_fitting")
    )

    character = PlayerCharacter(
        name=character_name.strip() or "Vaelen",
        past_work=past_work,
        personal_anchor=anchor_item,
        inventory=(anchor_item,),
        unlocked_capabilities=frozenset({initial_capability}),
        exposure=Exposure(0.0, 0.0, 0.0),
    )

    start_node_id = "stn_a_bunkroom"
    start_node = nodes[start_node_id]

    return GameState(
        character=character,
        current_node_id=start_node_id,
        nodes=nodes,
        companions=(),
        tree=tree,
        visited_nodes=frozenset({start_node_id}),
        depth_ticks={},
        cycle=0,
        player_row=start_node.size // 2,
        player_col=start_node.size // 2,
        message_buffer=(
            f"Welcome aboard, {character.name}.",
            "You wake in Deck 4 shared bunkroom.",
        ),
        action_log=("Awoke in bunkroom.",),
        flavor_enabled=True,
        active_view="compartment",
        proximity_menu_active=False,
        is_running=True,
    )
