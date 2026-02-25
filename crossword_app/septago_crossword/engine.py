from __future__ import annotations

from dataclasses import dataclass, replace
import uuid
from typing import Dict, List, Tuple, Literal

from .geometry import GridSpec, Cell, SlotId, Orientation, is_playable, first_playable_cell
from .puzzle_io import Puzzle

CheckState = Literal["none", "ok", "bad"]


@dataclass(frozen=True)
class TruthMap:
    truth: Dict[Cell, str]


@dataclass(frozen=True)
class GameState:
    puzzle_id: str
    state_id: str                       # unique per init/reset (forces frontend resync)
    grid_letters: Dict[Cell, str]          # "" or "A"-"Z"
    given_cells: frozenset[Cell]
    active_cell: Cell
    active_slot: SlotId
    orientation: Orientation               # H or V
    check_marks: Dict[Cell, CheckState]    # only for playable cells
    last_action: str = ""
    # Highest client_seq processed so far. Used by the frontend to ignore stale server renders.
    last_client_seq: int = 0


# --- truth/init ---

def build_truth_map(puzzle: Puzzle, grid: GridSpec) -> TruthMap:
    truth: Dict[Cell, str] = {}
    for sid, entry in puzzle.entries.items():
        cells = grid.slots[sid]
        for i, cell in enumerate(cells):
            truth[cell] = entry.answer[i]
    return TruthMap(truth=truth)


def init_state(puzzle: Puzzle, grid: GridSpec) -> GameState:
    grid_letters: Dict[Cell, str] = {}
    # "given_cells" are gameplay-relevant prefilled cells.
    # We do NOT use puzzle entry "initial" for givens; initials are admin/reference-only.
    # If you want givens, add a dedicated field (e.g., puzzle.meta.givens).
    given: set[Cell] = set()

    # Initialize empty
    for r in range(grid.size):
        for c in range(grid.size):
            if grid.playable_mask[r][c]:
                grid_letters[(r, c)] = ""

    # Optional: support explicit givens via meta.givens
    # Format: meta.givens = [{"cell": "r,c", "letter": "A"}, ...]
    givens_raw = (puzzle.meta or {}).get("givens", None)
    if isinstance(givens_raw, list):
        for item in givens_raw:
            if not isinstance(item, dict):
                continue
            cell_id = str(item.get("cell", ""))
            letter = str(item.get("letter", "")).upper().strip()
            try:
                r_s, c_s = cell_id.split(",")
                cell = (int(r_s), int(c_s))
            except Exception:
                continue
            if cell not in grid_letters:
                continue
            if not (len(letter) == 1 and "A" <= letter <= "Z"):
                continue
            grid_letters[cell] = letter
            given.add(cell)

    start = first_playable_cell(grid)
    orientation: Orientation = "H"
    active_slot = _resolve_active_slot(grid, start, orientation, prefer_hw=False)

    check_marks = {cell: "none" for cell in grid_letters.keys()}

    puzzle_id = str(puzzle.meta.get("id", puzzle.filename))
    return GameState(
        puzzle_id=puzzle_id,
        state_id=str(uuid.uuid4()),
        grid_letters=grid_letters,
        given_cells=frozenset(given),
        active_cell=start,
        active_slot=active_slot,
        orientation=orientation,
        check_marks=check_marks,
        last_action="init",
        last_client_seq=0,
    )


# --- event contracts ---

EventType = Literal[
    "CLICK_CELL",
    "TYPE_CHAR",
    "BACKSPACE",
    "ARROW",
    "TAB",
    "SHIFT_TAB",
    "TOGGLE_ORIENTATION",
    "REQUEST_CHECK_WORD",
    "REQUEST_CHECK_PUZZLE",
]


@dataclass(frozen=True)
class GridEvent:
    type: EventType
    payload: dict


SLOT_ORDER: List[SlotId] = ["h1", "h2", "v1", "v2", "hw"]


# --- reducers ---

