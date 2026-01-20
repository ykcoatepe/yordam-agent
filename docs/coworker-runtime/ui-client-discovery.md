# UI Client Discovery (Optional)
Last updated: 2026-01-20

## Objective
Decide whether a UI client (menubar or lightweight window) is justified for runtime
management beyond the CLI.

## Candidate Options
- **SwiftUI menubar app**: native status, quick approve/cancel, lightweight.
- **Web UI (local)**: cross-platform, heavier footprint, requires local server.
- **Stay CLI-only**: lowest risk, fastest iteration.

## Decision Criteria
- Frequency of approvals per day.
- Need for background visibility of task state.
- User tolerance for CLI + LaunchAgent workflow.
- Support burden (install, updates, OS permissions).

## Discovery Plan
1) Interview 3-5 CLI power users.
2) Measure approval latency and drop-offs.
3) Prototype low-fi menubar mock (no runtime integration).
4) Re-evaluate against criteria.

## Recommendation (current)
Defer UI until approval volume and latency justify the added surface area. Revisit
after runtime usage stabilizes.
