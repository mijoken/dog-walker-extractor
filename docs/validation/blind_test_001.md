# Blind Validation 001

## Status

PASS

## Purpose

First blind validation of the generic Dog Walker Extractor pipeline.

Ground-truth dog-walking timestamps were withheld until after the
software produced its final dog-walker events.

## Test video

- Resolution: 1280 x 720
- Frame rate: 30 fps
- Frames: 27,714
- Duration: 923.8 seconds
- Test video is not stored in Git.

## Blind prediction

### Event 001

- Time: 14:05.80 - 14:11.23
- Duration: 5.43 s
- Person track: 201
- Dog track: 188
- Pair score: 0.652

### Event 002

- Time: 14:50.40 - 14:58.70
- Duration: 8.30 s
- Person track: 226
- Dog tracks: 258, 323
- Mean pair score: 0.729

## Ground-truth disclosure

Only after final event generation was the developer informed that
both detections were correct.

No known dog-walking timestamps were used beforehand to tune:

- detection confidence
- candidate windows
- pair scoring
- duration thresholds
- dog/person association
- event-merging logic

## Interpretation

This is a successful first blind validation, but represents only one
video and must not be treated as proof of general performance.

Current parameters should remain frozen until additional unseen videos
provide evidence for a generalizable change.

## Checkpoint

v0.1.0-blind-success
