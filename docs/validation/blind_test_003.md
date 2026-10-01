# Blind Validation 003

## Status

OUT-OF-SAMPLE VALIDATION COMPLETED

The frozen v0.1 detection and association logic was used without
parameter changes.

## Test video

- File: park_test3.mp4
- Resolution: 1280 x 720
- Frame rate: 30 fps
- Frames: 62,989
- Duration: 2,099.63 seconds
- Approximate duration: 34 minutes 59.63 seconds
- Video is not stored in Git.

## Frozen pipeline

The validated v0.1 configuration was retained:

- YOLO model: yolo11n.pt
- Coarse scan image size: 640
- Coarse scan confidence: 0.15
- Coarse scan stride: 5
- Precision analysis image size: 640
- Precision analysis confidence: 0.10
- Association algorithm: V2
- Minimum pair score: 0.55
- Minimum pair span: 1.0 s
- Minimum dog frames: 5
- Event merge gap: 1.5 s

No parameter was changed after seeing this video's result.

## Coarse candidate windows

Eleven candidate windows were produced:

1. 09:09.50 - 09:19.50
2. 09:46.50 - 09:57.67
3. 10:01.33 - 10:12.00
4. 10:22.50 - 10:38.67
5. 13:56.50 - 14:06.50
6. 18:27.00 - 18:37.00
7. 19:20.33 - 19:43.17
8. 20:57.17 - 21:11.33
9. 21:04.67 - 21:14.67
10. 21:56.83 - 22:07.83
11. 22:53.67 - 23:07.00

## Frozen final predictions

Four internal events were produced:

### Event 001

- Source candidate: 004
- Time: 10:29.60 - 10:32.40
- Person track: 114
- Dog track: 263
- Pair score: 0.771

### Event 002

- Source candidate: 007
- Time: 19:26.20 - 19:30.97
- Person track: 151
- Dog track: 148
- Pair score: 0.643

### Event 003

- Source candidate: 007
- Time: 19:26.97 - 19:30.50
- Person track: 117
- Dog track: 170
- Pair score: 0.643

### Event 004

- Source candidate: 007
- Time: 19:30.87 - 19:38.47
- Person track: 253
- Dog tracks: 281, 295
- Mean pair score: 0.690

## Human review

### Candidate 001

No dog walker.

A woman wearing a brown, fluttering/frilled skirt passed through the
scene.

The frilled portion visually resembles a dog and is a plausible source
of the coarse dog proposal.

Final system result: rejected.

### Candidate 002

Dog walker present.

A person entered from the lower-left portion of the frame. A walking
lead was visible, followed by the dog becoming partly visible before
leaving the frame.

This is the first visible portion of the same dog-walking passage that
continues through Candidates 003 and 004.

Final system result: rejected.

### Candidate 003

Dog walker present.

This is a continuation of Candidate 002 and contains the same person
and dog.

Final system result: rejected.

### Candidate 004

Dog walker present.

This is the same person and dog seen in Candidates 002 and 003, now
visible farther away in the scene.

Final system result: accepted.

Classification at candidate-window level: true positive.

### Candidate 005

No dog walker.

A person in the center of the image picked up a brown handbag that had
been placed on the ground and then walked away.

The handbag can visually resemble a dog.

Final system result: rejected.

### Candidate 006

No dog walker.

A runner passed close to the camera.

Final system result: rejected.

### Candidate 007

Dog walker present.

One person was walking two dogs.

The frozen pipeline produced three accepted internal events during this
single human-observed passage.

Final system result: accepted.

Classification at candidate-window presence level: true positive.

The multiple internal events represent over-segmentation of one
human-observed dog-walking passage.

### Candidate 008

No dog walker.

A person carrying a brown handbag and another person pulling a wheeled
case passed through the scene.

Final system result: rejected.

### Candidate 009

No dog walker.

A person carrying a brown handbag passed in the distant background.

Final system result: rejected.

### Candidate 010

No dog walker.

A person carrying a brown handbag was again visible in the scene.

Final system result: rejected.

### Candidate 011

No dog walker.

A person pushing a stroller passed in the distant background.

Final system result: rejected.

## Candidate-window evaluation

At the coarse-candidate-window level:

- True Positive: 2
- False Positive: 0
- False Negative: 2
- True Negative: 7

Candidate-window precision:

100%

Candidate-window recall:

50%

This metric intentionally treats Candidates 002, 003, and 004 as
separate candidate windows even though human review determined that
they are one continuous real-world dog-walking passage.

It therefore understates passage-level detection performance.

## Passage-level interpretation

Human review identified two dog-walking passages among the candidate
windows:

1. One dog walker continuing through Candidates 002, 003, and 004.
2. One person walking two dogs in Candidate 007.

The first passage was missed in Candidates 002 and 003 but was detected
later in Candidate 004.

The second passage was detected in Candidate 007.

Therefore both human-observed dog-walking passages were detected at
least once by the frozen pipeline.

This can be described as a provisional passage-level hit count of 2/2.

However, the full video was reviewed only approximately rather than
through exhaustive frame-by-frame ground-truth annotation.

For that reason, 2/2 must not be presented as a definitive whole-video
recall estimate.

## Observed failure and success modes

### Short / partial dog visibility

Candidates 002 and 003 contained a real dog walker but produced only
short dog tracks and low final association scores.

The same real-world passage was eventually recovered in Candidate 004
when a more stable dog/person track became available.

This indicates that the current system can miss the beginning of a
passage while still detecting the passage later.

### Over-segmentation

Candidate 007 contained one person walking two dogs.

The pipeline emitted three final internal events for that one
human-observed passage.

This is an event-consolidation issue rather than a failure to detect
the presence of a dog walker.

### False coarse proposals successfully rejected

Several visually plausible dog-like objects or motions generated coarse
candidate windows:

- fluttering/frilled skirt,
- brown handbag,
- runner,
- wheeled case,
- stroller.

None of these became final dog-walker events.

This supports the observation that the frozen v0.1 pipeline remains
precision-oriented at the final decision stage.

## Development decision

No detection threshold, association score, duration rule, tracking
parameter, or event-merging rule will be changed based solely on Blind
Validation 003.

In particular:

- Candidates 002 and 003 will not be recovered by lowering the current
  pair-score threshold solely for this video.
- Candidate 007 will not trigger a special-case merge rule solely for
  this video.
- The skirt, handbag, wheeled case, runner, and stroller cases will not
  be used to create scene-specific exclusion rules.

These observations will instead be compared with additional unseen
videos.

Algorithm changes should be considered only when repeated validation
evidence reveals a generalizable failure pattern.

## Conclusion

Blind Validation 003 provides additional evidence that frozen v0.1 is
conservative at the final event stage.

It successfully rejected multiple visually dog-like false coarse
proposals and detected both dog-walking passages observed during the
manual review.

The main remaining behaviors are:

- delayed detection when dog visibility is short or partial;
- event over-segmentation when one person walks multiple dogs or track
  identities fragment.

The pipeline remains frozen pending further out-of-sample validation.
