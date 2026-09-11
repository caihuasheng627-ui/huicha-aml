import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

DB_PATH = Path(__file__).resolve().parent.parent / "huicha.db"
# 测试可设 HUICHA_DATABASE_URL=sqlite:// 避免 lifespan 撞到旧文件库
SQLALCHEMY_URL = os.getenv("HUICHA_DATABASE_URL") or f"sqlite:///{DB_PATH.as_posix()}"

engine = create_engine(
    SQLALCHEMY_URL,
    connect_args={"check_same_thread": False} if SQLALCHEMY_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 旧库缺的列：只 ALTER，不删数据
_SQLITE_ADDS = {
    "alerts": [("gold_label", "VARCHAR DEFAULT ''")],
    "investigations": [
        ("signed_by_id", "VARCHAR DEFAULT ''"),
        ("signed_by_name", "VARCHAR DEFAULT ''"),
    ],
    "human_decisions": [
        ("signed_by_id", "VARCHAR DEFAULT ''"),
        ("signed_by_name", "VARCHAR DEFAULT ''"),
    ],
}


def migrate_sqlite(bind=None) -> list[str]:
    """给已有 SQLite 补列/建新表所需的缺列。create_all 不会给旧表加列。"""
    bind = bind or engine
    if bind.dialect.name != "sqlite":
        return []
    insp = inspect(bind)
    applied: list[str] = []
    existing_tables = set(insp.get_table_names())
    for table, cols in _SQLITE_ADDS.items():
        if table not in existing_tables:
            continue
        have = {c["name"] for c in insp.get_columns(table)}
        for name, decl in cols:
            if name in have:
                continue
            with bind.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {decl}"))
            applied.append(f"{table}.{name}")
    return applied


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
