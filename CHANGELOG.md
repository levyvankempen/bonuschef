# CHANGELOG

<!-- version list -->

## v1.15.2 (2026-09-21)

### Bug Fixes

- **bonus**: A promotion with no dates is open, not excluded
  ([#82](https://github.com/levyvankempen/bonuschef/pull/82),
  [`1dc958a`](https://github.com/levyvankempen/bonuschef/commit/1dc958afcbf5d553680d3b634320a5dc54ca650a))


## v1.15.1 (2026-09-21)

### Bug Fixes

- **dags**: An op and its job cannot share a name, and CI must load the repository
  ([#81](https://github.com/levyvankempen/bonuschef/pull/81),
  [`25dc4f9`](https://github.com/levyvankempen/bonuschef/commit/25dc4f9889ff990917a8bc790e5dd6f803d06420))


## v1.15.0 (2026-09-20)

### Features

- **stores**: Choose a shop by its name, not by its number
  ([#80](https://github.com/levyvankempen/bonuschef/pull/80),
  [`4555ac3`](https://github.com/levyvankempen/bonuschef/commit/4555ac33e7aa0a979d1d40c3afe3568a802e0001))


## v1.14.0 (2026-09-20)

### Features

- **portal**: Every store-scoped read is told which store
  ([#79](https://github.com/levyvankempen/bonuschef/pull/79),
  [`3f8b67e`](https://github.com/levyvankempen/bonuschef/commit/3f8b67eebc7ec42768a5956a3dd6599bd4e21a30))


## v1.13.1 (2026-09-20)

### Bug Fixes

- **backfill**: A dry run must not alter the schema it is inspecting
  ([#78](https://github.com/levyvankempen/bonuschef/pull/78),
  [`3128a67`](https://github.com/levyvankempen/bonuschef/commit/3128a67aa8207ad5788735e955b98878505bda98))


## v1.13.0 (2026-09-20)

### Features

- **accounts**: The account schema and the backfill that claims existing data
  ([#77](https://github.com/levyvankempen/bonuschef/pull/77),
  [`349278a`](https://github.com/levyvankempen/bonuschef/commit/349278aae3baf9f42be5e725505cd68c9c49368a))


## v1.12.0 (2026-09-20)

### Documentation

- **specs**: Record the recognisability floor and correct what it falsified
  ([#74](https://github.com/levyvankempen/bonuschef/pull/74),
  [`6ff9a57`](https://github.com/levyvankempen/bonuschef/commit/6ff9a5727679bb85ed5dc0aed6e3a74bb117e0a1))

### Features

- **catalogue**: Adopt the two Allerhande recipes and withdraw zuurkoolstamppot
  ([#76](https://github.com/levyvankempen/bonuschef/pull/76),
  [`e7febb4`](https://github.com/levyvankempen/bonuschef/commit/e7febb496f34bef9eda4933506696e9ebb480910))


## v1.11.8 (2026-09-20)

### Bug Fixes

- **release**: A superseded run stands down instead of going red
  ([#73](https://github.com/levyvankempen/bonuschef/pull/73),
  [`86b0862`](https://github.com/levyvankempen/bonuschef/commit/86b0862e8576b8cc63b329b4d9bcffaae864deb9))


## v1.11.7 (2026-09-20)

### Bug Fixes

- **resolution**: Apply the naming test to links already in the database
  ([#72](https://github.com/levyvankempen/bonuschef/pull/72),
  [`c673fdd`](https://github.com/levyvankempen/bonuschef/commit/c673fdd7a715c72d233e4161abfbf51a0c3eb330))

### Chores

- Remove the code and tables nothing uses
  ([#71](https://github.com/levyvankempen/bonuschef/pull/71),
  [`f4e18a8`](https://github.com/levyvankempen/bonuschef/commit/f4e18a8665d8c20a604e5dcf742811bc49a6ea7e))


## v1.11.6 (2026-09-20)

### Bug Fixes

- **deploy**: Reclaim the build cache each deploy creates
  ([#69](https://github.com/levyvankempen/bonuschef/pull/69),
  [`84adc6a`](https://github.com/levyvankempen/bonuschef/commit/84adc6a710ba8336a3dc3cdc06e367820d43d59c))

- **matching**: Propose nothing when the best candidate is unrecognisable
  ([#70](https://github.com/levyvankempen/bonuschef/pull/70),
  [`ee51175`](https://github.com/levyvankempen/bonuschef/commit/ee51175e70df96546c1f15eed89ea90148bdad11))

### Documentation

- The backup restores, and this says what that does not prove
  ([#68](https://github.com/levyvankempen/bonuschef/pull/68),
  [`33f8ae3`](https://github.com/levyvankempen/bonuschef/commit/33f8ae3707ef081d1c7eb98efac82560e512b957))


## v1.11.5 (2026-09-20)

### Bug Fixes

- Bound what grows unattended, and ask a probe a real question
  ([#67](https://github.com/levyvankempen/bonuschef/pull/67),
  [`2030945`](https://github.com/levyvankempen/bonuschef/commit/2030945f333daffebb568524e1b12e3fa798e724))


## v1.11.4 (2026-09-20)

### Bug Fixes

- The warehouse declares what it holds, and a warn can pass
  ([#66](https://github.com/levyvankempen/bonuschef/pull/66),
  [`759a883`](https://github.com/levyvankempen/bonuschef/commit/759a8837861185b893720464efce079dc5cd3b8d))


## v1.11.3 (2026-09-20)

### Bug Fixes

- Three things the system computed and never showed
  ([#65](https://github.com/levyvankempen/bonuschef/pull/65),
  [`c7ce9a6`](https://github.com/levyvankempen/bonuschef/commit/c7ce9a6ffd1b25abbdac00fa5538e3956e8628ea))


## v1.11.2 (2026-09-20)

### Bug Fixes

- Classify what the local matcher proposes, and re-check adopted recipes
  ([#64](https://github.com/levyvankempen/bonuschef/pull/64),
  [`7c389c6`](https://github.com/levyvankempen/bonuschef/commit/7c389c6e012143c16171128ce1c82d5f35e61fef))


## v1.11.1 (2026-09-20)

### Bug Fixes

- One clearance unit is claimed once, and an offer keeps its key
  ([#63](https://github.com/levyvankempen/bonuschef/pull/63),
  [`254b9b8`](https://github.com/levyvankempen/bonuschef/commit/254b9b850d2268019ac8742e99ed275839a0112c))


## v1.11.0 (2026-09-20)

### Features

- A recipe you are shown can be kept ([#62](https://github.com/levyvankempen/bonuschef/pull/62),
  [`2097114`](https://github.com/levyvankempen/bonuschef/commit/2097114728ef7f6cbb30b8c6e742a6e2b8bd29b5))


## v1.10.2 (2026-09-20)

### Bug Fixes

- A promotion survives our never having priced the product
  ([#61](https://github.com/levyvankempen/bonuschef/pull/61),
  [`784ffe2`](https://github.com/levyvankempen/bonuschef/commit/784ffe2227380c4cb0bbfe067e048a1461f3a2da))


## v1.10.1 (2026-09-20)

### Bug Fixes

- An auth failure says where the credentials are, and is never an empty day
  ([#60](https://github.com/levyvankempen/bonuschef/pull/60),
  [`d0b3830`](https://github.com/levyvankempen/bonuschef/commit/d0b3830d834b756cf92a7e470bb5b55f631e645b))


## v1.10.0 (2026-09-20)

### Features

- A stand-in may replace a component's effects, not its interface
  ([#59](https://github.com/levyvankempen/bonuschef/pull/59),
  [`86d4130`](https://github.com/levyvankempen/bonuschef/commit/86d4130c8b9014e0eacb35fc020aec885ec2d2ee))


## v1.9.0 (2026-09-20)

### Features

- Check what a page reads against what its query returns
  ([#58](https://github.com/levyvankempen/bonuschef/pull/58),
  [`e81dd9c`](https://github.com/levyvankempen/bonuschef/commit/e81dd9cc54b105d95217119b64be8bf0374549bb))


## v1.8.1 (2026-09-20)

### Bug Fixes

- The portal's cache follows the data, not a wall clock
  ([#57](https://github.com/levyvankempen/bonuschef/pull/57),
  [`c3b7b93`](https://github.com/levyvankempen/bonuschef/commit/c3b7b93ab15fc0b8495345290f7b46028f2485c3))


## v1.8.0 (2026-09-20)

### Features

- Show what kind of thing each candidate is, and archive the change
  ([#56](https://github.com/levyvankempen/bonuschef/pull/56),
  [`69957af`](https://github.com/levyvankempen/bonuschef/commit/69957aff679861c173d371df71f594a1d4097884))


## v1.7.0 (2026-09-20)

### Bug Fixes

- The release can push past the gate it is subject to
  ([#55](https://github.com/levyvankempen/bonuschef/pull/55),
  [`91a0b24`](https://github.com/levyvankempen/bonuschef/commit/91a0b24db00dbdbfb876c38b3c2dd1c89f4e3103))

### Features

- A one-off backfill, for when the matching improves
  ([#54](https://github.com/levyvankempen/bonuschef/pull/54),
  [`94312be`](https://github.com/levyvankempen/bonuschef/commit/94312be69b41e7055d8c4a65618c3ad40e0e8dcf))

- Make a green check mean something ([#53](https://github.com/levyvankempen/bonuschef/pull/53),
  [`97ff1a1`](https://github.com/levyvankempen/bonuschef/commit/97ff1a122c5410ef1b32f50df4c7bb2dffa1740b))


## v1.6.0 (2026-09-19)

### Features

- Re-derive the products for concepts an older matcher settled
  ([#52](https://github.com/levyvankempen/bonuschef/pull/52),
  [`3eedde1`](https://github.com/levyvankempen/bonuschef/commit/3eedde1868515190153be5d85284fea5e385fb65))


## v1.5.0 (2026-09-19)

### Features

- Resolve ingredients by what a product is, not only what it is called
  ([#50](https://github.com/levyvankempen/bonuschef/pull/50),
  [`0f66503`](https://github.com/levyvankempen/bonuschef/commit/0f66503ecd92470e585697c8c920f4502ff938dc))


## v1.4.2 (2026-09-19)

### Bug Fixes

- The runner must find the checkout it no longer lives in
  ([#51](https://github.com/levyvankempen/bonuschef/pull/51),
  [`c4b5d36`](https://github.com/levyvankempen/bonuschef/commit/c4b5d36b63e48fe815b26ffff8c822c31093bbe6))


## v1.4.1 (2026-09-19)

### Bug Fixes

- The auto-deployer must outlive the releases it deploys
  ([#49](https://github.com/levyvankempen/bonuschef/pull/49),
  [`b446969`](https://github.com/levyvankempen/bonuschef/commit/b44696973847047e2bd5e8fc1309b03f3aa8ec29))


## v1.4.0 (2026-09-19)

### Documentation

- **openspec**: Sync and archive versioned-deployment
  ([#47](https://github.com/levyvankempen/bonuschef/pull/47),
  [`b3a5417`](https://github.com/levyvankempen/bonuschef/commit/b3a54177eb402a64487e3058b97db0d1432dcaec))

### Features

- Deploy the newest release automatically
  ([#48](https://github.com/levyvankempen/bonuschef/pull/48),
  [`75d3108`](https://github.com/levyvankempen/bonuschef/commit/75d31082735d2eb287f59dc78ed49fb52d3cc2b4))


## v1.3.1 (2026-09-15)

### Bug Fixes

- Two papercuts found deploying v1.3.0 ([#46](https://github.com/levyvankempen/bonuschef/pull/46),
  [`d37ffc6`](https://github.com/levyvankempen/bonuschef/commit/d37ffc6d111c31770eaa9cc2af2b4de9a380ab76))


## v1.3.0 (2026-09-15)

### Bug Fixes

- Deploy a version, and fix the release that never cut one
  ([#45](https://github.com/levyvankempen/bonuschef/pull/45),
  [`78cb0c8`](https://github.com/levyvankempen/bonuschef/commit/78cb0c8ce8dc5d890d3eda4de00ecd89a2629803))

### Features

- Clearance tracking, recipe opportunity ranking, and a live deployment
  ([#44](https://github.com/levyvankempen/bonuschef/pull/44),
  [`a1139db`](https://github.com/levyvankempen/bonuschef/commit/a1139dbb599a16e41c67584b8685f44970531d0c))


## v1.2.0 (2026-04-25)

### Features

- Add Kubernetes manifests for bonuschef deployment
  ([#42](https://github.com/levyvankempen/bonuschef/pull/42),
  [`a9dab17`](https://github.com/levyvankempen/bonuschef/commit/a9dab175f8b6c79970ceb6f9b3e04c37ed620571))


## v1.1.0 (2026-03-07)

### Features

- Containerize full stack with docker compose
  ([#41](https://github.com/levyvankempen/bonuschef/pull/41),
  [`a69a4c3`](https://github.com/levyvankempen/bonuschef/commit/a69a4c3f22ab6df89398af653619de6aac5721f4))


## v1.0.1 (2026-03-07)

### Bug Fixes

- Clean up semantic release config ([#40](https://github.com/levyvankempen/bonuschef/pull/40),
  [`b3d2aba`](https://github.com/levyvankempen/bonuschef/commit/b3d2abaf9a299e24621426ea55db90753204aada))


## v1.0.0 (2026-03-07)

- Initial Release
