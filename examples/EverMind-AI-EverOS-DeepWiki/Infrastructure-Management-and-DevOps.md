# Infrastructure Management and DevOps
Relevant source files
- [.github/workflows/deploy-website.yml](https://github.com/EverMind-AI/EverOS/blob/d40b8703/.github/workflows/deploy-website.yml)
- [methods/evermemos/.devcontainer/devcontainer.json](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/.devcontainer/devcontainer.json)
- [methods/evermemos/.devcontainer/docker-compose.devcontainer.yaml](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/.devcontainer/docker-compose.devcontainer.yaml)
- [methods/evermemos/.dockerignore](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/.dockerignore)
- [methods/evermemos/.pre-commit-config.yaml](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/.pre-commit-config.yaml)

EverMemOS utilizes a containerized infrastructure for its core storage and messaging components, managed primarily through Docker Compose. The system provides a robust suite of CLI tools and automated hooks to ensure data integrity, multi-tenant isolation, and high code quality.

## Docker Compose Service Topology

The infrastructure is orchestrated using `docker-compose.yaml`, which defines the service interdependencies and health requirements for the system backends. For development, a specialized `docker-compose.devcontainer.yaml` extends this configuration to provide a seamless environment for VS Code users [methods/evermemos/.devcontainer/docker-compose.devcontainer.yaml1-24](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/.devcontainer/docker-compose.devcontainer.yaml#L1-L24)

### Service Architecture

The topology consists of primary storage (MongoDB), search engines (Elasticsearch, Milvus), and supporting middleware (Redis, etcd, MinIO).

| Service | Image / Address | Role | Port |
| --- | --- | --- | --- |
| `mongodb` | `mongo:7.0` | Primary document storage for MemCells and metadata | 27017 |
| `elasticsearch` | `elasticsearch:8.11.0` | Keyword search (BM25) and text analysis | 19200 |
| `milvus-standalone` | `milvusdb/milvus:v2.5.2` | Vector database for embedding similarity search | 19530 |
| `milvus-minio` | `milvus-minio:9000` | Object storage for Milvus data persistence | 9000 |
| `redis` | `redis:7.2-alpine` | Distributed cache and temporary state | 6379 |

### Dev Container Integration

The project includes a comprehensive `.devcontainer` setup that automates the transition from a fresh clone to a running environment.

- **Post-Create Setup**: The `postCreate.sh` script installs system dependencies (`libgl1`, `ffmpeg`, `build-essential`), synchronizes Python packages using `uv sync --dev`, and initializes the `.env` file with Docker-internal hostnames [methods/evermemos/.devcontainer/postCreate.sh6-30](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/.devcontainer/postCreate.sh#L6-L30)
- **Port Forwarding**: The `devcontainer.json` automatically forwards ports 1995 (API), 27017 (Mongo), 19200 (ES), 19530 (Milvus), 6379 (Redis), and 9000/9001 (MinIO) to the host machine [methods/evermemos/.devcontainer/devcontainer.json44-53](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/.devcontainer/devcontainer.json#L44-L53)
- **Environment Automation**: The `postCreate.sh` script automatically updates `.env` hostnames from `localhost` to the internal Docker service names (e.g., `REDIS_HOST=redis`, `MONGODB_HOST=mongodb`) to ensure container-to-container connectivity [methods/evermemos/.devcontainer/postCreate.sh21-26](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/.devcontainer/postCreate.sh#L21-L26)

**Sources:**[methods/evermemos/.devcontainer/docker-compose.devcontainer.yaml1-24](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/.devcontainer/docker-compose.devcontainer.yaml#L1-L24)[methods/evermemos/.devcontainer/devcontainer.json1-63](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/.devcontainer/devcontainer.json#L1-L63)[methods/evermemos/.devcontainer/postCreate.sh1-45](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/.devcontainer/postCreate.sh#L1-L45)

---

## Infrastructure Flow Diagram

The following diagram illustrates how the development environment orchestrates the infrastructure services and the initialization sequence.

### DevContainer Bootstrapping Flow

[Flowchart Diagram]

**Sources:**[methods/evermemos/.devcontainer/docker-compose.devcontainer.yaml11-16](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/.devcontainer/docker-compose.devcontainer.yaml#L11-L16)[methods/evermemos/.devcontainer/postCreate.sh21-26](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/.devcontainer/postCreate.sh#L21-L26)[methods/evermemos/.devcontainer/devcontainer.json44-53](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/.devcontainer/devcontainer.json#L44-L53)

---

## Code Quality and DevOps Hooks

EverMemOS enforces strict coding standards and data safety through a series of local pre-commit hooks defined in `.pre-commit-config.yaml`.

### Pre-commit Hook Pipeline

The environment setup via `postCreate.sh` automatically installs these hooks using `uv run pre-commit install`[methods/evermemos/.devcontainer/postCreate.sh32-34](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/.devcontainer/postCreate.sh#L32-L34)

| Hook ID | Tool/Script | Stage | Purpose |
| --- | --- | --- | --- |
| `black` | `psf/black` | `pre-commit` | Automated Python code formatting [methods/evermemos/.pre-commit-config.yaml2-6](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/.pre-commit-config.yaml#L2-L6) |
| `check-i18n-files` | `i18n_tool.py` | `pre-commit` | Detects non-English (CJK) characters in source code [methods/evermemos/.pre-commit-config.yaml12-16](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/.pre-commit-config.yaml#L12-L16) |
| `check-i18n-commit-msg` | `i18n_tool.py` | `commit-msg` | Ensures commit messages are in English [methods/evermemos/.pre-commit-config.yaml21-25](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/.pre-commit-config.yaml#L21-L25) |
| `check-conventional-commit` | `conventional_commit_lint` | `commit-msg` | Enforces "feat:", "fix:", "docs:" prefixes [methods/evermemos/.pre-commit-config.yaml31-35](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/.pre-commit-config.yaml#L31-L35) |
| `check-sensitive-info` | `sensitive_info_tool.py` | `pre-commit` | Scans for leaked API keys or credentials [methods/evermemos/.pre-commit-config.yaml41-46](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/.pre-commit-config.yaml#L41-L46) |

### Automated Documentation Deployment

The repository includes a GitHub Action `deploy-website.yml` that handles the deployment of the EvoAgentBench website.

- **Trigger**: Triggers on pushes to the `feat/readme-redesign` branch specifically for paths under `benchmarks/EvoAgentBench/website/`[.github/workflows/deploy-website.yml3-9](https://github.com/EverMind-AI/EverOS/blob/d40b8703/.github/workflows/deploy-website.yml#L3-L9)
- **Build Process**: Uses Node.js 20 to run `npm run build` with `NEXT_PUBLIC_BASE_PATH` set to `/EverOS`[.github/workflows/deploy-website.yml28-37](https://github.com/EverMind-AI/EverOS/blob/d40b8703/.github/workflows/deploy-website.yml#L28-L37)
- **Deployment**: Deploys the static `out` directory to GitHub Pages via `actions/deploy-pages@v4`[.github/workflows/deploy-website.yml51-54](https://github.com/EverMind-AI/EverOS/blob/d40b8703/.github/workflows/deploy-website.yml#L51-L54)

**Sources:**[methods/evermemos/.pre-commit-config.yaml1-49](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/.pre-commit-config.yaml#L1-L49)[.github/workflows/deploy-website.yml1-54](https://github.com/EverMind-AI/EverOS/blob/d40b8703/.github/workflows/deploy-website.yml#L1-L54)[methods/evermemos/.devcontainer/postCreate.sh32-34](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/.devcontainer/postCreate.sh#L32-L34)

---

## Infrastructure Entity Mapping

This diagram bridges the conceptual memory entities to their physical storage backends and the scripts that manage them.

### Data Flow and Management

[Flowchart Diagram]

**Sources:**[methods/evermemos/.devcontainer/postCreate.sh12-34](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/.devcontainer/postCreate.sh#L12-L34)[methods/evermemos/.pre-commit-config.yaml12-46](https://github.com/EverMind-AI/EverOS/blob/d40b8703/methods/evermemos/.pre-commit-config.yaml#L12-L46)[.github/workflows/deploy-website.yml1-54](https://github.com/EverMind-AI/EverOS/blob/d40b8703/.github/workflows/deploy-website.yml#L1-L54)