def reduce(state: GameState, event: GridEvent, grid: GridSpec, truth: TruthMap) -> GameState:
    """
    Reducer remains the authoritative source of truth for server state.

    IMPORTANT: The frontend performs local-first updates for responsiveness and
    includes payload.client_seq. We track the max client_seq processed so the
    frontend can ignore stale renders during fast input.
    """
    payload = event.payload or {}
    client_seq = payload.get("client_seq", None)
    try:
        client_seq_int = int(client_seq) if client_seq is not None else None
    except Exception:
        client_seq_int = None

    t = event.type
    if t == "CLICK_CELL":
        out = _on_click_cell(state, payload, grid)
    elif t == "TYPE_CHAR":
        out = _on_type_char(state, payload, grid)
    elif t == "BACKSPACE":
        out = _on_backspace(state, grid)
    elif t == "ARROW":
        out = _on_arrow(state, payload, grid)
    elif t == "TAB":
        out = _on_tab(state, grid, forward=True)
    elif t == "SHIFT_TAB":
        out = _on_tab(state, grid, forward=False)
    elif t == "TOGGLE_ORIENTATION":
        out = _on_toggle_orientation(state, grid)
    elif t == "REQUEST_CHECK_WORD":
        out = check_word(state, grid, truth)
    elif t == "REQUEST_CHECK_PUZZLE":
        out = check_puzzle(state, grid, truth)
    else:
        out = replace(state, last_action=f"ignored:{t}")

    if client_seq_int is not None and client_seq_int > out.last_client_seq:
        out = replace(out, last_client_seq=client_seq_int)

    return out


def check_word(state: GameState, grid: GridSpec, truth: TruthMap) -> GameState:
    cells = grid.slots[state.active_slot]
    new_marks = dict(state.check_marks)
    for cell in cells:
        if cell not in truth.truth:
            continue
        val = state.grid_letters.get(cell, "")
        if val == "":
            new_marks[cell] = "bad"
        else:
            new_marks[cell] = "ok" if val == truth.truth[cell] else "bad"
    return replace(state, check_marks=new_marks, last_action="check_word")


def check_puzzle(state: GameState, grid: GridSpec, truth: TruthMap) -> GameState:
    new_marks = dict(state.check_marks)
    for cell, expected in truth.truth.items():
        val = state.grid_letters.get(cell, "")
        if val == "":
            new_marks[cell] = "bad"
        else:
            new_marks[cell] = "ok" if val == expected else "bad"
    return replace(state, check_marks=new_marks, last_action="check_puzzle")


def clear_checks(state: GameState) -> GameState:
    return replace(state, check_marks={cell: "none" for cell in state.check_marks.keys()})


# --- helpers ---

def _resolve_active_slot(grid: GridSpec, cell: Cell, orientation: Orientation, prefer_hw: bool) -> SlotId:
    slots = grid.cell_to_slots.get(cell, [])
    h_opts = [s for s in slots if s in ("h1", "h2")]
    v_opts = [s for s in slots if s in ("v1", "v2")]
    hw_opts = [s for s in slots if s == "hw"]

    if orientation == "H" and h_opts:
        return h_opts[0]
    if orientation == "V" and v_opts:
        return v_opts[0]
    if prefer_hw and hw_opts:
        return "hw"

    if h_opts:
        return h_opts[0]
    if v_opts:
        return v_opts[0]
    if hw_opts:
        return "hw"
    return "h1"


def _on_click_cell(state: GameState, payload: dict, grid: GridSpec) -> GameState:
    cell_id = str(payload.get("cell_id", ""))
    try:
        r, c = cell_id.split(",")
        cell = (int(r), int(c))
    except Exception:
        return replace(state, last_action="click:bad_cell_id")

    if not is_playable(grid, cell):
        return replace(state, last_action="click:black_or_oob")

    new_orientation = state.orientation
    if cell == state.active_cell:
        slots = grid.cell_to_slots.get(cell, [])
        has_h = any(s in ("h1", "h2") for s in slots)
        has_v = any(s in ("v1", "v2") for s in slots)
        if has_h and has_v:
            new_orientation = "V" if state.orientation == "H" else "H"

    new_slot = _resolve_active_slot(grid, cell, new_orientation, prefer_hw=False)
    return replace(state, active_cell=cell, orientation=new_orientation, active_slot=new_slot, last_action="click")


def _advance_within_slot(grid: GridSpec, slot: SlotId, cell: Cell, step: int) -> Cell:
    cells = grid.slots[slot]
    if cell not in cells:
        return cells[0]
    idx = cells.index(cell)
    nxt = idx + step
    if nxt < 0 or nxt >= len(cells):
        return cell
    return cells[nxt]


