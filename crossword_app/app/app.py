from __future__ import annotations

import os, sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st

from septago_crossword.geometry import build_grid_spec
from septago_crossword.puzzle_io import list_puzzles, load_puzzle, PuzzleValidationError
from septago_crossword.engine import build_truth_map, init_state, reduce, GridEvent
from septago_crossword.ui_adapters import make_component_props
from septago_crossword.component.crossword_grid import crossword_grid


APP_TITLE = "Septago Crossword"

# Fallback instructions (used if puzzle meta does not provide meta.instructions)
DEFAULT_INSTRUCTIONS = """**How to Play**

Each clue contains two possible words which are anagrams of each other. 
Each anagram takes a meaning from the clue. 
The hidden word is created from the intersection of the bars read left to right, top to bottom, clockwise. 
Use the hidden word's solution to determine which anagram fits the grid. 

- Click a square to focus it.
- Type to fill.
- Arrow keys move.
- **Tab / Enter** advances to the next clue. **Shift+Tab** goes back.
- **Space** toggles direction at intersections.
- Use **Check word (active)** to mark only the current entry, or **Check puzzle** to mark everything.
"""


def _ensure_state():
    if "grid_spec" not in st.session_state:
        st.session_state.grid_spec = build_grid_spec()

    if "puzzle" not in st.session_state:
        st.session_state.puzzle = None
    if "truth" not in st.session_state:
        st.session_state.truth = None
    if "game_state" not in st.session_state:
        st.session_state.game_state = None
    if "last_event_id" not in st.session_state:
        st.session_state.last_event_id = None

    if "show_instructions" not in st.session_state:
        st.session_state.show_instructions = False


def _slot_label(slot_id: str) -> str:
    return {
        "h1": "H1",
        "h2": "H2",
        "v1": "V1",
        "v2": "V2",
        "hw": "HW",
    }.get(slot_id, slot_id.upper())


def _render_clues(puzzle, grid_spec, game_state):
    st.markdown("### Clues")

    def clue_button(slot_id: str, entry):
        active = (game_state is not None and game_state.active_slot == slot_id)
        label = f"{_slot_label(slot_id)} — {entry.clue}"

        btn_type = "primary" if active else "secondary"
        if st.button(label, key=f"clue_{slot_id}", use_container_width=True, type=btn_type):
            # Jump to slot start
            cells = grid_spec.slots[slot_id]
            orientation = game_state.orientation
            if slot_id in ("h1", "h2"):
                orientation = "H"
            elif slot_id in ("v1", "v2"):
                orientation = "V"

            st.session_state.game_state = game_state.__class__(
                puzzle_id=game_state.puzzle_id,
                grid_letters=game_state.grid_letters,
                given_cells=game_state.given_cells,
                active_cell=cells[0],
                active_slot=slot_id,
                orientation=orientation,
                check_marks=game_state.check_marks,
                last_action="jump_slot",
                last_client_seq=game_state.last_client_seq,
            )

    c1, c2 = st.columns(2, gap="large")

    with c1:
        st.markdown("**Horizontal**")
        clue_button("h1", puzzle.entries["h1"])
        clue_button("h2", puzzle.entries["h2"])
        st.markdown("**Clue Word**")
        clue_button("hw", puzzle.entries["hw"])

    with c2:
        st.markdown("**Vertical**")
        clue_button("v1", puzzle.entries["v1"])
        clue_button("v2", puzzle.entries["v2"])


