# Blind Validation 002

## Status

OUT-OF-SAMPLE VALIDATION COMPLETED

No algorithm thresholds or scoring parameters were changed after
Blind Validation 001.

## Purpose

Evaluate the frozen generic Dog Walker Extractor pipeline on a second
previously unseen video.

The operator had not reviewed the video in advance and did not know
whether dog walkers were present.

This test therefore allowed a valid zero-event outcome as well as
positive detections.

## Test video

- File: park_test2.mp4
- Resolution: 1280 x 720
- Frame rate: 30 fps
- Frames: 36,003
- Duration: 1,200.1 seconds
- Video is not stored in Git.

## Frozen pipeline

The same model and parameters used after Blind Validation 001 were
retained:

- YOLO model: yolo11n.pt
- Coarse dog scan confidence: 0.15
- Coarse scan stride: 5
- Precision analysis confidence: 0.10
- Association algorithm: V2
- Minimum pair score: 0.55
- Minimum pair span: 1.0 s
- Minimum dog frames: 5
- Event merge gap: 1.5 s

No threshold was changed to improve this video's result.

## Coarse candidate windows

Eight candidate windows were generated:

1. 02:21.67 - 02:31.67
2. 03:32.17 - 03:42.17
3. 04:58.17 - 05:08.17
4. 08:14.17 - 08:24.17
5. 12:44.67 - 12:54.67
6. 15:52.17 - 16:04.17
7. 17:55.00 - 18:12.50
8. 18:16.00 - 18:26.00

## Human review of candidate windows

### Candidate 001

No dog walker.

The source of the coarse dog detection could not be identified by
visual review.

Final system result: rejected.

### Candidate 002

No dog walker.

A woman in a short skirt was present. The coarse detector may have
temporarily misclassified part of the lower body, but this is not
proven.

Final system result: rejected.

### Candidate 003

No dog walker.

A person pushing a stroller was present.

Final system result: rejected.

### Candidate 004

No dog walker.

Two bicycles passed the camera at approximately 08:14.17.

Final system result: rejected.

### Candidate 005

No dog walker.

A small child was jumping/moving in the scene.

Final system result: rejected.

### Candidate 006

Dog walker present.

The dog/person pair was detected but rejected by the frozen final
threshold.

Key association result:

- Dog track: 123
- Person track: 85
- Pair score: 0.509
- Pair span: 1.33 s
- Dog frames: 41
- Dog continuity: 1.000
- Dog mean confidence: 0.790
- Median normalized distance: 0.58
- Direction score: 0.971

The dog entered from the right side of the image and was primarily
visible from behind.

The direct reason for rejection was the final pair score being below
the frozen 0.55 threshold. The short visible duration is considered a
possible contributor.

Classification: false negative at final event decision stage.

### Candidate 007

Dog walker present.

The frozen system accepted two internal events:

- 17:59.47 - 18:01.80
  - Person track 116
  - Dog track 121
  - Pair score 0.627

- 18:03.00 - 18:07.97
  - Person track 161
  - Dog track 181
  - Pair score 0.746

Human review confirmed that a dog walker was present.

The two system events may represent fragmentation of one real-world
passage due to track-ID changes.

Classification: true positive at candidate-window presence level,
with possible over-segmentation.

### Candidate 008

Dog walker present.

This was the same dog walker from Candidate 007 returning into the
camera view.

Precision tracking retained only one dog frame:

- Dog track: 24
- Dog frames: 1

No valid person/dog association was therefore produced.

Classification: false negative caused before final association/event
generation.

## Candidate-window evaluation

This evaluation is conditional on the eight candidate windows produced
by the coarse scan.

It is NOT an estimate of whole-video recall because the full video was
not exhaustively frame-annotated for every possible missed dog walker.

At candidate-window level:

- True Positive: 1
- False Positive: 0
- False Negative: 2
- True Negative: 5

Candidate-window precision:

100%

Candidate-window recall:

33.3%

These figures must not be interpreted as the expected production
performance of the system.

## Generalizable observations

The frozen pipeline showed strong rejection of coarse false positives.

All five visually negative candidate windows were rejected by the final
pipeline.

Two different false-negative mechanisms were observed:

1. A real dog/person pair existed but the short temporal span reduced
   the final association score below the frozen threshold.

2. A returning dog walker was missed because the dog track survived
   for only one frame, preventing meaningful association.

A further issue was observed where one real-world dog-walking passage
appeared as two system events due to person/dog track fragmentation.

## Development decision

No parameter tuning will be performed based solely on this video.

In particular:

- the pair-score threshold will not be lowered from 0.55 merely to
  recover Candidate 006;
- minimum-duration requirements will not be weakened merely to recover
  Candidate 008;
- track-merging rules will not be modified solely to make Candidate 007
  appear as one event.

These failure modes will instead be compared against additional unseen
videos.

Changes will be considered only if repeated evidence indicates a
generalizable improvement.

## Interpretation

Blind Validation 001 demonstrated that the pipeline can correctly
detect dog-walking events in an unseen video.

Blind Validation 002 demonstrated both successful filtering of false
coarse detections and realistic failure modes in short or fragmented
tracks.

The current system should therefore remain frozen for further
out-of-sample validation before optimization.
