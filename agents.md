# Agent Instructions

## System Definition

This repository contains a local Flask web application for thermal comfort
index monitoring in animal production. The domain rules are based on the UNIP
master dissertation by Mariano Sergio Pacheco de Angelo and currently cover:

- ITU, ITUV and IGNU thermal comfort indexes.
- Species-specific index availability.
- Sensor simulation and automatic monitoring (single-station manual flow,
  "Principal" tab).
- Zones ("Zonas" tab): groups of Modbus-connected sensors, fans
  (ventiladores) and misters (nebulizadores), 0 to N of each per zone. The
  index calculation for a zone averages readings across all sensors that
  measure the same field, then drives that zone's own fan/mister state.
  This is a second, independent calculation path alongside the original
  manual/simulated flow -- both remain fully supported.
- Remote equipment control for fans and nebulizers, both for the single
  manual station and per-zone.
- SQLite persistence for readings, chart history, zones and equipment.

The main runtime is Python 3 + Flask. The frontend is plain HTML, CSS and
JavaScript, with Chart.js bundled locally. Modbus connectivity (TCP and
RTU/serial) is an optional dependency (`pymodbus`, see requirements.txt) --
the rest of the app works fully without it installed; only zone sensor
reads/actuator writes are affected (they return a clear "not connected"
state instead of raising).

## Engineering Priorities

Use software engineering practices that maximize performance, reliability and
stability:

- Keep domain formulas and thresholds centralized in `conforto_termico/thermal_indices.py`.
- Keep HTTP concerns in `conforto_termico/web.py`.
- Keep orchestration and stateful application behavior in `conforto_termico/services.py`
  (single-station manual/simulated flow) and `conforto_termico/zona_service.py`
  (per-zone Modbus flow) -- these are deliberately separate services; do not
  merge them into one class (see "Zonas Modbus" below for why).
- Keep persistence details in `conforto_termico/database.py`.
- Keep the Modbus TCP/RTU client abstraction in `conforto_termico/modbus_client.py`;
  nothing else in the codebase should import `pymodbus` directly.
- Keep UI behavior in `conforto_termico/static/js/app.js`.
- Add tests for changes that affect calculations, persistence, sensor
  simulation, equipment control, automatic mode, zones/Modbus, or public API
  responses.
- Prefer deterministic tests over timing-sensitive tests. Zone/Modbus tests
  must never depend on real hardware or real network reachability -- always
  fake/mock the Modbus client (see `tests/test_modbus_client.py`,
  `tests/test_zona_service.py`).
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

## Encoding And Mojibake Decision

The final repository policy is: all source, templates, stylesheets, scripts,
tests and documentation are UTF-8 without BOM.

Use real UTF-8 accents in Brazilian Portuguese text that is shown to users or
asserted as user-facing text in tests. Do not replace those strings with text
corrupted by an incorrect charset conversion, and do not convert normal text to
HTML entities just to work around a terminal display problem. HTML entities are
acceptable only when they are already part of a specific HTML escaping pattern
or when escaping is semantically useful in markup.

If a shell, PowerShell, test log or tool output displays readable Portuguese as
garbled text, treat it as a display/console decoding problem until proven
otherwise. Before editing files for encoding reasons, verify the file bytes by
reading them as UTF-8 and searching the decoded text for actual corrupted
sequences. Do not "fix" correctly encoded UTF-8 text because one terminal
rendered it incorrectly.

Recommended verification on Windows:

```powershell
$utf8 = [System.Text.UTF8Encoding]::new($false, $true)
$text = $utf8.GetString([System.IO.File]::ReadAllBytes("agents.md"))
$text.Contains("Configurações")
```

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

## Zonas Modbus

- Terminology: "zona" was kept as-is -- it already matches common industry
  usage for a climate-controlled area with its own sensors/actuators (e.g.
  commercial poultry/livestock controllers commonly call this a "zone").
  No need to rename it.
- **Fail-loud validation, on purpose.** `database._validar_zona` /
  `_validar_equipamento` REJECT invalid input with `ZonaInvalidaError`
  instead of silently falling back to a default, unlike
  `_sanitizar_configuracoes`. This is deliberate: a Modbus register
  address, unit ID, or connection setting identifies a specific physical
  device. Silently substituting a "safe default" here would mean reading
  or writing the WRONG real equipment, which is worse than a rejected
  request. Do not change this to a silent-sanitize pattern.
- **Averaging is the core requirement.** `ZonaService.ler_sensores` reads
  every sensor equipment in a zone via Modbus and averages readings that
  share the same `campo_medido` (e.g., two `tbs` sensors become one
  averaged `tbs` value) before calculating the index. A sensor that fails
  to respond is excluded from the average and reported in
  `sensores_com_falha`, but does not block the calculation unless it was
  the only sensor for a required field.
