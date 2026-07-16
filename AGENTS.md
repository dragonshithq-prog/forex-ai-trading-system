# AGENTS.md

## Work in progress (2026-07-14)

**Task:** Forex Trading Bot — full-stack automated trading system
**Status:** Active development

## Change history

## ADR-001 — Project setup (2026-07-14)
- Context: Full-stack Forex trading bot with Python backend, React frontend, ML, and AWS infra
- Stack: Python FastAPI + Next.js + PostgreSQL + Redis + EKS
- Decision: Monorepo with separate backend/frontend/ml/infra directories
- Why: Clean separation of concerns while keeping everything in one repo
- Consequences: CI/CD must handle multiple deploy targets
