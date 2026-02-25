from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .geometry import GridSpec, SlotId, Cell

ALLOWED_SLOTS: Tuple[SlotId, ...] = ("h1", "h2", "v1", "v2", "hw")


@dataclass(frozen=True)
class PuzzleMeta:
    id: str
    title: str
    subtitle: str
    author: str
    date: str
    difficulty: str
    filename: str


@dataclass(frozen=True)
class Entry:
    clue: str
    answer: str
    # Admin/reference-only field.
    # IMPORTANT: initials are NOT validated and do NOT affect puzzle validity.
    # If you want gameplay "givens", add an explicit field (e.g. meta.givens)
    # rather than overloading initials.
    initial: str = ""


@dataclass(frozen=True)
class Puzzle:
    schema_version: str
    meta: dict
    entries: Dict[SlotId, Entry]
    filename: str


class PuzzleValidationError(ValueError):
    pass


def _norm_letters(s: str) -> str:
    return "".join(ch for ch in s.upper().strip())


def _validate_letters_only(s: str, allow_dot: bool) -> None:
    for ch in s:
        if "A" <= ch <= "Z":
            continue
        if allow_dot and ch == ".":
            continue
        raise PuzzleValidationError(
            f"Invalid character '{ch}' in string '{s}'. Only A–Z{' and .' if allow_dot else ''} allowed."
        )


def list_puzzles(puzzle_dir: str) -> List[PuzzleMeta]:
    metas: List[PuzzleMeta] = []
    if not os.path.isdir(puzzle_dir):
        return metas

    for fn in sorted(os.listdir(puzzle_dir)):
        if not fn.lower().endswith(".json"):
            continue
        path = os.path.join(puzzle_dir, fn)
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            meta = raw.get("meta", {}) or {}
            metas.append(
                PuzzleMeta(
                    id=str(meta.get("id", fn.replace(".json", ""))),
                    title=str(meta.get("title", fn.replace(".json", ""))),
                    subtitle=str(meta.get("subtitle", "")),
                    author=str(meta.get("author", "")),
                    date=str(meta.get("date", "")),
                    difficulty=str(meta.get("difficulty", "")),
                    filename=fn,
                )
            )
        except Exception:
            # Skip unreadable/invalid files in listing; load will report details.
            continue
    return metas


def load_puzzle(path: str, grid: GridSpec) -> Puzzle:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    schema_version = str(raw.get("schema_version", "")).strip()
    if schema_version != "puzzlefile.v1":
        raise PuzzleValidationError(
            f"Unsupported or missing schema_version: {schema_version!r}. Expected 'puzzlefile.v1'."
        )

    meta = raw.get("meta", {}) or {}
    entries_raw = raw.get("entries", {}) or {}

    # Validate presence
    missing = [sid for sid in ALLOWED_SLOTS if sid not in entries_raw]
    if missing:
        raise PuzzleValidationError(f"Puzzle missing required entries: {missing}")

    entries: Dict[SlotId, Entry] = {}

    for sid in ALLOWED_SLOTS:
        e = entries_raw[sid] or {}
        clue = str(e.get("clue", "")).strip()
        if not clue:
            raise PuzzleValidationError(f"Entry {sid} missing non-empty 'clue'.")

        answer = _norm_letters(str(e.get("answer", "")))
        if not answer:
            raise PuzzleValidationError(f"Entry {sid} missing non-empty 'answer'.")
        _validate_letters_only(answer, allow_dot=False)

        required_len = grid.slot_lengths[sid]
        if len(answer) != required_len:
            raise PuzzleValidationError(
                f"Entry {sid} answer length {len(answer)} != required {required_len} for this grid."
            )

        # initials are admin/reference-only. Do not validate; do not require.
        initial = str(e.get("initial", "")).strip()
        entries[sid] = Entry(clue=clue, answer=answer, initial=initial)

    # Cross-consistency: project answers onto cells.
    truth: Dict[Cell, str] = {}
    for sid, entry in entries.items():
        cells = grid.slots[sid]
        for i, cell in enumerate(cells):
            ch = entry.answer[i]
            if cell in truth and truth[cell] != ch:
                raise PuzzleValidationError(
                    f"Cross inconsistency at cell {cell}: '{truth[cell]}' vs '{ch}' implied by slot {sid}."
                )
            truth[cell] = ch

    # Also ensure all playable cells are covered by truth.
    for r in range(grid.size):
        for c in range(grid.size):
            if grid.playable_mask[r][c] and (r, c) not in truth:
                raise PuzzleValidationError(
                    f"Playable cell {(r, c)} not covered by any entry; cannot validate/check puzzle."
                )

    return Puzzle(schema_version=schema_version, meta=meta, entries=entries, filename=os.path.basename(path))