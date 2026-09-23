# Scrape through opening hours

## Why

The clearance scrape runs 11:00–20:00. The shop is open 08:00–21:00, and the
gap shows: the portal reports the morning as "not yet scraped today", which
reads as a broken pipeline rather than as a deliberate choice.

The original window was a guess about when markdowns appear - "from midday,
deepening toward closing". That may well be where most of them are, but it is
not where all of them are, and the cost of finding out is three requests at
each end of the day.

There is a second reason, and it is the one that makes this worth doing
rather than merely tidy. `read_last_scrape_time` drives a banner saying
clearance is not from today. Between midnight and 11:00 that banner is
correct and useless: it reports a gap the schedule created. Starting at 08:00
means the banner, when it appears, is about something that went wrong.

## What Changes

- **MODIFIED** "The clearance scrape runs hourly through the afternoon" -
  the window becomes 08:00–21:00 Dutch local time, and the requirement stops
  asserting that the store publishes no markdowns outside it, which was an
  assumption rather than an observation.

## Impact

Ten runs a day becomes fourteen. Each is one GraphQL request per store, so at
one store this is four extra requests a day against an API the project
already calls hourly.

The 21:00 run is deliberately included rather than stopping at 20:00: the
last hour before closing is when a markdown is deepest and least likely to
still be there tomorrow, which is precisely the data the intraday series
exists to record.

Nothing else moves. The bonus refresh stays at 17:30 and the credential
heartbeat at 03:30/15:30, both on the half hour, so neither collides with a
scrape.
