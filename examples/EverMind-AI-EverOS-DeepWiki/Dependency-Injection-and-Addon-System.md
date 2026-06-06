# Dependency Injection and Addon System
Relevant source files
- [methods/evermemos/CONTRIBUTING.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1)
- [methods/evermemos/docs/OVERVIEW.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/docs/OVERVIEW.md?plain=1)

EverOS utilizes a custom Dependency Injection (DI) framework and a plugin-based Addon architecture. This system enables loose coupling between business logic and infrastructure, supports automated mock implementations for testing, and facilitates a clean "Open Core" vs. "Enterprise" code split.

## Dependency Injection Framework

The DI system is built around a central Bean Registry that manages the lifecycle and wiring of system components. It supports lazy injection, primary implementation selection, and a dedicated mock mode.

### Core Decorators

The framework uses specific decorators to categorize and register classes within the DI container:

| Decorator | Purpose | Typical Usage |
| --- | --- | --- |
| `@service` | Marks business logic providers. | `src/biz_layer`, `src/core` |
| `@repository` | Marks data access objects (DAOs). | `src/infra_layer/repositories` |
| `@component` | General purpose utility or infrastructure classes. | `src/component`, `src/core/lifespan` |
| `@mock_impl` | Defines a simulated implementation for testing or decoupled development. | `tests/`, `src/core/mock` |

### Implementation and Data Flow

The DI container scans designated paths at startup to discover these decorated classes. When a bean is requested via `get_beans_by_type` or `get_bean`, the registry instantiates the class and returns the singleton instance [methods/evermemos/src/core/lifespan/lifespan_factory.py9-10](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/lifespan/lifespan_factory.py#L9-L10)

**Bean Discovery and Retrieval Flow:**

1. **Scanning**: The system identifies classes with DI decorators across registered paths defined in `ScannerPathsRegistry`[methods/evermemos/src/core/addons/introduction.md57-59](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/addons/introduction.md?plain=1#L57-L59)
2. **Registration**: Classes are stored in a registry, keyed by their type and an optional name [methods/evermemos/src/core/lifespan/lifespan_factory.py130-142](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/lifespan/lifespan_factory.py#L130-L142)
3. **Mock Mode Check**: If mock mode is enabled, the registry prioritizes `@mock_impl` over standard implementations.
4. **Primary Selection**: If multiple real implementations exist, the one marked `primary=True` is selected.

**Sources:**[methods/evermemos/src/core/lifespan/lifespan_factory.py9-45](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/lifespan/lifespan_factory.py#L9-L45)[methods/evermemos/src/core/addons/introduction.md46-65](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/addons/introduction.md?plain=1#L46-L65)[methods/evermemos/src/core/addons/addon_registry.py46-57](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/addons/addon_registry.py#L46-L57)

---

## Addon and Plugin Architecture

The Addon system implements a plugin-based architecture using Python **Entry Points**. This allows the core system to remain agnostic of specific extensions (like Enterprise features) while providing a mechanism for those extensions to register themselves during bootstrap.

### Entry Points Mechanism

Addons are declared in the `pyproject.toml` of their respective packages under the `memsys.addons` group [methods/evermemos/src/core/addons/introduction.md91-97](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/addons/introduction.md?plain=1#L91-L97)

**Addon Registration and Discovery Flow**

[Flowchart Diagram]

**Sources:**[methods/evermemos/src/core/addons/introduction.md17-32](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/addons/introduction.md?plain=1#L17-L32)[methods/evermemos/src/core/addons/addons_registry.py143-170](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/addons/addons_registry.py#L143-L170)[methods/evermemos/src/core/addons/addon_registry.py12-33](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/addons/addon_registry.py#L12-L33)

### Key Classes

- **`AddonRegistry`**: A container for a single addon's configuration, including its `ScannerPathsRegistry` for DI and `TaskScanDirectoriesRegistry` for async tasks [methods/evermemos/src/core/addons/addon_registry.py12-33](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/addons/addon_registry.py#L12-L33)
- **`AddonsRegistry`**: A global singleton (`ADDONS_REGISTRY`) that manages discovery via `load_entrypoints()`. It uses `MEMSYS_ENTRYPOINTS_FILTER` environment variable to selectively load plugins [methods/evermemos/src/core/addons/addons_registry.py115-142](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/addons/addons_registry.py#L115-L142)

### Enterprise vs. Open Core Split

The architecture ensures that the Open Core does not depend on Enterprise code. Instead, the Enterprise addon provides implementations for abstract interfaces defined in the core. Because the DI system loads addons sequentially, Enterprise implementations can override core defaults by being registered later or marked as primary [methods/evermemos/src/core/addons/introduction.md25-32](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/addons/introduction.md?plain=1#L25-L32)

**Sources:**[methods/evermemos/src/core/addons/introduction.md1-42](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/addons/introduction.md?plain=1#L1-L42)[methods/evermemos/src/core/addons/introduction.md172-205](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/addons/introduction.md?plain=1#L172-L205)[methods/evermemos/src/core/addons/addons_registry.py55-113](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/addons/addons_registry.py#L55-L113)

---

## Mock Mode and Decoupled Development

To facilitate parallel development and isolated testing, EverOS supports a global mock toggle via environment variables.

### Mock Implementation Pattern

Developers define abstract interfaces using `abc.ABC` and provide both a real implementation and a mock implementation.

| Feature | Description | Code Reference |
| --- | --- | --- |
| **Decorator** | `@mock_impl("name")` | DI Framework Decorator |
| **Activation** | `MOCK_MODE=true` | Environment Variable |
| **Behavior** | Registry returns the mock bean instead of the service/repository bean. | DI Container Logic |

### Code Entity Space to Natural Language Mapping

**Implementation Selection Strategy**

```

```

**Sources:**[methods/evermemos/src/core/addons/introduction.md279-293](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/addons/introduction.md?plain=1#L279-L293)[methods/evermemos/src/core/addons/addons_registry.py15-53](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/addons/addons_registry.py#L15-L53)

---

## Lifecycle Integration

The DI system is tightly integrated with the FastAPI lifespan. Components can implement the `AppReadyListener` protocol to perform actions immediately after the system is fully wired and all lifespan providers have started [methods/evermemos/src/core/lifespan/lifespan_factory.py19-45](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/lifespan/lifespan_factory.py#L19-L45)

### Decoupled Ready Hook

1. **Discovery**: `LifespanFactory` uses `get_beans_by_type(AppReadyListener)` to find all listeners [methods/evermemos/src/core/lifespan/lifespan_factory.py81-82](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/lifespan/lifespan_factory.py#L81-L82)
2. **Execution**: The `on_app_ready()` method is called for each discovered component [methods/evermemos/src/core/lifespan/lifespan_factory.py83-91](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/lifespan/lifespan_factory.py#L83-L91)
3. **Example**: The `TenantConfigAppReadyListener` uses this hook to call `mark_app_ready()` on `TenantConfig`, enabling strict tenant checking once the application is ready [methods/evermemos/src/core/tenants/tenant_switch.py14-25](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenant_switch.py#L14-L25)

**Sources:**[methods/evermemos/src/core/lifespan/lifespan_factory.py47-111](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/lifespan/lifespan_factory.py#L47-L111)[methods/evermemos/src/core/tenants/tenant_switch.py1-25](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenant_switch.py#L1-L25)[methods/evermemos/src/core/tenants/tenant_config.py108-126](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/src/core/tenants/tenant_config.py#L108-L126)