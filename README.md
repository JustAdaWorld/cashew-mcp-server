# Cashew Expense Tracker MCP Server

An MCP (Model Context Protocol) server that provides access to your Cashew expense tracker SQLite database. This server exposes table schemas as resources, provides tools for running read-only SQL queries, and includes prompts for common data analysis tasks.

## Features

- **Database Schema Resources**: Access complete table schemas and structure information
- **Read-only SQL Query Tools**: Execute safe SELECT queries against your expense data
- **Data Analysis Prompts**: Pre-built prompts for common expense analysis tasks
- **Multiple Database Support**: Switch between test and production databases
- **Safety First**: Only read-only operations are allowed to protect your data

## Installation

The project uses [uv](https://docs.astral.sh/uv/) for dependency management. Make sure you have uv installed, then run:

```bash
uv sync
```

## Usage

### Running the Server

Start the MCP server with the test database:

```bash
uv run python cashew_mcp_server.py
```

Use your main Cashew database:

```bash
uv run python cashew_mcp_server.py --use-main-db
```

Use a custom database path:

```bash
uv run python cashew_mcp_server.py --db-path /path/to/your/database.sqlite
```

### MCP Client Integration

#### Claude Desktop

Add the server configuration to your Claude Desktop MCP settings file:

```json
{
  "mcpServers": {
    "cashew-expense-tracker": {
      "command": "uv",
      "args": [
        "run",
        "python",
        "cashew_mcp_server.py"
      ],
      "cwd": "/Users/yash/Developer/cashew-mcp",
      "env": {}
    }
  }
}
```

#### VSCode

Add the server configuration to your Vscode workspace's MCP settings file:

```json
{
    "servers": {
        "cashew-mcp-server": {
            "type": "stdio",
            "command": "/Users/yash/Developer/cashew-mcp/.venv/bin/python",
            "args": [
                "/Users/yash/Developer/cashew-mcp/cashew_mcp_server.py",
                "--db-path",
                "/Users/yash/Developer/cashew-mcp/db.sqlite"
            ]
        }
    }
}
```

#### MCP Inspector (Development)

Test the server with the MCP Inspector:

```bash
uv run mcp dev cashew_mcp_server.py
```

## Available Resources

The server exposes the following resources:

### Database Schema Resources

- `cashew://schema` - Complete database schema for all tables
- `cashew://schema/{table_name}` - Detailed schema for a specific table

Example tables in your Cashew database:

- `wallets` - Wallet/account information
- `categories` - Expense and income categories
- `transactions` - All financial transactions
- `budgets` - Budget definitions and limits
- `objectives` - Financial goals and objectives
- `category_budget_limits` - Category-specific budget limits

## Available Tools

### SQL Query Tools

1. **execute_sql_query(query: str)**
   - Execute read-only SELECT queries
   - Returns results with columns, rows, and execution metadata
   - Safety checks prevent dangerous operations

2. **get_table_sample(table_name: str, limit: int = 10)**
   - Get sample rows from any table
   - Useful for exploring data structure
   - Limit max 100 rows

3. **get_table_count(table_name: str)**
   - Get total row count for any table
   - Quick overview of data volume

## Available Prompts

### Data Analysis Prompts

1. **analyze_spending_patterns**
   - Comprehensive spending pattern analysis
   - Category breakdowns and trends
   - Temporal spending patterns
   - Budget performance analysis

2. **budget_analysis**
   - Budget performance evaluation
   - Budget vs actual spending
   - Recommendations for budget adjustments
   - Future projections

3. **income_vs_expenses**
   - Income and expense comparison
   - Cash flow analysis
   - Financial health indicators
   - Trend analysis and projections

4. **expense_anomaly_detection**
   - Detect unusual spending patterns
   - Identify potential duplicate transactions
   - Find spending anomalies and outliers
   - Budget violation detection

## Example Queries

Here are some example SQL queries you can run using the `execute_sql_query` tool:

### Basic Data Exploration

```sql
-- Get recent transactions
SELECT name, amount, date_created, income
FROM transactions
ORDER BY date_created DESC
LIMIT 10;

-- Top spending categories
SELECT c.name, SUM(t.amount) as total_spent, COUNT(*) as transaction_count
FROM transactions t
JOIN categories c ON t.category_fk = c.category_pk
WHERE t.income = 0
GROUP BY c.name
ORDER BY total_spent DESC
LIMIT 10;

-- Monthly spending summary
SELECT
  strftime('%Y-%m', date_created, 'unixepoch') as month,
  SUM(CASE WHEN income = 0 THEN amount ELSE 0 END) as expenses,
  SUM(CASE WHEN income = 1 THEN amount ELSE 0 END) as income,
  COUNT(*) as transactions
FROM transactions
GROUP BY strftime('%Y-%m', date_created, 'unixepoch')
ORDER BY month DESC;
```

### Budget Analysis

```sql
-- Current budget status
SELECT
  b.name as budget_name,
  b.amount as budget_amount,
  SUM(t.amount) as spent,
  (b.amount - SUM(t.amount)) as remaining,
  ROUND((SUM(t.amount) / b.amount) * 100, 2) as percent_used
FROM budgets b
LEFT JOIN transactions t ON t.date_created BETWEEN b.start_date AND b.end_date
  AND t.income = 0
WHERE b.archived = 0
GROUP BY b.budget_pk, b.name, b.amount;
```

### Category Analysis

```sql
-- Average transaction amount by category
SELECT
  c.name as category,
  ROUND(AVG(t.amount), 2) as avg_amount,
  MIN(t.amount) as min_amount,
  MAX(t.amount) as max_amount,
  COUNT(*) as transaction_count
FROM transactions t
JOIN categories c ON t.category_fk = c.category_pk
WHERE t.income = 0
GROUP BY c.name
HAVING COUNT(*) >= 5
ORDER BY avg_amount DESC;
```

## Database Schema

Your Cashew database contains the following main tables:

- **wallets**: Different accounts/wallets for organizing finances
- **categories**: Income and expense categories with hierarchical structure
- **transactions**: All financial transactions with amounts, dates, and categorization
- **budgets**: Budget definitions with time periods and amounts
- **objectives**: Financial goals and targets
- **category_budget_limits**: Category-specific budget constraints

Each table includes audit fields like `date_created` and `date_time_modified` for tracking changes.

## Safety Features

- **Read-only Access**: Only SELECT queries are allowed
- **Query Validation**: Dangerous SQL keywords are blocked
- **Input Sanitization**: All inputs are validated before execution
- **Error Handling**: Graceful error handling with informative messages

## Development

To contribute or modify the server:

1. Install dependencies: `uv sync`
2. Run tests: `uv run python -m pytest` (when tests are added)
3. Format code: `uv run black .`
4. Check types: `uv run mypy .` (when type hints are added)

## Troubleshooting

### Common Issues

1. **Import errors**: Make sure to use `uv run` to properly activate the virtual environment
2. **Database not found**: Check the database path and ensure the file exists
3. **Permission errors**: Ensure the SQLite database file is readable

### Debug Mode

Run the server with debug output:

```bash
uv run python cashew_mcp_server.py --db-path test.sqlite
```

The server will output:

- Database path being used
- Available tables found
- Connection status

## License

This project is licensed under the MIT License.
