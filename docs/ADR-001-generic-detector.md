# ADR-001: Generic Dog-Walker Detection

## Status

Accepted

## Goal

Detect "a person walking with a dog" in arbitrary fixed-camera video.

## Non-goals

The core detector must not identify:
- faces
- residents
- owners by identity
- specific locations

## Initial architecture

Object detector
    person
    dog

Multi-object tracker
    persistent person IDs
    persistent dog IDs

Association layer
    proximity
    direction similarity
    velocity correlation
    co-existence duration
    stop/start correlation
    assignment stability

Event layer
    converts frame-level associations into dog-walking events.

## Generalization rule

Changes based on test videos are accepted only when they represent
a general failure mode.

Location-specific coordinates, backgrounds or identities must never be
embedded in the generic detector.
