# Agent Instructions

## System Definition

This repository contains a local Flask web application for thermal comfort
index monitoring in animal production. The domain rules are based on the UNIP
master dissertation by Mariano Sergio Pacheco de Angelo and currently cover:

- ITU, ITUV and IGNU thermal comfort indexes.
- Species-specific index availability.
- Sensor simulation and automatic monitoring.
- Remote equipment control for fans and nebulizers.
- SQLite persistence for readings and chart history.

The main runtime is Python 3 + Flask. The frontend is plain HTML, CSS and
JavaScript, with Chart.js bundled locally.

## Engineering Priorities

Use software engineering practices that maximize performance, reliability and
stability:

- Keep domain formulas and thresholds centralized in `conforto_termico/thermal_indices.py`.
- Keep HTTP concerns in `conforto_termico/web.py`.
- Keep orchestration and stateful application behavior in `conforto_termico/services.py`.
- Keep persistence details in `conforto_termico/database.py`.
- Keep UI behavior in `conforto_termico/static/js/app.js`.
- Add tests for changes that affect calculations, persistence, sensor
  simulation, equipment control, automatic mode or public API responses.
- Prefer deterministic tests over timing-sensitive tests.
- Preserve backward-compatible JSON fields unless an API contract update is
  explicitly required.

## Recommended Patterns

Prefer patterns already present in the codebase:

- Service Layer for application use cases and orchestration.
- Strategy for replaceable behaviors, such as random sensor generation versus
  cooling-adjusted sensor generation.
- Repository-style functions for SQLite access in `database.py`.
- Small pure functions for formulas, validation and classification.
- Defensive copying when returning in-memory history or cached readings.

Use new abstractions only when they reduce real complexity or protect a clear
domain boundary. Do not add broad frameworks for small local behavior.

## Naming And Language Rules

The app is user-facing in Brazilian Portuguese.

Use accents only in text shown to users, for example labels, messages, email
body text and status text rendered in the UI or returned as user-facing API
messages.

Do not use accents in:

- File names.
- Directory names.
- Python module names.
- Class, function, method or variable names.
- JSON field names.
- HTML ids, CSS classes and data attributes.
- JavaScript identifiers.
- Test method names.
- Route names, query parameters and form/control names.
- Internal enum-like values or state-machine values.

Use ASCII identifiers and internal values such as `especie`, `indice`,
`historico`, `calculo`, `conforto`, `emergencia`, `intensidade`, `media`,
`maxima` and `leituras_consecutivas`.

## Stability Rules

- Do not change formulas, species mappings or limits without adding or
  updating tests that cite the expected behavior.
- Do not let a failure in charts, email or persistence hide a successful
  thermal calculation.
- Keep `/api/*` routes returning JSON errors.
- Keep automatic mode from overlapping cycles; one cycle must finish before
  the next one starts.
- When remote equipment is active, reductions in equipment intensity must not
  skip levels. A lower intensity level must be observed for the required
  number of consecutive readings before applying the reduction.
- If sensor values are missing for an index, that index must not be calculated
  unless it is the selected index, where normal validation errors should still
  be raised.

## Verification

Before finishing changes, run:

```powershell
.\.venv\Scripts\python -m unittest discover -v
```

If the virtual environment is unavailable, use:

```powershell
python -m unittest discover -v
```

For frontend or automatic-mode changes, also verify the running app locally at
`http://127.0.0.1:5000` when practical.
