-- What metadata.create_all() cannot express. fieldclub.db.create_schema() runs
-- this file after the tables exist, every time, so each statement must be
-- safe to repeat. A statement ends with a semicolon at the end of a line.
-- Don't write a percent sign: the driver reads it as a parameter placeholder.
--
-- It runs on the live database at every deploy while the old version still
-- serves. An ALTER TABLE takes the strongest lock even when it changes
-- nothing, so each one is skipped when its columns are there already
-- (fieldclub_has_columns). The checks that keep a column inside a vocabulary
-- are kept in step by fieldclub.db, not here.

-- Whether a table in this schema has every one of the columns named.
CREATE OR REPLACE FUNCTION fieldclub_has_columns(table_name text, column_names text[]) RETURNS boolean
    LANGUAGE sql STABLE
    AS $$
        SELECT count(*) = cardinality(column_names)
            FROM pg_attribute
            WHERE attrelid = to_regclass(table_name)
                AND attnum > 0
                AND NOT attisdropped
                AND attname = ANY (column_names)
    $$;

-- array_to_string() is only STABLE, and a generated column needs IMMUTABLE.
-- For text[] the result depends on nothing but the argument, so wrapping it
-- is safe.
CREATE OR REPLACE FUNCTION fieldclub_join_text(parts text[]) RETURNS text
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $$ SELECT coalesce(array_to_string(parts, ' '), '') $$;

-- A finding's line or shape (services.shapes). create_all adds these to a new
-- database. A database made before them gets them here, with the same
-- definitions, so the two end up alike. Nothing is backfilled: an old outline
-- gains its path and simplifications when it is next saved, and
-- `python -m fieldclub.services.shapes backfill` fills the simplifications.
DO $$
BEGIN
    IF NOT fieldclub_has_columns('findings', ARRAY[
        'path', 'outline_mid', 'outline_low', 'shape_kind', 'shape_length_m', 'shape_revision',
        'location_derived', 'looked_at', 'added_since_looked_m', 'added_view'
    ]) THEN
        ALTER TABLE findings
            ADD COLUMN IF NOT EXISTS path jsonb,
            ADD COLUMN IF NOT EXISTS outline_mid geometry(GEOMETRY, 4326),
            ADD COLUMN IF NOT EXISTS outline_low geometry(GEOMETRY, 4326),
            ADD COLUMN IF NOT EXISTS shape_kind text
                CONSTRAINT ck_findings_shape_kind_valid CHECK (shape_kind IN ('line', 'area')),
            ADD COLUMN IF NOT EXISTS shape_length_m real,
            ADD COLUMN IF NOT EXISTS shape_revision integer NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS location_derived boolean NOT NULL DEFAULT false,
            ADD COLUMN IF NOT EXISTS looked_at geometry(GEOMETRY, 4326),
            ADD COLUMN IF NOT EXISTS added_since_looked_m real,
            ADD COLUMN IF NOT EXISTS added_view jsonb;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT fieldclub_has_columns('observations', ARRAY['shape_revision']) THEN
        ALTER TABLE observations ADD COLUMN IF NOT EXISTS shape_revision integer;
    END IF;
END
$$;

-- Map views match a finding's shape as well as its point, for viewers who see it exactly.
CREATE INDEX IF NOT EXISTS idx_findings_outline ON findings USING gist (outline);

-- The shapes that cross a map box are looked up by themselves
-- (sensitivity.visible_match_clause). Few findings have a shape, so this index
-- is small and the planner always takes it. With the index of every outline
-- above, it sometimes read the whole table for them.
CREATE INDEX IF NOT EXISTS idx_findings_outline_shaped ON findings USING gist (outline)
    WHERE shape_kind IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_findings_outline_low ON findings USING gist (outline_low);

-- Full-text search over records. The name counts most, then the type terms,
-- then the summary.
DO $$
BEGIN
    IF NOT fieldclub_has_columns('records', ARRAY['search']) THEN
        ALTER TABLE records ADD COLUMN IF NOT EXISTS search tsvector
            GENERATED ALWAYS AS (
                setweight(to_tsvector('english', coalesce(name, '')), 'A')
                || setweight(
                    to_tsvector(
                        'english', coalesce(record_type, '') || ' ' || fieldclub_join_text(monument_types)
                    ),
                    'B'
                )
                || setweight(to_tsvector('english', coalesce(summary, '')), 'C')
            ) STORED;
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS ix_records_search ON records USING GIN (search);

