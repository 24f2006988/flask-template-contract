# flask-template-contract

An offline, deterministic static checker for variables passed by Flask routes
to Jinja templates. Frontier Buildathon 2026, Track 02.

## Status

Scaffold only. No analyzer or working CLI is implemented yet. The next
checkpoint defines the data contracts and fixture harness; a thin end-to-end
slice follows only after approval.

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

## Verify like the judges

```sh
docker build -t flask-template-contract . && docker run --rm --network none flask-template-contract python -m pytest -q
```

The build installs dependencies; container execution requires no network and
does not sync or download anything. Docker has not yet been verified in the
development sandbox because Docker is unavailable there.

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
