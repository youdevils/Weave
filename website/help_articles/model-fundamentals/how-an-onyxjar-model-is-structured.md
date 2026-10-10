---
title: "How an OnyxJar model is structured"
slug: "how-an-onyxjar-model-is-structured"
summary: "Understand the main building blocks of an OnyxJar model and how they fit together."
category: "model-fundamentals"
nav_order: 1
status: published
keywords:
  - model structure
  - object types
  - objects
  - relationship types
  - relationships
  - attributes
related: []
updated: "2026-10-10"
---

# How an OnyxJar model is structured

An OnyxJar model describes a subject area using defined kinds of things, individual things, and the connections between them. Attributes record useful details about those things and, where supported, their relationships.

The distinction between a definition and an individual item is important. Definitions give a model a consistent structure; the objects and relationships in the model represent the particular subject you are describing.

## The main building blocks

| Building block | What it means | Example |
| --- | --- | --- |
| **Object type** | Defines a kind of thing that can appear in the model. | Application, Project, Team |
| **Object** | Represents one particular thing of an object type. | A specific application or project |
| **Relationship type** | Defines a kind of connection that can be represented between objects. | A project contains a workstream |
| **Relationship** | Records a particular connection between objects. | Project A contains Workstream B |
| **Attribute** | Records a detail about an object or, where configured, a relationship. | Purpose, status, criticality |

These pieces work together. An object type defines the kind of item; an object is an instance of that type. A relationship type defines a kind of connection; a relationship records that connection between particular objects.

## Definitions and model content

A model contains both its structure and the actual content entered into that structure.

The definitions provide consistency. For example, an object type can establish that applications are a kind of thing the model tracks and specify the attributes used to describe them. Individual application objects then record the particular applications in the subject area.

Similarly, a relationship type describes a kind of connection, while individual relationships connect the relevant objects. This makes connections explicit rather than leaving them implied in descriptions or separate lists.

## Attributes add detail

Relationships show how parts of a model connect; attributes record details that help people understand them.

An object might have attributes such as a description, status or purpose. The attributes available depend on how its object type is defined. Some attributes can use specified choices or allowed values, helping keep entries consistent.

Relationship types can also have attributes where the model defines them. This is useful when a connection itself needs information, rather than only the objects at either end.

## How the pieces fit together

Imagine modelling a project and its workstreams:

- An **object type** defines what a Project is.
- An **object** represents a particular project.
- Another object type defines Workstreams, and individual workstream objects represent the work being organised.
- A **relationship type** defines how a project connects to a workstream.
- A **relationship** records which workstream belongs to the project.
- Attributes record useful details, such as a project's purpose or a workstream's status, where those attributes are defined.

The graph can make these connections easier to see, but the graph is a view of the model's underlying structure and content. The model is not just the picture: it also includes the definitions, attributes and connections that give the picture meaning.

## Start with the question you need to answer

You do not need to model every detail of a subject area. Start by identifying the kinds of things that matter, the details you need to record, and the connections that help answer your questions.

As the model develops, keep its definitions and content aligned. Use object types and relationship types to provide a consistent structure, and add objects, relationships and attributes that represent the part of the world you need to understand.
