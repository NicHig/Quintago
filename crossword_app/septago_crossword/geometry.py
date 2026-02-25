\
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Literal

Cell = Tuple[int, int]
SlotId = Literal["h1", "h2", "v1", "v2", "hw"]
Orientation = Literal["H", "V"]


@dataclass(frozen=True)
class GridSpec:
    size: int
    playable_mask: List[List[bool]]
    slots: Dict[SlotId, List[Cell]]
    cell_to_slots: Dict[Cell, List[SlotId]]
    slot_lengths: Dict[SlotId, int]


def build_grid_spec() -> GridSpec:
    """
    Fixed 5x5 geometry:
      playable rows (1-based): 2 and 4 -> r in {1,3}
      playable cols (1-based): 2 and 4 -> c in {1,3}
      playable = union of those rows/cols; all others black.
    Slots:
      h1: r=1, c=0..4
      h2: r=3, c=0..4
      v1: c=1, r=0..4
      v2: c=3, r=0..4
      hw: intersections clockwise: (1,1),(1,3),(3,3),(3,1)
    """
    size = 5
    playable_rows = {1, 3}
    playable_cols = {1, 3}

    playable_mask: List[List[bool]] = []
    for r in range(size):
        row = []
        for c in range(size):
            row.append((r in playable_rows) or (c in playable_cols))
        playable_mask.append(row)

    slots: Dict[SlotId, List[Cell]] = {
        "h1": [(1, c) for c in range(size)],
        "h2": [(3, c) for c in range(size)],
        "v1": [(r, 1) for r in range(size)],
        "v2": [(r, 3) for r in range(size)],
        "hw": [(1, 1), (1, 3), (3, 3), (3, 1)],
    }

    cell_to_slots: Dict[Cell, List[SlotId]] = {}
    for sid, cells in slots.items():
        for cell in cells:
            cell_to_slots.setdefault(cell, []).append(sid)

    slot_lengths = {sid: len(cells) for sid, cells in slots.items()}

    return GridSpec(
        size=size,
        playable_mask=playable_mask,
        slots=slots,
        cell_to_slots=cell_to_slots,
        slot_lengths=slot_lengths,
    )


def is_playable(grid: GridSpec, cell: Cell) -> bool:
    r, c = cell
    if r < 0 or c < 0 or r >= grid.size or c >= grid.size:
        return False
    return grid.playable_mask[r][c]


def first_playable_cell(grid: GridSpec) -> Cell:
    for r in range(grid.size):
        for c in range(grid.size):
            if grid.playable_mask[r][c]:
                return (r, c)
    raise RuntimeError("No playable cells in grid")
