"""
Database -- Async interface for SOTA agents.

Now backed by PostgreSQL (asyncpg).

The public API is unchanged -- every caller (butler_comms, butler_api,
hackathon agent, caller agent) keeps working without modification.

Usage::

    from agents.src.shared.database import Database

    db = await Database.connect()
    profile = await db.get_user_profile("default")
    await db.upsert_user_profile("default", {"full_name": "Alice", "email": "alice@example.com"})
    await db.close()
"""

# Re-export the PostgreSQL-backed implementation under the same name
from agents.src.shared.database_postgres import Database  # noqa: F401

__all__ = ["Database"]
