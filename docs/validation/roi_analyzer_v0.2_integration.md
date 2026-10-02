# ROI Analyzer v0.2 Integration Foundation

## Purpose

This component is separate from the frozen generic dog-walker
detector v0.2.0.

Its purpose is to analyze person and dog trajectories relative to a
camera-specific target region after a dog-walker event has already
been detected.

The intended production use is a fixed trail camera observing a
problem location such as the base of a wall or column.

## Current environment limitation

No production trail-camera footage exists yet.

At this stage, the only available real video samples are the four
existing park validation videos.

Therefore:

- the park videos are used only for structural integration testing;
- they are not used to define the future condominium ROI;
- they are not evidence of condominium-site ROI performance;
- no production ROI thresholds have been calibrated.

## Analyzer behavior

The analyzer supports separate person and dog tracks.

The primary behavior subject is the dog, with the associated person
retained as context.

For each track, the analyzer can record:

- APPROACH
- ENTER_NEAR_ZONE
- ARRIVE_TARGET
- DWELL
- STOP
- DEPART

The ground-contact proxy is the bottom-center of the tracked bounding
box.

The camera-specific geometry is externalized in a JSON profile using:

- target_polygon_norm
- near_polygon_norm
- frame dimensions
- behavioral thresholds

## Synthetic state-machine validation

A synthetic trajectory was used to test the geometry/state-machine
logic independently of the four sample videos.

The required states were all produced:

- APPROACH
- ENTER_NEAR_ZONE
- ARRIVE_TARGET
- DWELL
- STOP
- DEPART

The STOP condition is based on a continuous low-speed run inside the
near zone rather than the median speed of the entire near-zone visit.

## Four-sample structural integration test

The existing official dog-walker event outputs and previously
generated tracks.csv files were used.

No YOLO inference or tracking was rerun.

Results:

- Validation 001: 2 events
- Validation 002: 3 events
- Validation 003: 4 events
- Validation 004: 6 events

Total:

- 15 official dog-walker events
- 17 referenced dog tracks

Every event had:

- an available person track;
- at least one referenced dog track;
- all referenced dog tracks available to the ROI analyzer.

Structural integration result:

`ROI_4_SAMPLE_INTEGRATION_OK`

## Important limitation

The integration test intentionally used the entire image as the
temporary target and near-zone polygon.

Therefore labels such as DOG_AT_TARGET generated during that smoke
test have no behavioral or performance meaning.

Real ROI validation must wait until an actual production camera is
purchased, installed, and representative footage is available.

## Frozen boundary

The official generic dog-walker detector v0.2.0 is not modified by
this ROI layer.
