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

-- Seeded rows are removed first. ON CONFLICT DO NOTHING needs a constraint
-- to fire, and these source tables have none - dlt creates them from the shape
-- of what it loaded - so re-running the seed duplicated every row and broke
-- the uniqueness tests that the seed exists to exercise.
DELETE FROM public.ah__bonus_products WHERE webshop_id >= 999000000;
DELETE FROM public.ah__store_markdowns WHERE webshop_id >= 999000;
DELETE FROM public.github__products WHERE l LIKE 'wi999%';
DELETE FROM public.ah__bonus_products WHERE webshop_id IN (999003, 999004);
-- Created here as well as by the dbt hook, because the seeder runs BEFORE
-- dbt and these are the portal's own tables rather than dbt's models. Mirrors
-- the hook's definition exactly.
CREATE TABLE IF NOT EXISTS public.recipes (
    recipe_id   INTEGER NOT NULL,
    recipe_name TEXT    NOT NULL,
    servings    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS public.recipe_ingredients (
    recipe_id    INTEGER   NOT NULL,
    product_name TEXT      NOT NULL,
    product_link TEXT      NOT NULL,
    quantity     INTEGER   NOT NULL,
    valid_from   TIMESTAMP,
    valid_to     TIMESTAMP
);

-- An account whose shop has never been scraped.
--
-- The store spine used to be built from scraped markdowns, so a store with no
-- scrape had no row - and three models CROSS JOIN that spine, so it had no
-- rows anywhere downstream either, including national promotions that do not
-- depend on a store at all. A second person saw an empty application.
--
-- 999998 is scraped by nothing in this fixture on purpose. It is here so the
-- spine has to carry it.
CREATE TABLE IF NOT EXISTS public.accounts (
    account_id           BIGSERIAL PRIMARY KEY,
    username             TEXT        NOT NULL,
    password_hash        TEXT        NOT NULL DEFAULT '',
    must_change_password BOOLEAN     NOT NULL DEFAULT TRUE,
    store_id             BIGINT,
    is_operator          BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_sign_in_at      TIMESTAMPTZ
);

DELETE FROM public.accounts WHERE username LIKE 'fixture_%';
DELETE FROM public.recipe_ingredients WHERE recipe_id = 999900;
DELETE FROM public.recipes WHERE recipe_id = 999900;
DELETE FROM public."ah__pool_recipe_ingredients" WHERE recipe_id >= 999900000;
DELETE FROM public."ah__pool_recipes" WHERE recipe_id >= 999900000;
DELETE FROM public.ah_ingredient_products WHERE concept_id >= 999000;

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
     '2020-01-01', '2100-01-01', 4.00, 3.00, '2020-01-01T00:00:00', TRUE);

-- Two ingredients of one recipe, one clearance unit between them.
--
-- "ui" and "rode ui" both resolve to the same onion pack; the pack is on
-- clearance with one left. The recipe used to claim the discount twice,
-- because the count of claimants was carried and the flag derived from it was
-- even selected by the portal - and the saving was summed regardless.
--
-- The spec's word is "unnoticed". It was computed and never applied.
INSERT INTO public."ah__pool_recipes"
    (recipe_id, title, servings, url, image_url, description, cook_time_min,
     rating_average, rating_count, modified_at, fetched_at)
VALUES
    (999900002, 'Uientest', 2, 'u', 'i', 'd', 20, 4.0, 10,
     '2020-01-01T00:00:00', '2020-01-01T00:00:00');

INSERT INTO public."ah__pool_recipe_ingredients"
    (recipe_id, line_no, concept_id, concept_name, quantity, unit, raw_text,
     fetched_at)
VALUES
    (999900002, 1, 999001, 'ui',      1, 'stuk', '1 ui',      '2020-01-01T00:00:00'),
    (999900002, 2, 999002, 'rode ui', 1, 'stuk', '1 rode ui', '2020-01-01T00:00:00');

