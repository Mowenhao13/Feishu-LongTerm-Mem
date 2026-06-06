# Development Guide
Relevant source files
- [CLAUDE.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/CLAUDE.md?plain=1)
- [methods/evermemos/CONTRIBUTING.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1)

The Development Guide provides a comprehensive overview of the standards, practices, and infrastructure required to contribute to EverMemOS. This project follows a strict **Hexagonal Architecture** and an **asynchronous-first** programming model to ensure scalability and maintainability.

## 🚀 Quick Start for Developers

For a consistent development experience, it is recommended to use the provided DevContainer or the `uv` package manager.

1. **Environment Setup**: Install dependencies using `uv sync`[methods/evermemos/CONTRIBUTING.md23](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L23-L23)
2. **Infrastructure**: Start the required middleware (MongoDB, Milvus, Elasticsearch, Redis) using `docker-compose up -d`[methods/evermemos/CONTRIBUTING.md34](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L34-L34)
3. **Configuration**: Copy `env.template` to `.env` and configure your API keys and service endpoints [methods/evermemos/CONTRIBUTING.md28-30](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L28-L30)
4. **Execution**: Run the application via `make run` or the entrypoint [CLAUDE.md17-25](https://github.com/EverMind-AI/EverOS/blob/d40b8703/CLAUDE.md?plain=1#L17-L25)

**Sources:**[methods/evermemos/CONTRIBUTING.md23-34](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L23-L34)[CLAUDE.md11-25](https://github.com/EverMind-AI/EverOS/blob/d40b8703/CLAUDE.md?plain=1#L11-L25)

---

## 🏛️ Architecture and Coding Standards

EverMemOS enforces a clean separation of concerns through its layered architecture. The system is designed around a single event loop and requires all I/O operations to be non-blocking.

### Core Architectural Rules

- **Hexagonal Architecture**: Dependencies flow inward. Use absolute imports from the project root and avoid relative imports [methods/evermemos/CONTRIBUTING.md48](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L48-L48)
- **Async Constraints**: All I/O is async; use `await` consistently to avoid blocking the single event loop [CLAUDE.md31](https://github.com/EverMind-AI/EverOS/blob/d40b8703/CLAUDE.md?plain=1#L31-L31)
- **No Wildcard Imports**: Explicitly import only what is needed; `from module import *` is prohibited [methods/evermemos/CONTRIBUTING.md49](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L49-L49)
- **Timezone Awareness**: All `datetime` objects must be timezone-aware. Use `common_utils.datetime_utils` instead of the direct `datetime` module [methods/evermemos/CONTRIBUTING.md50](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L50-L50)
- **Documentation**: Use Google-style docstrings for all classes and functions [methods/evermemos/CONTRIBUTING.md43](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L43-L43)

For detailed implementation rules, see **[Architecture and Coding Standards](/EverMind-AI/EverOS/12.1-architecture-and-coding-standards)**.

### System Entity Mapping

The following diagram bridges the high-level architectural layers to their corresponding code entities and decorators used throughout the codebase.

**Diagram: System Layer to Code Entity Mapping**

[Flowchart Diagram]

**Sources:**[CLAUDE.md23-27](https://github.com/EverMind-AI/EverOS/blob/d40b8703/CLAUDE.md?plain=1#L23-L27)[methods/evermemos/CONTRIBUTING.md41-51](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L41-L51)

---

## 🧪 Testing Infrastructure

The project emphasizes isolated testing through a robust **Mock Mode** and automated quality checks.

- **Execution**: Run tests using `pytest`[CLAUDE.md18](https://github.com/EverMind-AI/EverOS/blob/d40b8703/CLAUDE.md?plain=1#L18-L18) or `pytest tests/`[methods/evermemos/CONTRIBUTING.md110](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L110-L110)
- **Code Quality**: Check code style with `ruff check .`[methods/evermemos/CONTRIBUTING.md114](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L114-L114) and perform type checking with `pyright`[CLAUDE.md20](https://github.com/EverMind-AI/EverOS/blob/d40b8703/CLAUDE.md?plain=1#L20-L20)
- **Formatting**: Use `black` and `isort` for automated formatting [CLAUDE.md19](https://github.com/EverMind-AI/EverOS/blob/d40b8703/CLAUDE.md?plain=1#L19-L19)
- **Mock Implementation**: Developers can define mock versions of services to run tests without external dependencies.
- **Documentation**: Update relevant documentation when changing functionality and maintain docstrings for new functions [methods/evermemos/CONTRIBUTING.md138-142](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L138-L142)

For details on writing and running tests, see **[Testing Infrastructure](/EverMind-AI/EverOS/12.2-testing-infrastructure)**.

**Sources:**[methods/evermemos/CONTRIBUTING.md107-114](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L107-L114)[methods/evermemos/CONTRIBUTING.md138-142](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L138-L142)[CLAUDE.md11-21](https://github.com/EverMind-AI/EverOS/blob/d40b8703/CLAUDE.md?plain=1#L11-L21)

---

## 🤖 LLM Provider and Tokenizer Integration

EverMemOS abstracts LLM interactions to support multiple backends through a unified interface.

- **Providers**: Supports OpenAI-compatible clients, including Gemini, Anthropic, and vLLM [CLAUDE.md33](https://github.com/EverMind-AI/EverOS/blob/d40b8703/CLAUDE.md?plain=1#L33-L33)
- **Prompts**: Prompts are stored separately in `methods/evermemos/src/memory_layer/prompts/` supporting both English and Chinese [CLAUDE.md33](https://github.com/EverMind-AI/EverOS/blob/d40b8703/CLAUDE.md?plain=1#L33-L33)
- **Tokenization**: Context window management is handled by specific tokenizer factories (e.g., `tiktoken`) to ensure extraction pipelines remain within model limits.

For details on adding new providers or configuring tokenizers, see **[LLM Provider and Tokenizer Integration](/EverMind-AI/EverOS/12.3-llm-provider-and-tokenizer-integration)**.

**Sources:**[CLAUDE.md29-34](https://github.com/EverMind-AI/EverOS/blob/d40b8703/CLAUDE.md?plain=1#L29-L34)

---

## 🌿 Branching and Contributions

EverMemOS follows a structured Git workflow to ensure code quality and traceability.

### Git Workflow and Commit Standards

[Flowchart Diagram]

- **Branch Naming**: Use prefixes like `feature/`, `fix/`, `docs/`, or `refactor/` followed by a short description [methods/evermemos/CONTRIBUTING.md57-60](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L57-L60)
- **Commit Messages**: We use **Gitmoji** for commit messages. Format: `<emoji> <type>: <description>`[methods/evermemos/CONTRIBUTING.md64-66](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L64-L66)
- `✨ feat:` for new features [methods/evermemos/CONTRIBUTING.md82](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L82-L82)
- `🐛 fix:` for bug fixes [methods/evermemos/CONTRIBUTING.md83](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L83-L83)
- `♻️ refactor:` for code refactoring [methods/evermemos/CONTRIBUTING.md86](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L86-L86)
- `✅ test:` for adding tests [methods/evermemos/CONTRIBUTING.md88](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L88-L88)
- **Pull Request Process**: Create a feature branch from `main`, ensure tests pass, and address review feedback promptly [methods/evermemos/CONTRIBUTING.md100-128](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L100-L128)

**Sources:**[methods/evermemos/CONTRIBUTING.md55-128](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/CONTRIBUTING.md?plain=1#L55-L128)