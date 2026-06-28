---
name: deploy
description: Deploys the Sports-Data-Ingestion-Pipeline project to the home server (192.168.1.166), connecting to the shared sports-gaming-engine infrastructure. Use this skill whenever the user asks to deploy, ship, push to the server, update the remote pipeline, or restart the ingestion stack on 192.168.1.166.
---

# Deploy Skill (Sports-Data-Ingestion-Pipeline)

Deploys the latest code to the home server at `192.168.1.166` and connects the services (`dagster-webserver`, `dagster-daemon`, `jupyter`) directly to the shared infrastructure (`signoz-otel-collector`, `redis`) running in `sports-gaming-engine`.

## How to Deploy

First, commit and push all local changes that need to be deployed, then:

1. SSH into `192.168.1.166` (SSH key is pre-configured, no password needed)
2. Change to `~/dllewellyn/Sports-Data-Ingestion-Pipeline`
3. Run `git pull` to fetch the latest code
4. Ensure the `.env` file on the remote machine is configured for remote deployment:
   ```bash
   COMPOSE_FILE=docker-compose.yml:docker-compose.remote.yml
   DAGSTER_UI_PORT=3002
   ```
5. Rebuild and restart the Docker stack:
   ```bash
   docker compose up -d --build
   ```

## Verifying the Deployment

After `docker compose up -d --build` completes, confirm the Dagster UI service is reachable on port `3002`:

```bash
curl -s -o /dev/null -w "%{http_code}" http://192.168.1.166:3002/
```

A `200` response means the Dagster webserver is up and running.

You can also verify container health and logs:
```bash
ssh 192.168.1.166 "cd ~/dllewellyn/Sports-Data-Ingestion-Pipeline && docker compose ps"
ssh 192.168.1.166 "cd ~/dllewellyn/Sports-Data-Ingestion-Pipeline && docker compose logs dagster-webserver --tail=30"
```

## Infrastructure Sharing & Deconflicting

This pipeline runs alongside `sports-gaming-engine` without conflicting or spinning up redundant infrastructure:

| Service / Infrastructure | Handling / Port on Host | Notes |
|---|---|---|
| **Docker Network** | `sports-quant` (external) | Joins existing bridge network created by `sports-gaming-engine` |
| **Telemetry (SigNoz/OTEL)** | `signoz-otel-collector:4317` | Exports traces/metrics via gRPC to shared SigNoz stack |
| **Redis Cache** | `redis:6379` | Shares Redis container running on `sports-quant` network |
| **Dagster Webserver** | Port `3002` (`3002:3000`) | Shifted from `3000` to avoid conflict with Grafana & other Dagster |
| **JupyterLab** | Port `8888` (`8888:8888`) | Standard Jupyter port |