def _on_type_char(state: GameState, payload: dict, grid: GridSpec) -> GameState:
    ch = str(payload.get("char", "")).upper()
    if len(ch) != 1 or not ("A" <= ch <= "Z"):
        return replace(state, last_action="type:ignored")

    if state.active_cell in state.given_cells:
        return replace(state, last_action="type:on_given_ignored")

    new_letters = dict(state.grid_letters)
    new_letters[state.active_cell] = ch

    new_state = replace(state, grid_letters=new_letters, last_action="type")
    new_state = clear_checks(new_state)

    next_cell = _advance_within_slot(grid, state.active_slot, state.active_cell, step=1)
    return replace(new_state, active_cell=next_cell)


def _on_backspace(state: GameState, grid: GridSpec) -> GameState:
    if state.active_cell in state.given_cells:
        return replace(state, last_action="backspace:on_given_ignored")

    val = state.grid_letters.get(state.active_cell, "")
    new_letters = dict(state.grid_letters)

    if val != "":
        new_letters[state.active_cell] = ""
        new_state = replace(state, grid_letters=new_letters, last_action="backspace:clear")
        return clear_checks(new_state)

    prev_cell = _advance_within_slot(grid, state.active_slot, state.active_cell, step=-1)
    if prev_cell == state.active_cell:
        return replace(state, last_action="backspace:at_start")

    if prev_cell in state.given_cells:
        return replace(state, active_cell=prev_cell, last_action="backspace:prev_is_given")

    new_letters[prev_cell] = ""
    new_state = replace(state, grid_letters=new_letters, active_cell=prev_cell, last_action="backspace:move_clear")
    return clear_checks(new_state)


def _step_dir(dir_: str) -> Tuple[int, int, Orientation]:
    if dir_ == "LEFT":
        return (0, -1, "H")
    if dir_ == "RIGHT":
        return (0, 1, "H")
    if dir_ == "UP":
        return (-1, 0, "V")
    if dir_ == "DOWN":
        return (1, 0, "V")
    return (0, 0, "H")


def _on_arrow(state: GameState, payload: dict, grid: GridSpec) -> GameState:
    dir_ = str(payload.get("dir", "")).upper()
    dr, dc, implied_orientation = _step_dir(dir_)
    if dr == 0 and dc == 0:
        return replace(state, last_action="arrow:ignored")

    orientation: Orientation = implied_orientation
    r, c = state.active_cell

    for _ in range(grid.size * grid.size):
        r += dr
        c += dc
        cell = (r, c)
        if r < 0 or c < 0 or r >= grid.size or c >= grid.size:
            return replace(
                state,
                orientation=orientation,
                active_slot=_resolve_active_slot(grid, state.active_cell, orientation, False),
                last_action="arrow:edge",
            )
        if is_playable(grid, cell):
            new_slot = _resolve_active_slot(grid, cell, orientation, prefer_hw=False)
            return replace(
                state,
                active_cell=cell,
                orientation=orientation,
                active_slot=new_slot,
                last_action=f"arrow:{dir_.lower()}",
            )
    return replace(state, last_action="arrow:failed")


def _on_tab(state: GameState, grid: GridSpec, forward: bool) -> GameState:
    cur = state.active_slot
    try:
        idx = SLOT_ORDER.index(cur)
    except ValueError:
        idx = 0
    nxt = (idx + (1 if forward else -1)) % len(SLOT_ORDER)
    slot = SLOT_ORDER[nxt]
    cells = grid.slots[slot]
    orientation: Orientation = state.orientation
    if slot in ("h1", "h2"):
        orientation = "H"
    elif slot in ("v1", "v2"):
        orientation = "V"
    return replace(state, active_slot=slot, active_cell=cells[0], orientation=orientation, last_action="tab")


def _on_toggle_orientation(state: GameState, grid: GridSpec) -> GameState:
    cell = state.active_cell
    slots = grid.cell_to_slots.get(cell, [])
    has_h = any(s in ("h1", "h2") for s in slots)
    has_v = any(s in ("v1", "v2") for s in slots)
    if not (has_h and has_v):
        return replace(state, last_action="toggle:ignored")

    new_orientation: Orientation = "V" if state.orientation == "H" else "H"
    new_slot = _resolve_active_slot(grid, cell, new_orientation, prefer_hw=False)
    return replace(state, orientation=new_orientation, active_slot=new_slot, last_action="toggle")