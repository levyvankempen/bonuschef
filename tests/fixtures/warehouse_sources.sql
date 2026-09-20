-- The source tables dbt reads but does not create.
--
-- dlt creates these at load time from the shape of what it loaded, so on a
-- database that has never run a load they do not exist and every staging
-- model fails. Empty is enough: the point of building in CI is to execute the
-- SQL, and a statement is executed against an empty table just as well.
--
-- Columns are only those the staging models select. If a model starts
-- selecting something absent here, the build fails naming the column - which
-- is the correct outcome and keeps this file honest without anyone policing
-- it.
--
-- The PORTAL source tables are deliberately NOT here. They are created by
-- ensure_catalogue_tables() in portal/db.py, and the fixture calls that
-- function rather than restating its DDL - two copies of a schema is how they
-- come to disagree.

CREATE TABLE IF NOT EXISTS public.ah__bonus_products (
    webshop_id        BIGINT,
    title             TEXT,
    bonus_mechanism   TEXT,
    bonus_start_date  TEXT,
    bonus_end_date    TEXT,
    price_before_bonus NUMERIC,
    bonus_price       NUMERIC,
    loaded_at         TEXT,
    is_bonus          BOOLEAN
);

CREATE TABLE IF NOT EXISTS public.ah__store_markdowns (
    store_id            BIGINT,
    webshop_id          BIGINT,
    title               TEXT,
    brand               TEXT,
    sales_unit_size     TEXT,
    image_url           TEXT,
    category_title      TEXT,
    markdown_type       TEXT,
    markdown_percentage NUMERIC,
    markdown_expiration_date TEXT,
    stock               INTEGER,
    price_was           NUMERIC,
    price_now           NUMERIC,
    scraped_at          TEXT
);

CREATE TABLE IF NOT EXISTS public.github__products (
    n            TEXT,
    l            TEXT,
    p            NUMERIC,
    s            TEXT,
    snapshot_sha TEXT,
    snapshot_at  TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS public.ah__pool_recipes (
    recipe_id      BIGINT,
    title          TEXT,
    servings       INTEGER,
    url            TEXT,
    image_url      TEXT,
    description    TEXT,
    cook_time_min  INTEGER,
    rating_average NUMERIC,
    rating_count   INTEGER,
    modified_at    TEXT,
    fetched_at     TEXT
);

CREATE TABLE IF NOT EXISTS public.ah__pool_recipe_ingredients (
    recipe_id    BIGINT,
    line_no      INTEGER,
    concept_id   BIGINT,
    concept_name TEXT,
    quantity     NUMERIC,
    unit         TEXT,
    raw_text     TEXT,
    fetched_at   TEXT
);

-- One promotion for a product no price snapshot has ever carried.
--
-- Without a row like this every check over these tables passes vacuously: an
-- empty warehouse proves the SQL parses, not that it keeps anything. This one
-- reproduces the defect that dropped 72% of the promotional feed, so the
-- comparison mart must emit it with product_link null and the observed saving
-- unknown rather than omitting it.
INSERT INTO public.ah__bonus_products
    (webshop_id, title, bonus_mechanism, bonus_start_date, bonus_end_date,
     price_before_bonus, bonus_price, loaded_at, is_bonus)
VALUES
    (999999001, 'Onbekend product in de bonus', '25% KORTING',
     '2020-01-01', '2100-01-01', 4.00, 3.00, '2020-01-01T00:00:00', TRUE)
ON CONFLICT DO NOTHING;
