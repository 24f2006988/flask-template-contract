# Benchmark results

The benchmark selection contains 15 public repositories pinned in
`benchmarks/repos.toml`. The runner cloned each pinned commit into the ignored
`benchmarks/.cache/`, ran the JSON CLI, and saved one result under
`benchmarks/results/`. It is not part of pytest or the Docker test command.

## Precision

| Run | FTC001 TRUE | FTC001 false positive | FTC001 unsure | FTC001 precision | FTC002 TRUE | FTC002 false positive | FTC002 unsure | FTC002 precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Before fixes | 72 | 9 | 0 | 88.9% | 0 | 0 | 0 | N/A |
| After fixes | 72 | 0 | 0 | 100.0% | 0 | 0 | 0 | N/A |

Precision is TRUE / (TRUE + FALSE POSITIVE); UNSURE is reported separately.
The before-fix FTC001 false positives were Flask-Babel's `_` global in
`frostming/Flog`. The dmaslov truthiness findings are counted TRUE because the
frozen v1 contract deliberately treats `if x` as a required read.

## Findings and examples

Before the fix there were 81 FTC001 findings and no FTC002 findings. After the
fix there are 72 FTC001 findings and no FTC002 findings. The nine removed
FTC001 findings were replaced by scoped FTC110 uncertainty for unsupported
extension customization.

Two concrete real-bug examples under the contract are dmaslov/flask-blog's
missing `error`/`error_type` values at `templates/index.html:25-48` for the
`add_user` and `edit_user` render calls in `web.py:244` and `web.py:251`, and
the missing `pagination` value at `templates/index.html:52-63` for multiple
render calls in `web.py`. These are required reads under v1 even when ordinary
Jinja falsey behavior makes the page render without an exception.

## Benchmark inventory

See `benchmarks/results/summary.md` for the per-repository templates, render
sites, errors, warnings, can’t-verify count, and runtime table. The benchmark
runner emitted two third-party Python SyntaxWarnings while scanning source; it
did not import or execute those applications.
