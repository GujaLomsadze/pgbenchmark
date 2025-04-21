import logging
import math
import os
import statistics
import time
from datetime import datetime, timezone
from typing import Generator, Optional

from psycopg2.extensions import connection as psycopg2_connection

__all__ = ["Benchmark"]

shared_benchmark: Optional["Benchmark"] = None

# Module-level logger
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class Benchmark:
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        raise TypeError(
            f"Inheriting from 'Benchmark' is not allowed. "
            f"Class '{cls.__name__}' attempted to subclass."
        )

    def __init__(
            self,
            db_connection: psycopg2_connection,
            number_of_runs: int = 1,
    ):
        if number_of_runs < 1:
            raise ValueError("number_of_runs must be at least 1.")

        self._db = db_connection
        self._runs = number_of_runs
        self._sql: Optional[str] = None
        self.execution_times: list[float] = []
        self._timestamps: list[dict] = []

        global shared_benchmark
        shared_benchmark = self

    def set_sql(self, query: str) -> None:
        """
        Set the SQL to execute, reading from a file if a path exists.
        """
        if os.path.isfile(query):
            with open(query, encoding="utf-8") as f:
                self._sql = f.read().strip()
        else:
            self._sql = query

    def get_sql(self) -> str:
        """Return the current SQL query."""
        if not self._sql:
            raise ValueError("SQL query is not set.")
        return self._sql

    def __iter__(self) -> Generator[dict, None, None]:
        """
        Iterate through benchmark runs, yielding timestamped durations.
        """
        if not self._db:
            raise ValueError("Database connection is not set.")
        sql = self.get_sql()

        self.execution_times.clear()
        self._timestamps.clear()

        for _ in range(self._runs):
            start = time.time()
            sent = datetime.now(timezone.utc)

            try:
                cursor = self._db.cursor()
                cursor.execute(sql)
                self._db.commit()
                cursor.close()
            except Exception as exc:
                # TODO: Adding Retries soon enough
                logger.exception("Query execution failed.")
                raise RuntimeError(f"Error executing query: {exc}") from exc

            duration = time.time() - start
            self.execution_times.append(duration)

            duration_str = f"{duration:.6f}".rstrip('0').rstrip('.')
            record = {"sent_at": sent.isoformat(), "duration": duration_str}
            self._timestamps.append(record)

            yield record

    def get_execution_results(self) -> dict:
        """
        After running, return summary of min, max, average, median, and percentiles.
        Includes the 99th percentile as well.
        """
        if not self.execution_times:
            raise ValueError("No execution data available. Please run the benchmark.")

        times = sorted(self.execution_times)

        runs = self._runs

        min_time = times[0]
        max_time = times[-1]

        avg_time = sum(times) / len(times)
        median_time = statistics.median(times)

        # Compute quartile percentiles (25th, 50th, 75th)
        quartiles = statistics.quantiles(times, n=4)
        p25, p50, p75 = quartiles[0], quartiles[1], quartiles[2]

        # Compute 99th percentile using nearest-rank method
        k = math.ceil(0.99 * len(times))
        p99 = times[k - 1]

        # Helper to format times
        def fmt(val: float) -> str:
            return f"{val:.6f}".rstrip('0').rstrip('.')

        return {
            "runs": runs,
            "min_time": fmt(min_time),
            "max_time": fmt(max_time),
            "avg_time": fmt(avg_time),
            "median_time": fmt(median_time),
            "percentiles": {
                "p25": fmt(p25),
                "p50": fmt(p50),
                "p75": fmt(p75),
                "p99": fmt(p99),
            },
        }

    def get_execution_timeseries(self) -> list[dict]:
        """
        Return list of records with timestamps and durations.
        """
        if not self._timestamps:
            raise ValueError("No timestamp data available. Please run the benchmark.")
        return self._timestamps
