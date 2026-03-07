"""Thin wrapper over the Databricks SQL connector."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class WarehouseConnection:
    """Manages a connection to a Databricks SQL warehouse.

    This is the sole external dependency injection point. Tests replace
    this class entirely with mocks.
    """

    def __init__(
        self,
        host: str,
        http_path: str,
        catalog: str,
        schema: str,
        access_token: str | None = None,
    ) -> None:
        from databricks import sql as databricks_sql

        self.host = host
        self.http_path = http_path
        self.catalog = catalog
        self.schema = schema
        self._connection = databricks_sql.connect(
            server_hostname=host,
            http_path=http_path,
            access_token=access_token,
        )

    def list_tables(self) -> list[str]:
        """List all tables/views in the configured catalog.schema."""
        fqn = f"{self.catalog}.{self.schema}"
        rows = self._execute(f"SHOW TABLES IN {fqn}")
        return [
            f"{self.catalog}.{self.schema}.{row['tableName']}"
            for row in rows
        ]

    def describe_view(self, fully_qualified_name: str) -> dict[str, Any]:
        """Run DESCRIBE TABLE EXTENDED AS JSON for a given view.

        Returns the parsed JSON dict.
        """
        rows = self._execute(
            f"DESCRIBE TABLE EXTENDED {fully_qualified_name} AS JSON"
        )
        if not rows:
            return {}
        # The result is a single row with a single column containing JSON
        import json

        first_row = rows[0]
        json_str = first_row.get("json", first_row.get(list(first_row.keys())[0], "{}"))
        return json.loads(json_str)

    def execute_query(self, sql: str, parameters: list | None = None) -> list[dict]:
        """Execute a SQL query and return rows as dicts."""
        return self._execute(sql, parameters)

    def _execute(self, sql: str, parameters: list | None = None) -> list[dict]:
        """Execute SQL and return results as a list of dicts."""
        cursor = self._connection.cursor()
        try:
            if parameters:
                cursor.execute(sql, parameters)
            else:
                cursor.execute(sql)

            if cursor.description is None:
                return []

            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            cursor.close()

    def close(self) -> None:
        """Close the underlying connection."""
        self._connection.close()
