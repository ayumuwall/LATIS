# LATIS

**Layered Agreement, Traceability & Intent System**  
**An Agreement Engine.**

LATIS is an experimental open-source system for structuring, tracing, and operating agreements in software development.

It starts from a simple observation: specification-driven development works unusually well with AI-assisted coding, but it does not scale gracefully once specifications grow, branch, overlap, and begin to affect one another.

Markdown documents remain readable, but they are a poor unit for retrieval, impact analysis, and agent context construction. LATIS explores a different approach: treat agreements, intent, rationale, open questions, and dependencies as first-class structured objects, then render human-readable artifacts from that system when needed.

This project is for people who take AI coding seriously, and for those who still believe specification-driven development has not yet reached its practical limit.

## Why LATIS

Modern AI coding workflows are strong at local execution and weak at durable shared context.

As projects grow, teams and agents alike run into the same problems:

- specifications are readable, but hard to query precisely
- related decisions are scattered across documents, code, and discussion
- unresolved questions are easy to lose
- rationale fades faster than the text that remains
- every meaningful change risks pulling too much irrelevant context into the prompt
- impact is often guessed rather than traced

LATIS is an attempt to make specification-driven development more scalable, without giving up the clarity that made it attractive in the first place.

## Core idea

LATIS does not treat a document as the fundamental unit.

Instead, it models development knowledge as a layered agreement structure:

- **Agreement** — what has been decided
- **Intent** — what the system or change is trying to achieve
- **Traceability** — what connects to what, and why
- **Rationale** — why a decision exists in its current form
- **Open questions** — what is still unresolved
- **Impact** — what is affected when something changes
- **Scope** — how local structures roll up into larger conceptual layers

Documents still matter. They are just no longer the only place where meaning lives.

## What LATIS aims to provide

### 1. A canonical agreement model
A structured representation for decisions, constraints, questions, relationships, and history.

### 2. Traceable change
A way to answer questions like:

- What does this decision depend on?
- What does this proposal affect?
- Which unresolved questions block this change?
- Why was this agreed in the first place?

### 3. Context for AI agents
Instead of handing an agent an entire folder of specifications, LATIS should be able to assemble a compact context pack containing only the agreements relevant to the current task.

### 4. Human-readable views
Markdown is not rejected. It is demoted from canonical storage to one possible rendering.

### 5. Scope-aware visualization
Large graphs are not useful if they collapse into noise. LATIS aims to support layered scopes, local graph views, impact lenses, and history-aware exploration.

## Design principles

### Agreement-first
The system should preserve what was agreed, what remains open, and what supports each decision.

### Layered, not flat
Software structure is easier to understand through scopes and layers than through one global graph.

### Traceability over guesswork
The system should make impact and dependency visible rather than implicit.

### Human-readable by default
Even if the internal model is structured, exported artifacts should remain easy to inspect, review, diff, and discuss.

### AI-compatible, not AI-dependent
LATIS should benefit from embeddings, clustering, reranking, and language models where useful, but the core data model should not depend on opaque generation.

## Proposed schema

### What is treated as essential

The current design treats the following as difficult to substitute later, and therefore worth supporting explicitly:

- stable identity
- typed nodes
- typed directed relations
- provenance
- revision history
- layered scope structure

This is why LATIS does not model scopes as a simple tag or category. In LATIS, a scope is a structural node: something that can group agreements, participate in hierarchy, and become the basis for navigation, retrieval, and impact analysis.

### Core entities

LATIS can begin with four canonical tables.

#### `nodes`
Stores the first-class units of meaning.

Representative fields:

- `id`
- `kind`
- `title`
- `body`
- `state`
- `created_at`
- `updated_at`

Typical node kinds may include:

- `agreement`
- `question`
- `scope`
- `intent`
- `rationale`
- `artifact`
- `task`

The exact set can evolve. What matters is that the model can distinguish kinds without changing its shape.

#### `relations`
Stores typed directed connections between nodes.

Representative fields:

- `id`
- `from_node_id`
- `to_node_id`
- `relation_kind`
- `state`
- `priority`
- `is_inferred`

Representative relation kinds may include:

- `contains`
- `depends_on`
- `conflicts_with`
- `supports`
- `scoped_to`
- `governs`
- `specializes`
- `exception_to`

