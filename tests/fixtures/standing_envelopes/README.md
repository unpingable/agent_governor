# Standing-class envelope fixtures

Frozen JSON corpus exercising the `StandingReceipt.from_dict`
deserialization path and (where applicable) the schema runtime
pre-pass.

## Layout

- `good/` — envelopes that must round-trip cleanly. Modifying one of
  these without intent is a regression.
- `bad/<violation_code>.json` — envelopes that must be rejected with
  the named violation code. Adding a new file here is the cheapest
  way to lock in a typed-rejection guarantee.

## Why fixtures, not inline literals

Inline test fixtures drift with whoever last touched the test file.
A frozen on-disk corpus is anti-regression scar tissue:

- Each fixture is a real bytes-on-disk artifact a hostile producer
  could send across a process boundary.
- The same fixture exercises the same `from_dict` code path every run.
- New rejection cases land as one new JSON file plus one parametrize
  row, not as bespoke setup per test.

## Naming convention

`bad/<violation_code>.json` where `<violation_code>` is the lowercase
`ViolationCode.value` the fixture should produce. If a fixture
legitimately produces multiple codes, name it after the one whose
absence would mean the schema discipline failed.
