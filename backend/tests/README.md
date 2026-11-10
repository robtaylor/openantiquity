# Backend tests

Tests run against a real PostGIS, never a mock database. Start it once from the repo root:

```
docker compose -f infra/docker-compose.yml up -d db
```

Then, from `backend/`:

```
uv run pytest                          # everything except live tests
uv run pytest tests/auth -q            # one area
uv run pytest -k sensitivity           # by name
uv run pytest --cov=fieldclub --cov-report=term-missing
uv run pytest -m live                  # tests that call real third-party services
```

## How the database works

Each pytest session creates its own database, named `fieldclub_test_<pid>_<random>`, on the server at `localhost:54329`. It builds the schema with `fieldclub.db.create_schema()` and drops the database when the session ends. Several sessions can run at the same time without seeing each other, and none of them touches the development database `fieldclub`.

Every test that uses the `db` fixture, directly or through another fixture, starts with all tables empty and identity columns reset. Tests that don't use the database don't pay for the truncate.

To run against a different server, set `FIELDCLUB_TEST_SERVER_URL` to any database on it. The user needs the right to create databases.

A session drops its database when it ends, whether the tests passed, failed, were interrupted with Ctrl-C, or the process was sent SIGTERM, which is what a CI timeout or a stopping container sends. SIGTERM ends the session with exit status 143.

A session that is killed outright (SIGKILL, a crash, a power cut) leaves its database and its runtime directory behind. The next session removes them. It only removes a database when the process named in it has gone and nothing is connected to it, and only on a server on the same machine, because a process id means nothing elsewhere. To list or drop leftovers by hand:

```
docker compose -f infra/docker-compose.yml exec db psql -U fieldclub -d fieldclub -c "\l fieldclub_test_*"
docker compose -f infra/docker-compose.yml exec db dropdb -U fieldclub --force <name>
```

There is no upgrade path for an older development database. When a model gains a column, rebuild it with `docker compose -f infra/docker-compose.yml down -v` and start the database again.

Sessions share the server, so a test must not assert anything about the server as a whole. A query on `pg_locks` or `pg_stat_activity` sees every database. Filter it to `current_database()`.

## Fixtures

All of these come from `tests/conftest.py`.

| Fixture | What you get |
|---------|--------------|
| `database` | The session's engine. Rarely needed directly |
| `db` | A SQLAlchemy `Session` on freshly emptied tables |
| `app` | The FastAPI app from `create_app()`, using the test database |
| `client` | A `TestClient` with no session. It sends `X-FieldClub-Client: web`, as the web app does |
| `make_user(role=Role.MEMBER, *, handle=None, **columns)` | A committed `User` who has finished the welcome step as an adult. Any `User` column can be passed. Pass `age_band=None, terms_accepted_at=None` for an account that hasn't |
| `client_as(user)` | A `TestClient` signed in as that user, with a real session cookie and the client header |
| `client_for(app, user=None, *, with_header=True)` | The same for an app of the test's own. Without a user it is signed out. `with_header=False` leaves out the client header |
| `newcomer` | A committed `User` straight from a provider sign-in who hasn't done the welcome step |
| `env(NAME=value, ...)` | Sets `FIELDCLUB_NAME` for the rest of the test and reloads the settings. Both are undone when the test ends |
| `limits_on` | Rate limits switched on, with one trusted proxy so a test can choose its address with `X-Forwarded-For` |
| `make_finding(author=None, *, lon=..., lat=..., feature_class=..., sensitivity=None, **columns)` | A committed `Finding`. Defaults to an enclosure at Avebury by a new member. Left out, `sensitivity` is the class default, so an enclosure is open and a round barrow protected. Any `Finding` column can be passed |

```python
def test_a_moderator_can_see_a_restricted_location(client_as, make_user, make_finding):
    finding = make_finding(sensitivity="restricted")
    response = client_as(make_user("moderator")).get(f"/api/v1/findings/{finding.public_id}")
    assert response.json()["location"]["obscured"] is False
```

## Things to know

- The app under test opens its own database sessions. It only sees what has been committed, so call `db.commit()` after setting up data by hand. `make_user` and `make_finding` commit for you.
- After a request changes a row you already hold, call `db.refresh(obj)` or `db.expire_all()` before asserting on it.
- Services flush and never commit. A test that calls a service directly should commit, or roll back, itself.
- Test clients use `https://testserver`, because outside development the session cookie is `Secure` and would not be sent back over plain HTTP.
- Write routes take the `Contributor` dependency, which refuses an account that hasn't finished the welcome step with `onboarding_required`. `make_user` users have finished it. Users made by `POST /auth/dev-login` haven't, so post to `/api/v1/auth/welcome` with `{"age_band": "18_plus", "accept_terms": true}` first.
- `findings.location_public` is written by the ORM when a finding is saved. A Core `insert()` or `update()` skips that, so use one only to test the database's own constraints, as `tests/models/test_constraints.py` does.
- To change the minimum age for one test, call `env(MIN_AGE="18")`.
- Use `client_as(user)` to act as someone. To go through sign-in itself, post to `/api/v1/auth/dev-login` with `{"handle": "TestRob"}`, and optionally a `role`. The development login is switched on for tests by `FIELDCLUB_DEV_LOGIN=true` in `conftest.py`. There are no guest accounts.
- The client header is checked by middleware for every path, so a new route needs no test of its own for it. To send a request without the header, use `client_for(app, with_header=False)`.
- Rate limits are switched off in tests. To test one, use the `limits_on` fixture.
- Write invisible or control characters in a test as escapes such as `"\u202e"`, never as the characters themselves, so the test can be read.
- Settings are fixed by `conftest.py` before `fieldclub` is imported, and any developer `.env` is ignored. To change a setting for one test, use the `env` fixture.
- Freeze time with `time_machine.travel(..., tick=False)`. Session expiry uses Python's clock, so it follows.
- A warning fails the test. If a dependency warns about something outside our control, add a narrow ignore with the reason to `filterwarnings` in `pyproject.toml`.
- Tests must not call live third-party services. Mock outbound HTTP with `respx`, which intercepts the shared client from `fieldclub.http`. A check against a real service carries `@pytest.mark.live` and is deselected by default.

## Layout

`tests/` mirrors `src/fieldclub/`: tests for `fieldclub/services/geo.py` live in `tests/services/test_geo.py`. Test directories have no `__init__.py`. A helper module shared by several test files sits beside them and is imported by its full path, as in `from tests.ingest.fakes import FakeConnector`.

`tests/helpers.py` holds what most test files need: the fixture types `MakeUser`, `MakeFinding`, `ClientAs` and `ClientFor`, `BASE_URL`, the `WEB` client header, `AVEBURY` (where `make_finding` puts a finding), and the small helpers `error_code(response)`, `count(db, Model)`, `nested(depth)`, `lon_lat(point)`, `settings(**values)` and `run_fresh(code)`, which runs Python in a new interpreter. It also builds rows by hand: `add_source(db, key, **columns)` and `add_record(db, source, name, lon, lat)` flush a source and a record, and `admin_area(kind, code, name, *boxes)` makes an unsaved nation or county. To build a geometry value, use `db_point(lon, lat)` or `to_db_geometry(shape)` from `fieldclub.models.common`.

`tests/ingest/fakes.py` has a `FakeConnector` that yields whatever records, or exceptions, a test hands it. Use it to test anything that drives the ingest runner.
