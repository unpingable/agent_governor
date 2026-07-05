# Status — nightshift-functional-mvp

Card ratified 2026-07-05. Gap assessment done (65% of lane exists; 6+1 packets).
NS-0 DONE (2026-07-05): the pin threads end-to-end — maude `run <plan.md>
--model X` (maude side, tests+refusal path) -> runtime.session.create
`harness_args` (strings-only, fail-closed; AG `f51e866`) ->
SessionRecord -> LaunchConfig.args -> claude CLI argv (adapter already
extended cmd). Model choice = operator's run-time spend decision, never
plan-envelope content. Both suites green.
NS-1..6 queued as maude governed plans (specimens/ns-*/, to be authored).
Operator acts pending: queue latches + plan promotions per wave.
