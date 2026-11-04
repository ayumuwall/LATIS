# LATIS

**Retrieval clarification, 2026-11-04:** Spec §8.4 and Design Decisions §10 describe how future reasoning-based retrieval, including DecisionRAG-style navigation, can supply candidates while keeping agreement records, revisions, and adoption checks authoritative. Generated retrieval hierarchies remain rebuildable derived data. The nine operations, wire contract, and required exhibition scope are unchanged.

**Layered Agreement, Traceability & Intent System**  
**An Agreement Engine.**

- Version: v0.3-demo-draft
- Updated: 2026-11-04, Japan Standard Time
- Target: implementation specification for the exhibition on 2026-11-07 JST.
- 状況：P0とP1の参照実装とClaude CLIでの利用確認が進んでいます。完全実装・性能達成の最終判定は未完了です。導入・結果・残作業はソースリポジトリの [実装ガイド](https://github.com/ayumuwall/LATIS/blob/main/docs/IMPLEMENTATION.ja.md)、[受け入れ記録](https://github.com/ayumuwall/LATIS/blob/main/docs/ACCEPTANCE.ja.md)、[タスク管理票](https://github.com/ayumuwall/LATIS/blob/main/docs/TASKS.ja.md) を参照してください。
- [日本語](README.ja.md)

## What we are building

LATIS is an agreement engine that an LLM can use when it needs to retrieve agreements, compare a request with previous decisions, and record a change with its rationale.
It aims to preserve what people and agents decided and checked as development continues across models and sessions.
Users make ordinary requests; the LLM decides when to use LATIS as it would other tools such as Git. Routine use requires neither human CLI operation nor a LATIS preflight for every task.

Agreement text remains in natural language. IDs, revisions, states, explicit relations, sources, and decision history provide reusable structure.
The calling LLM interprets meaning and asks the user only for choices that existing instructions leave unresolved.

## The nine documents and reading order

| Document | Role |
| --- | --- |
| [README.ja.md](README.ja.md) | Japanese introduction, scope, and document precedence. |
| [README.md](README.md) | The equivalent English introduction. |
| [LATIS_Spec.md](LATIS_Spec.md) | Core model, meaning, guarantees, and responsibility boundaries. |
| [LATIS_API.md](LATIS_API.md) | Concrete JSON and CLI contracts, consultation, application, errors, and retries. |
| [LATIS_Operation.md](LATIS_Operation.md) | Everyday retrieval, recording, negotiation, maintenance, and external observations. |
| [LATIS_LLM_Guide.md](LATIS_LLM_Guide.md) | Maintained instructions for an LLM to use LATIS and search iteratively. |
| [LATIS_Prototype_Plan.md](LATIS_Prototype_Plan.md) | November 4–7 implementation sequence, required and optional scope, and acceptance cases. |
| [LATIS_Design_Decisions.md](LATIS_Design_Decisions.md) | Disposition of earlier proposals, rationale, and conditions for later work. |
| [LATIS_Demo_Guide.md](LATIS_Demo_Guide.md) | Exhibition scenario, preparation, rehearsal, startup, and fallback procedure. |

Implementers should read Spec → API → Prototype Plan, then use Operation and the LLM Guide to verify the intended workflow.
A calling LLM starts with the LLM Guide and consults the API for the operations it needs. Exhibition operators start with the Demo Guide.
Design Decisions explains why choices were made. The LLM Guide remains part of the product after the exhibition.

**The Spec and API in this version are normative.** The Spec governs meaning and guarantees; the API governs fields, operations, and errors.
Operation and the LLM Guide explain usage; the Plan and Demo Guide explain implementation and validation; the READMEs provide an overview.
Resolve inconsistencies in the normative documents rather than using an overview or example to omit required checks.
Do not combine v0.2, the attached unadopted v0.3 revision proposal, or earlier discussion documents with this version as parallel specifications.

## Basic use

1. Search when needed, then use discovered terms, scopes, and explicit relations to continue exploring.
2. Compare the request with existing agreements. Explain the evidence and options when existing instructions leave a disagreement unresolved.
3. Consult the settled change, then apply it with an atomic freshness check and update.
4. Preserve reasons, executor, instruction references, and target revisions so another session can reuse the decision.
5. When checking implementation, observe external artifacts and record the result of an actual check as evidence linked to the agreement.

Do not request the same authorization again merely to record a decision. Reconsultation after a revision change can proceed without another human approval when no new semantic choice arises.
Start with unclassified records, duplicates, and open questions, then organize the parts needed for the task. Reject structural errors and prevent partial updates separately.
Neither complete retrieval in one query nor a fixed iteration count is required. “Two or three searches” and “95%” are examples, not acceptance conditions or achieved scores.
Scope hierarchy, locality, and priority values do not determine which agreement wins.

## Required exhibition core

P0 consists of nine correct everyday operations, decisions and history, and records of external artifacts and verification evidence.
The operations are meta, search, detail, relation-detail, relations, history, save-draft, consult, and apply.
Maintenance also includes init, backup, JSON export, and restore.

SQLite holds the canonical records and history. The initial execution path is a CLI that reads JSON from stdin and writes JSON responses to stdout.
HTTP methods and paths describe the operation contract; a persistent HTTP server or dedicated UI is not required.
Python 3.11 or later with the standard-library sqlite3 module is the recommended reference implementation. Storage and operation contracts remain language independent.
For the small exhibition dataset, scanning normalized strings is acceptable and must preserve two-character Japanese substring matches. FTS is optional.

## Preserve what was checked

A regular artifact can hold a locator and a content_hash computed by the caller for an external file or other resource. The core does not fetch the resource.
Verification evidence is an artifact recording subject revisions, method, outcome, observation time, and executor. A rerun or correction creates new evidence and preserves the previous result.
A confirmed verified_by relation requires passed evidence and includes the versions of the application and relevant inputs such as the test artifact.

current means that recorded revision references match. It does not establish freshness of unobserved physical files, completeness of dependencies, or semantic correctness.
A failed check or changed premise does not automatically invalidate the agreement. Executor, principal references, and model metadata are not authentication or proof of consent.

## Optional features and later work

P1 covers descendant-scope search (search_descendants) and read-only Markdown projection (markdown_export).
Check capability availability through meta. When unavailable, use ordinary follow-up searches and CLI responses. Editing projected Markdown does not change the canonical records.
A separate drift operation, authority engine and party nodes, hash-derived revision IDs, redaction, extension vocabularies, temporal evaluation, hybrid search, scope epochs, Markdown import, and automatic migration of older formats are outside this exhibition release.
Performance at 200,000 agreements has not been measured or demonstrated. That benchmark is a post-exhibition target, not an exhibition acceptance gate.

## Schedule to November 7

This is a plan, not a report of completed work.

| Date, JST | Milestone |
| --- | --- |
| November 4 | Run recording and retrieval with the LLM Guide; start real agent use with draft records. |
| November 5 | Complete consult, apply, and history; verify adoption and changes with recorded reasons. |
| November 6 | Exercise external artifacts, evidence, reuse in a separate session, backup, and restore; rehearse and freeze features. |
| November 7 | Start the validated configuration, check the existing scenario, and exhibit it. |

The example changes normal-log retention from 24 to 48 hours while a separate agreement keeps audit logs for 90 days (2160 hours). These durations are fictional demonstration settings.
Use [retention.py](examples/demo_project/retention.py), [test_retention.py](examples/demo_project/test_retention.py), and [seed_consult.request.json](examples/seed_consult.request.json).
They are application material, tests, and a request example for the exhibition, not an implementation of the LATIS engine. The Demo Guide and Prototype Plan define the procedure and acceptance criteria.
