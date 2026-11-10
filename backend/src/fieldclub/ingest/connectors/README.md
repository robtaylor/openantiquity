# Writing a connector

A connector reads one external source and yields `RecordIn` objects. The runner in `fieldclub/ingest/runner.py` does everything else: it stores the source's licence and attribution first, validates each record, upserts in batches, deletes what vanished upstream after a full run, and writes an `ingest_runs` row. A connector holds no credentials and never touches the database.

Most connectors are a class with a `SourceInfo` and a `fetch()` of a few lines, because the reading is done by a shared adapter in `fieldclub/ingest/adapters/`. The reference connector is `he_nhle_scheduled_monuments.py`. Copy it.

## 1. Find the source in the work-list

Every storable source is an entry in `docs/sources/worklists/sources.json` under `bulk`. The entry gives the key, the address, the tested request, the licence, the attribution, the reuse class, the field names and the quirks. Read the quirks. They're the reason the research was done.

Only `bulk` sources get a connector. A `live` source is queried by the browser and never stored (Decision 0007). Its definition goes in `fieldclub/data/live_sources.json` instead, and the frontend reads it from `GET /api/v1/context/live-sources`.

## 2. Pick the adapter

| `access_method` in the work-list | Adapter | Call |
|---|---|---|
| `file_download` | `download` then `files` | `download(url, cache_dir(settings, key) / name, client=self.http, max_age=...)`, then `read_vector(path)` |
| `arcgis_feature` | `arcgis` | `ArcGISLayer(url, client=self.http).features(bbox=bbox)` |
| `wfs` | `wfs` | `WFSLayer(url, type_name, client=self.http, sort_by="RecordNumber").features(bbox=bbox)` |
| `sparql` | `sparql` | `SparqlQuery(endpoint, query, client=self.http, geometry="coord").features()` |
| `csv` | `files` | `read_csv(path, x="Easting", y="Northing", crs="EPSG:27700", encoding="cp1252")` |
| `csv` inside a zip | `files` | `read_csv(path, member="Data/SU06.csv", fieldnames=HEADINGS)`, for a CSV read straight from the zip, and one whose headings are elsewhere |
| `ndjson` | `files` | `read_ndjson(path)` |
| `rest_json` | `rest` | `RestJson(self.http, polite=...).items(url, params=..., items="data", total="meta.total", next_url="links.next", id_path="id")` for a paged answer (add `cache=cache_dir(...) / "pages"` to keep each page for a day), `.document(url, dest=..., max_age=...)` for one big answer kept under `var/` |

Every adapter yields `Feature(properties, geometry, id)`. The properties are plain Python values with NaN turned into None. The geometry is shapely in WGS84, longitude first, whatever the source's own CRS. Requests go through `Polite`, which leaves a second between requests, retries 408, 429 and 5xx with backoff, and honours `Retry-After`. Pass a `Polite(delay_s=...)` of your own when a source's `robots.txt` or terms ask for a longer gap.

The REST reader follows the next page by a link (`next_url`, such as DataCite's `links.next`) or by a cursor (`cursor` and `cursor_param`, such as Crossref's), counts the distinct items by `id_path` against the total the service reports (`total`), and stops with an error when a next link or cursor repeats. It yields the JSON items as they are, for the connector to map.

The ArcGIS and WFS readers count first and raise `IncompleteReadError` when fewer distinct features arrive than the count promised, so a truncated answer, or one that repeats a feature where it skipped another, fails the run instead of deleting records. ArcGIS features are told apart by object id. A WFS layer needs `sort_by`, a unique property, which both keeps the paging stable and tells the features apart.

## 3. Write the class

The reference connector, cut to its parts:

```python
@register
class ScheduledMonuments(Connector):
    source: ClassVar[SourceInfo] = SourceInfo(
        key="he-nhle-scheduled-monuments",  # the work-list key
        name="Scheduled monuments",
        publisher="Historic England",
        licence="Open Government Licence v3.0, via Historic England Open Data Hub Terms and Conditions",
        licence_url="https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        # Copied with its placeholders. The runner fills in [year] and [date].
        attribution="© Historic England [year]. Contains Ordnance Survey data © Crown copyright and database right [year]. "
        + CURRENCY_STATEMENT,
        category=RecordCategory.DESIGNATION,
        access=SourceAccess.BULK,
        reuse=SourceReuse.OPEN,  # from the work-list, never guessed
        homepage="https://opendata-historicengland.hub.arcgis.com/",
        coverage="England",
    )
    max_age: ClassVar[timedelta] = timedelta(hours=20)

    def fetch(self, *, bbox=None, limit=None):
        path = cache_dir(self.settings, self.source.key) / "scheduled-monuments.gpkg"
        fetched = download(HUB_EXPORT, path, client=self.http, max_age=self.max_age)
        self.obtained_at = fetched.fetched_at  # dates the attribution
        info = vector_info(path)
        ...  # check the fields and CRS you rely on
        for feature in read_vector(path, bbox=bbox, info=info):
            yield to_record(feature)
```

