#!/usr/bin/env python3
"""
Cashew Expense Tracker MCP Server

An MCP server that provides access to your Cashew expense tracker SQLite database.
Exposes table schemas as resources, provides tools for read-only SQL queries,
and includes prompts for common data analysis tasks.
"""

import sqlite3
import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

from fastmcp import FastMCP
from pydantic import BaseModel


# Configuration
DEFAULT_DB_PATH = "test.sqlite"  # Use test database by default
MAIN_DB_PATH = "cashew.sqlite"  # Main database path
ENV_DB_PATH_KEY = "CASHEW_DB_PATH"  # Environment variable for database path


class QueryResult(BaseModel):
    """Result of a SQL query execution"""

    columns: List[str]
    rows: List[List[Any]]
    row_count: int
    execution_time_ms: float


class DatabaseSchema(BaseModel):
    """Database table schema information"""

    table_name: str
    columns: List[Dict[str, Any]]
    foreign_keys: List[Dict[str, Any]]
    indexes: List[Dict[str, Any]]


# Initialize FastMCP server
mcp = FastMCP("cashew-expense-tracker")


class CashewDatabase:
    """Helper class for database operations"""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database file not found: {db_path}")

    def get_connection(self) -> sqlite3.Connection:
        """Get a read-only database connection"""
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def get_table_names(self) -> List[str]:
        """Get all table names from the database"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
            return [row[0] for row in cursor.fetchall()]

    def get_table_schema(self, table_name: str) -> DatabaseSchema:
        """Get detailed schema information for a table"""
        with self.get_connection() as conn:
            # Get column information
            columns_cursor = conn.execute(f"PRAGMA table_info({table_name})")
            columns = []
            for row in columns_cursor.fetchall():
                columns.append(
                    {
                        "name": row["name"],
                        "type": row["type"],
                        "not_null": bool(row["notnull"]),
                        "default_value": row["dflt_value"],
                        "primary_key": bool(row["pk"]),
                    }
                )

            # Get foreign key information
            fk_cursor = conn.execute(f"PRAGMA foreign_key_list({table_name})")
            foreign_keys = []
            for row in fk_cursor.fetchall():
                foreign_keys.append(
                    {
                        "column": row["from"],
                        "referenced_table": row["table"],
                        "referenced_column": row["to"],
                    }
                )

            # Get index information
            index_cursor = conn.execute(f"PRAGMA index_list({table_name})")
            indexes = []
            for row in index_cursor.fetchall():
                indexes.append(
                    {
                        "name": row["name"],
                        "unique": bool(row["unique"]),
                        "origin": row["origin"],
                    }
                )

            return DatabaseSchema(
                table_name=table_name,
                columns=columns,
                foreign_keys=foreign_keys,
                indexes=indexes,
            )

    def execute_query(self, query: str) -> QueryResult:
        """Execute a read-only SQL query"""
        # Basic safety check - only allow SELECT statements
        query_stripped = query.strip().upper()
        if not query_stripped.startswith("SELECT"):
            raise ValueError("Only SELECT queries are allowed")

        # Prevent potentially dangerous operations - check for whole words only
        import re

        forbidden_keywords = [
            "DELETE",
            "UPDATE",
            "INSERT",
            "DROP",
            "ALTER",
            "CREATE",
            "PRAGMA",
        ]

        # Use word boundaries to check for complete keywords only
        for keyword in forbidden_keywords:
            pattern = r"\b" + re.escape(keyword) + r"\b"
            if re.search(pattern, query_stripped):
                raise ValueError(f"Query contains forbidden keyword: {keyword}")

        start_time = datetime.now()

        with self.get_connection() as conn:
            cursor = conn.execute(query)
            rows = cursor.fetchall()
            columns = (
                [description[0] for description in cursor.description]
                if cursor.description
                else []
            )

        end_time = datetime.now()
        execution_time_ms = (end_time - start_time).total_seconds() * 1000

        # Convert rows to list of lists for JSON serialization
        row_data = []
        for row in rows:
            row_data.append([row[col] for col in columns])

        return QueryResult(
            columns=columns,
            rows=row_data,
            row_count=len(rows),
            execution_time_ms=execution_time_ms,
        )


# Global database instance
db: Optional[CashewDatabase] = None


def init_database(db_path: str):
    """Initialize the database connection"""
    global db
    db = CashewDatabase(db_path)


# Resources: Expose table schemas
@mcp.resource("cashew://schema/{table_name}")
async def get_table_schema_resource(table_name: str) -> str:
    """Get the schema for a specific table as a resource"""
    if db is None:
        raise RuntimeError("Database not initialized")

    try:
        schema = db.get_table_schema(table_name)

        # Create a human-readable schema description
        content = f"# {table_name.title()} Table Schema\n\n"
        content += f"**Table:** `{schema.table_name}`\n\n"

        content += "## Columns\n\n"
        content += "| Column | Type | Null | Default | Primary Key |\n"
        content += "|--------|------|------|---------|-------------|\n"

        for col in schema.columns:
            null_str = "No" if col["not_null"] else "Yes"
            pk_str = "Yes" if col["primary_key"] else "No"
            default = col["default_value"] if col["default_value"] is not None else ""
            content += (
                f"| {col['name']} | {col['type']} | {null_str} |"
                + f" {default} | {pk_str} |\n"
            )

        if schema.foreign_keys:
            content += "\n## Foreign Keys\n\n"
            content += "| Column | References |\n"
            content += "|--------|------------|\n"
            for fk in schema.foreign_keys:
                content += (
                    f"| {fk['column']} | {fk['referenced_table']}"
                    + f".{fk['referenced_column']} |\n"
                )

        if schema.indexes:
            content += "\n## Indexes\n\n"
            content += "| Index Name | Unique | Origin |\n"
            content += "|------------|--------|--------|\n"
            for idx in schema.indexes:
                unique_str = "Yes" if idx["unique"] else "No"
                content += f"| {idx['name']} | {unique_str} | {idx['origin']} |\n"

        return content

    except Exception as e:
        raise RuntimeError(f"Failed to get schema for table {table_name}: {str(e)}")


@mcp.resource("cashew://schema")
async def get_all_schemas_resource() -> str:
    """Get all table schemas as a single resource"""
    if db is None:
        raise RuntimeError("Database not initialized")

    try:
        table_names = db.get_table_names()

        content = "# Cashew Expense Tracker Database Schema\n\n"
        content += f"**Database contains {len(table_names)} tables:**\n\n"

        for table_name in table_names:
            content += f"- [{table_name}](cashew://schema/{table_name})\n"

        content += "\n---\n\n"

        # Add detailed schema for each table
        for table_name in table_names:
            schema = db.get_table_schema(table_name)

            content += f"## {table_name.title()} Table\n\n"
            content += f"**Table:** `{schema.table_name}`\n\n"

            content += "### Columns\n\n"
            for col in schema.columns:
                constraints = []
                if col["not_null"]:
                    constraints.append("NOT NULL")
                if col["primary_key"]:
                    constraints.append("PRIMARY KEY")
                if col["default_value"] is not None:
                    constraints.append(f"DEFAULT {col['default_value']}")

                constraint_str = f" ({', '.join(constraints)})" if constraints else ""
                content += f"- **{col['name']}**: `{col['type']}`{constraint_str}\n"

            if schema.foreign_keys:
                content += "\n### Foreign Keys\n\n"
                for fk in schema.foreign_keys:
                    content += (
                        f"- `{fk['column']}` → `{fk['referenced_table']}."
                        + f"{fk['referenced_column']}`\n"
                    )

            content += "\n"

        return content

    except Exception as e:
        raise RuntimeError(f"Failed to get database schema: {str(e)}")


# Tools: SQL Query execution
@mcp.tool()
async def execute_sql_query(query: str) -> List[Dict[str, Any]]:
    """
    Execute a read-only SQL query against the Cashew database.

    Args:
        query: A SELECT SQL query to execute (INSERT, UPDATE, DELETE not allowed)

    Returns:
        Query results including columns, rows, and metadata
    """
    if db is None:
        raise RuntimeError("Database not initialized")

    try:
        result = db.execute_query(query)

        return [
            {
                "query": query,
                "columns": result.columns,
                "rows": result.rows,
                "row_count": result.row_count,
                "execution_time_ms": result.execution_time_ms,
                "success": True,
            }
        ]

    except Exception as e:
        return [{"query": query, "error": str(e), "success": False}]


@mcp.tool()
async def get_table_sample(table_name: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get a sample of rows from a specific table.

    Args:
        table_name: Name of the table to sample from
        limit: Maximum number of rows to return (default: 10, max: 100)

    Returns:
        Sample rows from the specified table
    """
    if db is None:
        raise RuntimeError("Database not initialized")

    # Validate table name exists
    table_names = db.get_table_names()
    if table_name not in table_names:
        return [
            {
                "error": f"Table '{table_name}' not found. Available tables: {', '.join(table_names)}",
                "success": False,
            }
        ]

    # Limit the number of rows
    limit = min(max(1, limit), 100)

    query = f"SELECT * FROM {table_name} LIMIT {limit}"
    return await execute_sql_query(query)


