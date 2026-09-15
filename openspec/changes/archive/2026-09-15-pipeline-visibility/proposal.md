## Why

Two guarantees this project has written down are not actually in force, and both concern the same question: **how would anyone know the pipeline had stopped working?**

Five sources declare `warn_after` / `error_after` freshness thresholds. Nothing evaluates them. `dbt build` does not check source freshness, `dbt source freshness` appears nowhere in the repo, and no asset check declares one. The comment sitting above one of those declarations reads *"This feed went 69 days without loading and nothing reported it; the marts served July promotions as current the whole time."* That is still a description of the present, not the past.

The failure alert sensor covers runs that fail. It cannot cover a run that was never launched, a sensor whose tick throws, or a feed that silently stops arriving — and those are the failures that produce no event at all. Alerting is also deliberately unsubscribed, which is a reasonable choice but leaves the portal as the only surface where anything can be noticed.

Today the portal reports on its *sources* — clearance snapshot age, bonus feed age — and nothing about the pipeline that turns them into answers. A dbt failure leaves every mart frozen while `ah__bonus_products.loaded_at` stays fresh, so the existing banners stay quiet and the page looks fine.

## What Changes

- Source freshness is evaluated on a schedule, so a feed that stops arriving is reported rather than silently served as current.
- The portal shows when each scheduled job last succeeded, and says so when one is overdue — the failures that emit no event become visible in the place the owner already looks daily.
- Freshness of the answer is judged on the mart that produced it, not only on the feed underneath it, so a load that succeeded followed by a rebuild that failed is not reported as fresh.

## Capabilities

### Modified Capabilities
- `data-quality`: the declared freshness thresholds are actually evaluated.
- `portal`: the page reports the health of the pipeline behind it, not only the age of its sources.

## Impact

- A new Dagster job and schedule that evaluates source freshness.
- `src/bonuschef/portal/` — a health summary on the default page, read from the Dagster run table that already lives in the same Postgres.
- No change to what any mart computes.
