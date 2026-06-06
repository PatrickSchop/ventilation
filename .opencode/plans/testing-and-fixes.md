# Test Foundation + Review Fixes — Phased Execution Plan

## Goal
Build a `pytest` suite that captures correct current behavior (must stay green) and expresses each known review bug as an `xfail(strict=True)` test asserting the **intended correct** behavior. When a fix lands, the strict-xfail flips the suite red ("unexpectedly passed"), forcing removal of the marker — every behavioral change is caught in both directions; no test encodes buggy behavior as correct.

## Framework & Command
- `pytest` + stdlib `unittest.mock`.
- `requirements-dev.txt`: `pytest`, `paho-mqtt`. `smbus2` stubbed (Linux-only), not installed.
- `pytest.ini`: `testpaths=tests`, `python_files=test_*.py`, `addopts=-q -ra`, marker registrations.
- Commands: install `python -m pip install -r requirements-dev.txt`; run `python -m pytest`.
- OpenCode exposure: `AGENTS.md` "Testing" section **and** `.opencode/command/test.md` slash command.

## Enabling refactorings (behavior-preserving; defaults keep prod identical)
- **R1 `Mqtt.py`:** `clientFactory=None` defaulting to `lambda: mqtt.Client()`.
- **R2 `Scd41.py`:** `bus=None` defaulting to `SMBus(1)`.
- **R3 `Clock` helper:** `Clock.now()` indirection in `Timer`, `Mqtt`, `EnvironmentMonitor`, `Ventilator`, `HomeAssistant`.
- **R4 `shouldPublish`:** extract `(dValue, dTime, publishInterval, forcePublishInterval) -> bool` (preserves current `.seconds`).
- **R5:** do not import `VentilationService.py` in tests.

## Test infrastructure
- `tests/stubs/smbus2.py` — fake `SMBus` (records `i2c_rdwr`, returns canned bytes) + `i2c_msg.read/write`.
- `tests/conftest.py` — repo root + `tests/stubs` on `sys.path`; autouse reset of `ExternalDemand._states` + `Configuration`; fixtures: `frozen_clock`, `mock_mqtt_client`, `logger_spy`.

## Global execution rules
1. Touch only files listed in the phase.
2. Never weaken/delete a test to make it pass.
3. `xfail(strict=True)` tests are expected to fail until the phase assigned to that finding removes the marker.
4. Run the phase Gate; must pass before reporting done.
5. **After Gate passes, commit only files this phase changed** (`git add <explicit paths>`; no `-A`; do not commit `config.json` credential changes; do not push).
6. `py_compile` after any refactor.

## H5 scope (locked)
- **In scope:** guard raw I²C ops in `Scd41._rdwr`/`_readRdwrResponse` and `EnvironmentMonitor._resetScd41` with try/except → log + treat as stale. Ensure `_resetScd41` reschedule survives a throwing `stopPeriodicMeasurement`.
- **Out of scope:** do **not** change the `delay=0.2` or `delay=120` timing constants in `EnvironmentMonitor.py:118-119`. Add a test asserting that a throwing `stopPeriodicMeasurement` still results in `startPeriodicMeasurement` being scheduled, but assert delay value `120` (current) only.

## Findings → phase mapping
- C1, C2 → P5 · H2 → P6 · H3, H4, H5 → P7 · M2, M3, M5, M6 → P8 · L4, L5 → P9 · L1, L2, L3, L6, M4 → P10 · M1 (bounded, no-op) noted, no action.

## Phase Gate definitions
- **Behavior-preserving phases (2,3):** `py_compile` + existing test set staying green with the **same** xfail/pass counts.
- **Baseline gate (end of P4):** full suite green; exactly **7 strict-xfail** reported as `xfail` (M5, M6, C2×2, H2, H4, L5); **0 xpass**.
- **Final gate (end of P11):** `grep` finds zero `xfail` markers; full suite green; `py_compile` clean on every module imported by `VentilationService.py`.

---

## Phases (sequential)

### Phase 0 — Scaffolding (no production code touched)
**Create:** `requirements-dev.txt`, `pytest.ini`, `tests/__init__.py`, `tests/stubs/smbus2.py`, `tests/conftest.py`, `AGENTS.md` (Testing section), `.opencode/command/test.md`. Install deps.
**Gate:** `python -m pytest` exits 0 (collects 0 tests, no import errors); `python -c "import smbus2"` resolves to the stub.
**Commit:** `chore(test): add pytest scaffolding, smbus2 stub, /test command`

### Phase 1 — Pure-logic tests
**Create tests, all green:** `test_mqtt_comparers.py`, `test_ventilator_pure.py` (`_mapValue`, `max` aggregation, clamp, itho), `test_home_assistant_pure.py` (`_generate_entity_id`, `object_id`), `test_configuration.py` (type inference, dotted getValue, missing-file silent, round-trip).
**Gate:** targeted `python -m pytest` on these four files → all pass.
**Commit:** `test: lock pure-logic behavior (comparers, demand, entity id, config)`

### Phase 2 — Refactor R3: Clock helper
**Create `Clock.py`** with `Clock.now()`; replace all 23 `datetime.now()` call sites (Timer×4, Mqtt×8, EnvironmentMonitor×5, Ventilator×4, HomeAssistant×2). Update `conftest.py` `frozen_clock` to monkeypatch `Clock.now`.
**Gate:** `py_compile` on the 5 files + `python -m pytest` (Phase 1 tests still green).
**Commit:** `refactor: introduce Clock.now() seam (behavior-preserving)`

