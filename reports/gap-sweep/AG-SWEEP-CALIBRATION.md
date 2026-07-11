verdict: confirmed-shipped

# Scope of testimony

Pinned revision: `fb1535f2ee6d9526f4de25af71aa5d3c28afa6f2`.

This verdict confirms the closure language at
`specs/gaps/CALIBRATION_LAYER_GAP.md:4` for the repository's revised Phase C2
contract: apply-only normalization with frozen parameter sets, followed by
offline parameter-set fitting. It does **not** testify that the older design
sketch and its six literal acceptance criteria at lines 35-104 shipped
unchanged.

That scope distinction is supported by the repository itself:

- `specs/gaps/CALIBRATION_LAYER_GAP.md:4` labels the file shipped and retained
  as design rationale.
- `specs/gaps/V2_4A_SPINE.md:546-557` states the lifecycle convention: gap
  specs say *why*; phase spines provide implementation contracts and completion
  criteria.
- The applicable Phase C contract is `specs/gaps/V2_4C_SPINE.md:338-561`.
  It specifies frozen `CalibrationParamSet` objects, companion envelopes,
  three bounded transforms, quality/provenance preservation, mismatch refusal,
  and nine C2 acceptance criteria. Lines 575-582 prescribe apply first and
  fitting second; lines 610-622 explicitly defer CLI commands, live adaptation,
  cross-run trending, and automatic parameter selection.
- `specs/gaps/V2_4C_CALIBRATION_FITTING.md:3-15,130-154` identifies the fitting
  half as shipped and gives its acceptance criteria.
- `specs/gaps/GAP_BUILD_ORDER.md:32-38` records C2 apply + fit as shipped, and
  `docs/V2_STATUS.md:139-147` inventories all three implementation modules.
- Corroborating historical notes call this gap cleanly closeable and its
  design-rationale retention intentional:
  `working/next-session-debt-sweep.md:35-49` and
  `working/gap-backlog-triage-2026-06-10.md:108-110`.

# Named implementation evidence

- `src/governor/signals/calibration_layer.py:71-160` implements the frozen,
  versioned `CalibrationParamSet`; lines 166-226 validate signal identity,
  version, target field, method, and parameters; lines 232-322 implement
  `apply_calibration()` and emit a new normalized companion `SignalEnvelope`
  containing raw and normalized values, source hash, parameter-set hash,
  quality, and provenance.
- `src/governor/signals/calibration_methods.py:63-177` implements and registers
  `identity_clip`, `linear_minmax`, and `log_minmax`, with unit-interval clipping
  and deterministic mismatch errors.
- `src/governor/signals/calibration_fitting.py:70-163` defines the frozen fit
  specification; lines 269-382 perform deterministic, reason-coded sample
  selection; lines 388-467 fit all three methods; lines 482-555 emit the fit
  summary; lines 561-660 enforce sample sufficiency and produce a frozen
  parameter set.
- `src/governor/signals/__init__.py:84-107,198-217` exports the calibration and
  fitting APIs.
- Golden artifacts exist at
  `tests/fixtures/signals/envelope_calibrated_exposure_proxy.json`,
  `tests/fixtures/signals/envelope_calibrated_sigma_rate.json`,
  `tests/fixtures/signals/envelope_calibrated_unavailable.json`,
  `tests/fixtures/signals/calibration_fit_summary_success.json`, and
  `tests/fixtures/signals/calibration_fit_summary_failure.json`.
- Git history names the implementation commits:
  `bcfa564 Add C2 CALIBRATION_LAYER: apply-only calibration with frozen param sets`
  and
  `af5c187 Add C2 CALIBRATION_FITTING: offline param-set fitting from replay corpus`.

# Named test evidence

The targeted run covered all tests in
`tests/test_signals_calibration_layer.py` and
`tests/test_signals_calibration_fitting.py`, plus the two C-chain receipt
provenance tests. Representative test names directly tied to the revised C2
acceptance criteria are:

- `tests/test_signals_calibration_layer.py::TestApplyCalibration::test_identity_clip_on_bounded_signal`
- `tests/test_signals_calibration_layer.py::TestApplyCalibration::test_log_minmax_on_unbounded_signal`
- `tests/test_signals_calibration_layer.py::TestApplyCalibration::test_normalized_value_in_unit_range`
- `tests/test_signals_calibration_layer.py::TestCompanionEnvelopeShape::test_values_has_required_keys`
- `tests/test_signals_calibration_layer.py::TestQualityPropagation::test_quality_never_upgraded`
- `tests/test_signals_calibration_layer.py::TestMissingNotZero::test_none_stays_none`
- `tests/test_signals_calibration_layer.py::TestMissingNotZero::test_zero_gets_calibrated`
- `tests/test_signals_calibration_layer.py::TestRealSignalFixtures::test_exposure_proxy_log_minmax`
- `tests/test_signals_calibration_layer.py::TestRealSignalFixtures::test_sigma_rate_identity_clip`
- `tests/test_signals_calibration_fitting.py::TestFitLinearMinmax::test_insufficient_samples_no_param_set`
- `tests/test_signals_calibration_fitting.py::TestIntegrationWithApply::test_fit_identity_then_apply`
- `tests/test_signals_calibration_fitting.py::TestIntegrationWithApply::test_fit_linear_then_apply`
- `tests/test_signals_calibration_fitting.py::TestIntegrationWithApply::test_fit_log_then_apply`
- `tests/test_signals_provenance.py::TestReceiptIdPropagation::test_calibration_layer_propagates`
- `tests/test_signals_provenance.py::TestReceiptIdPropagation::test_full_chain_monotonic`

