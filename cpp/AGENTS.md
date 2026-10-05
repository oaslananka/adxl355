# C++ Wrapper Instructions

These instructions apply to `cpp/**` and supplement the root instructions.

C++ is a thin wrapper over the authoritative C core.

- Do not duplicate register constants, conversion formulas, lifecycle logic, or transport state machines in C++.
- `Device` owns its `BusInterface` and maps stable C failures to typed exceptions.
- `NoexceptDevice` borrows caller-owned transport, stays non-copyable/non-movable, performs no dynamic allocation, and returns `Status`/`Result<T>`.
- Preserve the exception-free build with exceptions and RTTI disabled.
- C++ feature coverage is not automatically equal to C/Python; update the root matrix only for implemented/tested methods.

Keep C and C++ tests/package-install behavior green together.
