from __future__ import annotations

from typing import Dict, Any, List

from .geometry import GridSpec, Cell, SlotId
from .engine import GameState, CheckState, SLOT_ORDER


def cell_id(cell: Cell) -> str:
    return f"{cell[0]},{cell[1]}"


def make_component_props(state: GameState, grid: GridSpec) -> Dict[str, Any]:
    cells_payload = []
    for r in range(grid.size):
        for c in range(grid.size):
            playable = grid.playable_mask[r][c]
            is_black = not playable
            cell = (r, c)
            letter = state.grid_letters.get(cell, "") if playable else ""
            is_given = cell in state.given_cells if playable else False
            in_active_slot = playable and cell in grid.slots[state.active_slot]
            is_active_cell = playable and cell == state.active_cell
            check_state: CheckState = state.check_marks.get(cell, "none") if playable else "none"

            cells_payload.append(
                {
                    "id": cell_id(cell),
                    "r": r,
                    "c": c,
                    "is_black": is_black,
                    "is_playable": playable,
                    "letter": letter,
                    "is_given": is_given,
                    "highlight": {
                        "active_cell": is_active_cell,
                        "active_slot": in_active_slot,
                        "check_state": check_state,
                    },
                }
            )

    # Slot geometry for the JS local-first reducer (NYT feel without lag)
    slots_payload: Dict[str, List[str]] = {
        sid: [cell_id(c) for c in cells]
        for sid, cells in grid.slots.items()
    }
    cell_to_slots_payload: Dict[str, List[str]] = {
        cell_id(cell): list(slots)
        for cell, slots in grid.cell_to_slots.items()
    }

    return {
        "schema_version": "crosswordgridprops.v1",
        "grid": {
            "size": grid.size,
            "cells": cells_payload,
            "styling": {
                "outer_border_px": 3,
                "inner_border_px": 1,
                "outer_border_color": "#222222",
                "inner_border_color": "#666666",
                "black_cell_color": "#000000",
                "white_cell_color": "#FFFFFF",
                "active_cell_outline_px": 3,
                "active_slot_fill_color": "#DCEBFF",
                "given_cell_fill_color": "#F2F2F2",
                "ok_fill_color": "#DFF6DD",
                "bad_fill_color": "#F8D7DA",
                "bad_text_color": "#7A1C1C",
            },
            "slots": slots_payload,
            "cell_to_slots": cell_to_slots_payload,
            "slot_order": list(SLOT_ORDER),
        },
        "focus": {
            "active_cell_id": cell_id(state.active_cell),
            "active_slot": state.active_slot,
            "orientation": state.orientation,
        },
        "behavior": {
            "capture_keyboard": True,
            "allow_edit_given_cells": False,
            "advance_on_type": True,
            "skip_black_cells": True,
        },
        "sync": {
            "last_client_seq": int(getattr(state, "last_client_seq", 0)),
            "puzzle_id": getattr(state, "puzzle_id", ""),
            "state_id": getattr(state, "state_id", ""),
        },
    }