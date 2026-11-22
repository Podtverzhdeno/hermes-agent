---
name: fastmcp
description: Build and test scoped Python FastMCP servers with typed tools, bounded resource roots and verified client calls; require approval for installs, client registrations and external HTTP deployment.
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [MCP, FastMCP, Python, Tools, Resources, Prompts, Deployment]
    homepage: https://gofastmcp.com
    related_skills: [native-mcp, mcporter]
prerequisites:
  commands: [python3]
---

# FastMCP

Build **authorized** MCP servers in Python, testing locally before granting client or network access. The sibling `harness.yaml` is an advisory execution contract, not a runtime grant.

## When to Use

Use this skill when the task is to:

- create a new MCP server in Python
- wrap an API, database, CLI, or file-processing workflow as MCP tools
- expose resources or prompts in addition to tools
- smoke-test a server with the FastMCP CLI before wiring it into Hermes or another client
- install a server into Claude Code, Claude Desktop, Cursor, or a similar MCP client
- prepare a FastMCP server repo for HTTP deployment

Use `native-mcp` when the server already exists and only needs to be connected to Hermes. Use `mcporter` when the goal is ad-hoc CLI access to an existing MCP server instead of building one.

## Prerequisites — isolation and version control

FastMCP 4 reached general availability on 2026-08-31. Inspect the currently installed version and verify API/CLI compatibility before choosing examples; do not assume snippets written for 2.x or 3.x work unchanged on 4.x.

Package installs and upgrades execute code and require authorization. Install only into an isolated, project-owned virtual environment, preferably with a lockfile and an exact tested version:

```bash
python -m venv .venv
.venv/bin/python -m pip install 'fastmcp>=4,<5'  # only if installation is approved
.venv/bin/fastmcp version
```

On Windows use the corresponding `.venv/Scripts` executables. `httpx` is optional for the API template; authorize and pin it separately rather than installing it globally. Do not modify system Python or global MCP-client settings as a setup side effect.
## Included Files

### Templates

- `templates/api_wrapper.py` - REST API wrapper with auth header support
- `templates/database_server.py` - read-only SQLite query server
- `templates/file_processor.py` - text-file inspection and search server

### Scripts

- `scripts/scaffold_fastmcp.py` - copy a starter template and replace the server name placeholder

### References

- FastMCP 4 GA and migration: https://blog.gofastmcp.com/3mufbh2vcv22o
- Current documentation: https://gofastmcp.com/


- `references/fastmcp-cli.md` - FastMCP CLI workflow, installation targets, and deployment checks

## Workflow

### 1. Pick the Smallest Viable Server Shape

Choose the narrowest useful surface area first:

- API wrapper: start with 1-3 high-value endpoints, not the whole API
- database server: expose read-only introspection and a constrained query path
- file processor: expose deterministic operations with explicit path arguments
- prompts/resources: add only when the client needs reusable prompt templates or discoverable documents

Prefer a thin server with good names, docstrings, and schemas over a large server with vague tools.

### 2. Scaffold from a Template

Copy a template directly or use the scaffold helper:

```bash
python ~/.hermes/skills/mcp/fastmcp/scripts/scaffold_fastmcp.py \
  --template api_wrapper \
  --name "Acme API" \
  --output ./acme_server.py
```

Available templates:

```bash
python ~/.hermes/skills/mcp/fastmcp/scripts/scaffold_fastmcp.py --list
```

If copying manually, replace `__SERVER_NAME__` with a real server name.

### 3. Implement Tools First

Start with `@mcp.tool` functions before adding resources or prompts.

Rules for tool design:

- Give every tool a concrete verb-based name
- Write docstrings as user-facing tool descriptions
- Keep parameters explicit and typed
- Return structured JSON-safe data where possible
- Validate unsafe inputs, resource ownership, byte budgets and output sizes early
- Prefer read-only behavior by default for first versions
- Enforce any identity/authorization check at actual tool dispatch, not in descriptive prose alone

Good tool examples:

- `get_customer`
- `search_tickets`
- `describe_table`
- `summarize_text_file`

Weak tool examples:

- `run`
- `process`
- `do_thing`

### 4. Add Resources and Prompts Only When They Help

Add `@mcp.resource` when the client benefits from fetching stable read-only content such as schemas, policy docs, or generated reports.

Add `@mcp.prompt` when the server should provide a reusable prompt template for a known workflow.

Do not turn every document into a prompt. Prefer:

- tools for actions
- resources for data/document retrieval
- prompts for reusable LLM instructions

### 5. Test the Server Before Integrating It Anywhere

Use the FastMCP CLI for local validation:

```bash
fastmcp inspect acme_server.py:mcp
fastmcp list acme_server.py --json
fastmcp call acme_server.py search_resources query=router limit=5 --json
```

