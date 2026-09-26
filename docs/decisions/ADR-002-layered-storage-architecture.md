# ADR-002: Layered Storage Architecture

## Status

Accepted

## Date

2026-09-26

## Context

The financial market data platform requires storage at multiple stages of the ETL lifecycle.

The system must preserve original source responses, support reproducible reprocessing, provide an efficient intermediate analytical representation, quarantine invalid data, and expose analytics-ready information through PostgreSQL.

Using only PostgreSQL for every stage would make preservation of original provider responses and file-based processing experiments less natural.

Using only filesystem storage would make dimensional analytical querying, integrity constraints, and dashboard access less suitable.

The project also has a zero-cost constraint and must remain reproducible on a local development environment.

## Decision Drivers

The storage architecture should:

- preserve source responses before transformation;
- support reprocessing without unnecessary API requests;
- separate raw, processed, rejected, and analytics-ready data;
- support Pandas processing;
- support later PySpark experiments;
- provide database-level integrity for analytical facts;
- support idempotent analytical loading;
- remain locally reproducible;
- remain compatible with Docker-based development; and
- avoid unnecessary infrastructure.

## Options Considered

### Option 1: PostgreSQL for all storage layers

Store raw responses, intermediate datasets, rejected records, and analytical data entirely in PostgreSQL.

Advantages:

- one primary persistence technology;
- centralized querying; and
- database transaction support.

Disadvantages:

- original API responses become less naturally preserved as source artifacts;
- file-based Pandas and PySpark experiments become less direct;
- raw and analytical responsibilities become more tightly coupled.

### Option 2: Filesystem for all storage layers

Store raw, transformed, and final analytical datasets entirely as files.

Advantages:

- simple local operation;
- low infrastructure requirements; and
- convenient data-processing experimentation.

Disadvantages:

- weaker analytical serving layer;
- database uniqueness and integrity constraints are unavailable;
- less suitable for Streamlit analytical querying;
- dimensional modeling becomes less meaningful.

### Option 3: Layered filesystem and PostgreSQL storage

Use different persistence mechanisms according to the responsibility of each layer:

- Raw / Bronze: JSON on the local filesystem;
- Processed / Silver: Parquet on the local filesystem;
- Quarantine: local filesystem;
- Gold: PostgreSQL.

## Decision

The platform will use the layered filesystem and PostgreSQL approach.

The initial storage model is:

| Layer | Storage |
|---|---|
| Raw / Bronze | JSON files |
| Processed / Silver | Parquet files |
| Quarantine | Local filesystem |
| Gold | PostgreSQL |

Raw JSON preserves provider responses close to their original representation.

Silver Parquet provides a typed, columnar intermediate format suitable for analytical processing with Pandas and later PySpark experiments.

PostgreSQL provides the analytics-ready Gold layer, including dimensional modeling, uniqueness constraints, idempotent loading, and structured access for Streamlit.

## Consequences

### Positive

- raw provider evidence is preserved;
- transformations can be rerun without repeating extraction;
- Silver datasets are suitable for analytical processing;
- Pandas and PySpark can operate on a common intermediate format;
- PostgreSQL can enforce analytical uniqueness;
- Streamlit receives a structured analytical interface;
- storage responsibilities remain clearly separated; and
- the design remains compatible with the zero-cost local environment.

### Negative

- the platform uses more than one persistence technology;
- lifecycle management is required for local data files;
- consistency between Silver and Gold must be handled explicitly;
- filesystem organization must be documented and maintained.

## Idempotency Implications

The layers have different idempotency responsibilities.

Raw storage represents extraction evidence and may contain multiple extraction events covering the same logical market observations.

Silver processing should avoid duplicate logical observations within a processed dataset.

Gold provides the strongest uniqueness boundary.

For daily market observations, the logical analytical identity is based on:

`(asset, observation_date)`

The PostgreSQL schema should enforce this identity using appropriate keys or uniqueness constraints.

## Future Evolution

Local filesystem storage is appropriate for the initial educational implementation.

If the platform later moves to a cloud environment, Raw and Silver storage could be migrated to object storage while preserving the same logical Bronze/Silver/Gold boundaries.

Such a migration should be treated as a separate architectural decision rather than changing this decision implicitly.

## Related Documents

- `docs/architecture/initial-architecture.md`
- `docs/decisions/ADR-001-financial-data-source.md`
- `docs/requirements.md`
- `docs/experiments/EXP-001-data-source-validation.md`