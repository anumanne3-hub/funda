"""Initialize the optional SQLite demo; PostgreSQL uses supabase/migrations SQL."""

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.models import chat  # noqa: F401


def main() -> None:
    if not get_settings().database_url.startswith("sqlite:"):
        raise SystemExit("SQLite demo only. Use Supabase SQL migrations for PostgreSQL.")
    Base.metadata.create_all(engine)


if __name__ == "__main__":
    main()
