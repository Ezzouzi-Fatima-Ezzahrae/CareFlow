"""Run once: `python -m app.db.init_db` — creates the SQLite schema."""
from app.db.session import Base, engine
from app.db import models  # noqa: F401  (register models)


def main() -> None:
    Base.metadata.create_all(bind=engine)
    print("Tables created.")


if __name__ == "__main__":
    main()