Rules for the class:

- The file name is the key with hyphens as underscores. `registry.discover()` imports every module in this package, so the file is all it takes.
- `SourceInfo` refuses a blank licence or attribution and an unknown reuse class, and the `sources` table has a check that does the same. Copy licence, attribution and reuse from the work-list word for word, and test them for equality with the entry. Leave `[year]` and `[date]` in the attribution as the work-list writes them: the runner fills both in when it stores the `sources` row, from `self.obtained_at` if `fetch()` set it and from the day of the run if not. Set `self.obtained_at` to the download's `fetched_at`, so a copy reused from the cache keeps the date it was really obtained. Add any statement the work-list's `gotchas` say the publisher asks for, such as Historic England's currency statement.
- Use `self.http`, the shared client with the project `User-Agent`. Don't build your own.
- Keep downloads under `cache_dir(self.settings, key)`, which is `var/ingest/<key>/`. Set `max_age` to how often the source changes, so a second run the same day costs the publisher nothing.
- Check the shape you rely on before reading: the field names, the CRS, the layer. Raise `UpstreamFormatError` when it changed. A wrong assumption must stop the run, not write bad rows.

## 4. Map the fields

`to_record` turns one `Feature` into one `RecordIn`:

| `RecordIn` field | From |
|---|---|
| `external_id` | The work-list's `id_field`, as text. It must be stable across runs, because the runner upserts on it. When `id_field` is null, see below |
| `name` | `name_field`, stripped |
| `geom` | `feature.geometry`. The runner works out the centroid, repairs invalid shapes and refuses anything outside the isles' box, which also holds Normandy and Picardy. A source that reaches abroad filters with `in_britain_and_ireland(lon, lat)` or `geometry_in_britain_and_ireland(geometry)` from `ingest.base` |
| `category` | Leave it out to use the source's |
| `record_type`, `monument_types` | `type_field`. Keep thesaurus terms as the source writes them |
| `periods` | `period_field`, mapped onto `vocab.Period`. The runner refuses anything else |
| `summary` | `summary_field` |
| `url` | `record_url_template` filled from the feature |
| `precision_m` | The work-list's `precision_m` |
| `source_updated_at` | A timezone-aware datetime, if the source has one |
| `raw` | `json_ready(feature.properties)`, so nothing is lost |

### When the work-list has no `id_field`

Many entries have `id_field` null: the source publishes no identifier of its own. Build `external_id` from upstream fields that name the thing itself and don't change when the file is republished, such as the grid reference and the name, or a hash of them:

```python
external_id = hashlib.sha256(f"{props['NGR']}|{props['Name'].strip().lower()}".encode()).hexdigest()[:20]
```

Don't use `OBJECTID`, `FID`, a row number or `feature.id` unless the publisher states the value is stable. They're numbered afresh when a layer is republished, and then a full run upserts every record under a new id and deletes the old ones, with their links from evidence and investigations. Check that the key is unique in the data, and raise `UpstreamFormatError` when two features give the same one, because the runner would otherwise keep the first and count the rest as duplicates. Say in the connector's docstring which fields the key is built from.

Where polygons share their upstream fields, as a monument's several drawn features do, add the geometry to the key. `FeatureKeys` in `adapters/common.py` builds it from the fields you name and the geometry rounded to a centimetre, and numbers an exact repeat (`-2`, `-3`) instead of losing it. `he_aim_detailed_mapping.py` is the example.

## 5. Record a fixture and test against it

Tests never call the live service. Record a small fixture from it once, with a handful of requests and a second between them, and put it in `tests/ingest/adapters/fixtures/` or beside the connector's test. Write down where and how it was recorded, as `tests/ingest/adapters/support.py` does. Then mock the upstream with `respx` and run the connector through the real runner:

```python
@respx.mock
def test_running_twice_gives_the_same_rows(db):
    serve_hub(FIXTURE.read_bytes())
    run_connector(ScheduledMonuments())
    before = rows(db)
    run_connector(ScheduledMonuments())
    assert rows(db) == before
```

`tests/records/test_scheduled_monuments.py` is the model: the field mapping, the licence against the work-list, two runs giving the same rows, a partial run by box, and an upstream that changed shape failing the run. Give each test its own `var/` with the `env` fixture, or the download cache leaks between tests.

## 6. Run it for real

From `backend/`, with `var/` pointing at the shared runtime directory:

```
uv run python -m fieldclub.db                                  # once, to apply any schema additions
FIELDCLUB_VAR_DIR=../var uv run fieldclub-ingest run <key> --limit 50
FIELDCLUB_VAR_DIR=../var uv run fieldclub-ingest run <key>
```

Compare the count with the work-list's `expected_count`. The scheduled monuments gave 20,006 on 2026-11-10, the same as the research recorded. A run that is more than a few percent out means a filter, a page limit or a CRS is wrong.
