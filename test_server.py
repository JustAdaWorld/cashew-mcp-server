#!/usr/bin/env python3
"""
Test script for the Cashew MCP Server
"""

import asyncio
import sqlite3
from pathlib import Path


async def test_database_connection():
    """Test basic database connectivity and schema"""
    db_path = Path("test.sqlite")

    if not db_path.exists():
        print("❌ Test database not found at test.sqlite")
        return False

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        expected_tables = ["wallets", "categories", "transactions", "budgets"]
        found_tables = [t for t in expected_tables if t in tables]

        print("✅ Database connection successful")
        print(f"✅ Found {len(tables)} tables: {', '.join(tables)}")
        print(f"✅ Key tables present: {', '.join(found_tables)}")

        return len(found_tables) >= 3

    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False


async def test_sample_queries():
    """Test some sample SQL queries"""
    db_path = Path("test.sqlite")

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)

        # Test basic transaction count
        cursor = conn.execute("SELECT COUNT(*) FROM transactions")
        transaction_count = cursor.fetchone()[0]
        print(f"✅ Found {transaction_count} transactions in database")

        # Test category query
        cursor = conn.execute("SELECT COUNT(*) FROM categories")
        category_count = cursor.fetchone()[0]
        print(f"✅ Found {category_count} categories in database")

        # Test wallet query
        cursor = conn.execute("SELECT COUNT(*) FROM wallets")
        wallet_count = cursor.fetchone()[0]
        print(f"✅ Found {wallet_count} wallets in database")

        conn.close()
        return True

    except Exception as e:
        print(f"❌ Sample queries failed: {e}")
        return False


async def main():
    """Run all tests"""
    print("🧪 Testing Cashew MCP Server Setup")
    print("=" * 40)

    # Test database
    db_test = await test_database_connection()

    if db_test:
        query_test = await test_sample_queries()
    else:
        query_test = False

    print("\n" + "=" * 40)
    if db_test and query_test:
        print("✅ All tests passed! Your Cashew MCP server is ready to use.")
        print("\nNext steps:")
        print("1. Start the server: uv run python cashew_mcp_server.py")
        print("2. Test with MCP Inspector: uv run mcp dev cashew_mcp_server.py")
        print("3. Configure in Claude Desktop using mcp_config.json")
    else:
        print("❌ Some tests failed. Please check the setup.")

    return db_test and query_test


if __name__ == "__main__":
    asyncio.run(main())
