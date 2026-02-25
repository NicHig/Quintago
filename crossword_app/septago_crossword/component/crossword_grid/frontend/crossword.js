/**
 * Streamlit component messaging (vanilla JS).
 * Local-first reducer for NYT-like responsiveness (no lag).
 */
(function () {
  const root = document.getElementById("root");

  root.innerHTML = `<div style="font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Inter,Arial,sans-serif;
                               font-size: 13px; opacity: 0.75; padding: 8px;">
                      Loading grid…
                    </div>`;
  root.tabIndex = 0;

  let lastProps = null;

  // client_seq monotonic counter; server acks the max processed seq in props.sync.last_client_seq
  let clientSeq = 0;
  let latestSentSeq = 0;

  // Local state for immediate UI updates
  let local = null; // { meta, focus, letters, given, checks }

  function postMessage(type, payload) {
    window.parent.postMessage(
      Object.assign({ isStreamlitMessage: true, type: type }, payload || {}),
      "*"
    );
  }

  function setFrameHeight() {
    const height = document.body.scrollHeight + 8;
    postMessage("streamlit:setFrameHeight", { height });
  }

  function emitEvent(type, payload) {
    const seq = ++clientSeq;
    latestSentSeq = seq;

    const stateId = lastProps?.sync?.state_id || null;

    const ev = {
      schema_version: "crosswordgridevent.v1",
      event_id: (crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now()) + "-" + Math.random(),
      ts_ms: Date.now(),
      type,
      payload: Object.assign({}, payload || {}, {
        client_seq: seq,
        state_id: stateId,   // ✅ ADD THIS
      }),
  };

  postMessage("streamlit:setComponentValue", { value: ev });
  return seq;
}

  function applyStyling(sty) {
    if (!sty) return;
    const s = document.documentElement.style;
    if (sty.outer_border_px != null) s.setProperty("--outer-border-px", `${sty.outer_border_px}px`);
    if (sty.inner_border_px != null) s.setProperty("--inner-border-px", `${sty.inner_border_px}px`);
    if (sty.outer_border_color) s.setProperty("--outer-border-color", sty.outer_border_color);
    if (sty.inner_border_color) s.setProperty("--inner-border-color", sty.inner_border_color);
    if (sty.black_cell_color) s.setProperty("--black", sty.black_cell_color);
    if (sty.white_cell_color) s.setProperty("--white", sty.white_cell_color);
    if (sty.active_slot_fill_color) s.setProperty("--active-slot", sty.active_slot_fill_color);
    if (sty.given_cell_fill_color) s.setProperty("--given-fill", sty.given_cell_fill_color);
    if (sty.ok_fill_color) s.setProperty("--ok-fill", sty.ok_fill_color);
    if (sty.bad_fill_color) s.setProperty("--bad-fill", sty.bad_fill_color);
    if (sty.bad_text_color) s.setProperty("--bad-text", sty.bad_text_color);
    if (sty.active_cell_outline_px != null) s.setProperty("--active-outline-px", `${sty.active_cell_outline_px}px`);
  }

  function clamp(x, lo, hi) {
    return Math.max(lo, Math.min(hi, x));
  }

  function computeCellSize(gridSize) {
    // Root padding is minimal in CSS. Leave a bit of slack for borders.
    const pad = 8;
    const w = Math.max(0, root.clientWidth - pad);
    const cell = Math.floor(w / gridSize);
    // Allow the grid to expand to fill the column while keeping a sane minimum.
    // (The previous max clamp caused visible "dead space" on wide layouts.)
    return clamp(cell, 34, 140);
  }

  function buildMetaFromProps(props) {
    const grid = props.grid;
    const size = grid.size;

    const playableSet = new Set();
    const givenSet = new Set();
    const letters = new Map();
    const checks = new Map();

    for (const cell of grid.cells) {
      if (cell && cell.is_playable && !cell.is_black) {
        playableSet.add(cell.id);
        letters.set(cell.id, cell.letter || "");
        if (cell.is_given) givenSet.add(cell.id);
        checks.set(cell.id, (cell.highlight && cell.highlight.check_state) ? cell.highlight.check_state : "none");
      }
    }

    const slots = (grid.slots || {});
    const cellToSlots = (grid.cell_to_slots || {});
    const slotOrder = (grid.slot_order || ["h1", "h2", "v1", "v2", "hw"]);

    // Precompute index maps for O(1) advance
    const slotIndex = {};
    for (const sid of Object.keys(slots)) {
      const arr = slots[sid] || [];
      const im = {};
      for (let i = 0; i < arr.length; i++) im[arr[i]] = i;
      slotIndex[sid] = im;
    }

    const sync = (props.sync || {});
    const puzzleId = (sync.puzzle_id != null) ? String(sync.puzzle_id) : "";
    const stateId = (sync.state_id != null) ? String(sync.state_id) : "";

    return {
      size,
      puzzleId,
      stateId,
      playableSet,
      givenSet,
      slots,
      slotOrder,
      cellToSlots,
      slotIndex,
    };
  }

  function stateFromProps(props) {
    const meta = buildMetaFromProps(props);
    const focus = props.focus || {};
    return {
      meta,
      activeCellId: focus.active_cell_id,
      activeSlot: focus.active_slot,
      orientation: focus.orientation, // "H" or "V"
      letters: new Map(meta.playableSet.size ? Array.from(meta.playableSet).map(id => [id, meta.playableSet.has(id) ? (meta.letters?.get?.(id) || "") : ""]) : []),
      given: meta.givenSet,
      checks: new Map(), // checks are painted via props highlights; we keep local paint simple
    };
  }

  // Build local state from props but preserve letters from props accurately
  function syncLocalFromProps(props) {
    const meta = buildMetaFromProps(props);
    const focus = props.focus || {};
    const letters = new Map();
    const checks = new Map();

    for (const cell of props.grid.cells) {
      if (cell && cell.is_playable && !cell.is_black) {
        letters.set(cell.id, cell.letter || "");
        checks.set(cell.id, (cell.highlight && cell.highlight.check_state) ? cell.highlight.check_state : "none");
      }
    }

    local = {
      meta,
      activeCellId: focus.active_cell_id,
      activeSlot: focus.active_slot,
      orientation: focus.orientation,
      letters,
      given: meta.givenSet,
      checks,
    };
  }

  function idToRC(cellId) {
    const [r, c] = String(cellId).split(",");
    return [parseInt(r, 10), parseInt(c, 10)];
  }

  function rcToId(r, c) {
    return `${r},${c}`;
  }

  function resolveActiveSlot(meta, cellId, orientation, preferHW) {
    const slots = meta.cellToSlots[cellId] || [];
    const hOpts = slots.filter(s => (s === "h1" || s === "h2"));
    const vOpts = slots.filter(s => (s === "v1" || s === "v2"));
    const hwOpts = slots.filter(s => s === "hw");

    if (orientation === "H" && hOpts.length) return hOpts[0];
    if (orientation === "V" && vOpts.length) return vOpts[0];
    if (preferHW && hwOpts.length) return "hw";

    if (hOpts.length) return hOpts[0];
    if (vOpts.length) return vOpts[0];
    if (hwOpts.length) return "hw";
    return "h1";
  }

  function hasH(meta, cellId) {
    const s = meta.cellToSlots[cellId] || [];
    return s.some(x => x === "h1" || x === "h2");
  }

  function hasV(meta, cellId) {
    const s = meta.cellToSlots[cellId] || [];
    return s.some(x => x === "v1" || x === "v2");
  }

  function advanceWithinSlot(meta, slotId, cellId, step) {
    const arr = meta.slots[slotId] || [];
    const im = meta.slotIndex[slotId] || {};
    if (!(cellId in im)) return (arr.length ? arr[0] : cellId);
    const idx = im[cellId];
    const nxt = idx + step;
    if (nxt < 0 || nxt >= arr.length) return cellId;
    return arr[nxt];
  }

  function stepDir(dir) {
    const d = String(dir || "").toUpperCase();
    if (d === "LEFT") return [0, -1, "H"];
    if (d === "RIGHT") return [0, 1, "H"];
    if (d === "UP") return [-1, 0, "V"];
    if (d === "DOWN") return [1, 0, "V"];
    return [0, 0, "H"];
  }

  function applyLocalAction(actionType, payload) {
    if (!local) return;
    const meta = local.meta;

    if (actionType === "CLICK_CELL") {
      const cid = String(payload.cell_id || "");
      if (!meta.playableSet.has(cid)) return;

      let newOrientation = local.orientation;
      if (cid === local.activeCellId) {
        if (hasH(meta, cid) && hasV(meta, cid)) {
          newOrientation = (local.orientation === "H") ? "V" : "H";
        }
      } else {
        // Keep orientation if possible at new cell; otherwise switch to the available one.
        if (newOrientation === "H" && !hasH(meta, cid) && hasV(meta, cid)) newOrientation = "V";
        if (newOrientation === "V" && !hasV(meta, cid) && hasH(meta, cid)) newOrientation = "H";
      }

      const newSlot = resolveActiveSlot(meta, cid, newOrientation, false);
      local.activeCellId = cid;
      local.orientation = newOrientation;
      local.activeSlot = newSlot;
      return;
    }

    if (actionType === "TOGGLE_ORIENTATION") {
      const cid = local.activeCellId;
      if (!(hasH(meta, cid) && hasV(meta, cid))) return;
      const newOrientation = (local.orientation === "H") ? "V" : "H";
      local.orientation = newOrientation;
      local.activeSlot = resolveActiveSlot(meta, cid, newOrientation, false);
      return;
    }

    if (actionType === "ARROW") {
      const [dr, dc, implied] = stepDir(payload.dir);
      if (dr === 0 && dc === 0) return;

      let [r, c] = idToRC(local.activeCellId);

      // arrows imply orientation
      const orientation = implied;

      // scan until playable or edge
      for (let i = 0; i < meta.size * meta.size; i++) {
        r += dr; c += dc;
        if (r < 0 || c < 0 || r >= meta.size || c >= meta.size) {
          // at edge: only orientation changes; active cell stays
          local.orientation = orientation;
          local.activeSlot = resolveActiveSlot(meta, local.activeCellId, orientation, false);
          return;
        }
        const cid = rcToId(r, c);
        if (meta.playableSet.has(cid)) {
          local.activeCellId = cid;
          local.orientation = orientation;
          local.activeSlot = resolveActiveSlot(meta, cid, orientation, false);
          return;
        }
      }
      return;
    }

    if (actionType === "TYPE_CHAR") {
      const ch = String(payload.char || "").toUpperCase();
      if (!(ch.length === 1 && ch >= "A" && ch <= "Z")) return;

      const cid = local.activeCellId;
      if (local.given.has(cid)) return;

      local.letters.set(cid, ch);
      // advance within slot
      const next = advanceWithinSlot(meta, local.activeSlot, cid, 1);
      local.activeCellId = next;
      return;
    }

    if (actionType === "BACKSPACE") {
      const cid = local.activeCellId;
      if (local.given.has(cid)) return;

      const val = local.letters.get(cid) || "";
      if (val !== "") {
        local.letters.set(cid, "");
        return;
      }

      const prev = advanceWithinSlot(meta, local.activeSlot, cid, -1);
      if (prev === cid) return;

      local.activeCellId = prev;
      if (!local.given.has(prev)) local.letters.set(prev, "");
      return;
    }

    if (actionType === "TAB" || actionType === "SHIFT_TAB") {
      const forward = (actionType === "TAB");
      const order = meta.slotOrder || ["h1", "h2", "v1", "v2", "hw"];
      const cur = local.activeSlot;
      let idx = order.indexOf(cur);
      if (idx < 0) idx = 0;
      const nxt = (idx + (forward ? 1 : -1) + order.length) % order.length;
      const slot = order[nxt];

      const cells = meta.slots[slot] || [];
      if (!cells.length) return;

      let orientation = local.orientation;
      if (slot === "h1" || slot === "h2") orientation = "H";
      else if (slot === "v1" || slot === "v2") orientation = "V";

      local.activeSlot = slot;
      local.orientation = orientation;
      local.activeCellId = cells[0];
      return;
    }
  }

  function renderFromLocal(props) {
    root.innerHTML = "";

    if (!props || !props.grid || !props.grid.cells || !local) {
      root.innerHTML = `<div style="font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Inter,Arial,sans-serif;
                                 font-size: 13px; opacity: 0.85; padding: 8px;">
                          Grid props missing.
                        </div>`;
      setFrameHeight();
      return;
    }

    const grid = props.grid;
    applyStyling(grid.styling);

    // Responsive sizing: fill the column (~1/3 of Streamlit content width)
    const size = local.meta.size;
    const cellPx = computeCellSize(size);
    document.documentElement.style.setProperty("--cell-size", `${cellPx}px`);

    const gridEl = document.createElement("div");
    gridEl.className = "grid";
    gridEl.style.gridTemplateColumns = `repeat(${size}, var(--cell-size))`;
    gridEl.style.gridTemplateRows = `repeat(${size}, var(--cell-size))`;

    // Map from props for check paint; letters + active focus from local
    const cellMap = {};
    for (const cell of grid.cells) cellMap[cell.id] = cell;

    // Local-first active-slot highlight to avoid 1-keystroke lag.
    // (Server will eventually converge, but we don't wait for it.)
    const activeSlotCells = new Set();
    if (local && local.activeSlot && local.meta && local.meta.slots) {
      const arr = local.meta.slots[local.activeSlot] || [];
      for (const cid of arr) activeSlotCells.add(cid);
    }

    for (let r = 0; r < size; r++) {
      for (let c = 0; c < size; c++) {
        const cid = `${r},${c}`;
        const cell = cellMap[cid];

        const el = document.createElement("div");
        el.className = "cell";
        if (c === size - 1) el.classList.add("last-col");
        if (r === size - 1) el.classList.add("last-row");

        if (!cell || cell.is_black) {
          el.classList.add("black");
        } else {
          el.classList.add("playable");

          // Active slot highlight from LOCAL focus (no lag). If local is missing
          // (e.g., first paint), fall back to server highlight.
          if (activeSlotCells.size) {
            if (activeSlotCells.has(cid)) el.classList.add("active-slot");
          } else {
            if (cell.highlight && cell.highlight.active_slot) el.classList.add("active-slot");
          }

          // active cell highlight from local (so it responds immediately)
          if (cid === local.activeCellId) el.classList.add("active-cell");

          if (cell.is_given) el.classList.add("given");

          const cs = (cell.highlight && cell.highlight.check_state) ? cell.highlight.check_state : "none";
          if (cs === "ok") el.classList.add("check-ok");
          if (cs === "bad") el.classList.add("check-bad");

          el.textContent = local.letters.get(cid) || "";
          el.dataset.cellId = cid;

          el.addEventListener("click", (e) => {
            e.preventDefault();
            root.focus();
            const clicked = el.dataset.cellId;

            // local-first
            applyLocalAction("CLICK_CELL", { cell_id: clicked });
            renderFromLocal(lastProps);

            // server event
            emitEvent("CLICK_CELL", { cell_id: clicked });
          });
        }

        gridEl.appendChild(el);
      }
    }

    root.appendChild(gridEl);

    const hint = document.createElement("div");
    hint.className = "hint";
    hint.textContent = "Type letters • Arrows move • Tab/Shift+Tab jumps • Space toggles direction at intersections";
    root.appendChild(hint);

    setTimeout(setFrameHeight, 0);
  }

  function handleKeydown(e) {
    if (!lastProps?.behavior?.capture_keyboard) return;
    if (!local) return;

    const key = e.key;

    // Letters
    if (key && key.length === 1) {
      const ch = key.toUpperCase();
      if (ch >= "A" && ch <= "Z") {
        e.preventDefault();

        applyLocalAction("TYPE_CHAR", { char: ch });
        renderFromLocal(lastProps);

        emitEvent("TYPE_CHAR", { char: ch });
        return;
      }
    }

    // Controls
    if (key === "Backspace") {
      e.preventDefault();
      applyLocalAction("BACKSPACE", {});
      renderFromLocal(lastProps);
      emitEvent("BACKSPACE", {});
      return;
    }

    if (key === "ArrowLeft") {
      e.preventDefault();
      applyLocalAction("ARROW", { dir: "LEFT" });
      renderFromLocal(lastProps);
      emitEvent("ARROW", { dir: "LEFT" });
      return;
    }
    if (key === "ArrowRight") {
      e.preventDefault();
      applyLocalAction("ARROW", { dir: "RIGHT" });
      renderFromLocal(lastProps);
      emitEvent("ARROW", { dir: "RIGHT" });
      return;
    }
    if (key === "ArrowUp") {
      e.preventDefault();
      applyLocalAction("ARROW", { dir: "UP" });
      renderFromLocal(lastProps);
      emitEvent("ARROW", { dir: "UP" });
      return;
    }
    if (key === "ArrowDown") {
      e.preventDefault();
      applyLocalAction("ARROW", { dir: "DOWN" });
      renderFromLocal(lastProps);
      emitEvent("ARROW", { dir: "DOWN" });
      return;
    }

    if (key === "Tab" || key === "Enter") {
      // Treat Enter as NYT-ish "next clue" as well.
      e.preventDefault();
      const typ = (e.shiftKey ? "SHIFT_TAB" : "TAB");

      applyLocalAction(typ, {});
      renderFromLocal(lastProps);

      emitEvent(typ, {});
      return;
    }

    if (key === " ") {
      e.preventDefault();
      applyLocalAction("TOGGLE_ORIENTATION", { source: "SPACE" });
      renderFromLocal(lastProps);
      emitEvent("TOGGLE_ORIENTATION", { source: "SPACE" });
      return;
    }
  }

  root.addEventListener("keydown", handleKeydown);

  // Resize observer for responsive sizing + frame height.
  const ro = new ResizeObserver(() => {
    if (lastProps && local) {
      renderFromLocal(lastProps);
    } else {
      setFrameHeight();
    }
  });
  ro.observe(root);

  // Accept multiple Streamlit render message shapes.
  window.addEventListener("message", (event) => {
    const msg = event.data;
    const type = msg?.type;
    if (typeof type !== "string") return;

    if (type === "streamlit:render") {
      let props = null;
      if (msg.args && msg.args.props) props = msg.args.props;
      else if (msg.args && msg.args.args && msg.args.args.props) props = msg.args.args.props;
      else if (Array.isArray(msg.args) && msg.args[0] && msg.args[0].props) props = msg.args[0].props;
      else if (msg.props) props = msg.props;
      else props = msg.args || msg;

      lastProps = props;

      // Hard resync when the server starts a fresh state (load puzzle / reset grid)
      const nextStateId = (props?.sync?.state_id != null) ? String(props.sync.state_id) : "";
      const prevStateId = (local && local.meta && local.meta.stateId != null) ? String(local.meta.stateId) : "";
      if (prevStateId && nextStateId && prevStateId !== nextStateId) {
        local = null;
        clientSeq = 0;
        latestSentSeq = 0;
      }

      // Ack handling: ignore stale server renders during fast typing
      const ack = props?.sync?.last_client_seq != null ? parseInt(props.sync.last_client_seq, 10) : 0;

      if (!local) {
        syncLocalFromProps(props);
      } else {
        // If server is caught up (or ahead), adopt canonical state.
        // If not caught up, keep local to avoid visual "rollback".
        if (ack >= latestSentSeq) {
          syncLocalFromProps(props);
        }
      }

      renderFromLocal(props);
      return;
    }
  });

  // Tell Streamlit we're ready
  postMessage("streamlit:componentReady", { apiVersion: 1 });
  postMessage("streamlit:componentReady", { apiVersion: 1, ready: true });

  setTimeout(setFrameHeight, 0);
})();