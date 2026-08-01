# Game of Thrones Story Memory Demo
Relevant source files
- [use-cases/game-of-throne-demo/README.md](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/README.md?plain=1)
- [use-cases/game-of-throne-demo/backend/src/routes/chat.ts](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/backend/src/routes/chat.ts)
- [use-cases/game-of-throne-demo/backend/src/server.ts](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/backend/src/server.ts)
- [use-cases/game-of-throne-demo/backend/src/services/EverMemOSService.ts](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/backend/src/services/EverMemOSService.ts)

The Game of Thrones Story Memory Demo is a web application designed to showcase the impact of persistent AI memory on Large Language Model (LLM) performance. By providing a side-by-side comparison, users can observe how the same LLM (Claude-3-Haiku) responds to complex narrative queries both with and without context retrieved from the EverMemOS infrastructure [use-cases/game-of-throne-demo/README.md1-7](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/README.md?plain=1#L1-L7)

## System Overview

The demo utilizes a classic client-server architecture. The frontend is a React 18 application that handles user interaction and SSE (Server-Sent Events) streaming, while the Node.js backend orchestrates memory retrieval from EverMemOS and response generation via OpenRouter [use-cases/game-of-throne-demo/README.md20-25](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/README.md?plain=1#L20-L25)

### High-Level Data Flow

The following diagram illustrates the flow of a single user query through the system, highlighting the parallel execution of the "With Memory" and "Without Memory" streams.

**Query Execution Flow**

[Flowchart Diagram]

Sources: [use-cases/game-of-throne-demo/backend/src/routes/chat.ts109-170](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/backend/src/routes/chat.ts#L109-L170)[use-cases/game-of-throne-demo/backend/src/services/EverMemOSService.ts109-136](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/backend/src/services/EverMemOSService.ts#L109-L136)

## Backend Architecture

The backend is built with Node.js and Express, utilizing a service-oriented approach to abstract memory and LLM providers.

### Memory Service Integration

The backend uses the `IMemoryService` interface to allow for swappable memory implementations.

- **EverMemOSService**: The primary implementation that connects to the EverMemOS API or EverMind Cloud. It performs hybrid search (vector + keyword) via the `/api/v0/memories/search` endpoint [use-cases/game-of-throne-demo/backend/src/services/EverMemOSService.ts111-115](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/backend/src/services/EverMemOSService.ts#L111-L115) It maps raw results, including `original_data` messages and metadata like `bookTitle` and `chapterName`, into a unified `Memory` format [use-cases/game-of-throne-demo/backend/src/services/EverMemOSService.ts183-225](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/backend/src/services/EverMemOSService.ts#L183-L225)
- **MockMemoryService**: A fallback implementation for offline testing that uses a simple keyword-matching algorithm against a local JSON dataset of GoT passages [use-cases/game-of-throne-demo/backend/src/server.ts32](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/backend/src/server.ts#L32-L32)

### API Endpoints

The `createChatRouter` defines the core interaction logic [use-cases/game-of-throne-demo/backend/src/routes/chat.ts11-15](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/backend/src/routes/chat.ts#L11-L15):

| Endpoint | Method | Description |
| --- | --- | --- |
| `/chat` | POST | Standard single-response chat with memory augmentation. Streams tokens and then generates follow-up questions [use-cases/game-of-throne-demo/backend/src/routes/chat.ts17-79](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/backend/src/routes/chat.ts#L17-L79) |
| `/chat/compare` | POST | Triggers two parallel LLM streams: one using retrieved context and one using only the model's base knowledge. Uses `Promise.all` to process both streams concurrently [use-cases/game-of-throne-demo/backend/src/routes/chat.ts109-170](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/backend/src/routes/chat.ts#L109-L170) |
| `/health` | GET | Checks the availability of both the `IMemoryService` and `OpenAIService`[use-cases/game-of-throne-demo/backend/src/server.ts61](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/backend/src/server.ts#L61-L61) |

### Implementation Mapping

This diagram maps the logical components of the demo to their specific code entities.

**Code Entity Mapping**

[Flowchart Diagram]

Sources: [use-cases/game-of-throne-demo/backend/src/routes/chat.ts11-14](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/backend/src/routes/chat.ts#L11-L14)[use-cases/game-of-throne-demo/backend/src/services/EverMemOSService.ts85](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/backend/src/services/EverMemOSService.ts#L85-L85)[use-cases/game-of-throne-demo/backend/src/server.ts25-34](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/backend/src/server.ts#L25-L34)[use-cases/game-of-throne-demo/backend/src/routes/health.ts1-10](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/backend/src/routes/health.ts#L1-L10)

## Data Pipeline: Loading Novel Content

The demo includes a specialized script, `load-novel-cloud.ts`, to ingest the "A Game of Thrones" text into the memory system [use-cases/game-of-throne-demo/README.md134-135](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/README.md?plain=1#L134-L135)

### Ingestion Logic

1. **Boundary Detection**: The script automatically detects chapter boundaries using regex patterns (e.g., "PROLOGUE", "EDDARD", "CATELYN") [use-cases/game-of-throne-demo/README.md114](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/README.md?plain=1#L114-L114)
2. **Text Segmentation**: The novel is split into paragraphs to ensure that retrieved "memories" are granular enough to be useful as LLM context [use-cases/game-of-throne-demo/README.md115](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/README.md?plain=1#L115-L115)
3. **Metadata Enrichment**: Each segment is tagged with the book title, chapter number, and chapter name before being uploaded via the EverMind Cloud API [use-cases/game-of-throne-demo/README.md116](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/README.md?plain=1#L116-L116)
4. **Resumption**: The script supports resuming if the process is interrupted [use-cases/game-of-throne-demo/README.md117](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/README.md?plain=1#L117-L117)

### Sample Data

A sample file (`sample/got-sample.txt`) containing the first five chapters is provided for quick initialization [use-cases/game-of-throne-demo/README.md91-99](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/README.md?plain=1#L91-L99)

## Deployment and Configuration

The application is containerized and managed via environment variables.

### Environment Configuration

The backend requires several keys to function correctly [use-cases/game-of-throne-demo/backend/src/server.ts11-18](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/backend/src/server.ts#L11-L18):

- `OPENAI_API_KEY`: API key for the LLM provider (OpenRouter) [use-cases/game-of-throne-demo/backend/src/server.ts12](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/backend/src/server.ts#L12-L12)
- `OPENAI_MODEL`: The specific model to use, defaults to `openai/gpt-5.2` (configured for Claude Haiku in practice) [use-cases/game-of-throne-demo/backend/src/server.ts13](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/backend/src/server.ts#L13-L13)
- `EVERMEMOS_API_KEY`: Key for the EverMind Cloud infrastructure [use-cases/game-of-throne-demo/backend/src/server.ts17](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/backend/src/server.ts#L17-L17)
- `USE_EVERMEMOS`: Boolean flag to toggle between `EverMemOSService` and `MockMemoryService`[use-cases/game-of-throne-demo/backend/src/server.ts15](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/backend/src/server.ts#L15-L15)
- `EVERMEMOS_URL`: The base URL for the memory service, defaults to `http://localhost:1995` for local or `https://api.evermind.ai` for cloud [use-cases/game-of-throne-demo/backend/src/server.ts16](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/backend/src/server.ts#L16-L16)
- `EVERMEMOS_GROUP_ID`: The namespace for the book content, defaults to `asoiaf`[use-cases/game-of-throne-demo/backend/src/server.ts18](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/backend/src/server.ts#L18-L18)

### Execution

The demo can be started using `bun run dev`, which launches both the Vite-based React frontend (port 3000) and the Express backend (port 3001) [use-cases/game-of-throne-demo/README.md77-83](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/README.md?plain=1#L77-L83)

Sources: [use-cases/game-of-throne-demo/README.md48-83](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/README.md?plain=1#L48-L83)[use-cases/game-of-throne-demo/backend/src/server.ts11-42](https://github.com/EverMind-AI/EverOS/blob/d40b8703/use-cases/game-of-throne-demo/backend/src/server.ts#L11-L42)