WITH

source AS (

    {{ source('github', 'products_ah') }}

)

renamed AS (
    SELECT
        n AS name,
        l AS link,
        p AS price,
        s AS amount

    FROM source
)

select * from renamed