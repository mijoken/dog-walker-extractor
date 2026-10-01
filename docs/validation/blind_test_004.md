# Blind Validation 004 - Human Review

## Status

Predictions were frozen before human review.

Input:

`sample_data/park_test4.mp4`

Video duration:

approximately 66 minutes.

## Frozen predictions

v0.1 produced 5 final events.

v0.2 Experiment A produced 6 final events.

The only additional v0.2-exp-A event was:

- 04:23.57 - 04:24.87
- Person track 84
- Dog track 124
- Pair score 0.551

This event was not accepted by frozen v0.1.

## Human-reviewed candidate windows

### Candidate 001
04:18.50 - 04:30.50

DOG WALKER PRESENT.

A dog walker enters from the right edge of the frame.
Rear view.
The v0.2-exp-A-only event is a true positive.

### Candidate 002
06:19.17 - 06:39.17

DOG WALKER PRESENT.

A somewhat distant dog walker is visible.
The dog appears dark/black and is visually difficult to distinguish.

### Candidate 003
06:42.50 - 06:52.50

DOG WALKER PRESENT.

Continuation of the same dog walker seen in Candidate 002,
now closer to the camera.

### Candidate 004
17:34.17 - 17:46.50

NO DOG WALKER CONFIRMED.

Fluttering/frilled lower clothing can superficially resemble a dog.

### Candidate 005
18:13.50 - 18:24.67

DOG WALKER PRESENT.

Rear-view dog walker enters very close to the camera from the left edge.
Visually difficult case.

### Candidate 006
18:28.33 - 18:39.00

DOG WALKER PRESENT.

Same dog walker as Candidate 005.

### Candidate 007
18:49.50 - 19:05.67

DOG WALKER PRESENT.

Same dog walker as Candidates 005/006, now farther from the camera.

### Candidate 008
22:23.50 - 22:33.50

NO DOG WALKER CONFIRMED.

A person lifts and carries a brown handbag.
The scene can superficially resemble a person walking a brown dog.

### Candidate 009
26:54.00 - 27:04.00

NO DOG WALKER CONFIRMED.

A runner is visible at large scale.
No dog confirmed.

### Candidate 010
27:47.33 - 28:10.33

DOG WALKER PRESENT.

One person walking two dogs.

### Candidate 011
29:24.17 - 29:38.33

NO DOG WALKER CONFIRMED.

A person pulls a wheeled suitcase.
The appearance is highly similar to a dog-walking scene,
even on manual visual inspection.

### Candidate 012
30:23.83 - 30:33.83

NO DOG WALKER CONFIRMED.

The source of the coarse dog proposal is unclear.

### Candidate 013
31:18.67 - 31:34.00

NO DOG WALKER CONFIRMED.

The source of the coarse dog proposal is unclear.

### Candidate 014
56:56.33 - 57:06.33

NO DOG WALKER CONFIRMED.

A handbag can superficially resemble a dog-walking scene.

## Candidate-window review summary

Human-positive candidate windows:

- 001
- 002
- 003
- 005
- 006
- 007
- 010

Human-negative candidate windows:

- 004
- 008
- 009
- 011
- 012
- 013
- 014

## Passage-level interpretation

The positive candidate windows correspond to four human-observed
dog-walking passages:

- Passage A: Candidate 001
- Passage B: Candidates 002/003
- Passage C: Candidates 005/006/007
- Passage D: Candidate 010

Frozen v0.1 detected at least one event in 3 of these 4 passages.

v0.2 Experiment A detected at least one event in all 4 of these
4 passages.

Neither algorithm produced a final dog-walker event in the seven
human-reviewed negative candidate windows.

This passage-level result applies only to the reviewed coarse-candidate
windows. It must not be interpreted as exhaustive whole-video recall,
because the entire 66-minute video was not frame-by-frame annotated.

## Low-light question

The latter part of the source video becomes progressively darker,
although obvious night-like darkness occurs mainly after approximately
60 minutes.

Several later coarse proposals failed to form stable precision dog
tracks.

A separate quantitative lighting audit is therefore required before
attributing the degradation specifically to illumination.

No algorithm parameter is changed as part of this audit.

## Quantitative lighting audit

A frame-level luminance audit was run after the blind predictions and
human review had already been frozen.

For Candidates 001-013, mean grayscale luminance remained in a
relatively narrow range of approximately 133-141.

Examples:

- Candidate 001:
  - mean luminance: 138.84
  - dark-pixel ratio (<64): 0.208
  - longest dog track: 1.30 s
  - detection frames: 40
  - mean dog confidence: 0.799

- Candidate 005:
  - mean luminance: 138.33
  - longest dog track: 1.03 s
  - detection frames: 19
  - mean dog confidence: 0.327

- Candidate 006:
  - mean luminance: 136.38
  - longest dog track: 0.73 s
  - detection frames: 7
  - mean dog confidence: 0.427

- Candidate 010:
  - mean luminance: 133.21
  - longest dog track: 10.73 s
  - detection frames: 299
  - mean dog confidence: 0.666

Candidate 014 was qualitatively different:

- mean luminance: 95.66
- median luminance: 77.40
- dark-pixel ratio (<64): 0.385
- no stable precision dog track

### Interpretation

The deterioration seen across Candidates 008-013 cannot be explained
primarily by overall scene darkness, because their luminance remained
close to earlier candidates.

The evidence instead points toward viewpoint, object scale, occlusion,
edge-of-frame appearance, and dog-like non-dog objects such as bags,
clothing, and wheeled luggage as important contributors.

Candidate 014 provides separate evidence that genuinely low-light
conditions begin to become materially different later in the video.

Therefore low-light performance should be treated as a separate future
validation topic rather than used to explain all later false coarse
proposals in Validation 004.
