"""One-shot schema migration — runs SQL files against DATABASE_URL, then exits."""
import asyncio
import os
import sys
import asyncpg


async def main():
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("MIGRATE: DATABASE_URL not set, skipping")
        return

    sql_dir = os.path.join(os.path.dirname(__file__), "sql")
    schema_file = os.path.join(sql_dir, "000_staging_schema.sql")
    if not os.path.exists(schema_file):
        schema_file = os.path.join(sql_dir, "000_full_schema.sql")
    if not os.path.exists(schema_file):
        print("MIGRATE: no schema file found, skipping")
        return

    print(f"MIGRATE: applying {os.path.basename(schema_file)}...")
    conn = await asyncpg.connect(url, ssl="prefer")
    try:
        with open(schema_file) as f:
            sql = f.read()
        await conn.execute(sql)
        tables = await conn.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' ORDER BY table_name"
        )
        print(f"MIGRATE: done — {len(tables)} tables")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
