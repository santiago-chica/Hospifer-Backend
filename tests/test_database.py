import unittest

from app.database import async_engine


class DatabaseConfigurationTests(unittest.IsolatedAsyncioTestCase):
    async def test_sqlite_connections_enforce_foreign_keys(self):
        if async_engine.url.get_backend_name() != "sqlite":
            self.skipTest("SQLite-specific connection behavior")
        async with async_engine.connect() as connection:
            result = await connection.exec_driver_sql("PRAGMA foreign_keys")
            self.assertEqual(result.scalar_one(), 1)


if __name__ == "__main__":
    unittest.main()
