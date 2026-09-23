-- The accounts, reduced to what the warehouse needs of them.
--
-- Deliberately not the password hash, the session tokens or anything else
-- identifying. dbt materialises into schemas the portal can read and that a
-- person browsing the warehouse can see; a credential has no business in
-- either, and the warehouse has no use for one.

WITH source AS (

    SELECT
        account_id,
        store_id
    FROM {{ source('portal', 'accounts') }}

)

SELECT
    account_id,
    store_id
FROM source
WHERE store_id IS NOT null
