"""SQL query formatting and templating."""

import hashlib
import logging
import random
import re
import string
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Union

from jinja2 import Environment, Template, TemplateSyntaxError, meta

logger = logging.getLogger(__name__)


class SQLFormatter:
    """SQL query formatting and templating with Jinja2."""

    def __init__(self):
        self.env = Environment(
            autoescape=False,  # Don't autoescape for SQL
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.generators: Dict[str, Callable] = {}
        self.static_params: Dict[str, Any] = {}
        self._setup_default_filters()

    def _setup_default_filters(self):
        """Setup default Jinja2 filters for SQL formatting."""
        # Add SQL-safe string escaping
        self.env.filters["sql_escape"] = self._sql_escape
        self.env.filters["sql_identifier"] = self._sql_identifier
        self.env.filters["sql_list"] = self._sql_list
        self.env.filters["sql_like"] = self._sql_like_pattern

    @staticmethod
    def _sql_escape(value: Any) -> str:
        """Escape a value for SQL."""
        if value is None:
            return "NULL"
        elif isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, datetime):
            return f"'{value.isoformat()}'"
        else:
            return ""

    @staticmethod
    def _sql_identifier(name: str) -> str:
        """Format a SQL identifier (table/column name)."""
        # Remove any non-alphanumeric characters except underscore
        clean_name = re.sub(r"[^\w]", "", name)
        # Quote the identifier
        return f'"{clean_name}"'

    @staticmethod
    def _sql_list(values: List[Any]) -> str:
        """Format a list of values for SQL IN clause."""
        if not values:
            return "(NULL)"
        escaped_values = [SQLFormatter._sql_escape(v) for v in values]
        return f"({', '.join(escaped_values)})"

    @staticmethod
    def _sql_like_pattern(
        value: str, prefix: bool = False, suffix: bool = False
    ) -> str:
        """Format a LIKE pattern."""
        escaped = value.replace("%", "\\%").replace("_", "\\_")
        if prefix and suffix:
            return f"'%{escaped}%'"
        elif prefix:
            return f"'%{escaped}'"
        elif suffix:
            return f"'{escaped}%'"
        else:
            return f"'{escaped}'"

    def add_generator(self, placeholder: str, generator: Callable):
        """
        Add a value generator for a placeholder.

        Args:
            placeholder: The placeholder name to replace
            generator: A callable that returns a value
        """
        if not callable(generator):
            raise ValueError(f"Generator for '{placeholder}' must be callable")
        self.generators[placeholder] = generator
        logger.debug(f"Added generator for placeholder: {placeholder}")

    def add_static_param(self, name: str, value: Any):
        """Add a static parameter value."""
        self.static_params[name] = value

    def format(self, sql: str, params: Optional[Dict[str, Any]] = None) -> str:
        """
        Format SQL with parameters and generators.

        Args:
            sql: SQL template with Jinja2 placeholders
            params: Optional parameters to override defaults

        Returns:
            Formatted SQL query
        """
        params = params or {}

        # Generate values for registered generators
        generated_values = {}
        for placeholder, generator in self.generators.items():
            if placeholder not in params:  # Don't override provided params
                try:
                    generated_values[placeholder] = generator()
                except Exception as e:
                    logger.error(f"Generator for '{placeholder}' failed: {e}")
                    generated_values[placeholder] = None

        # Combine all parameters (priority: params > generated > static)
        all_params = {**self.static_params, **generated_values, **params}

        # Add utility functions to template context
        all_params.update(
            {
                "now": datetime.now,
                "random": random,
                "range": range,
                "len": len,
            }
        )

        try:
            # Use Jinja2 for templating
            template = self.env.from_string(sql)
            formatted = template.render(**all_params)

            # Clean up any extra whitespace
            formatted = re.sub(r"\s+", " ", formatted).strip()

            return formatted
        except TemplateSyntaxError as e:
            logger.error(f"SQL template syntax error: {e}")
            raise ValueError(f"Invalid SQL template: {e}")
        except Exception as e:
            logger.error(f"SQL formatting failed: {e}")
            raise

    def validate_sql(self, sql: str) -> bool:
        """
        Validate SQL template syntax.

        Args:
            sql: SQL template to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            # Parse the template to check syntax
            ast = self.env.parse(sql)

            # Extract undefined variables
            undefined = meta.find_undeclared_variables(ast)

            if undefined:
                logger.warning(f"Template has undefined variables: {undefined}")

            return True
        except TemplateSyntaxError as e:
            logger.error(f"Invalid SQL template: {e}")
            return False

    def get_template_variables(self, sql: str) -> List[str]:
        """
        Extract all variables from a SQL template.

        Args:
            sql: SQL template

        Returns:
            List of variable names
        """
        try:
            ast = self.env.parse(sql)
            return list(meta.find_undeclared_variables(ast))
        except TemplateSyntaxError:
            return []

    def clear_generators(self):
        """Clear all registered generators."""
        self.generators.clear()

    def clear_static_params(self):
        """Clear all static parameters."""
        self.static_params.clear()


class DynamicValueGenerator:
    """Generator for dynamic values in SQL queries."""

    def __init__(self, seed: Optional[int] = None):
        self.random = random.Random(seed)

    def random_int(self, min_val: int = 1, max_val: int = 1000000) -> int:
        """Generate a random integer."""
        return self.random.randint(min_val, max_val)

    def random_float(self, min_val: float = 0.0, max_val: float = 1000.0) -> float:
        """Generate a random float."""
        return self.random.uniform(min_val, max_val)

    def random_string(self, length: int = 10, charset: str = None) -> str:
        """Generate a random string."""
        if charset is None:
            charset = string.ascii_letters + string.digits
        return "".join(self.random.choices(charset, k=length))

    def random_email(self) -> str:
        """Generate a random email address."""
        username = self.random_string(8)
        domain = self.random.choice(["example.com", "test.org", "demo.net"])
        return f"{username}@{domain}"

    def random_date(
        self, start_date: datetime = None, end_date: datetime = None
    ) -> datetime:
        """Generate a random date between start and end."""
        if start_date is None:
            start_date = datetime.now() - timedelta(days=365)
        if end_date is None:
            end_date = datetime.now()

        time_delta = end_date - start_date
        random_days = self.random.randint(0, time_delta.days)
        return start_date + timedelta(days=random_days)

    def random_uuid(self) -> str:
        """Generate a random UUID-like string."""
        return "-".join(
            [
                self.random_string(8),
                self.random_string(4),
                self.random_string(4),
                self.random_string(4),
                self.random_string(12),
            ]
        )

    def random_choice(self, choices: List[Any]) -> Any:
        """Choose a random item from a list."""
        return self.random.choice(choices)

    def weighted_choice(self, choices: Dict[Any, float]) -> Any:
        """Choose a random item with weights."""
        items = list(choices.keys())
        weights = list(choices.values())
        return self.random.choices(items, weights=weights)[0]

    def sequential_id(self, start: int = 1) -> Callable[[], int]:
        """Create a sequential ID generator."""
        counter = {"value": start - 1}

        def generator():
            counter["value"] += 1
            return counter["value"]

        return generator

    def hash_based_id(self, prefix: str = "") -> Callable[[], str]:
        """Create a hash-based ID generator."""
        counter = {"value": 0}

        def generator():
            counter["value"] += 1
            value = f"{prefix}{counter['value']}{datetime.now().timestamp()}"
            return hashlib.md5(value.encode()).hexdigest()[:16]

        return generator
