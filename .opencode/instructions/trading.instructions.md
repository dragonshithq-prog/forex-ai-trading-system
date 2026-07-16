---
description: "Forex Trading Bot project conventions — backend, ML models, broker API, risk management, deployment."
applyTo: "**"
---

# Forex Trading Bot — Project Instructions

This is a full-stack Forex Trading Bot with Python backend, ML models, React frontend, and AWS infrastructure.

## Project Structure
- `backend/` — Python FastAPI backend
- `frontend/` — Next.js React frontend
- `ml/` — ML models and training pipeline
- `infrastructure/` — Terraform + K8s deployment
- `intelligence/` — Market intelligence reporting
- `hermes-agent/` — Hermes Agent (cloned repo)

## Tech Stack
- **Backend**: Python, FastAPI, SQLAlchemy, Celery, Redis, PostgreSQL
- **Frontend**: Next.js, React, Tailwind, shadcn/ui, TypeScript
- **ML**: Python, scikit-learn, TensorFlow/PyTorch
- **Infra**: Terraform, EKS, Docker, GitHub Actions
- **Broker**: MetaTrader 5 API via MCP

## Development Commands
- Backend: `cd backend && uvicorn main:app --reload`
- Frontend: `cd frontend && npm run dev`
- ML training: `cd ml && python train.py`

## Broker Connection
- Uses MetaTrader 5 MCP server for trade execution
- MCP configured in opencode.json under `mcp.metatrader`
