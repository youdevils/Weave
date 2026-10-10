---
title: "What is OnyxJar?"
slug: what-is-onyxjar
summary: "A quick orientation to OnyxJar's living model: what it is, who it's for, and the core ideas you'll meet throughout these docs."
category: getting-started
nav_order: 1
status: published
keywords: [overview, model, living model, orientation]
related: [roles-and-permissions]
updated: "2026-10-01"
---

OnyxJar turns the connected parts of complex work into a structured, living
model that you can explore, change with confidence, and share.

## Who OnyxJar is for

OnyxJar is built for people who need to understand how the parts of a
complex system fit together, and who need that understanding to stay
trustworthy as things change.

!!! note "Beta"
    OnyxJar is in beta. The concepts below are stable; some workflows are
    still evolving.

## The core building blocks

| Term | What it means |
| --- | --- |
| Object | A single thing in your model: a process, a team, a system. |
| Connection | A relationship between two objects. |
| Change | A proposed or recorded modification to the model. |

## A minimal example

A tiny model can be described directly:

```text
Team "Platform" owns System "Billing"
System "Billing" supports Process "Invoice customers"
```

## Keep it current

!!! warning "Models are living documents"
    A model that is never updated stops being trustworthy. Review and
    publish changes regularly.
