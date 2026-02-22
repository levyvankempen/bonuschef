WITH

source AS (

    SELECT * FROM {{ source('github', 'products') }}

),

renamed AS (

    SELECT
        n AS product_name,
        l AS product_link,
        'https://www.ah.nl/producten/product/' || l AS product_url,
        p AS price,
        s AS amount,
        snapshot_sha AS sha,
        snapshot_at AS snapshot_timestamp

    FROM source
)

SELECT * FROM renamed
