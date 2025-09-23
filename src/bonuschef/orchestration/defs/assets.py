import dagster as dg

@dg.asset
def products() -> str:
    return "https://github.com/supermarkt/checkjebon/blob/main/data/supermarkets.json"