# RAG Application — Azure

Production-ready RAG app running on **Azure Container Apps**, with Azure Blob Storage, Azure Database for PostgreSQL, Azure Cache for Redis, and Azure Key Vault for secrets.

## Azure Service Map

| Component | Azure Service |
|---|---|
| Container registry | Azure Container Registry (ACR) |
| App hosting | Azure Container Apps |
| Database | Azure Database for PostgreSQL Flexible Server |
| Cache + Queue | Azure Cache for Redis |
| File storage | Azure Blob Storage |
| Secrets | Azure Key Vault |
| Logs | Azure Monitor / Log Analytics |
| CI/CD | GitHub Actions → ACR → Container Apps |

## Local development

```bash
cp backend/.env.example backend/.env  # fill in real API keys
docker-compose up --build
# Azurite (local blob emulator) starts automatically
# Frontend: http://localhost:3000
# Backend:  http://localhost:8000
```

## Deploy

See the full Azure deployment guide (azure-deployment-guide.docx) for step-by-step instructions.

GitHub Secrets required:

| Secret | How to get it |
|---|---|
| `AZURE_CREDENTIALS` | `az ad sp create-for-rbac --sdk-auth` output |
| `NEXT_PUBLIC_API_URL` | Your backend Container App FQDN |

## Key differences from AWS version

| AWS | Azure |
|---|---|
| S3 | Azure Blob Storage (`azure-storage-blob`) |
| ECR | Azure Container Registry (ACR) |
| ECS Fargate | Azure Container Apps |
| RDS Postgres | Azure Database for PostgreSQL Flexible Server |
| ElastiCache Redis | Azure Cache for Redis (TLS port 6380) |
| Secrets Manager | Azure Key Vault |
| IAM Roles | Managed Identity + RBAC |
| CloudWatch | Azure Monitor + Log Analytics |
| API Gateway | Container Apps built-in ingress |
# Prod_RAG_Application
