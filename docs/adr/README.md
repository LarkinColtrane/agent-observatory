# Architecture Decision Records

One file per decision: `NNNN-kebab-title.md`, numbered sequentially. Start from
`0000-template.md`. ADRs are append-only: to change a decision, write a new
ADR that supersedes it and update the old one's status line. Every ADR file
must be listed here (the governance checker enforces both directions).

| ADR | Title | Status |
|---|---|---|
| [0001](0001-adopt-development-operating-system.md) | Adopt the development operating system before product work | accepted (P1 clause superseded by 0003) |
| [0002](0002-phase-1-technology-stack.md) | Phase 1 technology stack — modular monolith | accepted |
| [0003](0003-phase-order-and-event-protocol-deferral.md) | Phase order and deferral of the universal event protocol | accepted |
| [0005](0005-phase-1-foundation-contract.md) | Phase 1 engineering-foundation contract | accepted (frozen at tag `contract-phase1-foundation-v1.0.0`) |
| [0004](0004-dedicated-private-repository.md) | Dedicated private repository | accepted (implemented; protection pending, TD-004) |
| [0006](0006-dependency-security-patch-exception.md) | Security-patch exception to the dependency age cutoff | accepted |
| [0007](0007-typed-usage-telemetry-in-logs.md) | Typed usage telemetry survives log redaction (repays TD-022) | accepted |
| [0008](0008-universal-event-protocol.md) | Universal agent event protocol v1 (contract `event-protocol`) | accepted (approved; frozen at the end of P2) |
