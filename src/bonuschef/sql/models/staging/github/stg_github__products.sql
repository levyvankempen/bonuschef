WITH

source AS (

    SELECT * FROM {{ source('github', 'products_ah') }}

),

renamed AS (

    SELECT
        n AS product_name,
        l AS product_link,
        p AS price,
        s AS amount

    FROM source
)

SELECT * FROM renamed
