from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.config.settings import get_settings

# Import all models so autogenerate can detect them
from app.modules.appointments.model import Appointment  # noqa: F401
from app.modules.articles.model import Article  # noqa: F401
from app.modules.audit_logs.model import AuditLog  # noqa: F401
from app.modules.clients.model import Client, ClientNote  # noqa: F401
from app.modules.deadlines.model import Deadline, DeadlineAlert  # noqa: F401
from app.modules.external_api_logs.model import ExternalApiLog  # noqa: F401
from app.modules.finance.model import FinancialTransaction  # noqa: F401
from app.modules.forensic_holidays.model import ForensicHoliday  # noqa: F401
from app.modules.google_calendar.model import GoogleCredential  # noqa: F401
from app.modules.leads.model import Lead  # noqa: F401
from app.modules.notifications.model import NotificationPreference  # noqa: F401
from app.modules.office_config.model import OfficeConfig  # noqa: F401
from app.modules.processes.model import Process  # noqa: F401
from app.modules.tasks.model import Task  # noqa: F401
from app.modules.users.model import User  # noqa: F401
from app.shared.db.base_model import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

config.set_main_option("sqlalchemy.url", get_settings().database_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
