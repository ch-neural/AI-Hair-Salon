from contextlib import contextmanager
import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/app.db")

# Ensure sqlite file parent directory exists to avoid 'unable to open database file'
if DATABASE_URL.startswith("sqlite:///") and ":memory:" not in DATABASE_URL:
    db_path = DATABASE_URL.split("sqlite:///")[-1]
    try:
        parent = Path(db_path).expanduser().resolve().parent
        parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        # best-effort; real error will surface on connect if still invalid
        pass

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


