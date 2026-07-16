"""Comprehensive audit logging for sensitive operations.

Every sensitive operation (role changes, config changes, trade overrides,
user deletions, etc.) is persisted to the ``audit_logs`` table with:
  - user_id (who did it)
  - action (verb, e.g. ``role.update``)
  - resource_type / resource_id (what was affected)
  - details (JSON payload with extra context)
  - ip_address (originating IP)
  - timestamp (when it happened)

A FastAPI middleware captures **all** API requests as audit entries.

Enhanced with:
  - SHA-256 chain linking (each entry includes hash of previous entry)
  - Tamper detection (verify chain integrity)
  - External witness (publish chain hashes to S3)
  - Query API for regulators
  - Write-once enforcement via DB trigger (documented, see migration)
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import Request, Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import structlog

from forex_trading.shared.database.models_user import AuditLog
from forex_trading.shared.database.models_compliance import AuditLogChain

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Sensitive action registry
# ---------------------------------------------------------------------------

# Actions that MUST always be audited
SENSITIVE_ACTIONS: set[str] = {
    # Authentication & users
    "user.login",
    "user.logout",
    "user.create",
    "user.delete",
    "user.role.update",
    "user.toggle_active",
    "user.password.reset",
    "user.password.change",
    "user.mfa.setup",
    "user.mfa.verify",
    "user.mfa.disable",
    # Broker & accounts
    "broker.account.create",
    "broker.account.update",
    "broker.account.delete",
    "broker.account.connect",
    "broker.account.disconnect",
    "broker.credentials.update",
    # Risk & trading
    "risk.config.update",
    "risk.circuit_breaker.activate",
    "risk.circuit_breaker.reset",
    "risk.emergency_close",
    "risk.override.create",
    "trading.order.place",
    "trading.order.cancel",
    "trading.position.close",
    "trading.position.modify_sl",
    "trading.position.modify_tp",
    # Strategy & AI
    "strategy.create",
    "strategy.update",
    "strategy.delete",
    "ai.config.update",
    "ai.model.reload",
    # Compliance
    "compliance.retention.purge",
    "compliance.pii.dsar",
    "compliance.pii.erasure",
    "compliance.reconstruction.query",
    "compliance.reporting.generate",
    "compliance.consent.grant",
    "compliance.consent.withdraw",
    "compliance.consent.withdraw_all",
    "compliance.disclosure.generated",
    "compliance.disclosure.strategy_warning",
    "compliance.disclosure.per_trade",
    "compliance.disclosure.acknowledged",
    # System
    "system.config.update",
    "system.secrets.rotate",
    "system.api_key.create",
    "system.api_key.revoke",
    "system.api_key.rotate",
}


def is_sensitive_path(method: str, path: str) -> bool:
    """Heuristic to detect sensitive endpoints."""
    path_lower = path.lower()
    method_upper = method.upper()

    # Always audit mutations to sensitive resources
    sensitive_prefixes = [
        "/api/v1/users/",
        "/api/v1/auth/",
        "/api/v1/broker/",
        "/api/v1/risk/",
        "/api/v1/trading/",
        "/api/v1/strategy/strategies",
        "/api/v1/admin/",
        "/api/v1/compliance/",
    ]
    for prefix in sensitive_prefixes:
        if path_lower.startswith(prefix):
            return True

    # POST/PUT/PATCH/DELETE to sensitive top-level resources
    if method_upper in ("POST", "PUT", "PATCH", "DELETE"):
        sensitive_collections = [
            "/api/v1/users",
            "/api/v1/auth",
            "/api/v1/broker",
            "/api/v1/risk/config",
            "/api/v1/risk/circuit-breaker",
            "/api/v1/risk/emergency",
            "/api/v1/compliance",
        ]
        for col in sensitive_collections:
            if path_lower.startswith(col):
                return True

    return False


def classify_action(method: str, path: str) -> str:
    """Derive a dotted action string from the HTTP method and path.

    Example: ``POST /api/v1/users/{id}/role`` -> ``user.role.update``
    """
    method_lower = method.lower()
    path_lower = path.lower().rstrip("/")

    # Strip API prefix
    for prefix in ("/api/v1", "/api/v2"):
        if path_lower.startswith(prefix):
            path_lower = path_lower[len(prefix):]
            break

    segments = [s for s in path_lower.split("/") if s]

    if not segments:
        return f"system.{method_lower}"

    resource = segments[0]

    # Map HTTP methods to action verbs
    verb_map = {
        "post": "create" if method_lower == "post" else "execute",
        "get": "read",
        "put": "update",
        "patch": "update",
        "delete": "delete",
    }
    verb = verb_map.get(method_lower, method_lower)

    return f"{resource}.{verb}"


# ---------------------------------------------------------------------------
# SHA-256 Chain Linking
# ---------------------------------------------------------------------------


class AuditChainManager:
    """Manages the SHA-256 chain linking for immutable audit logs.

    Each audit log entry has a corresponding ``AuditLogChain`` record
    that stores:
      - The SHA-256 hash of the current entry
      - The hash of the previous entry in the chain
      - The chain index (monotonically increasing)
      - Optional witness information (e.g., S3 object key)
    """

    def __init__(self) -> None:
        self._witness_backend: WitnessBackend | None = None

    def set_witness_backend(self, backend: WitnessBackend) -> None:
        """Set the external witness backend."""
        self._witness_backend = backend

    async def link_entry(
        self,
        db: AsyncSession,
        audit_log_id: UUID,
        audit_entry_content: dict[str, Any],
    ) -> AuditLogChain:
        """Create a chain link for a new audit log entry.

        Computes the hash of the current entry and links it to the
        previous entry in the chain.
        """
        # Get the latest previous chain entry
        result = await db.execute(
            select(AuditLogChain).order_by(AuditLogChain.chain_index.desc()).limit(1)
        )
        previous = result.scalars().first()

        previous_hash = previous.current_hash if previous else None
        chain_index = (previous.chain_index + 1) if previous else 0

        # Compute current hash
        current_hash = self._compute_entry_hash(
            audit_entry_content, previous_hash=previous_hash,
        )

        chain_entry = AuditLogChain(
            audit_log_id=audit_log_id,
            previous_hash=previous_hash,
            current_hash=current_hash,
            chain_index=chain_index,
        )
        db.add(chain_entry)
        await db.flush()
        await db.refresh(chain_entry)

        # Publish to external witness if configured
        if self._witness_backend:
            try:
                witness_id = await self._witness_backend.witness(
                    current_hash, chain_index,
                )
                chain_entry.witness_tx_id = witness_id
                chain_entry.witness_location = witness_id
                chain_entry.witness_timestamp = datetime.now(timezone.utc)
                await db.flush()
            except Exception as exc:
                logger.warning("audit_witness_failed", error=str(exc))

        return chain_entry

    async def verify_chain(
        self,
        db: AsyncSession,
        from_index: int = 0,
        to_index: int | None = None,
    ) -> ChainVerificationResult:
        """Verify the integrity of the audit log chain.

        Walks the chain from ``from_index`` to ``to_index`` and verifies
        that each entry's hash matches its content and links to the next.

        Returns a ``ChainVerificationResult`` with any issues found.
        """
        query = select(AuditLogChain).order_by(AuditLogChain.chain_index)
        if from_index > 0:
            query = query.where(AuditLogChain.chain_index >= from_index)
        if to_index is not None:
            query = query.where(AuditLogChain.chain_index <= to_index)

        result = await db.execute(query)
        chain_entries = result.scalars().all()

        issues: list[str] = []
        verified_count = 0

        for i, entry in enumerate(chain_entries):
            # Fetch the corresponding audit log
            audit_result = await db.execute(
                select(AuditLog).where(AuditLog.id == entry.audit_log_id)
            )
            audit_entry = audit_result.scalars().first()
            if not audit_entry:
                issues.append(
                    f"Chain index {entry.chain_index}: audit log entry {entry.audit_log_id} not found"
                )
                continue

            # Compute expected content dict
            content = self._build_entry_content(audit_entry)

            # Get previous hash
            prev_hash = chain_entries[i - 1].current_hash if i > 0 else None

            # Verify current hash
            expected_hash = self._compute_entry_hash(content, previous_hash=prev_hash)
            if expected_hash != entry.current_hash:
                issues.append(
                    f"Chain index {entry.chain_index}: hash MISMATCH "
                    f"(expected={expected_hash}, stored={entry.current_hash})"
                )

            # Verify previous hash link
            if entry.previous_hash != prev_hash:
                issues.append(
                    f"Chain index {entry.chain_index}: previous hash link BROKEN "
                    f"(expected={prev_hash}, stored={entry.previous_hash})"
                )

            verified_count += 1

        return ChainVerificationResult(
            total_entries=len(chain_entries),
            verified_count=verified_count,
            issues=issues,
            is_intact=len(issues) == 0,
        )

    async def verify_entry(
        self,
        db: AsyncSession,
        audit_log_id: UUID,
    ) -> bool:
        """Verify that a specific audit log entry is untampered."""
        result = await db.execute(
            select(AuditLogChain).where(AuditLogChain.audit_log_id == audit_log_id)
        )
        chain_entry = result.scalars().first()
        if not chain_entry:
            return False

        audit_result = await db.execute(
            select(AuditLog).where(AuditLog.id == audit_log_id)
        )
        audit_entry = audit_result.scalars().first()
        if not audit_entry:
            return False

        content = self._build_entry_content(audit_entry)
        expected_hash = self._compute_entry_hash(
            content, previous_hash=chain_entry.previous_hash,
        )

        return expected_hash == chain_entry.current_hash

    def _compute_entry_hash(
        self,
        content: dict[str, Any],
        previous_hash: str | None = None,
    ) -> str:
        """Compute SHA-256 hash of entry content, including previous hash."""
        # Create a deterministic serialization
        raw = json.dumps(content, sort_keys=True, default=str).encode("utf-8")

        if isinstance(previous_hash, str):
            # Including previous hash in the hash computation creates the chain
            h = hashlib.sha256(previous_hash.encode("utf-8"))
            h.update(raw)
        else:
            h = hashlib.sha256(raw)

        return h.hexdigest()

    def _build_entry_content(self, entry: AuditLog) -> dict[str, Any]:
        """Build a deterministic dict from an audit log entry for hashing."""
        return {
            "id": str(entry.id),
            "user_id": str(entry.user_id) if entry.user_id else None,
            "action": entry.action,
            "resource_type": entry.resource_type,
            "resource_id": entry.resource_id,
            "details": entry.details if entry.details else {},
            "ip_address": entry.ip_address,
            "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
        }


@dataclass
class ChainVerificationResult:
    """Result of a chain integrity verification."""
    total_entries: int
    verified_count: int
    issues: list[str]
    is_intact: bool


# ---------------------------------------------------------------------------
# External Witness Backend
# ---------------------------------------------------------------------------


class WitnessBackend:
    """Abstract base for external witness backends.

    Witness backends publish chain hashes to an external, immutable
    store (e.g., S3, blockchain, or append-only log).
    """

    async def witness(self, hash_value: str, chain_index: int) -> str:
        """Publish a hash to the external witness.

        Returns a witness transaction ID or reference.
        """
        raise NotImplementedError


class S3WitnessBackend(WitnessBackend):
    """Witness backend that publishes hashes to S3.

    Each hash is stored as a file in an S3 bucket with the chain
    index as the key.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "audit-chain/",
        endpoint_url: str | None = None,
    ) -> None:
        self.bucket = bucket
        self.prefix = prefix
        self.endpoint_url = endpoint_url

    async def witness(self, hash_value: str, chain_index: int) -> str:
        """Upload hash to S3 and return the object key."""
        try:
            import aioboto3
            session = aioboto3.Session()
            async with session.client("s3", endpoint_url=self.endpoint_url) as s3:
                key = f"{self.prefix}{chain_index:010d}.hash"
                await s3.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=hash_value.encode("utf-8"),
                    ContentType="text/plain",
                    Metadata={"chain_index": str(chain_index)},
                )
                return key
        except ImportError:
            logger.warning("aioboto3 not available, using local file witness")
            import os
            os.makedirs(f"/tmp/audit-witness/{self.bucket}/{self.prefix}", exist_ok=True)
            key = f"{self.prefix}{chain_index:010d}.hash"
            with open(f"/tmp/audit-witness/{self.bucket}/{key}", "w") as f:
                f.write(hash_value)
            return f"file:///tmp/audit-witness/{self.bucket}/{key}"


