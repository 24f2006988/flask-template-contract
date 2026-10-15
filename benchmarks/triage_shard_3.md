# Triage shard 3

Pinned repositories: `miguelgrinberg/flask-celery-example`, `gouthambs/Flask-Blogging`, `dmaslov/flask-blog`, `DogukanUrker/FlaskBlog`, and `frostming/Flog`.

## Summary

| Repository | FTC001 | FTC002 | TRUE | FALSE POSITIVE | UNSURE |
|---|---:|---:|---:|---:|---:|
| miguelgrinberg/flask-celery-example | 0 | 0 | 0 | 0 | 0 |
| gouthambs/Flask-Blogging | 0 | 0 | 0 | 0 | 0 |
| dmaslov/flask-blog | 72 | 0 | 0 | 72 | 0 |
| DogukanUrker/FlaskBlog | 0 | 0 | 0 | 0 | 0 |
| frostming/Flog | 9 | 0 | 0 | 9 | 0 |
| **Total** | **81** | **0** | **0** | **81** | **0** |

## Findings

### `miguelgrinberg/flask-celery-example`

No FTC001/FTC002 findings (0 total).

### `gouthambs/Flask-Blogging`

No FTC001/FTC002 findings (0 total).

### `dmaslov/flask-blog`

All 72 findings are **FALSE POSITIVE**. They are inherited `index.html` reads guarded by Jinja `if` conditions, and undefined Jinja values are falsey rather than render failures:

- 36 `error`/`error_type` findings: `templates/add_user.html:25-47` → `web.py:244` and `templates/edit_user.html:26-57` → `web.py:251`; each use is inside `{% if error and ... %}` and therefore safely handles omission (the result also reports the repeated `edit_user.html:53-54` reads).
- 36 `pagination` findings (including duplicate dependency-path reports): inherited `templates/index.html:52-63` → `web.py:53`, `web.py:146`, `web.py:175`, `web.py:237`, and `web.py:244/251`; the whole pagination block is guarded by `{% if pagination and ... %}`, so omitted pagination is intentionally supported.

The template line in the result JSON is the inherited location `templates/index.html:25-63` for these reports; the concrete variable reads are in the child templates at the lines cited above.

### `DogukanUrker/FlaskBlog`

No FTC001/FTC002 findings (0 total).

### `frostming/Flog`

All 9 findings are **FALSE POSITIVE**. The `_` function is supplied by Flask-Babel's Jinja integration when `Babel(app)` is initialized at `flaskblog/app.py:25`; the template reads therefore do not require a render-call keyword:

- 1 finding: `flaskblog/templates/404.html:538` → `flaskblog/views.py:98` (`render_template("404.html")`).
- 8 findings (including duplicate inherited-template reports): `flaskblog/templates/mail/layout.html:2,10,16,50` → `flaskblog/tasks.py:65-67` (`new_reply.html`) and `flaskblog/tasks.py:86-88` (`new_comment.html`). The child templates also use `_` at `mail/new_reply.html:2,16` and `mail/new_comment.html:2,10`; all are covered by Flask-Babel's global.
