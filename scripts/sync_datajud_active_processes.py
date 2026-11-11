from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.database import SessionLocal, init_db  # noqa: E402
from app.modules.datajud.datajud_service import DataJudApiService  # noqa: E402
from app.modules.datajud.protocol import DataJudClient  # noqa: E402
from app.modules.datajud.schema import DataJudBatchSyncRequest  # noqa: E402
from app.modules.datajud.service import DataJudService  # noqa: E402
from app.modules.email.protocol import EmailProvider  # noqa: E402
from app.modules.email.sender import TemplatedEmailSender  # noqa: E402
from app.modules.external_api_logs.notifier import (  # noqa: E402
    ExternalApiFailureNotifier,
)
from app.modules.external_api_logs.repository import (  # noqa: E402
    ExternalApiLogRepository,
)
from app.modules.notifications.repository import (  # noqa: E402
    NotificationPreferenceRepository,
)
from app.modules.notifications.service import NotificationService  # noqa: E402
from app.modules.processes.repository import ProcessRepository  # noqa: E402
from app.modules.users.repository import UserRepository  # noqa: E402
from app.shared.deps.email import get_email_renderer, get_email_service  # noqa: E402


def _env_int(name: str, default: int | None = None) -> int | None:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value == "":
        return default
    return int(raw_value)


def build_parser() -> argparse.ArgumentParser:
    default_alias = os.getenv("DATAJUD_SYNC_TRIBUNAL_ALIAS")
    parser = argparse.ArgumentParser(
        description="Synchronize active process movements from DataJud."
    )
    parser.add_argument(
        "--tribunal-alias",
        default=default_alias,
        help=(
            "Optional DataJud tribunal alias. When omitted, each active process uses "
            "its saved tribunal alias. Can also be set with "
            "DATAJUD_SYNC_TRIBUNAL_ALIAS."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=_env_int("DATAJUD_SYNC_LIMIT", 50),
        help="Maximum active processes to synchronize in this run.",
    )
    parser.add_argument(
        "--user-id",
        type=int,
        default=_env_int("DATAJUD_SYNC_USER_ID"),
        help=(
            "Optional system/admin user id stored as the author of imported "
            "movements and external API logs."
        ),
    )
    parser.add_argument(
        "--fail-on-process-error",
        action="store_true",
        help="Exit with status 1 when at least one process sync fails.",
    )
    return parser


def resolve_sync_user_id(db: Session, user_id: int | None) -> int | None:
    if user_id is None:
        return None

    user = UserRepository(db).get_by_id(user_id)
    if user is None:
        raise ValueError(f"User id {user_id} was not found")
    return user.id


def run_sync(
    tribunal_alias: str | None,
    limit: int,
    user_id: int | None = None,
    db: Session | None = None,
    datajud_client: DataJudClient | None = None,
    email: EmailProvider | None = None,
):
    if db is None:
        init_db()
        db = SessionLocal()
        should_close_db = True
    else:
        should_close_db = False

    try:
        users = UserRepository(db)
        notifications = NotificationService(
            NotificationPreferenceRepository(db),
            users,
            TemplatedEmailSender(get_email_renderer(), email or get_email_service()),
        )
        log_repository = ExternalApiLogRepository(db)
        service = DataJudService(
            ProcessRepository(db),
            log_repository,
            datajud_client or DataJudApiService(),
            failure_notifier=ExternalApiFailureNotifier(
                users, notifications, log_repository
            ),
        )
        return service.sync_active_processes(
            DataJudBatchSyncRequest(tribunal_alias=tribunal_alias, limit=limit),
            actor_id=resolve_sync_user_id(db, user_id),
        )
    finally:
        if should_close_db:
            db.close()


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_sync(
        tribunal_alias=args.tribunal_alias,
        limit=args.limit,
        user_id=args.user_id,
    )
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False))
    if args.fail_on_process_error and result.failure_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
