import os
import sqlite3
import json
import argparse
from typing import Dict, List, Any, Optional, Tuple
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class SQLiteManager:
    """Manages connections and queries to a SQLite database."""

    def __init__(self, db_path: str):
        """Initialize with path to SQLite database."""
        self.db_path = db_path
        self._validate_db()

    def _validate_db(self):
        """Validate database exists and is accessible."""
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Database not found: {self.db_path}")
        try:
            conn = sqlite3.connect(self.db_path)
            conn.close()
        except sqlite3.Error as e:
            raise ConnectionError(f"Failed to connect to database: {e}")

    def get_schema(self) -> str:
        """Return the database schema as a string."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Get all tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()

            schema = []
            for table in tables:
                table_name = table[0]
                cursor.execute(f"PRAGMA table_info({table_name});")
                columns = cursor.fetchall()

                col_definitions = []
                for col in columns:
                    col_id, col_name, col_type, not_null, default_val, is_pk = col
                    col_def = f"{col_name} {col_type}"
                    if is_pk:
                        col_def += " PRIMARY KEY"
                    if not_null:
                        col_def += " NOT NULL"
                    if default_val is not None:
                        col_def += f" DEFAULT {default_val}"
                    col_definitions.append(col_def)

                schema.append(
                    f"CREATE TABLE {table_name} (\n  "
                    + ",\n  ".join(col_definitions)
                    + "\n);"
                )

            conn.close()
            return "\n\n".join(schema)
        except sqlite3.Error as e:
            return f"Error retrieving schema: {e}"

    def execute_query(self, query: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Execute a SQL query and return results as a list of dictionaries.

        Returns:
            Tuple of (results, error_message)
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query)

            if query.strip().upper().startswith(("SELECT", "PRAGMA")):
                rows = cursor.fetchall()
                result = [dict(row) for row in rows]
                error = None
            else:
                conn.commit()
                result = [{"affected_rows": cursor.rowcount}]
                error = None

            conn.close()
            return result, error
        except sqlite3.Error as e:
            return [], str(e)

    def sample_data(self, limit: int = 3) -> Dict[str, List[Dict[str, Any]]]:
        """Get sample data from each table."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get all tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()

            samples = {}
            for table in tables:
                table_name = table[0]
                try:
                    cursor.execute(f"SELECT * FROM {table_name} LIMIT {limit};")
                    rows = cursor.fetchall()
                    samples[table_name] = [dict(row) for row in rows]
                except sqlite3.Error:
                    samples[table_name] = [
                        {"error": f"Could not retrieve sample data from {table_name}"}
                    ]

            conn.close()
            return samples
        except sqlite3.Error as e:
            return {"error": str(e)}


class LLMClient:
    """Client for interacting with LLM API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.0-flash",
        api_type: str = "openai",
        api_base: Optional[str] = None,
    ):
        """Initialize LLM client with API key, model and API type."""
        self.api_type = api_type.lower()

        # Set API key based on API type
        if self.api_type == "anthropic":
            self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
            if not self.api_key:
                raise ValueError(
                    "API key not found. Set ANTHROPIC_API_KEY env variable or pass as argument."
                )
        else:  # openai or openai-compatible
            self.api_key = api_key or os.getenv("OPENAI_API_KEY")
            if not self.api_key:
                raise ValueError(
                    "API key not found. Set OPENAI_API_KEY env variable or pass as argument."
                )

        self.model = model

        # Set base URL based on API type
        if self.api_type == "anthropic":
            self.base_url = "https://api.anthropic.com/v1/messages"
        else:  # openai or openai-compatible
            self.base_url = (
                api_base
                or os.getenv("OPENAI_API_BASE")
                or "https://api.openai.com/v1/chat/completions"
            )

        # Set headers based on API type
        if self.api_type == "anthropic":
            self.headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
        else:  # openai or openai-compatible
            self.headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

    def generate_sql(
        self, question: str, schema: str, sample_data: Dict[str, List[Dict[str, Any]]]
    ) -> str:
        """Generate SQL query from natural language question."""
        system_prompt = f"""You are a SQL expert. Convert the user's natural language question into a valid SQLite query.

Database schema:
{schema}

Sample data:
{json.dumps(sample_data, indent=2)}

