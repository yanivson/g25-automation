# Project rules

This project builds a fully automated G25 analysis pipeline around a local clone of the Vahaduo browser engine.

## Non-negotiable constraints

- No manual edits to generated source panels
- Raw data files are immutable
- All transformations must be deterministic and reproducible
- Do not automate the public hosted site as the primary execution path
- Use the local cloned Vahaduo page as the engine
- Use Playwright only as a thin local wrapper
- Prefer direct JS evaluation over fragile selector-driven UI flows
- AI may explain results, but must not drive optimization logic

## Delivery style

- Work in plan mode first
- Implement in small modules
- Add tests with each stable unit
- Keep parsing and optimization logic separate
- Keep browser-specific code isolated under engine/

## Preferred sequence

1. scaffold project
2. create local Vahaduo runner
3. validate one target + one source panel run
4. build preprocessing
5. build deterministic optimizer
6. add run logging
7. add optional interpretation layer

## Report generation

All report rules, section layout, chart specs, design system, and CLI details live in **`report/CLAUDE.md`**.
Do not duplicate them here — `report/CLAUDE.md` is the authoritative source.