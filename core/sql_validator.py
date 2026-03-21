"""
SQLValidator — validates LLM-generated SQL before execution.
Enforces read-only policy by default.
Prevents injection, forbidden keywords, and dangerous patterns.
"""
import re
import logging
from core.sql_schema_registry import FORBIDDEN_KEYWORDS, ALLOWED_READONLY

logger = logging.getLogger(__name__)


class SQLValidator:
    """Validate SQL queries for safety and correctness before execution."""

    MAX_QUERY_LENGTH = 4000
    MAX_RESULTS_DEFAULT = 100

    def validate(self, sql: str, allow_write: bool = False) -> tuple[bool, str]:
        """
        Validate SQL query.
        Returns (is_valid: bool, error_message: str).
        Empty error_message means valid.
        """
        if not sql or not sql.strip():
            return False, "SQL query is empty"

        if len(sql) > self.MAX_QUERY_LENGTH:
            return False, f"Query too long ({len(sql)} chars, max {self.MAX_QUERY_LENGTH})"

        normalized = sql.upper().strip()

        # Check for forbidden keywords
        if not allow_write:
            for keyword in FORBIDDEN_KEYWORDS:
                pattern = r'\b' + keyword + r'\b'
                if re.search(pattern, normalized):
                    return False, f"Forbidden keyword '{keyword}' — read-only mode"

        # Must start with allowed keyword
        first_word = normalized.split()[0] if normalized.split() else ""
        if not allow_write and first_word not in ALLOWED_READONLY:
            return False, f"Query must start with SELECT or WITH (got '{first_word}')"

        # Prevent SQL injection patterns
        injection_patterns = [
            r';\s*(?:SELECT|INSERT|UPDATE|DELETE|DROP)',  # stacked queries
            r'--\s*$',                                     # comment at end
            r'/\*.*?\*/',                                  # block comments
            r'\bXP_\w+',                                   # xp_ procedures
            r'\bEXEC\s*\(',                                # exec()
        ]
        for pattern in injection_patterns:
            if re.search(pattern, normalized, re.DOTALL):
                return False, f"Potential injection pattern detected: {pattern}"

        # Require LIMIT clause for SELECT queries (prevent full table scans)
        if first_word == "SELECT" and "LIMIT" not in normalized:
            return False, "SELECT query must include LIMIT clause (max safety)"

        return True, ""

    def add_limit(self, sql: str, max_rows: int = None) -> str:
        """Add LIMIT clause if missing."""
        limit = max_rows or self.MAX_RESULTS_DEFAULT
        normalized = sql.upper().strip()
        if "LIMIT" not in normalized:
            sql = sql.rstrip().rstrip(";")
            sql += f"\nLIMIT {limit};"
        return sql

    def extract_tables(self, sql: str) -> list[str]:
        """Extract table names from SQL query."""
        pattern = r'\bFROM\s+(\w+)|\bJOIN\s+(\w+)'
        matches = re.findall(pattern, sql, re.IGNORECASE)
        tables = []
        for match in matches:
            for name in match:
                if name:
                    tables.append(name.lower())
        return list(set(tables))

    def sanitize_identifier(self, identifier: str) -> str:
        """Sanitize table/column names to prevent injection."""
        return re.sub(r'[^\w]', '', identifier)