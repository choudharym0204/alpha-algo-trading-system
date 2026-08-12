# Architecture Decisions

## ADR-0001 - Use Modular Monorepo

Status: Accepted

Decision: Start with a modular monorepo containing `apps`, `services`, `packages`, `backtesting`, `migrations`, `tests`, `docs`, `infra`, and `docker`.

Reason: The system needs strong domain separation without the operational cost of premature microservices.

## ADR-0002 - Use PostgreSQL with TimescaleDB and Redis

Status: Accepted

Decision: PostgreSQL is the authoritative store, TimescaleDB handles market time-series data, and Redis handles transient realtime state.

Reason: Financial history must remain durable and queryable, while market data and realtime UI updates require efficient temporal storage and cache/pub-sub behavior.

## ADR-0003 - Keep Broker Logic Out of Strategies

Status: Accepted

Decision: Strategies emit broker-agnostic signals. Broker-specific behavior lives only in broker adapters.

Reason: Strategy behavior must be testable, versioned, portable, and auditable.

## ADR-0004 - Risk Engine Is a Mandatory Security Boundary

Status: Accepted

Decision: Every live order intent must pass through risk evaluation and execution must reject intents without valid risk approval.

Reason: Trading safety depends on a single enforceable path between strategy signals and broker orders.

## ADR-0005 - Defer Kubernetes and Kafka

Status: Accepted

Decision: Use Docker Compose for initial development and avoid Kafka unless scale or replay requirements justify it.

Reason: The initial platform should be reliable and modular without unnecessary distributed-systems complexity.

