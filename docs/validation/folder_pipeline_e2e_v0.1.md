# Folder Pipeline End-to-End Validation

## Scope

This validation confirms the production-style folder / SD-card entry
pipeline around the official generic dog-walker detector v0.2.0.

It does not validate a condominium ROI because no production trail
camera or production camera footage exists yet.

## Input

Existing sample:

`sample_data/park_test.mp4`

Duration:

- 923.8 sec
- approximately 15.4 minutes
- 1280x720
- 30 fps

Only this shortest sample was rerun to avoid unnecessary repeated
computation.

## Pipeline

The test exercised the complete non-ROI application path:

1. folder video discovery
2. official v0.2 coarse dog scan
3. precision tracking
4. track-quality audit
5. official v0.2 dog-person association
6. dog-walker event generation
7. review clip generation
8. per-video run manifest
9. batch JSON summary
10. batch CSV summary

## Result

Folder pipeline:

- videos processed: 1
- successful videos: 1
- failed videos: 0
- final dog-walker events: 2
- generated review clips: 2

Final events:

- Event 001: 14:05.80 - 14:11.23
- Event 002: 14:50.40 - 14:58.70

The output agrees with the established result for this validation
sample.

Completion markers:

- `VALIDATION_RUNNER_OK`
- `FOLDER_PIPELINE_OK`

## Runtime observation

The coarse scan took approximately 584 seconds.

The five precision candidate tracking passes took approximately:

- 36.98 sec
- 33.13 sec
- 38.44 sec
- 40.86 sec
- 55.95 sec

This runtime observation is descriptive only and is not a formal
performance benchmark.

## ROI status

ROI analysis was disabled for this run.

The ROI layer has already passed separate synthetic state-machine and
four-sample structural integration tests, but production ROI
validation must wait for an actual fixed trail-camera view.

## Conclusion

The application-level folder entry path can now take a real folder
containing video, process it through the official dog-walker detector
v0.2.0, generate review clips, and produce machine-readable batch
summaries.

This establishes the non-GUI operational foundation for SD-card use.
