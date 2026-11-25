# Isolated environment infrastructure

An additive, parameterized root for the new `onolys-staging` and `onolys-eval` projects.
Production remains in the existing `infra/` root/state. No migration is automatic.

See [setup, imports, state protection and rollout dependencies](../../docs/implementation/isolated-environments.md).

- `examples/`: versioned staging/eval variables and backends, plus explicitly legacy production references.
- `bootstrap/`: reviewed state-bucket creation, using separate administrative state.
- `tests/`: offline plans with mocked providers.

Do not run a clean apply against existing production or use its backend for this root.