@mcp.tool()
async def get_table_count(table_name: str) -> List[Dict[str, Any]]:
    """
    Get the total number of rows in a specific table.

    Args:
        table_name: Name of the table to count

    Returns:
        Row count for the specified table
    """
    if db is None:
        raise RuntimeError("Database not initialized")

    # Validate table name exists
    table_names = db.get_table_names()
    if table_name not in table_names:
        return [
            {
                "error": f"Table '{table_name}' not found. Available tables: {', '.join(table_names)}",
                "success": False,
            }
        ]

    query = f"SELECT COUNT(*) as row_count FROM {table_name}"
    return await execute_sql_query(query)


# Prompts: Common data analysis tasks
@mcp.prompt()
async def analyze_spending_patterns() -> str:
    """Analyze spending patterns and trends in the expense data"""
    return """I want to analyze my spending patterns. Please help me understand:

1. **Overall Spending Summary**
   - Total expenses and income over the specified time period
   - Average daily/weekly/monthly spending
   - Spending trend (increasing/decreasing)

2. **Category Analysis**
   - Top spending categories
   - Category-wise breakdown with percentages
   - Categories with unusual spending patterns

3. **Temporal Patterns**
   - Spending by day of week/month
   - Seasonal trends if applicable
   - Peak spending periods

4. **Budget Performance**
   - How actual spending compares to budgets
   - Categories where budget is exceeded
   - Budget utilization rates

Please use the available SQL tools to query the transactions, categories,
wallets, and budgets tables. Start with getting an overview of the data
structure, then dive into the analysis."""


