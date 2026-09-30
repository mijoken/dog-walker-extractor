# Dog Walker Extractor

Generic video-analysis software for detecting dog-walking events.

## Core principle

The detector must NOT depend on:

- a specific camera
- a specific park
- a specific building
- a fixed camera angle
- a specific dog
- a specific person

A dog-walking event is modeled as a temporal relationship between:

1. a detected person
2. a detected dog
3. persistent spatial proximity
4. correlated motion
5. temporal continuity

## Planned pipeline

Video
 -> Object Detection
 -> Multi Object Tracking
 -> Person/Dog Track Association
 -> Dog-Walker Relationship Scoring
 -> Event Consolidation
 -> Video Clip Extraction
 -> GUI

## Development policy

Validation videos are test data, not training data.

Site-specific logic such as a condominium wall ROI must remain separate
from the generic dog-walker detection engine.
