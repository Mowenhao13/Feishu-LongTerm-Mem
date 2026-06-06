# Observability and Operations
Relevant source files
- [methods/evermemos/docs/OVERVIEW.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/OVERVIEW.md?plain=1)
- [methods/evermemos/docs/usage/CONFIGURATION_GUIDE.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/usage/CONFIGURATION_GUIDE.md?plain=1)

EverMemOS provides a robust observability stack designed for high-throughput memory operations and production reliability. The system leverages Prometheus for real-time metrics, a structured logging architecture, and standardized infrastructure management via Docker and specialized CLI tools.

## Monitoring and Metrics

The observability framework is built around a centralized metrics registry that isolates the business logic from the underlying monitoring implementation. It provides a unified interface for standard Prometheus metric types, including `Counter`, `Histogram`, and `BaseGauge`.

### HTTP Instrumentation

The system uses a custom `PrometheusMiddleware` to automatically instrument all incoming HTTP requests. This middleware records:

- **Request Volume**: `http_requests_total` partitioned by method, path, and status.
- **Latency**: `http_request_duration_seconds` with buckets optimized for API response times.
- **Payload Sizes**: Tracking both `http_request_size_bytes` and `http_response_size_bytes`.

### Pipeline and Service Metrics

Beyond HTTP, EverMemOS instruments deep internal pipelines:

- **Retrieval Pipeline**: Tracks end-to-end latency via `RETRIEVE_DURATION_SECONDS`, stage-specific durations (e.g., `milvus_search`, `rrf_fusion`), and result counts.
- **ML Services**: Specialized metrics for `Vectorize` (embeddings) and `Rerank` services, including provider tracking (vLLM vs. DeepInfra), fallback counters (`VECTORIZE_FALLBACK_TOTAL`), and token usage.
- **Auto-Refreshing Gauges**: The `BaseGauge` class allows for instantaneous values (like queue sizes) that automatically refresh at defined intervals.

### Metrics Server Lifecycle

The metrics are exposed via a standalone HTTP server, typically on port `9090`, which is initialized during the application bootstrap process by the `MetricsLifespanProvider`. This isolation ensures that metrics remain available even if the main API server is under heavy load.

For detailed implementation of instrumentation and metric definitions, see **[Prometheus Metrics and Monitoring](/EverMind-AI/EverOS/10.1-prometheus-metrics-and-monitoring)**.

### Observability Architecture

The following diagram illustrates how observability components bridge the high-level request space to the underlying code entities.

**Diagram: Metrics and Middleware Integration**

[Flowchart Diagram]

**Sources:**[methods/evermemos/docs/OVERVIEW.md84-100](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/OVERVIEW.md?plain=1#L84-L100)[methods/evermemos/docs/OVERVIEW.md103-106](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/OVERVIEW.md?plain=1#L103-L106)

## Infrastructure and DevOps

EverMemOS is designed as a cloud-native application, utilizing a multi-database strategy to handle the diverse requirements of memory persistence (MongoDB), keyword search (Elasticsearch), and vector search (Milvus).

### Service Topology

The infrastructure is orchestrated using Docker Compose, defining a topology of interdependent services as outlined in the configuration guide:

- **Primary Storage**: MongoDB for document persistence (MemCells, Profiles) [methods/evermemos/docs/usage/CONFIGURATION_GUIDE.md81-86](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/usage/CONFIGURATION_GUIDE.md?plain=1#L81-L86)
- **Search Engines**: Elasticsearch for BM25 keyword search [methods/evermemos/docs/usage/CONFIGURATION_GUIDE.md88-90](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/usage/CONFIGURATION_GUIDE.md?plain=1#L88-L90) and Milvus for high-dimensional vector similarity [methods/evermemos/docs/usage/CONFIGURATION_GUIDE.md92-95](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/usage/CONFIGURATION_GUIDE.md?plain=1#L92-L95)
- **Coordination**: Redis for caching and distributed locks [methods/evermemos/docs/usage/CONFIGURATION_GUIDE.md72-76](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/usage/CONFIGURATION_GUIDE.md?plain=1#L72-L76)
- **External ML**: Integration with providers like DeepInfra or local vLLM for Vectorize and Rerank services [methods/evermemos/docs/usage/CONFIGURATION_GUIDE.md29-66](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/usage/CONFIGURATION_GUIDE.md?plain=1#L29-L66)

### Operational Tooling

Operations are managed through several key interfaces:

- **manage.py CLI**: A unified entry point for administrative tasks such as tenant initialization (`tenant-init`) and interactive shells.
- **Data Synchronization**: Specialized services like `MemorySyncService` for rebuilding Elasticsearch indexes or syncing data between MongoDB and vector backends.
- **Environment Configuration**: Centralized management via `.env` files, including `TENANT_SINGLE_TENANT_ID` for resource prefixing [methods/evermemos/docs/usage/CONFIGURATION_GUIDE.md78-79](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/usage/CONFIGURATION_GUIDE.md?plain=1#L78-L79)

For infrastructure configuration, deployment patterns, and administrative commands, see **[Infrastructure Management and DevOps](/EverMind-AI/EverOS/10.2-infrastructure-management-and-devops)**.

### System Infrastructure Mapping

This diagram maps the operational services to the code-level management entities and the data flow.

**Diagram: Infrastructure and Management Mapping**

[Flowchart Diagram]

**Sources:**[methods/evermemos/docs/usage/CONFIGURATION_GUIDE.md72-95](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/usage/CONFIGURATION_GUIDE.md?plain=1#L72-L95)[methods/evermemos/docs/OVERVIEW.md73-76](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/OVERVIEW.md?plain=1#L73-L76)

## Summary of Sub-pages

| Page | Description |
| --- | --- |
| **[Prometheus Metrics and Monitoring](/EverMind-AI/EverOS/10.1-prometheus-metrics-and-monitoring)** | Detailed documentation on the `PrometheusMiddleware`, `RetrieveMetricsContext`, `HistogramBuckets`, and the `BaseGauge` auto-refresh pattern. |
| **[Infrastructure Management and DevOps](/EverMind-AI/EverOS/10.2-infrastructure-management-and-devops)** | Overview of the Docker Compose stack, the `manage.py` CLI, and database maintenance procedures. |

**Sources:**[methods/evermemos/docs/OVERVIEW.md1-139](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/OVERVIEW.md?plain=1#L1-L139)[methods/evermemos/docs/usage/CONFIGURATION_GUIDE.md1-154](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/usage/CONFIGURATION_GUIDE.md?plain=1#L1-L154)