# QA Runner consumer contract v0.1

This contract lets QAWorkbench, Codex, Only Chat, and other AI clients consume the same runner and evidence semantics without sharing UI code or user credentials.

## Ownership

- The QA host owns target registration, run IDs, desktop sessions, profile roots, artifacts, report persistence, stop lifecycle, and user approvals.
- A consumer may request/list/report work only through a host adapter. It must not keep a separate process-local registry that can outlive the process or stop another consumer's target.
- `qa_runner.WindowsRunner` is currently a process-local implementation for QAWorkbench. It is not a cross-process service. A separate authenticated local job broker is required before another app can start or stop native sessions.

## Execution and approval

- Observe-only is the default. Starting a desktop run requires a user action in the QA host and an explicitly selected registered disposable target.
- The model cannot approve its own run or UI actions. Each action remains in the host's per-step review flow; each external/provider request requires separate user approval.
- Consumers do not receive click/type tools. Only the host's exact run-owned UIA adapter may execute reviewed safe actions.
- Stop is restricted to the run ID and process Job Object created by the same host process. Process/session ownership must be verified before stopping.

## Report semantics

- `observed` means the host obtained the evidence it claims in `checks`; it does not imply every requested surface was covered.
- `partial` means a required surface such as exact pixels, UIA, or a window was unavailable. `uncovered` evidence is never a visual pass.
- Reports separate target/session identity, checks, findings, reviewed actions, artifacts, and unverified items. Consumers must preserve that distinction and must not promote AI advice into execution evidence.
- Do not forward screenshots, field values, captured text, absolute paths, tokens, or credentials by default. A consumer must use an explicit, user-approved sharing flow for any such content.

## Example consumer status

- QAWorkbench is the first consumer. Its UI owns isolated browser/native execution, approvals and report persistence.
- Its Codex stdio adapter can list targets/reports, read sanitized summaries and create an observe-only pending request. It cannot start or approve a run. A user approves/rejects that request in the host UI; desktop runs require the separate isolation checkbox.
- An Only Chat adapter is not part of this package. A host can map the same request/report lifecycle into an in-app QA room after it has a broker that authenticates consumers and preserves the host's explicit user approval boundary.
