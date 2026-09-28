"""Live-session control: who holds the session, guarded automation, and human-in-the-loop handoff.

- `lease`       LeaseManager: holder in {automation, human, nobody}, audited transitions
- `guarded`     GuardedSurface: automation acts only while it holds the lease and policy allows
- `board`       InterventionBoard: open/resolved interventions and captured human actions
- `human_input` HumanInputChannel: lease-checked operator input injected into the SAME session
- `escalation`  ConsoleEscalator / ScriptedEscalator implementing the core Escalator port
"""