- **Per-zone equipment state.** `ZonaService` keeps one `Resfriamento`
  instance per `zona_id` (in-memory dict), so zones have fully independent
  intensity/hysteresis state -- one zone can be in "Perigo" while another
  is in "Conforto". This reuses the exact same `Resfriamento` class as the
  manual flow; do not fork the intensity/hysteresis logic.
- **Humidity-derived fields.** `zona_service._derivar_campos_calculaveis`
  derives `ur`/`tpo` from `tbs`+`tbu` (same psychrometric formulas as the
  manual flow) whenever the zone has no dedicated sensor for that field.
  Unlike the manual flow's "medido"/"calculado" toggle, this is always
  automatic for zones: sensor value wins if present, otherwise derive if
  possible. Altitude for this derivation comes from the global app config
  (`altitudeMetros`), not a per-zone field.
- **SMTP-like graceful degradation.** `modbus_client.py` never raises: a
  missing `pymodbus` install, an unreachable device, or a Modbus exception
  response all just produce `None` (read) / `False` (write) / `False`
  (connectivity test), the same resilience pattern already used for
  SMTP/email. Any new Modbus operation must follow this pattern.
- **Historical data survives zone deletion.** `leituras.zona_id` is
  `ON DELETE SET NULL` (not CASCADE) -- deleting a zone removes its
  `equipamentos` rows (CASCADE) but keeps previously recorded `leituras`
  rows, just without a zone reference. Do not change this to CASCADE.
- **Two independent calculation paths, on purpose.** `services.CalculoIctService`
  (manual/simulated, single station, `especie`+`indice` scoped) and
  `zona_service.ZonaService` (per-zone, Modbus-driven) are separate
  services that both end up writing to the same `leituras` table (the
  zone-scoped rows just also carry a `zona_id`). Do not try to unify them
  into one service -- they have different input sources (manual/simulated
  vs. averaged Modbus reads) and different equipment-state scopes (one
  global `Resfriamento` vs. one per zone).
- **Simulated Modbus mode.** `modbus_simulador.SimuladorModbusZonas`
  provides drop-in replacements for `modbus_client.ler_valor`/
  `escrever_valor`/`testar_conexao`, generating plausible readings by
  reusing `services.SensorSimuladoService` (one instance per zone, so the
  gradual-cooling behavior is independent per zone, same as
  `Resfriamento`). Which one `ZonaService` actually calls is decided PER
  CALL by `_em_modo_simulado()`, reading the persisted `modoSimuladoZonas`
  config flag (default `True`) -- not fixed at construction time. This is
  deliberate: it lets `web.py` wire one `ZonaService` instance for the
  whole app lifetime while the person freely flips real/simulated from the
  UI at any moment. `ZonaService.definir_simulador(...)` exists (instead of
  a constructor parameter) specifically to break a circular dependency: the
  simulator needs `zona_service.resfriador_da_zona` to know current cooling
  state, which only exists after `ZonaService` itself is constructed (see
  the wiring in `web.py`).
- **Seeding example zones.** `seed_zonas.py` (project root, not part of the
  running app) creates 5 example zones with realistic Modbus parameters
  for demonstration/testing. It's idempotent by default (does nothing if
  zones already exist; `--forcar` overrides). If you change
  `thermal_indices.CAMPOS_POR_INDICE` or add a species/index combination,
  keep this script's sensor sets covering whatever fields the configured
  índice actually needs -- a zone that can never calculate its own índice
  is a bad example, not a realistic one.
- **Per-zone automatic mode and charts (frontend only).** The Zonas tab has
  its own "modo automático" toggle (`cfg-zonas-auto`,
  `alternarModoAutomaticoZonas`/`cicloAutomaticoZonas` in app.js) that
  cycles through active zones SEQUENTIALLY (mirrors a real RS-485 bus:
  one device at a time), reusing the exact same non-overlapping-cycle
  pattern as the Principal tab's automatic mode (`autoZonasEmExecucao`/
  `autoZonasTimeoutId` mirror `autoEmExecucao`/`autoTimeoutId`). Each zone
  card renders its own Chart.js chart of that zone's calculated index over
  time (`atualizarGraficoZona`, fed by `/api/zonas/<id>/historico`) --
  replacing the single shared chart the Principal tab shows for one
  dataset. `cfg-zonas-simulado` persists to the `modoSimuladoZonas` config
  key through the same `coletarConfig`/`aplicarConfiguracoes` pipeline as
  every other config checkbox, even though it physically lives in the
  Zonas tab rather than Configurações.

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
