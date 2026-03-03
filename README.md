# HIVE Agent Framework - Railway Deployment Template

Deploy HIVE's self-improving AI agent framework to Railway in minutes.

## What is HIVE?

HIVE is an outcome-driven agent development framework that:
- Generates agent graphs from natural language goals
- Self-heals when failures occur
- Provides built-in observability and cost controls
- Supports 100+ LLM providers (OpenAI, Anthropic, Gemini, etc.)

## Quick Deploy to Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/hive-railway)

## Demo Agent

The template ships with a built-in `demo_agent` so you can test immediately after deployment:

```bash
curl -X POST https://your-app.railway.app/agents/run/demo_agent \
  -H "Content-Type: application/json" \
  -d '{"task": "Hello HIVE!"}'
```

## Manual Deployment Steps

### 1. Prerequisites

- Railway account ([signup here](https://railway.app))
- API key for at least one LLM provider:
  - Anthropic (Claude): https://console.anthropic.com
  - OpenAI (GPT-5): https://platform.openai.com
  - Google (Gemini): https://ai.google.dev

### 2. Deploy to Railway

1. Go to [Railway](https://railway.app)
2. Click "New Project" → "Deploy from GitHub repo"
3. Select this repository / Template
4. Configure environment variables (see below)
5. Deploy!

### 3. Configure Environment Variables

In Railway dashboard, add these variables:

**Required:**
```
ANTHROPIC_API_KEY=sk-ant-xxxxx
```
or
```
OPENAI_API_KEY=sk-xxxxx
```
or
```
GOOGLE_API_KEY=AI-xxxxx
```

**Optional:**
```
DEFAULT_MODEL=claude-sonnet-4-20250514
PORT=8000
```

### 4. Add Persistent Storage (Recommended)

HIVE needs persistent storage for:
- Agent exports
- Credentials
- Conversation logs

In Railway dashboard:
1. Go to your service
2. Click "Volumes"
3. Add volume mounted to `/app/data`

## Deployment Modes

This template supports two deployment modes:

### Mode 1: HTTP API (Default)

Runs HIVE as a REST API you can call from your applications.

**Dockerfile:** `Dockerfile.api`

**Endpoints:**
- `GET /health` - Health check
- `GET /agents` - List available agents
- `POST /agents/run/{agent_name}` - Run an agent
- `POST /agents/create` - Create an agent
- `DELETE /agents/manage/{agent_name}` - Delete an agent

**Example request:**
```bash
# Quick start
curl -X POST https://your-app.railway.app/agents/run/my_agent \
  -H "Content-Type: application/json" \
  -d '{"task": "Analyze sales data"}'
  
  # 1. Test demo agent (built-in)
  curl -X POST https://your-app.railway.app/agents/run/demo_agent \
    -d '{"task": "test"}'
  
  # 2. Create your own agent via API
  curl -X POST https://your-app.railway.app/agents/create \
    -d '{"agent_name": "my_agent", "goal": "Process data"}'
  
  # 3. Run your agent
  curl -X POST https://your-app.railway.app/agents/run/my_agent \
    -d '{"data": "sample"}'
  
  # 4. List all agents
  curl https://your-app.railway.app/agents
  
  # 5. Delete if needed
  curl -X DELETE https://your-app.railway.app/agents/manage/my_agent
```

### Mode 2: TUI Dashboard

Runs the interactive Terminal UI (not recommended for Railway, better for local).

**Dockerfile:** `Dockerfile`

## Project Structure

```
hive-railway/
├── Dockerfile              # TUI mode deployment
├── Dockerfile.api          # HTTP API mode deployment  
├── server.py               # FastAPI wrapper for agents
├── docker-compose.yml      # Local testing
├── railway.json            # Railway configuration
├── .env.example            # Environment variables template
└── README.md              # This file
```

## Creating Agents

### Method 1: Via Claude Code (Recommended)

Once deployed, you'll need to build agents locally, then deploy them:

```bash
# Clone HIVE locally
git clone https://github.com/aden-hive/hive.git
cd hive
./quickstart.sh

# Build agent with Claude Code
claude> /hive

# Agent is created in exports/your_agent_name/
```

Then copy your agent to the Railway deployment:
```bash
# Add your agent to this repository
cp -r exports/my_agent /path/to/hive-railway/exports/

# Commit and push
git add exports/my_agent
git commit -m "Add my_agent"
git push

# Railway will auto-deploy
```

## Monitoring and Observability

HIVE provides built-in observability:

- **Real-time logs:** Check Railway logs tab
- **Cost tracking:** Monitor LLM API usage in agent responses
- **Health checks:** `/health` endpoint

## Troubleshooting

### Agent not found
- Ensure agent exists in `/app/exports/`
- Check Railway logs for import errors
- Verify `agent.json` exists in agent directory

### API key errors
- Verify environment variables in Railway dashboard
- Check variable names match (e.g., `ANTHROPIC_API_KEY` not `ANTHROPIC_KEY`)
- Ensure API key is valid and has credits

### Import errors
- HIVE requires Python 3.11+
- Check Railway build logs for dependency issues

## Scaling and Production

### Horizontal Scaling
Enable in Railway:
```
Settings → Deploy → Replicas: 2+
```

### Add PostgreSQL for Persistence
```bash
railway add postgresql
# Update server.py to use PostgreSQL for conversation logs
```

### Add Redis for Caching
```bash
railway add redis
# Implement caching in server.py
```

## Cost Considerations

Railway charges for:
- Compute time (based on plan)
- Data transfer
- Storage (volumes)

HIVE charges for:
- LLM API calls (your API key, not Railway)

**Estimate:**
- Small agent: ~$5-10/month Railway + LLM costs
- Production agent: ~$20-50/month Railway + LLM costs

## Security Best Practices

1. **Never commit API keys** - Use Railway environment variables
2. **Enable Railway's built-in auth** if exposing publicly
3. **Use secrets management** for production
4. **Monitor costs** - Set budget alerts in LLM provider dashboards

## Support

- HIVE Docs: https://docs.adenhq.com
- HIVE GitHub: https://github.com/aden-hive/hive
- HIVE Discord: https://discord.com/invite/MXE49hrKDk
- Railway Docs: https://docs.railway.app

## License

HIVE is licensed under Apache 2.0.
This template is MIT licensed.

## Contributing

PRs welcome! Please:
1. Test locally with `docker-compose up`
2. Update README if adding features
3. Follow HIVE's contribution guidelines
