## ADDED Requirements

### Requirement: A list meant for recognition carries its imagery

Where the portal shows items a person matches against physical objects — products on a shelf, dishes to cook — it SHALL show the image the source provides. Where the source provides an image and the portal does not display it, that is a defect rather than a choice.

#### Scenario: Clearance items on a phone

- **WHEN** clearance items are shown
- **THEN** each carries its product image, so the list can be recognised rather than read

#### Scenario: The source has no image for an item

- **WHEN** no image is available for an item
- **THEN** the entry still renders, without a gap where a picture would be

#### Scenario: Imagery is not fetched while rendering

- **WHEN** images are shown
- **THEN** they were obtained when the data was collected, not requested from a third party during the render

### Requirement: Finding a recipe does not require knowing its name

The portal SHALL let a person find a recipe without first typing a search term. It SHALL offer the catalogue's own recipes on arrival, ordered by something useful, and SHALL let that ordering be changed.

#### Scenario: Arriving with nothing in mind

- **WHEN** a person opens the page to add a recipe and types nothing
- **THEN** recipes are already shown, and any of them can be adopted

#### Scenario: Choosing what to see

- **WHEN** a person wants what is new rather than what is popular
- **THEN** the ordering can be changed between the options the catalogue supports

#### Scenario: Searching still works

- **WHEN** a person types a search term
- **THEN** the results for that term replace the browsable list

#### Scenario: The catalogue is unreachable

- **WHEN** the catalogue cannot be reached on arrival
- **THEN** the person is told so, rather than shown an empty page that reads as having no recipes
