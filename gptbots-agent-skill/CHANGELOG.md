# Changelog

## 2026-07-15

### Fixed

- **Variable node: success branch handle.** The success edge now emits
  `right{id}-variable_true` + `name:"_true"` instead of the bare
  `right{id}-variable` + `name:null`. The bare handle does not anchor to the
  canvas "assignment successful" port, so the line rendered detached/floating
  and the port greyed out. `connect(var, dst)` now produces the correct handle
  automatically. (`build_gptbots_flowagent.py`)

- **`EDGE_DUP_HANDLE`: false positives on fan-out.** The check errored on any
  repeated `sourceHandle`, wrongly flagging legitimate parallel fan-out.
  FlowAgent explicitly supports one output port driving several edges to
  *different* targets. It now errors only on a genuinely duplicated edge — the
  same `sourceHandle` → same target. (`validate_gptbots_config.py`)

- **`BRANCH_EXCEPTION_EDGE`: false error.** A classifier's wired
  `branch_exception` edge was rejected outright. Real platform exports contain
  it (`name:"_exception"`, with `exceptionSwitch:true`), structurally identical
  to the LLM/Condition wired exception. It now only warns when the edge exists
  but `exceptionSwitch` is off, and the builder no longer blocks wiring it.
  (`validate_gptbots_config.py`, `build_gptbots_flowagent.py`)

### Added

- **`VAR_SUCCESS_HANDLE` check.** Catches the bare `variable` success handle.
  The handle parser drops the `_true` suffix, so the generic source-key check
  could not distinguish `variable` from `variable_true`.
  (`validate_gptbots_config.py`)

### Docs

- `references/flowagent-components.md`: documented the Variable node's
  Success/Failure handles at the node; corrected the "exactly one edge per
  output handle" and "the classifier has no `branch_exception` edge" claims.
  `SKILL.md` intentionally unchanged — node-level detail belongs in the
  component reference.