The important decision here is not the final vocabulary but the fact that relations are explicit, directed, and typed.

#### `provenance`
Stores where something came from, who introduced it, and why it exists.

Representative fields:

- `id`
- `target_type`
- `target_id`
- `actor`
- `source_ref`
- `reason`
- `created_at`

This exists because rationale is too important to leave implicit, but does not necessarily require a separate top-level document every time.

#### `revisions`
Stores historical change.

Representative fields:

- `id`
- `target_type`
- `target_id`
- `change_type`
- `snapshot`
- `created_at`

This exists because LATIS is not only interested in current agreement state. It also needs to support proposal views, history tracing, and change-oriented visualization.

## Why scopes are modeled as nodes

A scope in LATIS is not just a label such as `Inbox` or `Search`.

If scopes were only categories, they could classify nodes, but they could not do much else. They would not naturally support hierarchy, local zooming, named structural grouping, or scoped impact traversal.

By treating a scope as a node, LATIS can express things like:

- `Message List` is part of `Inbox Experience`
- `Inbox Experience` is part of `Messaging`
- a single agreement belongs to both a feature scope and a concern scope
- a scope can be auto-generated, renamed, described, and revised

This makes scope less like a flat tag and more like a lightweight structural junction. It does not need to behave like a rule itself, but it becomes a meaningful unit for exploration and retrieval.

## Retrieval shape

The retrieval layer should not operate on whole documents by default. It should assemble compact context bundles from the graph.

A minimal bundle might include:

- the target agreement or proposal
- directly connected decisions and constraints
- unresolved questions in the same scope
- relevant rationale
- nearby impact candidates
- a short scope summary

One of the reasons LATIS exists is to make less text sufficient.

## Initial implementation path

A realistic early implementation could use:

- SQLite for canonical storage
- FTS for lexical retrieval
- optional vector search for semantic lookup
- Markdown as an import/export format rather than the only source of truth

This keeps the early system inspectable and lightweight while preserving a path toward larger-scale retrieval backends later.

## Non-goals

LATIS is not intended to be:

- a replacement for version control
- a universal project management suite
- a pure graph visualization toy
- a document editor with a graph attached
- a system that assumes AI output is authoritative

## Early direction

The initial exploration is centered on these questions:

1. Can specification-driven development remain practical at larger scale if agreements are stored structurally rather than only as Markdown?
2. Can agent context be reduced to the minimum relevant agreement set without losing critical intent?
3. Can changes be reviewed through impact and rationale rather than raw text diff alone?
4. Can layered scopes become a better interface than a single global dependency graph?

## Relationship to OpenSpec

LATIS is conceptually related to specification-driven workflows such as OpenSpec, but it is not limited to document-first artifact storage.

A nearby experiment may exist as an OpenSpec-oriented extension or fork. LATIS is the broader idea: a system for managing agreements, traceability, intent, and scope as a first-class substrate for human and AI collaboration.

## Current status

This project is in the design and prototyping phase.

Current work includes:

- data model exploration
- agreement graph and scope tree concepts
- impact-oriented UI mockups
- proposal and history visualization ideas
- research into traceability, design rationale, and structured specification workflows

## Why open source

LATIS should be inspectable.

A system that stores decisions, rationale, and intent should not ask its users to trust a black box. The structure should be visible, the model should be discussable, and the assumptions should remain open to revision.

Open source is also the natural environment for this kind of tool: one where serious practitioners can challenge the model, improve the abstractions, and test whether this approach actually makes software development more legible.

## Long-term view

The ambition here is restrained, but not small.

If software development is increasingly mediated by agents, then shared intent, durable rationale, and scoped agreement will matter more, not less. LATIS is a small attempt to build infrastructure for that future.

Not to replace thinking, but to keep it from dissolving into scattered files, prompts, and forgotten decisions.

## Contributing

Ideas, criticism, and architectural objections are welcome.

The most useful early contributions are likely to be:

- criticism of the core model
- comparisons to existing research and tools
- concrete workflow examples
- counterexamples where the agreement model breaks down
- prototype implementations of storage, retrieval, or rendering layers

## Status note

Everything may change, including the model itself.

That is part of the point.
