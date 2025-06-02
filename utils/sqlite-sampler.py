#!/usr/bin/env python3
"""
SQLite Database Sampler

This script creates a smaller SQLite database from a larger one while maintaining:
- Exact same schema and metadata
- Referential integrity between tables
- Consistent data relationships

Usage:
    python sqlite_sampler.py source.db target.db --sample-size 1000
"""

import sqlite3
import argparse
import sys
from typing import Dict, List, Set, Tuple, Optional
import random


class SQLiteSampler:
    def __init__(
        self,
        source_db: str,
        target_db: str,
        sample_size: int = 1000,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        date_column: str = "created_at",
    ):
        self.source_db = source_db
        self.target_db = target_db
        self.sample_size = sample_size
        self.start_date = start_date
        self.end_date = end_date
        self.date_column = date_column
        self.source_conn = None
        self.target_conn = None
        self.table_dependencies: dict = {}
        self.sampled_records: dict = {}

    def connect(self):
        """Establish connections to source and target databases"""
        try:
            self.source_conn = sqlite3.connect(self.source_db)
            self.target_conn = sqlite3.connect(self.target_db)
            print(f"Connected to source: {self.source_db}")
            print(f"Connected to target: {self.target_db}")
        except sqlite3.Error as e:
            print(f"Error connecting to databases: {e}")
            sys.exit(1)

    def close(self):
        """Close database connections"""
        if self.source_conn:
            self.source_conn.close()
        if self.target_conn:
            self.target_conn.close()

    def get_table_names(self) -> List[str]:
        """Get all table names from the source database"""
        cursor = self.source_conn.cursor()  # type: ignore
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = [row[0] for row in cursor.fetchall()]
        print(f"Found {len(tables)} tables: {', '.join(tables)}")
        return tables

    def copy_schema(self):
        """Copy the complete schema from source to target database"""
        cursor = self.source_conn.cursor()  # type: ignore

        # Copy tables, indexes, views, triggers
        cursor.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE type IN ('table', 'index', 'view', 'trigger')
            AND name NOT LIKE 'sqlite_%'
            AND sql IS NOT NULL
            ORDER BY type DESC
        """
        )

        target_cursor = self.target_conn.cursor()  # type: ignore

        for (sql,) in cursor.fetchall():
            try:
                target_cursor.execute(sql)
                print(f"Created: {sql[:50]}...")
            except sqlite3.Error as e:
                print(f"Warning: Could not execute: {sql[:50]}... Error: {e}")

        self.target_conn.commit()  # type: ignore
        print("Schema copied successfully")

    def analyze_foreign_keys(self) -> Dict[str, List[Tuple[str, str, str]]]:
        """Analyze foreign key relationships between tables"""
        cursor = self.source_conn.cursor()  # type: ignore
        fk_relationships: dict = {}

        tables = self.get_table_names()

        for table in tables:
            cursor.execute(f"PRAGMA foreign_key_list({table})")
            foreign_keys = cursor.fetchall()

            if foreign_keys:
                fk_relationships[table] = []
                for fk in foreign_keys:
                    # fk format: (id, seq, table, from, to, on_update, on_delete, match)
                    referenced_table = fk[2]
                    from_column = fk[3]
                    to_column = fk[4]
                    fk_relationships[table].append(
                        (referenced_table, from_column, to_column)
                    )
                    print(
                        f"FK: {table}.{from_column} -> {referenced_table}.{to_column}"
                    )

        return fk_relationships

    def get_table_order(self, fk_relationships: Dict) -> List[str]:
        """Determine the order to process tables based on dependencies"""
        tables = self.get_table_names()
        processed = set()
        ordered_tables: list = []

        def can_process(table):
            if table not in fk_relationships:
                return True

            for ref_table, _, _ in fk_relationships[table]:
                if ref_table not in processed and ref_table != table:
                    return False
            return True

        # Process tables in dependency order
        while len(ordered_tables) < len(tables):
            progress_made = False

            for table in tables:
                if table not in processed and can_process(table):
                    ordered_tables.append(table)
                    processed.add(table)
                    progress_made = True

            if not progress_made:
                # Handle circular dependencies by adding remaining tables
                remaining = [t for t in tables if t not in processed]
                ordered_tables.extend(remaining)
                break

        print(f"Table processing order: {' -> '.join(ordered_tables)}")
        return ordered_tables

    def get_table_row_count(self, table: str) -> int:
        """Get the number of rows in a table"""
        cursor = self.source_conn.cursor()  # type: ignore
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        return cursor.fetchone()[0]

    def sample_table_data(self, table: str, fk_relationships: Dict) -> Set:
        """Sample data from a table while maintaining referential integrity"""
        cursor = self.source_conn.cursor()  # type: ignore

        # Check if this is the transactions table and we have date filtering
        is_transactions_table = table.lower() == "transactions"
        has_date_filter = is_transactions_table and (self.start_date or self.end_date)

        # Get total row count (with date filtering if applicable)
        if has_date_filter:
            # Check if the date column exists in the transactions table
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [col[1] for col in cursor.fetchall()]

            if self.date_column not in columns:
                print(
                    f"Warning: Date column '{self.date_column}' not found in {table}. "
                    f"Available columns: {', '.join(columns)}"
                )
                print(f"Falling back to regular sampling for {table}")
                total_rows = self.get_table_row_count(table)
                has_date_filter = False  # Disable date filtering for this table
            else:
                # Build date filter query
                date_conditions = []
                date_params = []

                if self.start_date:
                    date_conditions.append(f"{self.date_column} >= ?")
                    date_params.append(self.start_date)

                if self.end_date:
                    date_conditions.append(f"{self.date_column} <= ?")
                    date_params.append(self.end_date)

                date_filter = " AND ".join(date_conditions)

                cursor.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {date_filter}", date_params
                )
                total_rows = cursor.fetchone()[0]
                print(
                    f"Found {total_rows} records in {table} matching date filter ({self.start_date} to {self.end_date})"
                )
        else:
            total_rows = self.get_table_row_count(table)

        if total_rows == 0:
            if has_date_filter:
                print(
                    f"Table {table} has no records matching the date filter, skipping"
                )
            else:
                print(f"Table {table} is empty, skipping")
            return set()

        # Calculate sample size for this table
        table_sample_size = min(self.sample_size, total_rows)

        # Get primary key column
        cursor.execute(f"PRAGMA table_info({table})")
        columns_info = cursor.fetchall()
        pk_column = None

        for col_info in columns_info:
            if col_info[5] == 1:  # is primary key
                pk_column = col_info[1]
                break

        if not pk_column:
            # If no explicit PK, use rowid
            pk_column = "rowid"

        sampled_ids = set()

        # Build base query with date filtering if applicable
        base_query_parts = []
        base_params = []

        if has_date_filter:
            if self.start_date:
                base_query_parts.append(f"{self.date_column} >= ?")
                base_params.append(self.start_date)

            if self.end_date:
                base_query_parts.append(f"{self.date_column} <= ?")
                base_params.append(self.end_date)

        # If this table has foreign key dependencies, we need to sample based on existing data
        if table in fk_relationships:
            # Strategy: Try different approaches to get valid records
            valid_ids = []

            # Approach 1: Try to find records that satisfy all non-null FK constraints
            mandatory_constraints = []
            optional_constraints = []

            for ref_table, from_col, to_col in fk_relationships[table]:
                if (
                    ref_table in self.sampled_records
                    and self.sampled_records[ref_table]
                ):
                    # Check if this FK column allows NULL values
                    cursor.execute(f"PRAGMA table_info({table})")
                    columns = cursor.fetchall()
                    column_allows_null = True

                    for col_info in columns:
                        if col_info[1] == from_col:
                            column_allows_null = not col_info[3]  # notnull flag
                            break

                    ref_ids = list(self.sampled_records[ref_table])
                    if column_allows_null:
                        optional_constraints.append((from_col, ref_ids))
                    else:
                        mandatory_constraints.append((from_col, ref_ids))

            # First, try with all mandatory constraints
            if mandatory_constraints or optional_constraints:
                constraints_to_use = mandatory_constraints.copy()

                # If we have optional constraints, try adding them one by one
                all_constraints = constraints_to_use + optional_constraints

                for constraint_set_size in range(len(all_constraints), 0, -1):
                    if constraint_set_size <= len(mandatory_constraints):
                        # Only use mandatory constraints
                        current_constraints = mandatory_constraints
                    else:
                        # Use mandatory + some optional constraints
                        current_constraints = (
                            mandatory_constraints
                            + optional_constraints[
                                : constraint_set_size - len(mandatory_constraints)
                            ]
                        )

                    if current_constraints:
                        where_clauses = base_query_parts.copy()
                        params = base_params.copy()

                        for from_col, ref_ids in current_constraints:
                            placeholders = ",".join(["?" for _ in ref_ids])
                            where_clauses.append(
                                f"({from_col} IN ({placeholders}) OR {from_col} IS NULL)"
                            )
                            params.extend(ref_ids)

                        where_clause = (
                            " AND ".join(where_clauses) if where_clauses else "1=1"
                        )

                        try:
                            query = f"SELECT {pk_column} FROM {table} WHERE {where_clause} ORDER BY RANDOM() LIMIT ?"
                            cursor.execute(
                                query, params + [table_sample_size * 2]
                            )  # Get more candidates
                            valid_ids = [row[0] for row in cursor.fetchall()]

                            if valid_ids:
                                print(
                                    f"Found {len(valid_ids)} valid records for {table} using "
                                    f"{len(current_constraints)} constraints"
                                )
                                break
                        except sqlite3.Error as e:
                            print(f"Error querying {table} with constraints: {e}")
                            continue

            # Fallback: If no valid records found with constraints, try sampling randomly
            # and then validate each record
            if not valid_ids:
                print(
                    f"No valid records found with FK constraints for {table}, trying random sampling with validation"
                )

                where_clause = (
                    " AND ".join(base_query_parts) if base_query_parts else "1=1"
                )
                query = f"SELECT {pk_column} FROM {table} WHERE {where_clause} ORDER BY RANDOM() LIMIT ?"
                cursor.execute(query, base_params + [table_sample_size * 5])
                candidate_ids = [row[0] for row in cursor.fetchall()]

                valid_ids = []
                for candidate_id in candidate_ids:
                    is_valid = True

                    # Check each FK constraint
                    for ref_table, from_col, to_col in fk_relationships[table]:
                        if (
                            ref_table in self.sampled_records
                            and self.sampled_records[ref_table]
                        ):
                            cursor.execute(
                                f"SELECT {from_col} FROM {table} WHERE {pk_column} = ?",
                                (candidate_id,),
                            )
                            fk_value = cursor.fetchone()

                            if fk_value and fk_value[0] is not None:
                                if fk_value[0] not in self.sampled_records[ref_table]:
                                    # This FK points to a record we don't have, need to include it
                                    self.sampled_records[ref_table].add(fk_value[0])

                    if is_valid:
                        valid_ids.append(candidate_id)
                        if len(valid_ids) >= table_sample_size:
                            break

            if valid_ids:
                sampled_ids = set(valid_ids[:table_sample_size])
            else:
                print(f"Could not find any valid records for {table}")
                return set()
        else:
            # No foreign key dependencies, sample randomly (with date filter if applicable)
            where_clause = " AND ".join(base_query_parts) if base_query_parts else "1=1"
            query = f"SELECT {pk_column} FROM {table} WHERE {where_clause} ORDER BY RANDOM() LIMIT ?"
            cursor.execute(query, base_params + [table_sample_size])
            sampled_ids = set(row[0] for row in cursor.fetchall())

        print(f"Sampled {len(sampled_ids)} records from {table} (total: {total_rows})")
        return sampled_ids

    def copy_sampled_data(self, table: str, sampled_ids: Set):
        """Copy the sampled data to the target database"""
        if not sampled_ids:
            return

        cursor = self.source_conn.cursor()  # type: ignore
        target_cursor = self.target_conn.cursor()  # type: ignore

        # Get column names
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [col[1] for col in cursor.fetchall()]

        # Determine primary key column
        cursor.execute(f"PRAGMA table_info({table})")
        pk_column = "rowid"
        for col_info in cursor.fetchall():
            if col_info[5] == 1:  # is primary key
                pk_column = col_info[1]
                break

        # Fetch sampled data
        id_list = list(sampled_ids)
        placeholders = ",".join(["?" for _ in id_list])

        query = f"SELECT * FROM {table} WHERE {pk_column} IN ({placeholders})"
        cursor.execute(query, id_list)

        # Insert into target database
        column_placeholders = ",".join(["?" for _ in columns])
        insert_query = f"INSERT OR IGNORE INTO {table} VALUES ({column_placeholders})"

        rows_inserted = 0
        for row in cursor.fetchall():
            try:
                target_cursor.execute(insert_query, row)
                if target_cursor.rowcount > 0:
                    rows_inserted += 1
            except sqlite3.Error as e:
                print(f"Error inserting row into {table}: {e}")

        self.target_conn.commit()  # type: ignore
        print(f"Inserted {rows_inserted} rows into {table}")

    def ensure_referenced_records_exist(
        self, table: str, sampled_ids: Set, fk_relationships: Dict
    ):
        """Ensure that all referenced records exist in their respective tables"""
        if table not in fk_relationships or not sampled_ids:
            return

        cursor = self.source_conn.cursor()  # type: ignore

        for ref_table, from_col, to_col in fk_relationships[table]:
            if ref_table not in self.sampled_records:
                self.sampled_records[ref_table] = set()

            # Get all foreign key values from sampled records
            id_list = list(sampled_ids)
            placeholders = ",".join(["?" for _ in id_list])

            # Get primary key column for this table
            cursor.execute(f"PRAGMA table_info({table})")
            pk_column = "rowid"
            for col_info in cursor.fetchall():
                if col_info[5] == 1:  # is primary key
                    pk_column = col_info[1]
                    break

            query = (
                f"SELECT DISTINCT {from_col} FROM {table} WHERE {pk_column} IN "
                f"({placeholders}) AND {from_col} IS NOT NULL"
            )
            cursor.execute(query, id_list)

            referenced_ids = {row[0] for row in cursor.fetchall()}

            # Add missing referenced records
            missing_refs = referenced_ids - self.sampled_records[ref_table]
            if missing_refs:
                print(
                    f"Adding {len(missing_refs)} missing {ref_table} records referenced by {table}"
                )
                self.sampled_records[ref_table].update(missing_refs)

                # Copy these additional records to the target database
                self.copy_sampled_data(ref_table, missing_refs)

    def create_sample_database(self):
        """Main method to create the sample database"""
        print(
            f"Creating sample database with up to {self.sample_size} records per table"
        )

        # Connect to databases
        self.connect()

        try:
            # Copy schema
            self.copy_schema()

            # Analyze foreign key relationships
            fk_relationships = self.analyze_foreign_keys()

            # Determine table processing order
            table_order = self.get_table_order(fk_relationships)

            # Process each table in order
            for table in table_order:
                print(f"\nProcessing table: {table}")

                # Sample data while maintaining referential integrity
                sampled_ids = self.sample_table_data(table, fk_relationships)

                # Store sampled IDs for use by dependent tables
                if table not in self.sampled_records:
                    self.sampled_records[table] = set()
                self.sampled_records[table].update(sampled_ids)

                # Copy sampled data to target database
                self.copy_sampled_data(table, sampled_ids)

                # Ensure all referenced records exist (this might add more records to referenced tables)
                self.ensure_referenced_records_exist(
                    table, sampled_ids, fk_relationships
                )

            print(f"\nSample database created successfully: {self.target_db}")

            # Print summary
            print("\nSummary:")
            for table in table_order:
                source_count = self.get_table_row_count(table)

                cursor = self.target_conn.cursor()  # type: ignore
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                target_count = cursor.fetchone()[0]

                print(f"  {table}: {target_count}/{source_count} records")

        finally:
            self.close()


def main():
    parser = argparse.ArgumentParser(
        description="Create a smaller SQLite database sample"
    )
    parser.add_argument("source_db", help="Path to source SQLite database")
    parser.add_argument("target_db", help="Path to target SQLite database")
    parser.add_argument(
        "--sample-size",
        type=int,
        default=1000,
        help="Maximum number of records per table (default: 1000)",
    )
    parser.add_argument(
        "--seed", type=int, help="Random seed for reproducible sampling"
    )
    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date for filtering transactions table (YYYY-MM-DD format, optional)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="End date for filtering transactions table (YYYY-MM-DD format, optional)",
    )
    parser.add_argument(
        "--date-column",
        type=str,
        default="created_at",
        help="Date column name for filtering transactions (default: created_at)",
    )

    args = parser.parse_args()

    if args.seed:
        random.seed(args.seed)
        print(f"Using random seed: {args.seed}")

    sampler = SQLiteSampler(
        args.source_db,
        args.target_db,
        args.sample_size,
        args.start_date,
        args.end_date,
        args.date_column,
    )
    sampler.create_sample_database()


if __name__ == "__main__":
    main()
