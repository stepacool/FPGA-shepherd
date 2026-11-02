# Broken example: unconstrained IO

`led[*]` pins are missing from the `.cst`. A real `shepherd build` fails in place-and-route;
VerifyAgent should report cause/fix without needing AI.

For offline tests, feed `tests/fixtures/apio/build_pnr_unconstrained.log` to `shepherd explain`.
