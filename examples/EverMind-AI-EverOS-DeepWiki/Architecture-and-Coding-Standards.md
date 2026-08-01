# Architecture and Coding Standards
Relevant source files
- [CLAUDE.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/CLAUDE.md?plain=1)
- [methods/evermemos/.pylintrc](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/.pylintrc)
- [methods/evermemos/.vscode/settings.json](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/.vscode/settings.json)
- [methods/evermemos/CONTRIBUTING.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1)

This page defines the architectural principles and coding standards for EverOS. Adherence to these standards ensures system stability, maintainability, and high performance in a multi-tenant, asynchronous environment.

## Hexagonal Architecture and Dependency Rules

EverOS follows a layered, hexagonal architecture (also known as Clean Architecture). The core principle is the **one-way dependency rule**: dependencies must only point inwards toward the business logic.

### Layer Definitions

1. **Agentic Layer**: Orchestrates high-level memory flows and retrieval strategies, such as the `MemoryManager`[methods/evermemos/src/agentic_layer/memory_manager.py1-26](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/agentic_layer/memory_manager.py#L1-L26)
2. **Business Layer**: Contains the core logic for memory extraction and processing (e.g., `EpisodeMemoryExtractor`, `ProfileManager`).
3. **Memory/Infrastructure Layer**: Handles persistence (MongoDB, Milvus, Elasticsearch) and external service integrations, including the REST API controllers [methods/evermemos/src/infra_layer/adapters/input/api/1-27](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/infra_layer/adapters/input/api/#L1-L27)

### Enforcement

- **Data Access Convergence**: All external storage operations (database, search engine, etc.) must be converged into infrastructure layer repository methods. Direct calls to databases from the business layer are strictly prohibited.
- **Interface Abstraction**: Components interact via abstract base classes (ABC) to define clear interfaces, allowing for decoupled development and mock implementations.
- **Pylint Configuration**: The system enforces module discovery via a specific initialization hook that adds `src`, `demo`, `evaluation`, and `data_format` to the system path [methods/evermemos/.pylintrc1-2](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/.pylintrc#L1-L2)

### Natural Language to Code Entity Space: Dependency Injection

The following diagram illustrates how abstract system requirements (Natural Language Space) map to specific code decorators and the DI container (Code Entity Space).

**DI System Mapping**

[Flowchart Diagram]

Sources: [methods/evermemos/CONTRIBUTING.md41-52](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L41-L52)[methods/evermemos/.pylintrc1-2](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/.pylintrc#L1-L2)

## Full Async Architecture

EverOS operates on a **Single Event Loop** model. All I/O-bound operations must be non-blocking to ensure the scalability of the FastAPI server.

### Async Constraints

- **Mandatory `await`**: All I/O is asynchronous. Developers must use `await` for database, network, and file operations [CLAUDE.md31](https://github.com/EverMind-AI/EverOS/blob/d40b8703/CLAUDE.md?plain=1#L31-L31)
- **Prohibition of Threads/Processes**: Standard practice requires avoiding synchronous blocking calls or manual threading that can interfere with the single event loop.
- **Concurrency Pattern**: Use `asyncio.gather` for parallelizing independent operations to improve performance.
- **Prohibition of I/O in Loops**: Database access and API calls inside `for` or `while` loops are strictly prohibited to prevent performance degradation. Developers must use batch operations instead.
- **Testing Consistency**: Developers must ensure that tests (e.g., via `pytest`) properly handle the async lifecycle [methods/evermemos/CONTRIBUTING.md107-114](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L107-L114)

Sources: [CLAUDE.md31](https://github.com/EverMind-AI/EverOS/blob/d40b8703/CLAUDE.md?plain=1#L31-L31)[methods/evermemos/CONTRIBUTING.md107-114](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L107-L114)

## Timezone-Aware Datetime Requirements

To ensure consistency across global deployments and multi-tenant environments, all datetime objects must be timezone-aware.

- **No `datetime.now()`**: Direct usage of the standard `datetime` module for current time is discouraged.
- **Utility Functions**: All time operations must use `common_utils.datetime_utils` instead of the direct `datetime` module to ensure timezone awareness [methods/evermemos/CONTRIBUTING.md50](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L50-L50)
- **Consistency**: This prevents "naive" datetime objects from causing comparison errors or database storage inconsistencies.

Sources: [methods/evermemos/CONTRIBUTING.md50](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L50-L50)

## Coding Standards and Documentation

### Import and Structure Standards

- **Absolute Imports**: Use absolute imports from the project root. Relative imports are strictly prohibited [methods/evermemos/CONTRIBUTING.md48](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L48-L48)
- **No Wildcard Imports**: Avoid `from module import *` to maintain namespace clarity [methods/evermemos/CONTRIBUTING.md49](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L49-L49)
- **`__init__.py`**: Use these only as package markers; do not place logic inside them [methods/evermemos/CONTRIBUTING.md51](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L51-L51)
- **Type Hints**: Use type hints for all function parameters and return values [methods/evermemos/CONTRIBUTING.md42](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L42-L42)

### Documentation and Comments

- **Google-Style Docstrings**: All classes and functions must include docstrings following the Google format [methods/evermemos/CONTRIBUTING.md43](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L43-L43)
- **Language**: All code and documentation must be in English.
- **Commit Messages**: Follow the Conventional Commits format and use [Gitmoji](https://gitmoji.dev/)[methods/evermemos/CONTRIBUTING.md62-96](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L62-L96)

### Tooling and Workflow

- **Dependency Management**: Use `uv` for managing dependencies and synchronization (`uv sync`) [methods/evermemos/CONTRIBUTING.md11-23](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L11-L23)[CLAUDE.md16](https://github.com/EverMind-AI/EverOS/blob/d40b8703/CLAUDE.md?plain=1#L16-L16)
- **Formatting**: Use `black` and `isort` for code formatting [CLAUDE.md19](https://github.com/EverMind-AI/EverOS/blob/d40b8703/CLAUDE.md?plain=1#L19-L19)
- **Linting and Type Checking**: The project uses `ruff` for code checking [methods/evermemos/CONTRIBUTING.md113](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L113-L113) and `pyright` for type checking [CLAUDE.md20](https://github.com/EverMind-AI/EverOS/blob/d40b8703/CLAUDE.md?plain=1#L20-L20)
- **Max Line Length**: Maximum line length is set to 100 characters [methods/evermemos/CONTRIBUTING.md44](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L44-L44)

Sources: [methods/evermemos/CONTRIBUTING.md37-96](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L37-L96)[CLAUDE.md11-21](https://github.com/EverMind-AI/EverOS/blob/d40b8703/CLAUDE.md?plain=1#L11-L21)

## System Development Flow: Code Entities to Standards

The following diagram bridges the conceptual coding standards to the specific tools and workflows that enforce them during the development lifecycle.

**Standard Enforcement Flow**

[Flowchart Diagram]

Sources: [methods/evermemos/CONTRIBUTING.md11-23](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L11-L23)[methods/evermemos/CONTRIBUTING.md37-52](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L37-L52)[CLAUDE.md11-21](https://github.com/EverMind-AI/EverOS/blob/d40b8703/CLAUDE.md?plain=1#L11-L21)