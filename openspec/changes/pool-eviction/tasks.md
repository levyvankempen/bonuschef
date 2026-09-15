# Tasks

- [x] 1.1 Both pool resources load with `write_disposition="replace"`, so the table holds what the latest enumeration returned
- [x] 1.2 Keep the guard that refuses to write an empty pool over a good one — it is what makes `replace` safe, and it predates this change
- [x] 1.3 Test: a refresh returning a listing without a previously held recipe leaves it absent
- [x] 1.4 Test: adoption, hand-entry and rejection remain exempt, because they do not live in the pool table
- [x] 1.5 Verify on the live warehouse that the pool count after a refresh equals what the enumeration returned
