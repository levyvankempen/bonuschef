# Tasks

- [x] 1. Move the clearance cron to `0 8-21 * * *`
- [x] 2. Replace the comment asserting markdowns appear from midday
- [x] 3. Pin the window against opening hours rather than a literal cron
      string, so the reason survives the next move. Two mutations verified:
      reverting to 11-20 and stopping at 20:00 both fail with the hours named
- [x] 4. Confirm nothing else lands on the hour - the bonus refresh (17:30)
      and the credential heartbeat (03:30/15:30) are both on the half hour,
      and a test now enforces it
