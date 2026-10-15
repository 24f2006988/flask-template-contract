# Benchmark triage

The triage input was the first benchmark run, before the unsupported-extension
fix. All 15 repositories were checked. The worker reports are retained in
`triage_shard_1.md`, `triage_shard_2.md`, and `triage_shard_3.md`.

The final labels below are lead-adjudicated. The v1 contract explicitly treats
`if x` as a required read, so the worker-3 claim that the dmaslov findings were
false positives because Jinja treats missing values as falsey is not accepted.

## Every FTC001/FTC002 label

The first 72 rows below are result-file finding indices, so every individual
finding is identified even where the analyzer emitted duplicate dependency
evidence.

| Result indices | Repository | Code | Variable | Template line | Render call | Label | Justification |
|---|---|---|---|---|---|---|---|
| 1 | dmaslov/flask-blog | FTC001 | error | templates/index.html:25 | web.py:244 | TRUE | `if error` is a required read under v1 and is not supplied. |
| 2 | dmaslov/flask-blog | FTC001 | error_type | templates/index.html:25 | web.py:244 | TRUE | `if error_type` is a required read under v1 and is not supplied. |
| 3 | dmaslov/flask-blog | FTC001 | error | templates/index.html:26 | web.py:244 | TRUE | Required truthiness read is not supplied. |
| 4 | dmaslov/flask-blog | FTC001 | error_type | templates/index.html:26 | web.py:244 | TRUE | Required truthiness read is not supplied. |
| 5 | dmaslov/flask-blog | FTC001 | error | templates/index.html:26 | web.py:251 | TRUE | Required truthiness read is not supplied. |
| 6 | dmaslov/flask-blog | FTC001 | error_type | templates/index.html:26 | web.py:251 | TRUE | Required truthiness read is not supplied. |
| 7 | dmaslov/flask-blog | FTC001 | error | templates/index.html:27 | web.py:251 | TRUE | Required truthiness read is not supplied. |
| 8 | dmaslov/flask-blog | FTC001 | error_type | templates/index.html:27 | web.py:251 | TRUE | Required truthiness read is not supplied. |
| 9-16 | dmaslov/flask-blog | FTC001 | error/error_type | templates/index.html:31-33 | web.py:244/251 | TRUE | Every `if error` and `if error_type` read is required under v1. |
| 17-24 | dmaslov/flask-blog | FTC001 | error/error_type | templates/index.html:40-42 | web.py:244/251 | TRUE | Every truthiness read is required under v1. |
| 25-32 | dmaslov/flask-blog | FTC001 | error/error_type | templates/index.html:46-48 | web.py:244/251 | TRUE | Every truthiness read is required under v1. |
| 33-44 | dmaslov/flask-blog | FTC001 | pagination | templates/index.html:52 | web.py:244,251,175,146,53,237 | TRUE | `if pagination` is a required read under v1 and is not supplied at those calls. |
| 45-48 | dmaslov/flask-blog | FTC001 | error/error_type | templates/index.html:53-54 | web.py:251 | TRUE | Required truthiness reads are not supplied. |
| 49-54 | dmaslov/flask-blog | FTC001 | pagination | templates/index.html:55 | web.py:244,251,175,146,53,237 | TRUE | Required pagination read is not supplied. |
| 55-60 | dmaslov/flask-blog | FTC001 | pagination | templates/index.html:57 | web.py:244,251,175,146,53,237 | TRUE | Required pagination read is not supplied. |
| 61-66 | dmaslov/flask-blog | FTC001 | pagination | templates/index.html:62 | web.py:244,251,175,146,53,237 | TRUE | Required pagination read is not supplied. |
| 67-72 | dmaslov/flask-blog | FTC001 | pagination | templates/index.html:63 | web.py:244,251,175,146,53,237 | TRUE | Required pagination read is not supplied. |
| 1 | frostming/Flog | FTC001 | _ | flaskblog/templates/404.html:538 | flaskblog/views.py:98 | FALSE POSITIVE | Flask-Babel registers `_` through `Babel(app)` at flaskblog/app.py:25. |
| 2-3 | frostming/Flog | FTC001 | _ | flaskblog/templates/mail/layout.html:2 | flaskblog/tasks.py:65-67 | FALSE POSITIVE | Flask-Babel supplies `_`; the mail templates are rendered by the task calls. |
| 4-5 | frostming/Flog | FTC001 | _ | flaskblog/templates/mail/layout.html:10 | flaskblog/tasks.py:86-88 / 65-67 | FALSE POSITIVE | Flask-Babel supplies `_`. |
| 6-7 | frostming/Flog | FTC001 | _ | flaskblog/templates/mail/layout.html:16 | flaskblog/tasks.py:65-67 / 86-88 | FALSE POSITIVE | Flask-Babel supplies `_`. |
| 8-9 | frostming/Flog | FTC001 | _ | flaskblog/templates/mail/layout.html:50 | flaskblog/tasks.py:65-67 / 86-88 | FALSE POSITIVE | Flask-Babel supplies `_`. |

No FTC002 findings occurred in the benchmark run. The other 13 repositories
had no FTC001/FTC002 findings to label.

## Lead random re-check

I independently re-checked ten labels: dmaslov result indices 1, 17, 33, 55,
and 72, plus all five distinct frostming locations. I agreed with the five
Flog FALSE POSITIVE labels. I disagreed with the worker's five dmaslov FALSE
POSITIVE labels: under the frozen contract, `if error`, `if error_type`, and
`if pagination` are required reads, even though ordinary Jinja rendering treats
missing values as falsey. The final labels above use the contract definition.

## Counts

Before the extension-global fix: FTC001 TRUE 72, FALSE POSITIVE 9, UNSURE 0;
FTC002 TRUE 0, FALSE POSITIVE 0, UNSURE 0. After the fix, the nine Flog
extension-global findings became FTC110 and no longer produce FTC001.