For fast iterative debugging, run the server locally:

```bash
fastmcp run acme_server.py:mcp
```

To test HTTP transport on **loopback**, only when starting a local listener is approved:

```bash
fastmcp run acme_server.py:mcp --transport http --host 127.0.0.1 --port 8000
fastmcp list http://127.0.0.1:8000/mcp --json
fastmcp call http://127.0.0.1:8000/mcp search_resources query=router --json
```

Always run at least one real `fastmcp call` against each new tool before claiming the server works.

### 6. Install into a Client When Local Validation Passes

FastMCP can register the server with supported MCP clients:

```bash
fastmcp install claude-code acme_server.py
fastmcp install claude-desktop acme_server.py
fastmcp install cursor acme_server.py -e .
```

Use `fastmcp discover` to inspect named MCP servers already configured on the machine.

When the goal is Hermes integration, either:

- configure the server in `~/.hermes/config.yaml` using the `native-mcp` skill, or
- keep using FastMCP CLI commands during development until the interface stabilizes

### 7. Deploy Only When Explicitly Authorized

For managed hosting, verify the current FastMCP Gateway or other supported provider documentation, identity, cost, network exposure and audit controls. Never deploy simply because the Skill was selected. Before an authorized deployment:

```bash
fastmcp inspect acme_server.py:mcp
```

Make sure the repo contains:

- a Python file with the FastMCP server object
- `requirements.txt` or `pyproject.toml`
- any environment-variable documentation needed for deployment

For generic HTTP hosting, validate the HTTP transport locally first, then deploy on any Python-compatible platform that can expose the server port.

## Common Patterns

### API Wrapper Pattern

Use when exposing a REST or HTTP API as MCP tools.

Recommended first slice:

- one read path
- one list/search path
- optional health check

Implementation notes:

- keep auth in environment variables, not hardcoded
- centralize request logic in one helper
- surface API errors with concise context
- normalize inconsistent upstream payloads before returning them

Start from `templates/api_wrapper.py`.

### Database Pattern

Use when exposing safe query and inspection capabilities.

Recommended first slice:

- `list_tables`
- `describe_table`
- one constrained read query tool

Implementation notes:

- default to read-only DB access
- reject non-`SELECT` SQL in early versions, but recognize that SELECT-only string checking is not a security sandbox; keep the DB read-only and restrict the OS account
- limit row counts
- return rows plus column names

Start from `templates/database_server.py`.

### File Processor Pattern

Use when the server needs to inspect or transform files on demand.

Recommended first slice:

- summarize file contents
- search within files
- extract deterministic metadata

Implementation notes:

- accept explicit file paths
- check for missing files and encoding failures
- cap previews and result counts
- avoid shelling out unless a specific external tool is required
- configure a dedicated `MCP_FILE_ROOT` before running the bundled file processor, which fails closed when the variable is absent
- never point a file-reading server at a home directory or credentials; apply OS-level isolation for hostile filesystem content

Start from `templates/file_processor.py`.

## File template: explicit root and bounded reads

`templates/file_processor.py` requires `MCP_FILE_ROOT` to be configured to an approved, dedicated data folder. It rejects absolute paths, `..` traversal and symlinks and limits input to 1 MiB, previews to 4,000 characters and match excerpts. These checks are **not an OS sandbox or a proof against filesystem TOCTOU races**. Limit the process's actual filesystem access independently, especially when untrusted local actors can modify the folder.

Do not run a scaffolded file tool on user home, secrets, repository credentials or an unrestricted filesystem. Audit templates before registering clients.

## Quality Bar

Before handing off a FastMCP server, verify all of the following:

- server imports cleanly
- `fastmcp inspect <file.py:mcp>` succeeds
- `fastmcp list <server spec> --json` succeeds
- every new tool has at least one real `fastmcp call` or is explicitly reported untested
- invalid inputs, traversal and unauthorized operations are tested
- environment variables are documented
- the tool surface is small enough to understand without guesswork

## Troubleshooting

### FastMCP command missing

Install the package in the active environment:

```bash
pip install fastmcp
fastmcp version
```

### `fastmcp inspect` fails

Check that:

- the file imports without side effects that crash
- the FastMCP instance is named correctly in `<file.py:object>`
- optional dependencies from the template are installed

### Tool works in Python but not through CLI

Run:

```bash
fastmcp list server.py --json
fastmcp call server.py your_tool_name --json
```

This usually exposes naming mismatches, missing required arguments, or non-serializable return values.

### Hermes cannot see the deployed server

The server-building part may be correct while the Hermes config is not. Load the `native-mcp` skill and configure the server in `~/.hermes/config.yaml`, then restart Hermes.

## References

For CLI details, install targets, and deployment checks, read `references/fastmcp-cli.md`.