def main():
    st.set_page_config(page_title=APP_TITLE, page_icon="🧩", layout="wide")
    _ensure_state()

    grid_spec = st.session_state.grid_spec

    puzzle_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "puzzles")
    metas = list_puzzles(puzzle_dir)

    with st.sidebar:
        st.header("Puzzle")
        if not metas:
            st.warning(f"No puzzles found in {puzzle_dir}")
            st.stop()

        options = {f"{m.id} — {m.title}": m for m in metas}
        pick = st.selectbox("Select a puzzle", list(options.keys()))
        chosen = options[pick]

        load_clicked = st.button("Load puzzle", type="primary", use_container_width=True)
        reset_clicked = st.button("Reset grid", use_container_width=True, disabled=st.session_state.puzzle is None)
        st.divider()
        check_word_clicked = st.button("Check word (active)", use_container_width=True, disabled=st.session_state.game_state is None)
        check_puz_clicked = st.button("Check puzzle", use_container_width=True, disabled=st.session_state.game_state is None)

        # Instructions toggle (always available)
        if st.button("Instructions", use_container_width=True):
            st.session_state.show_instructions = not st.session_state.show_instructions

    if load_clicked:
        path = os.path.join(puzzle_dir, chosen.filename)
        try:
            puzzle = load_puzzle(path, grid_spec)
        except PuzzleValidationError as e:
            st.session_state.puzzle = None
            st.session_state.truth = None
            st.session_state.game_state = None
            st.error(f"Puzzle invalid: {e}")
        else:
            st.session_state.puzzle = puzzle
            st.session_state.truth = build_truth_map(puzzle, grid_spec)
            st.session_state.game_state = init_state(puzzle, grid_spec)
            st.session_state.last_event_id = None

    if reset_clicked and st.session_state.puzzle is not None:
        st.session_state.game_state = init_state(st.session_state.puzzle, grid_spec)
        st.session_state.last_event_id = None

    puzzle = st.session_state.puzzle
    truth = st.session_state.truth
    game_state = st.session_state.game_state

    # Header / subtitle: driven from puzzle meta (or selected puzzle meta pre-load)
    if puzzle is not None:
        title = str((puzzle.meta or {}).get("title", chosen.title)).strip() or chosen.title
        subtitle = str((puzzle.meta or {}).get("subtitle", chosen.subtitle)).strip() or chosen.subtitle
        instructions = (puzzle.meta or {}).get("instructions", DEFAULT_INSTRUCTIONS)
    else:
        title = str(chosen.title).strip() or APP_TITLE
        subtitle = str(chosen.subtitle).strip()
        instructions = DEFAULT_INSTRUCTIONS

    st.title(title)
    if subtitle:
        st.caption(subtitle)

    if st.session_state.show_instructions:
        with st.expander("Instructions", expanded=True):
            st.markdown(instructions)

    if puzzle is None or truth is None or game_state is None:
        st.info("Load a puzzle to start playing.")
        st.stop()

    # Apply check buttons
    if check_word_clicked:
        game_state = reduce(game_state, GridEvent(type="REQUEST_CHECK_WORD", payload={}), grid_spec, truth)
        st.session_state.game_state = game_state

    if check_puz_clicked:
        game_state = reduce(game_state, GridEvent(type="REQUEST_CHECK_PUZZLE", payload={}), grid_spec, truth)
        st.session_state.game_state = game_state

    # NYT-style layout: grid ~1/3, clues ~2/3
    left, right = st.columns([1, 2], gap="large")

    with left:
        props = make_component_props(st.session_state.game_state, grid_spec)
        event = crossword_grid(props, key="crossword_grid")

        # Process component event (dedupe by event_id)
        if isinstance(event, dict) and event.get("schema_version") == "crosswordgridevent.v1":
            ev_id = event.get("event_id")
            if ev_id and ev_id != st.session_state.last_event_id:
                st.session_state.last_event_id = ev_id
                etype = event.get("type", "")
                payload = event.get("payload", {}) or {}

                # ----------------------------------------------
                # 🔒 Ignore stale events from previous state_id
                # ----------------------------------------------
                ev_state_id = payload.get("state_id")
                cur_state_id = getattr(st.session_state.game_state, "state_id", None)

                if ev_state_id is not None and cur_state_id is not None and ev_state_id != cur_state_id:
                    # Stale event posted before reset/new puzzle; ignore
                    pass
                else:
                    game_state = reduce(
                        st.session_state.game_state,
                        GridEvent(type=etype, payload=payload),
                        grid_spec,
                        truth
                    )
                    st.session_state.game_state = game_state

        st.caption(
            f"Active: {_slot_label(st.session_state.game_state.active_slot)} • "
            f"Orientation: {st.session_state.game_state.orientation} • "
            f"Last: {st.session_state.game_state.last_action}"
        )

    with right:
        _render_clues(puzzle, grid_spec, st.session_state.game_state)


if __name__ == "__main__":
    main()