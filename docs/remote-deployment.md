# Remote MCP Deployment Guide

Run CrossRef Local as a persistent MCP server accessible over the network.

## Why HTTP Transport?

| SSH Transport | HTTP Transport |
|--------------|----------------|
| Claude Code hangs on connection failure | Graceful timeout/retry |
| Spawns new process per session | Persistent server |
| Shell management overhead | Clean HTTP protocol |
| Requires SSH key setup | Firewall-friendly |

**Note:** SSE transport is deprecated as of MCP spec 2025-03-26. Use HTTP (Streamable HTTP) instead.

## Quick Start

```bash
# Start MCP server with HTTP transport.
# The corpus lives in this host's shared store; scitex-dev resolves it.
# Set SCITEX_STORE_DSN only to point at a store other than this host's.
crossref-local run-server-mcp -t http --host 0.0.0.0 --port 8082
```

Client configuration:
```json
{
  "mcpServers": {
    "crossref-remote": {
      "url": "http://your-server:8082/mcp"
    }
  }
}
```

## Systemd Service (Recommended)

For production deployment, use systemd to manage the service.

### 1. Edit the service file

```bash
# Copy and customize the service file
sudo cp scripts/deployment/mcp/crossref-mcp.service /etc/systemd/system/

# Edit to match your setup
sudo nano /etc/systemd/system/crossref-mcp.service
```

Key settings to customize:
- `User` and `Group` - your user account
- `SCITEX_STORE_DSN` - only if the store is not this host's own
- `--port` - change if 8082 is in use

### 2. Enable and start

```bash
sudo systemctl daemon-reload
sudo systemctl enable crossref-mcp
sudo systemctl start crossref-mcp
```

### 3. Verify

```bash
# Check service status
sudo systemctl status crossref-mcp

# View logs
journalctl -u crossref-mcp -f

# Test endpoint
curl http://localhost:8082/mcp
```

## Docker Deployment

### Using Docker Compose

```yaml
# docker-compose.yml
services:
  crossref-mcp:
    image: python:3.11-slim
    command: >
      sh -c "pip install crossref-local[mcp] &&
             crossref-local run-server-mcp -t http --host 0.0.0.0 --port 8082"
    ports:
      - "8082:8082"
    environment:
      # Reach the host's store from inside the container.
      - SCITEX_STORE_DSN=${SCITEX_STORE_DSN}
    restart: unless-stopped
```

There is no volume to mount: the corpus is not a file. A container needs a
route to the store instead — `SCITEX_STORE_DSN` naming a reachable address,
or the host's store socket bind-mounted in.

### Using Dockerfile

```dockerfile
FROM python:3.11-slim

RUN pip install crossref-local[mcp]

EXPOSE 8082

CMD ["crossref-local", "run-server-mcp", "-t", "http", "--host", "0.0.0.0", "--port", "8082"]
```

Build and run:
```bash
docker build -t crossref-mcp .
docker run -d \
  -p 8082:8082 \
  -e SCITEX_STORE_DSN="$SCITEX_STORE_DSN" \
  --name crossref-mcp \
  crossref-mcp
```

## Client Configuration

### Claude Desktop / Claude Code

Add to your MCP configuration file:

```json
{
  "mcpServers": {
    "crossref-remote": {
      "url": "http://your-server:8082/mcp"
    }
  }
}
```

Configuration file locations:
- **Claude Desktop (macOS):** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Claude Desktop (Windows):** `%APPDATA%\Claude\claude_desktop_config.json`
- **Claude Code:** `.claude/settings.json` or `~/.claude/settings.json`

### Multiple Servers

You can configure both local and remote servers:

```json
{
  "mcpServers": {
    "crossref-local": {
      "command": "crossref-local",
      "args": ["run-server-mcp"]
    },
    "crossref-remote": {
      "url": "http://store-host:8082/mcp"
    }
  }
}
```

> Replace `store-host` with the actual hostname or IP of the machine whose
> shared store holds the corpus (any reachable Linux box — commonly a NAS or
> workstation; the package is host-agnostic).

## Security Considerations

### Firewall

Restrict access to trusted networks:

```bash
# UFW example
sudo ufw allow from 192.168.1.0/24 to any port 8082

# iptables example
iptables -A INPUT -p tcp --dport 8082 -s 192.168.1.0/24 -j ACCEPT
iptables -A INPUT -p tcp --dport 8082 -j DROP
```

### Reverse Proxy with TLS

For production, use a reverse proxy with TLS:

```nginx
# /etc/nginx/sites-available/crossref-mcp
server {
    listen 443 ssl http2;
    server_name crossref.example.com;

    ssl_certificate /etc/letsencrypt/live/crossref.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/crossref.example.com/privkey.pem;

    location /mcp {
        proxy_pass http://127.0.0.1:8082;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }
}
```

## Troubleshooting

### Service won't start

```bash
# Check logs
journalctl -u crossref-mcp -n 50

# Common issues:
# - Store unreachable (wrong SCITEX_STORE_DSN, or the host's store is down)
# - Port already in use
# - Permission denied
```

### Connection refused

```bash
# Verify service is running
systemctl status crossref-mcp

# Check port is listening
ss -tlnp | grep 8082

# Test locally first
curl http://localhost:8082/mcp
```

### Claude Code hangs

If using SSH transport and experiencing hangs, switch to HTTP:

```json
// Before (SSH - can hang)
{
  "crossref-remote": {
    "command": "ssh",
    "args": ["store-host", "crossref-local", "run-server-mcp"]
  }
}

// After (HTTP - recommended)
{
  "crossref-remote": {
    "url": "http://store-host:8082/mcp"
  }
}
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SCITEX_STORE_DSN` | Connection string for the shared store, read by `scitex_dev.store.host_store()` | This host's own store |
| `CROSSREF_LOCAL_MCP_HOST` | Host to bind | `localhost` |
| `CROSSREF_LOCAL_MCP_PORT` | Port to listen on | `8082` |

`crossref-local` never builds or reads a DSN itself — resolution belongs to
`scitex_dev.store.host_store()`, so setting `SCITEX_STORE_DSN` is the only
way to point it at a store other than this host's.

## References

- [MCP Transports Specification](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
