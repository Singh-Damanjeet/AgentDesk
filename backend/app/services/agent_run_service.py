from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.agent_run import AgentRun
from app.models.agent_step import AgentStep
from app.schemas.agent import (
    AgentRunDetailResponse,
    AgentRunListResponse,
    AgentRunSummaryResponse,
    AgentStepResponse,
)


class AgentRunServiceError(RuntimeError):
    """Raised when agent-run history cannot be read safely."""

    def __init__(self, message: str):
        self.user_message = message
        super().__init__(message)


class AgentRunNotFoundError(AgentRunServiceError):
    """Raised when a run ID or trace ID does not exist."""


class AgentRunService:
    DEFAULT_PAGE_SIZE = 50
    MAX_PAGE_SIZE = 100

    @staticmethod
    def list_runs(
        db: Session,
        *,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> AgentRunListResponse:
        normalized_limit = AgentRunService._normalize_limit(limit)
        normalized_offset = AgentRunService._normalize_offset(offset)

        try:
            total = int(db.scalar(select(func.count(AgentRun.id))) or 0)
            runs = db.scalars(
                select(AgentRun)
                .order_by(AgentRun.started_at.desc(), AgentRun.id.desc())
                .offset(normalized_offset)
                .limit(normalized_limit)
            ).all()
            step_counts = AgentRunService._step_counts(
                db,
                [run.id for run in runs],
            )
        except SQLAlchemyError as exc:
            db.rollback()
            raise AgentRunServiceError(
                "Agent run history is currently unavailable."
            ) from exc

        return AgentRunListResponse(
            items=[
                AgentRunService._summary(
                    run,
                    step_count=step_counts.get(run.id, 0),
                )
                for run in runs
            ],
            total=max(total, 0),
            limit=normalized_limit,
            offset=normalized_offset,
        )

    @staticmethod
    def get_run(
        db: Session,
        identifier: str,
    ) -> AgentRunDetailResponse:
        normalized_identifier = identifier.strip()
        if not normalized_identifier:
            raise AgentRunNotFoundError("Agent run not found.")

        try:
            run = db.scalar(
                select(AgentRun).where(
                    or_(
                        AgentRun.id == normalized_identifier,
                        AgentRun.trace_id == normalized_identifier,
                    )
                )
            )
            if run is None:
                raise AgentRunNotFoundError("Agent run not found.")

            steps = db.scalars(
                select(AgentStep)
                .where(AgentStep.agent_run_id == run.id)
                .order_by(
                    AgentStep.sequence_number.asc(),
                    AgentStep.id.asc(),
                )
            ).all()
        except AgentRunNotFoundError:
            raise
        except SQLAlchemyError as exc:
            db.rollback()
            raise AgentRunServiceError(
                "Agent run history is currently unavailable."
            ) from exc

        return AgentRunDetailResponse(
            **AgentRunService._summary(
                run,
                step_count=len(steps),
            ).model_dump(),
            steps=[AgentRunService._step_response(step) for step in steps],
        )

    @staticmethod
    def _step_counts(
        db: Session,
        run_ids: list[str],
    ) -> dict[str, int]:
        if not run_ids:
            return {}

        rows = db.execute(
            select(
                AgentStep.agent_run_id,
                func.count(AgentStep.id),
            )
            .where(AgentStep.agent_run_id.in_(run_ids))
            .group_by(AgentStep.agent_run_id)
        ).all()
        return {run_id: int(count) for run_id, count in rows}

    @staticmethod
    def _summary(
        run: AgentRun,
        *,
        step_count: int,
    ) -> AgentRunSummaryResponse:
        return AgentRunSummaryResponse(
            id=run.id,
            trace_id=run.trace_id,
            ticket_id=run.ticket_id,
            status=run.status,
            provider=run.provider,
            model=run.model,
            started_at=run.started_at,
            finished_at=run.finished_at,
            latency_ms=run.latency_ms,
            error=run.error,
            step_count=max(step_count, 0),
        )

    @staticmethod
    def _step_response(step: AgentStep) -> AgentStepResponse:
        return AgentStepResponse(
            id=step.id,
            sequence_number=step.sequence_number,
            step_type=step.step_type,
            input_summary=step.input_summary,
            output_summary=step.output_summary,
            metadata=(
                dict(step.step_metadata)
                if isinstance(step.step_metadata, dict)
                else None
            ),
            duration_ms=step.duration_ms,
        )

    @classmethod
    def _normalize_limit(cls, limit: int) -> int:
        if not 1 <= limit <= cls.MAX_PAGE_SIZE:
            raise AgentRunServiceError(
                f"Agent run limit must be between 1 and "
                f"{cls.MAX_PAGE_SIZE}."
            )
        return limit

    @staticmethod
    def _normalize_offset(offset: int) -> int:
        if offset < 0:
            raise AgentRunServiceError("Agent run offset cannot be negative.")
        return offset
