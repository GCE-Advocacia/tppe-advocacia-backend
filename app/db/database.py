from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    future=True,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, class_=Session
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    from sqlalchemy import select

    from app.modules.office_config.model import LandingPageTheme, OfficeConfig

    with SessionLocal() as db:
        existing = db.scalars(select(OfficeConfig).where(OfficeConfig.id == 1)).first()
        if existing is None:
            first_theme = db.scalars(
                select(LandingPageTheme)
                .where(LandingPageTheme.is_predefined.is_(True))
                .order_by(LandingPageTheme.id.asc())
            ).first()
            theme_id = first_theme.id if first_theme else None
            db.add(
                OfficeConfig(
                    id=1,
                    theme_id=theme_id,
                    differentials=[],
                    areas_of_practice=[],
                )
            )
            db.commit()


def check_database_connection() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
