## ADDED Requirements

### Requirement: An image carries the version it was built from

A built image SHALL record the version and the commit it was built from,
where both a running container and an operator inspecting the image can read
them. An image built from a working tree with uncommitted or unpushed changes
SHALL say so rather than claiming the version it is closest to.

#### Scenario: An image built from a released tag

- **WHEN** an image is built from a checkout at a released tag
- **THEN** it reports that version and that commit

#### Scenario: An image built from a modified tree

- **WHEN** an image is built from a checkout carrying changes that are not committed
- **THEN** what it reports marks it as such, so it is not mistaken for the release it resembles

#### Scenario: Inspecting an image without running it

- **WHEN** an operator inspects a built image
- **THEN** the version and commit are readable from its metadata
