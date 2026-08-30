# Scripts Directory

Helper scripts for CrossRef Local operations and deployment.

## Directory Structure

```
scripts/
├── status.sh         # Overall system status (store, MCP server)
├── database/         # Retired build pipeline — see database/README.md
└── deployment/       # Container deployment + MCP server service
    ├── install_apptainer.sh
    ├── build_apptainer.sh
    ├── run_apptainer.sh
    ├── run_docker.sh
    └── mcp/          # systemd / Docker packaging for the MCP server
```

## Corpus Management

There are no corpus build scripts any more. The corpus lives in the fleet's
shared store primitive, so ingest and bookkeeping are package commands rather
than a directory of shell steps:

```bash
crossref-local update-db            # incremental ingest from the CrossRef REST API
crossref-local update-db --dry-run  # count what would be upserted, write nothing
crossref-local sync-stats           # recompute the exact-count cache
crossref-local status               # store resolution + cached counts
```

See [`database/README.md`](database/README.md) for what each retired script
used to do and what replaced it.

## Status

### `status.sh`

Overall system status: whether the store resolves, and the MCP server's state.

```bash
./scripts/status.sh           # Full status report
./scripts/status.sh --quiet   # Exit 0 if healthy, 1 if issues
./scripts/status.sh --json    # JSON output for scripting
```

## Deployment Scripts

### `deployment/install_apptainer.sh`

Install Apptainer container runtime.

```bash
./scripts/deployment/install_apptainer.sh --help
./scripts/deployment/install_apptainer.sh           # Install default version
./scripts/deployment/install_apptainer.sh -v 1.2.5  # Specific version
```

### `deployment/build_apptainer.sh`

Build Apptainer/Singularity container image.

```bash
./scripts/deployment/build_apptainer.sh --help
./scripts/deployment/build_apptainer.sh         # Build with defaults
./scripts/deployment/build_apptainer.sh --force # Force rebuild
```

### `deployment/run_apptainer.sh`

Run crossref-local with Apptainer container.

```bash
./scripts/deployment/run_apptainer.sh --help
./scripts/deployment/run_apptainer.sh              # Start API server
./scripts/deployment/run_apptainer.sh search CRISPR # Run search
./scripts/deployment/run_apptainer.sh shell        # Interactive shell
```

### `deployment/run_docker.sh`

Run crossref-local with Docker container.

```bash
./scripts/deployment/run_docker.sh --help
./scripts/deployment/run_docker.sh              # Start API server
./scripts/deployment/run_docker.sh search CRISPR # Run search
./scripts/deployment/run_docker.sh shell        # Interactive shell
```

### `deployment/mcp/`

Systemd unit, Dockerfile and helper scripts for the MCP server. Driven from
the repo root with `make mcp-install`, `make mcp-status`, `make mcp-logs`.

## Quick Reference

**First-time setup:**
```bash
make install          # install the package
make status           # check the store resolves
crossref-local update-db   # pull recent works into the store
make test
```

<!-- EOF -->