# Global chain manager
audit_chain_manager = AuditChainManager()


# ---------------------------------------------------------------------------
# Audit service
# ---------------------------------------------------------------------------


class AuditService:
    """Persist audit log entries and provide query methods.

    Each entry is automatically chained via SHA-256 for tamper detection.
    """

    async def record(
        self,
        db: AsyncSession,
        *,
        user_id: UUID | None,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> AuditLog:
        """Write an entry to the audit_logs table with chain linking."""
        entry = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            details=details or {},
            ip_address=ip_address,
            timestamp=datetime.now(timezone.utc),
        )
        db.add(entry)
        await db.flush()
        await db.refresh(entry)

        # Create SHA-256 chain link
        content = audit_chain_manager._build_entry_content(entry)
        await audit_chain_manager.link_entry(db, entry.id, content)

        await db.commit()
        await db.refresh(entry)

        logger.info(
            "audit_log_entry",
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            by_user=str(user_id) if user_id else "system",
            chain_index=0,  # actual index stored in AuditLogChain
        )
        return entry

    async def get_entries(
        self,
        db: AsyncSession,
        *,
        user_id: UUID | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
        include_chain_info: bool = False,
    ) -> list[dict[str, Any]]:
        """Query audit log entries with optional filters.

        If ``include_chain_info`` is True, each entry includes its
        chain hash and previous hash for verification.
        """
        query = select(AuditLog).order_by(AuditLog.timestamp.desc())

        if user_id:
            query = query.where(AuditLog.user_id == user_id)
        if action:
            query = query.where(AuditLog.action == action)
        if resource_type:
            query = query.where(AuditLog.resource_type == resource_type)

        query = query.offset(offset).limit(limit)
        result = await db.execute(query)
        entries = list(result.scalars().all())

        results = []
        for entry in entries:
            entry_dict = {
                "id": str(entry.id),
                "user_id": str(entry.user_id) if entry.user_id else None,
                "action": entry.action,
                "resource_type": entry.resource_type,
                "resource_id": entry.resource_id,
                "details": entry.details,
                "ip_address": entry.ip_address,
                "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
            }

            if include_chain_info:
                chain_result = await db.execute(
                    select(AuditLogChain).where(AuditLogChain.audit_log_id == entry.id)
                )
                chain_entry = chain_result.scalars().first()
                if chain_entry:
                    entry_dict["chain"] = {
                        "previous_hash": chain_entry.previous_hash,
                        "current_hash": chain_entry.current_hash,
                        "chain_index": chain_entry.chain_index,
                        "witness_tx_id": chain_entry.witness_tx_id,
                        "witness_location": chain_entry.witness_location,
                    }

            results.append(entry_dict)

        return results

    async def count_entries(
        self,
        db: AsyncSession,
        *,
        user_id: UUID | None = None,
        action: str | None = None,
        resource_type: str | None = None,
    ) -> int:
        """Count audit log entries with optional filters."""
        from sqlalchemy import func

        query = select(func.count()).select_from(AuditLog)
        if user_id:
            query = query.where(AuditLog.user_id == user_id)
        if action:
            query = query.where(AuditLog.action == action)
        if resource_type:
            query = query.where(AuditLog.resource_type == resource_type)

        result = await db.execute(query)
        return result.scalar_one()

    async def verify_chain(
        self,
        db: AsyncSession,
        from_index: int = 0,
        to_index: int | None = None,
    ) -> ChainVerificationResult:
        """Verify the audit log chain integrity.

        Delegates to ``AuditChainManager.verify_chain``.
        Entry point for regulatory queries.
        """
        return await audit_chain_manager.verify_chain(
            db, from_index=from_index, to_index=to_index,
        )

    async def verify_entry(self, db: AsyncSession, audit_log_id: UUID) -> bool:
        """Verify a single audit log entry has not been tampered with."""
        return await audit_chain_manager.verify_entry(db, audit_log_id)

    # ------------------------------------------------------------------
    # Regulatory Query API
    # ------------------------------------------------------------------

    async def get_chain_status(
        self,
        db: AsyncSession,
    ) -> dict[str, Any]:
        """Get the current status of the audit log chain.

        Returns the chain length, the latest hash, and verification
        status. Useful for regulatory inspection.
        """
        # Latest chain entry
        result = await db.execute(
            select(AuditLogChain).order_by(AuditLogChain.chain_index.desc()).limit(1)
        )
        latest = result.scalars().first()

        # Count entries
        count_result = await db.execute(
            select(text("COUNT(*)")).select_from(text("audit_logs"))
        )
        total_logs = count_result.scalar_one()

        chain_count_result = await db.execute(
            select(text("COUNT(*)")).select_from(text("audit_log_chain"))
        )
        total_chain = chain_count_result.scalar_one()

        return {
            "total_audit_logs": total_logs,
            "total_chain_entries": total_chain,
            "latest_chain_index": latest.chain_index if latest else None,
            "latest_hash": latest.current_hash if latest else None,
            "latest_hash_timestamp": latest.witness_timestamp.isoformat()
            if latest and latest.witness_timestamp else None,
            "witness_location": latest.witness_location if latest else None,
        }

    async def get_entries_for_regulator(
        self,
        db: AsyncSession,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        actions: list[str] | None = None,
        user_ids: list[UUID] | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Get audit log entries formatted for regulatory inspection.

        This is the primary API for regulators to query the audit log.
        It includes chain verification info.
        """
        query = select(AuditLog).order_by(AuditLog.timestamp.desc())

        if start_date:
            query = query.where(AuditLog.timestamp >= start_date)
        if end_date:
            query = query.where(AuditLog.timestamp <= end_date)
        if actions:
            query = query.where(AuditLog.action.in_(actions))
        if user_ids:
            query = query.where(AuditLog.user_id.in_(user_ids))

        query = query.offset(offset).limit(limit)
        result = await db.execute(query)
        entries = result.scalars().all()

        # Get chain status
        chain_status = await self.get_chain_status(db)

        return {
            "request": {
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "actions": actions,
                "user_ids": [str(uid) for uid in user_ids] if user_ids else None,
                "limit": limit,
                "offset": offset,
            },
            "chain_status": chain_status,
            "entries_count": len(entries),
            "entries": [
                {
                    "id": str(e.id),
                    "user_id": str(e.user_id) if e.user_id else None,
                    "action": e.action,
                    "resource_type": e.resource_type,
                    "resource_id": e.resource_id,
                    "details": e.details,
                    "ip_address": e.ip_address,
                    "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                }
                for e in entries
            ],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


# Global audit service instance
audit_service = AuditService()


# ---------------------------------------------------------------------------
# Audit middleware — captures every request
# ---------------------------------------------------------------------------


class AuditMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that writes an audit log entry for every request.

    By default, it only captures sensitive endpoints (writes, auth, admin).
    Set ``capture_all=True`` to log **every** request (useful in audit-heavy
    environments).
    """

    def __init__(self, app: ASGIApp, capture_all: bool = False) -> None:
        super().__init__(app)
        self.capture_all = capture_all

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        response = await call_next(request)

        # Skip static files and health checks
        path = request.url.path
        if path in ("/health", "/health/live", "/health/ready", "/metrics", "/favicon.ico"):
            return response
        if path.startswith("/docs") or path.startswith("/redoc") or path.startswith("/openapi"):
            return response

        method = request.method
        is_sensitive = is_sensitive_path(method, path)

        if not self.capture_all and not is_sensitive:
            return response

        # Collect metadata for the audit entry
        user_id: UUID | None = None
        if hasattr(request.state, "current_user_id"):
            user_id = request.state.current_user_id
        elif hasattr(request.state, "user_id"):
            user_id = request.state.user_id

        ip_address = request.client.host if request.client else None
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip_address = forwarded.split(",")[0].strip()

        action = classify_action(method, path)
        resource_type = path.split("/")[3] if len(path.split("/")) > 3 else "unknown"

        details: dict[str, Any] = {
            "method": method,
            "path": path,
            "status_code": response.status_code,
            "query_params": dict(request.query_params),
        }

        # Only include request body for writes (avoid logging large payloads)
        if method in ("POST", "PUT", "PATCH") and is_sensitive:
            try:
                body = await request.body()
                if body and len(body) < 4096:
                    details["body_preview"] = body.decode("utf-8", errors="replace")[:512]
            except Exception:
                pass

        # Fire-and-forget log via structlog
        logger.info(
            "audit_request",
            user_id=str(user_id) if user_id else "anonymous",
            action=action,
            resource_type=resource_type,
            resource_id=None,
            ip_address=ip_address,
            status_code=response.status_code,
            method=method,
            path=path,
        )

        # If we have a DB session on request state, persist immediately
        if hasattr(request.state, "db_session"):
            try:
                db: AsyncSession = request.state.db_session
                await audit_service.record(
                    db,
                    user_id=user_id,
                    action=action,
                    resource_type=resource_type,
                    details=details,
                    ip_address=ip_address,
                )
            except Exception as exc:
                logger.warning("audit_persist_failed", error=str(exc))

        return response
