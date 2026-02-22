{% macro seed_default_recipes() %}

    -- Only insert when the recipes table is empty (fresh environment)
    INSERT INTO public.recipes (recipe_id, recipe_name, servings)
    SELECT 1, 'Taco''s met kibbeling, rodekool en aiolidressing', 4
    WHERE NOT EXISTS (SELECT 1 FROM public.recipes);

    INSERT INTO public.recipe_ingredients
        (recipe_id, product_name, product_link, quantity, valid_from, valid_to)
    SELECT *
    FROM (
        VALUES
            (1, 'AH Tortilla naturel wraps',       'wi136836/ah-tortilla-naturel-wraps',       1, NULL::timestamp,                    '2025-02-17'::timestamp),
            (1, 'AH Tortilla wraps volkoren large', 'wi453733/ah-tortilla-wraps-volkoren-large', 1, '2025-02-17'::timestamp,            NULL::timestamp),
            (1, 'AH Avocado eetrijp',               'wi129400/ah-avocado-eetrijp',               1, NULL::timestamp,                    NULL::timestamp),
            (1, 'AH Peen julienne',                  'wi104817/ah-peen-julienne',                  1, NULL::timestamp,                    NULL::timestamp),
            (1, 'AH Biologisch Rode kool',           'wi160648/ah-biologisch-rode-kool',           1, NULL::timestamp,                    NULL::timestamp),
            (1, 'AH Aioli',                          'wi497585/ah-aioli',                          1, NULL::timestamp,                    NULL::timestamp),
            (1, 'AH Koriander',                      'wi238968/ah-koriander',                      1, NULL::timestamp,                    NULL::timestamp),
            (1, 'AH Limoen los',                     'wi231211/ah-limoen-los',                     1, NULL::timestamp,                    '2025-02-17'::timestamp),
            (1, 'AH Limoen',                         'wi231211/ah-limoen',                         1, '2025-02-17'::timestamp,            NULL::timestamp),
            (1, 'Iglo Kibbeling traditioneel',       'wi371592/iglo-kibbeling-traditioneel',       2, NULL::timestamp,                    '2025-02-17'::timestamp),
            (1, 'Iglo Kibbeling',                    'wi582316/iglo-kibbeling',                    2, '2025-02-17'::timestamp,            '2025-11-17'::timestamp),
            (1, 'Iglo Viskraam Kibbeling',           'wi582316/iglo-viskraam-kibbeling',           2, '2025-11-17'::timestamp,            NULL::timestamp)
    ) AS v(recipe_id, product_name, product_link, quantity, valid_from, valid_to)
    WHERE NOT EXISTS (SELECT 1 FROM public.recipe_ingredients);

{% endmacro %}