@mcp.prompt()
async def budget_analysis() -> str:
    """Analyze budget performance and recommendations"""
    return """Please analyze my budget performance and provide recommendations:

1. **Budget Overview**
   - List all active budgets with their amounts and time periods
   - Budget status (active, expired, upcoming)

2. **Performance Analysis**
   - Current spending vs budget for each budget
   - Percentage of budget used
   - Remaining budget amounts and days

3. **Category Budget Analysis**
   - Category-specific budget limits and usage
   - Categories that frequently exceed budgets
   - Under-utilized budget categories

4. **Recommendations**
   - Suggest budget adjustments based on actual spending patterns
   - Identify categories that need budget increases/decreases
   - Recommend new budgets for untracked spending areas

5. **Future Projections**
   - Projected end-of-period budget status
   - Likely budget overruns based on current trends

Please use SQL queries to analyze the budgets, category_budget_limits,
and transactions tables."""


@mcp.prompt()
async def income_vs_expenses() -> str:
    """Compare income vs expenses analysis"""
    return """Please provide a comprehensive income vs expenses analysis:

1. **Summary**
   - Total income and expenses for the analysis period
   - Net income (income - expenses)
   - Income to expense ratio

2. **Trends Analysis**
   - Monthly income and expense trends
   - Identify months with highest/lowest net income
   - Growth rates for income and expenses

3. **Category Breakdown**
   - Income sources breakdown
   - Major expense categories
   - Discretionary vs necessary expenses

4. **Cash Flow Analysis**
   - Monthly cash flow patterns
   - Identify cash flow positive/negative periods
   - Seasonal variations in cash flow

5. **Financial Health Indicators**
   - Savings rate (if applicable)
   - Expense to income ratios by category
   - Financial stability indicators

6. **Projections**
   - Based on current trends, project future cash flow
   - Identify potential financial challenges or opportunities

Use the transactions table with the 'income' field to distinguish between
income (income=1) and expenses (income=0)."""