Rules:
1. Return ONLY the SQL query with no additional text, comments, or explanations
2. Use proper SQLite syntax
3. Don't select unnecessary columns
4. If the question isn't clear, make a reasonable inference
5. If the question cannot be answered with SQL, respond with: "Cannot be converted to SQL."
6. Don't use markdown syntax or code blocks. Just return the SQL query as plain text.
"""

        try:
            if self.api_type == "anthropic":
                # Anthropic API format
                payload = {
                    "model": self.model,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": question}],
                    "max_tokens": 1000,
                }

                response = requests.post(
                    self.base_url, headers=self.headers, json=payload
                )
                response.raise_for_status()
                sql_query = (
                    response.json().get("content", [{}])[0].get("text", "").strip()
                )
            else:
                # OpenAI API format
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": question},
                    ],
                    "max_tokens": 1000,
                }

                response = requests.post(
                    self.base_url, headers=self.headers, json=payload
                )
                response.raise_for_status()
                sql_query = (
                    response.json()
                    .get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )

            return sql_query
        except Exception as e:
            return f"Error generating SQL: {str(e)}"

    def format_chat_response(
        self,
        question: str,
        sql_query: str,
        query_results: List[Dict[str, Any]],
        error: Optional[str] = None,
    ) -> str:
        """Use LLM to format query results into natural language."""
        try:
            # Format the query results or error
            if error:
                result_str = f"Error executing query: {error}"
            else:
                result_str = json.dumps(query_results, indent=2)

            system_prompt = """You are an AI assistant that explains SQL query results in natural language.
Your task is to:
1. Interpret the SQL query and its results
2. Provide a clear, conversational answer to the original question
3. Include relevant data points from the results
4. Be concise yet informative
5. If there was an error in the query execution, explain what might have gone wrong

Respond directly to the user's question without mentioning that you're interpreting results."""

            user_content = f"""
Original question: {question}

SQL query executed: 
{sql_query}

Query results:
{result_str}

Please provide a natural language response to the original question based on these results.
"""

            if self.api_type == "anthropic":
                # Anthropic API format
                payload = {
                    "model": self.model,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_content}],
                    "max_tokens": 1000,
                }

                response = requests.post(
                    self.base_url, headers=self.headers, json=payload
                )
                response.raise_for_status()
                answer = response.json().get("content", [{}])[0].get("text", "").strip()
            else:
                # OpenAI API format
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                    "max_tokens": 1000,
                }

                response = requests.post(
                    self.base_url, headers=self.headers, json=payload
                )
                response.raise_for_status()
                answer = (
                    response.json()
                    .get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )

            return answer
        except Exception as e:
            return f"Error formatting response: {str(e)}"


class ChatSession:
    """Manages a chat session with context tracking."""

    def __init__(
        self,
        db_path: str,
        api_key: Optional[str] = None,
        model: str = "gpt-4o",
        api_type: str = "openai",
        api_base: Optional[str] = None,
    ):
        """Initialize chat session with database and LLM."""
        self.db_manager = SQLiteManager(db_path)
        self.llm_client = LLMClient(api_key, model, api_type, api_base)

        # Get database schema and sample data for context
        self.schema = self.db_manager.get_schema()
        self.sample_data = self.db_manager.sample_data()

        # Initialize conversation history
        self.history = []

    def process_question(self, question: str) -> str:
        """Process a natural language question about the database."""
        # Generate SQL query
        sql_query = self.llm_client.generate_sql(
            question, self.schema, self.sample_data
        )

        print(f"Generated SQL query: {sql_query}")

        if sql_query == "Cannot be converted to SQL.":
            return "I'm sorry, but I can't convert your question to a SQL query. Could you rephrase or ask something about the data in the database?"

        # Execute query
        results, error = self.db_manager.execute_query(sql_query)

        # Format response using LLM
        response = self.llm_client.format_chat_response(
            question, sql_query, results, error
        )

        # Track in history
        self.history.append(
            {
                "question": question,
                "sql_query": sql_query,
                "results": results,
                "error": error,
                "response": response,
            }
        )

        return response


def main():
    parser = argparse.ArgumentParser(
        description="Chat with your SQLite database using natural language"
    )
    parser.add_argument("db_path", help="Path to SQLite database file")
    parser.add_argument(
        "--api-key",
        help="API key (defaults to OPENAI_API_KEY or ANTHROPIC_API_KEY env variable)",
    )
    parser.add_argument(
        "--model",
        default="gemini-2.0-flash",
        help="LLM model to use (default: gemini-2.0-flash)",
    )
    parser.add_argument(
        "--api-type",
        default="openai",
        choices=["openai", "anthropic"],
        help="API type to use (default: openai)",
    )
    parser.add_argument(
        "--api-base", help="Base URL for API (for OpenAI-compatible APIs)"
    )

    args = parser.parse_args()

    try:
        chat_session = ChatSession(
            args.db_path, args.api_key, args.model, args.api_type, args.api_base
        )
        print(f"Connected to database: {args.db_path}")
        print(f"Using API type: {args.api_type}")
        print(f"Using model: {args.model}")
        print("Enter your questions about the database (type 'exit' to quit):")

        while True:
            question = input("\nQuestion: ").strip()
            if question.lower() in ("exit", "quit"):
                break

            print("\nThinking...")
            response = chat_session.process_question(question)
            print(f"\nAnswer: {response}")

    except Exception as e:
        print(f"Error: {str(e)}")


if __name__ == "__main__":
    main()