-- Distance queries cast to geography. These make the casts indexable.
CREATE INDEX IF NOT EXISTS ix_records_centroid_geography ON records USING GIST ((centroid::geography));

CREATE INDEX IF NOT EXISTS ix_findings_location_geography ON findings USING GIST ((location::geography));

-- Signed-out visitors are served from location_public, so its distance
-- queries need the same index as location's.
CREATE INDEX IF NOT EXISTS ix_findings_location_public_geography
    ON findings USING GIST ((location_public::geography));

-- A private investigation has exactly one member, its owner (Decision 0009).
-- fieldclub.services.investigations checks this and gives a clear error. These
-- triggers hold the rule for any write that skips the service. FOR SHARE
-- stops a member being added while the investigation is made private.
CREATE OR REPLACE FUNCTION fieldclub_check_private_member() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    parent record;
BEGIN
    SELECT visibility, owner_id INTO parent
        FROM investigations WHERE id = NEW.investigation_id FOR SHARE;
    IF parent.visibility = 'private' AND NEW.user_id <> parent.owner_id THEN
        RAISE EXCEPTION USING ERRCODE = 'check_violation',
            MESSAGE = 'private_investigation_has_one_member: investigation '
                || NEW.investigation_id || ' is private';
    END IF;
    RETURN NEW;
END
$$;

CREATE OR REPLACE TRIGGER investigation_members_private_check
    BEFORE INSERT OR UPDATE OF investigation_id, user_id ON investigation_members
    FOR EACH ROW EXECUTE FUNCTION fieldclub_check_private_member();

CREATE OR REPLACE FUNCTION fieldclub_check_private_investigation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW.visibility = 'private' AND EXISTS (
        SELECT 1 FROM investigation_members
            WHERE investigation_id = NEW.id AND user_id <> NEW.owner_id
    ) THEN
        RAISE EXCEPTION USING ERRCODE = 'check_violation',
            MESSAGE = 'private_investigation_has_one_member: investigation '
                || NEW.id || ' has other members';
    END IF;
    RETURN NEW;
END
$$;

CREATE OR REPLACE TRIGGER investigations_private_check
    BEFORE UPDATE OF visibility, owner_id ON investigations
    FOR EACH ROW EXECUTE FUNCTION fieldclub_check_private_investigation();

-- location_public is kept right by an ORM listener (services.sensitivity).
-- This trigger refuses two writes that skip it: an open finding whose public
-- position differs from its location, and a finding made protected while its
-- public position is still its exact location. The
-- second check also refuses an open finding that sits exactly on the centre
-- of its square, which is impossible in practice. A write that moves a
-- protected finding to another point in the same square is not caught, and
-- neither is one that leaves a stale square after a move, because the grid
-- is only in Python.
CREATE OR REPLACE FUNCTION fieldclub_check_location_public() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW.sensitivity = 'open' AND NOT ST_Equals(NEW.location_public, NEW.location) THEN
        RAISE EXCEPTION USING ERRCODE = 'check_violation',
            MESSAGE = 'location_public_mismatch: open finding ' || NEW.public_id
                || ' has a public position that is not its location';
    ELSIF TG_OP = 'UPDATE' AND OLD.sensitivity = 'open' AND NEW.sensitivity <> 'open'
        AND ST_Equals(NEW.location_public, NEW.location) THEN
        RAISE EXCEPTION USING ERRCODE = 'check_violation',
            MESSAGE = 'location_public_mismatch: finding ' || NEW.public_id
                || ' was made ' || NEW.sensitivity || ' but its public position is still exact';
    END IF;
    RETURN NEW;
END
$$;

CREATE OR REPLACE TRIGGER findings_location_public_check
    BEFORE INSERT OR UPDATE OF sensitivity, location, location_public ON findings
    FOR EACH ROW EXECUTE FUNCTION fieldclub_check_location_public();

-- Record tiles count records by the point they sit at, so the tile query
-- filters on centroid and needs it indexed as geometry too.
CREATE INDEX IF NOT EXISTS ix_records_centroid ON records USING GIST (centroid);

-- Record search finds names that start with the query through this, in name
-- order, so a common word is cut short by the index instead of ranked whole.
CREATE INDEX IF NOT EXISTS ix_records_name_prefix ON records (lower(name) text_pattern_ops);
