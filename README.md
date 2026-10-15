# flask-template-contract

An offline, deterministic static checker for variables passed by Flask routes
to Jinja templates. Frontier Buildathon 2026, Track 02.

## Status

Steps 1–2 plus the first thin end-to-end slice are implemented. The thin slice
statically finds literal `render_template` calls, compares simple Jinja reads,
and reports unsupported dependencies conservatively. Deep scope and data-flow
analysis is not implemented yet.

See [docs/analysis-contract.md](docs/analysis-contract.md) for approved semantics,
diagnostic codes, future fixture inventory, and explicitly deferred features.

## Thin-slice CLI

```sh
flask-template-contract path/to/flask-project
flask-template-contract path/to/flask-project --format json
flask-template-contract path/to/flask-project --strict
```

The checker never imports or runs the target application. Literal template
names, explicit keyword arguments, simple Jinja free reads, Flask's built-in
globals, and the assumed `current_user`/`csrf_token` globals are supported in
this slice. Dynamic template names, `**kwargs`, dependency directives, and
context processors are labelled CAN'T VERIFY. Warnings fail only with
`--strict`; CAN'T VERIFY never changes the exit code.

## Setup

Use Python **3.14.8** and uv **0.13.1**. With Python 3.14.8 installed, bootstrap
uv locally (not globally) and prepare the project from this repository:

```sh
python3.14 -m venv .tools
.tools/bin/python -m pip install uv==0.13.1
export PATH="$PWD/.tools/bin:$PATH"
uv sync --locked
```

On Windows, use `.tools\Scripts\python.exe` and add `.tools\Scripts` to PATH
instead. Dependencies live in `.venv`; `.tools` is an ignored tool environment.
No Flask app is imported, no templates are rendered, and no secrets are needed.

## Test

After setup, the single test command is `python -m pytest -q` with `.venv`
activated. The equivalent explicit offline invocation is:

```sh
uv run --offline --no-sync python -m pytest -q
```

On Linux with namespace privileges, additionally run:

```sh
unshare -rn uv run --offline --no-sync python -m pytest -q
```

## Verify like the judges

```sh
docker build -t flask-template-contract . && docker run --rm --network none flask-template-contract python -m pytest -q
```

The build installs dependencies; container execution requires no network and
does not sync or download anything. This exact command was verified on a real
Docker host running Windows 11 with Docker Desktop and the WSL 2 backend:

```text
75 passed in 0.14s
```

The Docker build first installs locked dependencies (including Hatchling), then
builds a non-editable package with build isolation disabled so the locked backend
environment is reused. It uses no host virtual environment or external files.
The Python image tag was confirmed in Docker Hub's public tag API. Image tags
are version-pinned, not digest-pinned. The verified host needed no compiler or
other extra system package.

## Run and deploy

The checker CLI is not available at this checkpoint. Do not use this scaffold
as a completed checker. Docker currently defaults to running the tests, and
the judge command can override CMD without an ENTRYPOINT conflict.

## Planned semantics

Errors fail with exit 1. Warnings fail only under `--strict`. CAN'T VERIFY
never changes the exit code, including under strict mode; it marks analysis
incomplete. Exit 2 is reserved for tool/usage failure, not per-file problems.

## License

MIT; see [LICENSE](LICENSE).