# Commands run and output

Revision:

```text
$ git rev-parse HEAD
fb1535f2ee6d9526f4de25af71aa5d3c28afa6f2
```

The implementation commits and all three modules are contained in the claimed
v2.5.0 repository tag:

```text
$ git merge-base --is-ancestor bcfa564 v2.5.0
(no stdout; exit 0)
$ git merge-base --is-ancestor af5c187 v2.5.0
(no stdout; exit 0)
$ git show v2.5.0:src/governor/signals/calibration_layer.py >/dev/null
(no stdout; exit 0)
$ git show v2.5.0:src/governor/signals/calibration_methods.py >/dev/null
(no stdout; exit 0)
$ git show v2.5.0:src/governor/signals/calibration_fitting.py >/dev/null
(no stdout; exit 0)
$ git show v2.5.0:tests/test_signals_calibration_layer.py >/dev/null
(no stdout; exit 0)
$ git show v2.5.0:tests/test_signals_calibration_fitting.py >/dev/null
(no stdout; exit 0)
```

Targeted tests were run without bytecode or pytest-cache writes:

```text
$ PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider tests/test_signals_calibration_layer.py tests/test_signals_calibration_fitting.py tests/test_signals_provenance.py::TestReceiptIdPropagation::test_calibration_layer_propagates tests/test_signals_provenance.py::TestReceiptIdPropagation::test_full_chain_monotonic -q
........................................................................ [ 36%]
........................................................................ [ 72%]
......................................................                   [100%]
198 passed in 1.21s
```

Searches for the older gap sketch's defining types and surfaces returned no
matches:

```text
$ rg -n 'CalibratedSignal|SignalBaseline|baseline_mean|baseline_std|minimum 50|sample_count.?[<>=]+.?50' src tests
(no output; exit 1)
$ rg -n 'calibration (status|compare|drift)|@.*calibration|def calibration|calibration_status|calibration_compare|calibration_drift' src tests
(no output; exit 1)
$ rg -n 'regime' src/governor/signals/calibration_layer.py src/governor/signals/calibration_methods.py src/governor/signals/calibration_fitting.py tests/test_signals_calibration_layer.py tests/test_signals_calibration_fitting.py
(no output; exit 1)
$ rg -n 'apply_calibration\(' src | rg -v 'def apply_calibration'
(no output; exit 1)
```

The pre-report worktree check was clean:

```text
$ git status --short --untracked-files=all
(no output; exit 0)
```

# What could not be verified

- The old gap body's specific architecture could not be verified and is absent
  from the calibration implementation: there is no `CalibratedSignal` or
  `SignalBaseline`, normal-CDF mapping, per-regime EWMA baseline store,
  baseline persistence, universal source-registration API, or calibration
  `status`/`compare`/`drift` CLI. There is likewise no evidence here for the
  proposed detector merge or per-dimension correlator handling.
- The old fixed trust/fail-safe rules did not ship under those semantics.
  `CalibrationFitSpec.min_sample_count` is configurable and defaults to `1` at
  `src/governor/signals/calibration_fitting.py:93`, rather than being fixed at
  50. Missing or unavailable input becomes `None` at
  `src/governor/signals/calibration_layer.py:259-268`; passing tests including
  `TestApplyCalibration::test_source_value_none` and
  `TestMissingNotZero::test_none_stays_none` confirm that behavior rather than
  the old proposal's `risk_score = 1.0`.
- No production caller of `apply_calibration()` was found under `src/` at this
  revision. Live runtime wiring therefore was not verified. This does not
  violate the revised Phase C contract, which is an offline, observe-only API,
  but it limits the testimony to the shipped library, fitting path, exports,
  fixtures, and tests.
- The full repository test suite was not run; only the 198 calibration and
  provenance tests above were executed. No installed package, deployed system,
  or external release artifact was tested; v2.5.0 was verified as a Git tag in
  this repository.
- The status word `shipped` is closure prose, not one of the normalized statuses
  listed in `specs/README.md:17-27,274-279`. This sweep verifies the prose claim
  but does not normalize it or edit the gap.
- The header's citation to `V2_4A_SPINE.md §8` establishes the design-rationale
  convention but that table names only Phase A gap files. The actual calibration
  implementation authority is `V2_4C_SPINE.md §3`; the literal precision of the
  header citation could not be confirmed.

Accordingly, the shipped claim is confirmed for the repository's documented
Phase C2 apply + fit scope. Reading the superseded lines 35-104 as still-binding
acceptance criteria would instead be contradicted by the pinned implementation;
the repository explicitly classifies those lines as retained rationale rather
than the completion contract.