### Phase 3 — Refactor R1/R2/R4
**R1:** `MqttConnection.__init__(..., clientFactory=None)`. **R2:** `Scd41.__init__(..., bus=None)`. **R4:** extract `shouldPublish`; `__publishTopic` calls it (preserve current `.seconds` boolean).
**Gate:** `py_compile` on `Mqtt.py`/`Scd41.py` + full `python -m pytest`.
**Commit:** `refactor: inject mqtt client + smbus, extract shouldPublish`

### Phase 4 — Event-loop/safety-net/MQTT/sensor/HA tests
**Create (green unless marked xfail-strict):**
- `test_action_runner.py` — arity 0–4; exception caught, not propagated.
- `test_timer.py` — scheduling/precedence/cancellation (green); **xfail-strict M5** independent default tokens; **xfail-strict M6** loop survives raw exception.
- `test_mqtt_connection.py` — wiring, prefixing, on_connect, routing, ping echo, modulo id, `shouldPublish` integration (green); **xfail-strict C2** reset when disconnected+stale; **xfail-strict C2** reset when connected+stale; **xfail-strict H2** no double subscribe/callback on reset.
- `test_average.py` — average/reliability/eviction/stale-clear (green).
- `test_environment_monitor.py` — measurement JSON, flat-line, stale escalation 3/10, reset scheduling (green).
- `test_home_assistant_register.py` — register config topics, status→register (green).
- `test_ventilator_external.py` — state mapping/validation (green); **xfail-strict H4** per-button routing with `count>1`.
- Append to `test_configuration.py` — **xfail-strict L5** malformed JSON handled gracefully.
**Gate:** full suite green; exactly **7 xfail / 0 xpass** reported.
**Commit:** `test: lock loop/safety-net/mqtt/sensor behavior + strict-xfail bug specs`

### Phase 5 — Fix C1 + C2
- **C1:** `__createClient` → guard with try/except log; `connect_async`; guard old-client teardown with `self.__client is not None`; assign `self.__client = client` even on connect failure.
- **C2:** in `__healthCheck`, move `elapsed > failureThreshold → __aggressiveReset(); return` **above** the `is_connected()` early return. Update `__lastSuccessfulCommunication` in `__on_connect` and `__on_message`.
- Remove the two **C2 xfail markers**.
**Gate:** `python -m pytest` green; C2 tests pass (no xpass).
**Commit:** `fix(C1,C2): crash-safe client setup; health-check reset while disconnected`

### Phase 6 — Fix H2
Delete the manual re-subscribe + callback loop in `__aggressiveReset` (rely on async `__on_connect`). Remove the **H2 xfail marker**.
**Gate:** full suite green.
**Commit:** `fix(H2): stop double re-subscribe/callback on aggressive reset`

### Phase 7 — Fix H3 + H4 + H5
- **H3:** `mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)`. Add test asserting the factory default constructs with VERSION1.
- **H4:** `lambda v, i=i:` closure fix in `ExternalDemand`. Remove **H4 xfail marker**.
- **H5:** guard raw I²C ops; ensure `_resetScd41` reschedule survives a throwing `stopPeriodicMeasurement`. **Do NOT change `delay=0.2` / `delay=120`.** Add test asserting a throwing `stopPeriodicMeasurement` still results in `startPeriodicMeasurement` being scheduled (delay 120, the current value).
**Gate:** full suite green; H4 test passes.
**Commit:** `fix(H3,H4,H5): pin paho API; closure binding; I2C crash-safety`

### Phase 8 — Fix M2 + M3 + M5 + M6
- **M2:** `shouldPublish` + call sites use `.total_seconds()`; update tests.
- **M3:** `objectId = objectId.lstrip("_")`; update test.
- **M5:** `Timer.run(cancellationToken=None)` → create inside. Remove **M5 xfail marker**.
- **M6:** wrap `Timer.run` loop body in try/except → `Logger.error`. Remove **M6 xfail marker**.
**Gate:** full suite green; M5/M6 tests pass.
**Commit:** `fix(M2,M3,M5,M6): total_seconds; object_id lstrip; loop backstop; token`

### Phase 9 — Fix L4 + L5
- **L4:** guard `SMBus(1)` construction (lazy or try/except with clear log).
- **L5:** `Configuration.load` also catches `json.JSONDecodeError` (log + continue). Remove **L5 xfail marker**.
**Gate:** full suite green; L5 test passes.
**Commit:** `fix(L4,L5): guard SMBus init and malformed config json`

### Phase 10 — Fix L1/L2/L3/L6 + M4
- **L3:** `Logger` absolute log path + try/except around handler setup.
- **L2/L1:** route hot-path `print` to `Logger` where appropriate (minimal).
- **L6:** remove unused `__outstandingPings` or wire it (default: remove unless a test needs it).
- **M4:** delete dead `MQTT_SERVER/USER/PASSWORD` constants in `VentilationService.py`. Note (do not rotate) the plaintext creds in `config.json`.
**Gate:** full suite green; `py_compile` on all touched files.
**Commit:** `fix(L1,L2,L3,L6,M4): logging hardening; cleanup dead code`

### Phase 11 — Final integration
Confirm zero remaining `xfail` markers (`grep`). Verify `mqtt-test.py` still imports after API changes. Confirm `AGENTS.md` Testing section reflects final command.
**Gate:** `python -m pytest` fully green, **0 xfail / 0 xpass**; `python -m py_compile` on every module imported by `VentilationService.py`.
**Commit:** `chore: final integration, remove all xfail markers, verify clean`

---

## Dependency graph
`0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11` (strictly sequential; each Gate must pass before the next phase starts).