-- One product, priced, that both concepts resolve to.
INSERT INTO public.github__products (n, l, p, s, snapshot_sha, snapshot_at)
VALUES ('AH Uien', 'wi999002/ah-uien', 2.00, '1 kg', 'seed', now());

-- On clearance, with exactly one left.
INSERT INTO public.ah__store_markdowns
    (store_id, webshop_id, title, brand, sales_unit_size, image_url,
     category_title, markdown_type, markdown_percentage,
     markdown_expiration_date, stock, price_was, price_now, scraped_at)
VALUES
    (1876, 999002, 'AH Uien', 'AH', '1 kg', NULL, 'Groente', 'PERCENT', 50,
     '2100-01-01', 1, 2.00, 1.00, to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SS'));

-- Both concepts resolved to that one pack, which is what makes them compete.
-- Confirmed, so nothing re-derives them out from under the fixture.
INSERT INTO public.ah_ingredient_products
    (concept_id, product_link, product_name, confirmed_at, proposed_at)
VALUES
    (999001, 'wi999002/ah-uien', 'AH Uien', now(), now()),
    (999002, 'wi999002/ah-uien', 'AH Uien', now(), now());

-- A promotion on a product we DO have a price for, so a bonus offer exists at
-- all. Without one, "does a bonus offer carry its pack size" is a question
-- about an empty table.
--
-- The pack size is the point: it was CAST(NULL AS text) for every promotion,
-- so "hele verpakking: 500 g" only ever appeared on clearance lines and a
-- recipe needing 100 g of a promoted 500 g pack was costed at the pack with
-- nothing on the page to say so.
INSERT INTO public.github__products (n, l, p, s, snapshot_sha, snapshot_at)
VALUES ('AH Roomboter', 'wi999003/ah-roomboter', 3.00, '250 g', 'seed', now());

INSERT INTO public.ah__bonus_products
    (webshop_id, title, bonus_mechanism, bonus_start_date, bonus_end_date,
     price_before_bonus, bonus_price, loaded_at, is_bonus)
VALUES
    (999003, 'AH Roomboter', '25% KORTING', '2020-01-01', '2100-01-01',
     3.00, 2.25, to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SS'), TRUE);

-- A promotion carrying no dates at all.
--
-- AH ships these: two standing Robijn volume discounts had NULL start and end
-- dates on 2026-09-21. `bonus_start_date <= CURRENT_DATE` is NULL rather than
-- false for such a row, so three-valued logic dropped them from the
-- comparison without recording them anywhere as rejected. An absent bound is
-- not a failed one, and this row is here so that stays true.
INSERT INTO public.github__products (n, l, p, s, snapshot_sha, snapshot_at)
VALUES ('AH Wasmiddel 2-pack', 'wi999004/ah-wasmiddel-2-pack', 8.00, '2 x 1 l',
        'seed', now());

INSERT INTO public.ah__bonus_products
    (webshop_id, title, bonus_mechanism, bonus_start_date, bonus_end_date,
     price_before_bonus, bonus_price, loaded_at, is_bonus)
VALUES
    (999004, 'AH Wasmiddel 2-pack', '30% volume voordeel', NULL, NULL,
     8.00, 5.60, to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SS'), TRUE);

-- A hand-entered recipe, so the recipe pages have something to return.
--
-- This used to arrive by accident. An on-run-start dbt hook seeded a default
-- recipe whenever public.recipes was empty, which in CI it always was - so
-- the fixture depended on a production bootstrap it never mentioned. Removing
-- that hook (it resurrected recipes a person had deliberately deleted) left
-- read_recipe_summary returning nothing, and the assertion that its readers
-- return rows is what noticed.
INSERT INTO public.recipes (recipe_id, recipe_name, servings)
VALUES (999900, 'Testrecept met boter', 2);

INSERT INTO public.recipe_ingredients
    (recipe_id, product_name, product_link, quantity, valid_from, valid_to)
VALUES
    (999900, 'AH Roomboter', 'wi999003/ah-roomboter', 1, NULL, NULL);

INSERT INTO public.accounts (username, store_id)
VALUES ('fixture_unscraped_store', 999998);