@mcp.prompt()
async def expense_anomaly_detection() -> str:
    """Detect unusual spending patterns and anomalies"""
    return """Please help me identify unusual spending patterns and potential anomalies:

1. **Large Transactions**
   - Identify transactions that are significantly larger than usual
   - Compare against average transaction amounts by category
   - Flag potentially suspicious large expenses

2. **Frequency Anomalies**
   - Detect categories with unusual spending frequency
   - Identify sudden increases/decreases in transaction frequency
   - Find categories with irregular patterns

3. **Category Anomalies**
   - Spending in categories that are rarely used
   - Categories with sudden spending spikes
   - Missing spending in usually active categories

4. **Temporal Anomalies**
   - Unusual spending times (if timestamps available)
   - Spending patterns that deviate from normal routines
   - Weekend vs weekday spending anomalies

5. **Duplicate Detection**
   - Potential duplicate transactions (same amount, date, category)
   - Similar transaction names that might be duplicates

6. **Budget Anomalies**
   - Transactions that push categories significantly over budget
   - Spending in categories without assigned budgets

Please use statistical analysis on the transactions table to identify these
patterns. Consider transaction amounts, dates, categories, and frequencies."""


def main() -> int:
    """Main entry point for the MCP server"""
    parser = argparse.ArgumentParser(description="Cashew Expense Tracker MCP Server")
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to the SQLite database file (overrides environment variable)",
    )
    parser.add_argument(
        "--use-main-db",
        action="store_true",
        help=f"Use the main database ({MAIN_DB_PATH}) instead of the test database",
    )

    args = parser.parse_args()

    # Determine which database to use with priority order:
    # 1. Command line --db-path argument
    # 2. --use-main-db flag
    # 3. Environment variable CASHEW_DB_PATH
    # 4. Default test database
    db_path: str = DEFAULT_DB_PATH  # Default to test database
    if args.db_path:
        db_path = args.db_path
        print(
            f"Using database from command line: {db_path}", file=sys.stderr, flush=True
        )
    elif args.use_main_db:
        db_path = MAIN_DB_PATH
        print(f"Using main database: {db_path}", file=sys.stderr, flush=True)
    elif os.getenv(ENV_DB_PATH_KEY) is not None:
        db_path = os.getenv(ENV_DB_PATH_KEY, DEFAULT_DB_PATH)
        print(
            f"Using database from environment variable {ENV_DB_PATH_KEY}: {db_path}",
            file=sys.stderr,
            flush=True,
        )
    else:
        print(f"Using default database: {db_path}", file=sys.stderr, flush=True)

    print(
        f"Initializing Cashew MCP Server with database: {db_path}",
        file=sys.stderr,
        flush=True,
    )

    try:
        init_database(db_path)
        print(
            f"Successfully connected to database: {db_path}",
            file=sys.stderr,
            flush=True,
        )

        # Print available tables for debugging
        if db is not None:
            table_names = db.get_table_names()
            print(
                f"Available tables: {', '.join(table_names)}",
                file=sys.stderr,
                flush=True,
            )

    except Exception as e:
        print(f"Failed to initialize database: {e}", file=sys.stderr, flush=True)
        return 1

    # Run the MCP server
    mcp.run()

    return 0


if __name__ == "__main__":
    exit(main())
