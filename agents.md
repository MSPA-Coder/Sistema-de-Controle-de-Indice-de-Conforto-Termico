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
- Shared config dicts in `thermal_indices.py` (`LIMITES`, `INDICES_POR_ESPECIE`,
  `CAMPOS_POR_INDICE`, etc.) are frozen with `MappingProxyType` via the
  `_congelar` helper. Do not work around this by unfreezing them; add new
  entries by editing the literal dict before it is frozen. If you add a new
  such dict, freeze it too and make sure `web.py`'s `ProvedorJSON` is still
  the app's `app.json` provider (it is what makes `jsonify`/`tojson` able to
  serialize `MappingProxyType`).
- `database.salvar_configuracoes` / `obter_configuracoes` always pass values
  through `_sanitizar_configuracoes`. Any new config key needs a matching
  coercion rule there (`_coagir_booleano`, `_coagir_numero`, `_coagir_enum`,
  or a dedicated validator like `_coagir_email`) with a safe fallback to
  `CONFIGURACOES_PADRAO` on invalid input -- never let a malformed config
  value propagate unchecked into equipment control or email sending.
- `especie`/`indice` are now persisted config keys (moved from the
  Principal tab's selector card into a "Espécie e índice" card in
  Configurações). They are validated together, not independently:
  `_coagir_indice(valor, especie, padrao)` needs the already-resolved
  `especie` to know which indices are even valid (ITUV only exists for
  frangos, for example). If you add a new species/index combination,
  update `thermal_indices.INDICES_POR_ESPECIE` first -- the config
  validator reads from there, not from a separate hardcoded list.
- `smtpHost`/`smtpPorta`/`smtpUsuario`/`smtpSenha` are persisted config keys
  backing the "E-mail" card in Configurações (same four values documented
  in the README as `SMTP_*` environment variables). `smtpSenha` is
  write-only end to end:
  - `web._configuracoes_publicas` always returns `smtpSenha: ""` to any
    HTTP caller (GET or POST), plus a `smtpSenhaConfigurada: bool` flag.
    Never remove this masking or return the raw value over HTTP.
  - `database.salvar_configuracoes` treats a blank incoming `smtpSenha` as
    "leave the current one alone" (fetches the existing value before
    sanitizing), not as "clear it". This matters because the front-end
    always POSTs a full config object, and its password field is always
    blank unless the user just typed a new one.
  - `services.CalculoIctService._smtp_config_atual` fetches SMTP
    credentials directly from `obter_configuracoes` (server-side, real
    values), never from the client-supplied `config` in `/api/calcular` --
    that `config` always carries a blank `smtpSenha`, so reading the
    secret from it would silently break real email sending.
  - `models.Email.enviar(smtp_config=None)` prefers `smtp_config` fields
    when present/non-empty, falling back to the `SMTP_*` environment
    variables per field. Keep both paths working; some deployments may
    still rely purely on environment variables.

## Security & Configuration

- Server runtime settings (`debug`, `host`, `port`, `threaded`,
  `max_content_length`) are centralized in `web.AppConfig`, populated via
  `AppConfig.from_env()`. Do not read `os.environ` ad hoc elsewhere in
  `web.py` for these; add a field to `AppConfig` instead.
- Environment variables (all optional, all default to safe local values):
  `CONFORTO_DEBUG` (default `0`/off), `CONFORTO_HOST` (default
  `127.0.0.1`), `CONFORTO_PORT` (default `5000`), `CONFORTO_THREADED`
  (default `1`/on), `CONFORTO_MAX_CONTENT_LENGTH` (default `1000000`
  bytes).
- `debug=True` enables the Werkzeug interactive debugger, which can execute
  arbitrary code from the browser. Never change the default of
  `CONFORTO_DEBUG` to on; a developer who wants it opts in locally via the
  environment variable.
- `/api/*` responses never include raw exception text (see
  `MENSAGEM_ERRO_INTERNO` in `web.py`). Full details always go to
  `app.logger.exception` server-side. Keep this split when adding new
  error handling.
- Any config value that ends up inside an SMTP header (currently
  `emailDestino`) must be validated to reject whitespace/control
  characters before use, both where it is persisted (`database.py`) and
  again where it is actually used to build the message (`models.Email`).
  Treat this as two independent checks, not one shared one -- see
  `test_models.py` / `test_database.py` for the expected behavior.

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
