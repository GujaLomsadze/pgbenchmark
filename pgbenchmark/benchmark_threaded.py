import os
import threading
import time
from datetime import datetime, timezone
from typing import Union, List, Dict, Any

try:
    import psycopg2
    from psycopg2.extensions import connection as Psycopg2Connection
except ImportError:
    psycopg2 = None
    Psycopg2Connection = None

try:
    from sqlalchemy.engine import Engine as SQLAlchemyEngine
    from sqlalchemy.sql import text as sqlalchemy_text
except ImportError:
    SQLAlchemyEngine = None
    sqlalchemy_text = None

# Keep the shared_benchmark concept if needed, though its utility
# might decrease if you frequently switch between Benchmark and ThreadedBenchmark
shared_benchmark = None


class ThreadedBenchmark:
    """
    Runs SQL benchmarks concurrently using multiple threads.

    Requires either psycopg2 connection parameters or a SQLAlchemy Engine.
    """

    def __init__(
            self,
            num_threads: int,
            number_of_runs: int,  # <--- This now means runs PER THREAD
            db_connection_info: Union[Dict[str, Any], "SQLAlchemyEngine"],
    ):
        """
        :param num_threads: The number of concurrent threads to use.
        :param number_of_runs: Number of times to run the SQL query PER THREAD.
        :param db_connection_info: EITHER a dictionary of parameters for
            psycopg2.connect() (e.g., {'dbname': 'test', 'user': 'postgres', ...})
            OR a SQLAlchemy Engine object. Passing a live psycopg2 connection
            is discouraged due to thread-safety issues.
        """
        if num_threads <= 0:
            raise ValueError("Number of threads must be positive.")
        # Allow number_of_runs to be 0 if user wants to test thread setup?
        # Let's keep the original check for simplicity, requiring at least 1 run.
        if number_of_runs <= 0:
            raise ValueError("Number of runs per thread must be positive.")

        self.sql_query = None
        self.num_threads = num_threads
        self.number_of_runs_per_thread = number_of_runs  # Store with a descriptive name
        self.db_connection_info = db_connection_info
        self._is_sqlalchemy = SQLAlchemyEngine is not None and isinstance(db_connection_info, SQLAlchemyEngine)
        self._is_psycopg2 = isinstance(db_connection_info, dict)

        if not self._is_sqlalchemy and not self._is_psycopg2:
            raise TypeError("db_connection_info must be a dict for psycopg2 or a SQLAlchemy Engine.")
        if self._is_psycopg2 and psycopg2 is None:
            raise ImportError("psycopg2 library is required when providing connection parameters as dict.")
        if self._is_sqlalchemy and SQLAlchemyEngine is None:
            raise ImportError("SQLAlchemy library is required when providing an Engine object.")

        # Thread-safe storage for results
        self.execution_times: List[float] = []
        self._run_timestamps: List[Dict[str, str]] = []
        self._lock = threading.Lock()
        self._errors: List[str] = []  # To collect errors from threads

        global shared_benchmark
        shared_benchmark = self

    def set_sql(self, query: str):
        """Sets the SQL query, reading from a file if `query` is a valid path."""
        if os.path.isfile(query):
            with open(query, "r", encoding="utf-8") as f:
                self.sql_query = f.read().strip()
        else:
            self.sql_query = query.strip()

    def get_sql(self) -> str:
        """Returns the currently set SQL query."""
        return self.sql_query

    def _worker(self, runs_for_this_thread: int):
        """Target function for each worker thread."""
        conn = None
        try:
            # --- Establish Connection ---
            if self._is_sqlalchemy:
                # SQLAlchemy Engine manages pooling, connection is obtained per execution
                engine = self.db_connection_info
            elif self._is_psycopg2:
                # Create a new connection for this thread
                conn = psycopg2.connect(**self.db_connection_info)
            else:
                # Double check. In case Client sets up the benchmark class and while it's started, connection dropped
                raise RuntimeError("Invalid database connection configuration.")

            sql_stmt = self.sql_query  # Cache locally
            if self._is_sqlalchemy and sqlalchemy_text:
                sql_stmt = sqlalchemy_text(sql_stmt)  # Prepare for SQLAlchemy execute

            results_local = []  # Accumulate locally before locking

            for _ in range(runs_for_this_thread):
                start_time = time.time()
                timestamp_sent = datetime.now(timezone.utc)

                try:
                    if self._is_sqlalchemy:
                        with engine.connect() as connection:  # Get connection from pool
                            with connection.begin():  # Start transaction
                                connection.execute(sql_stmt)
                            # Connection automatically returned to pool
                    elif conn:  # Psycopg2 connection exists
                        with conn.cursor() as cursor:
                            cursor.execute(sql_stmt)
                        conn.commit()  # Commit transaction for this thread's connection
                    else:
                        raise RuntimeError("No valid connection or engine available.")

                except Exception as e:
                    error_msg = f"Thread {threading.current_thread().name}: Error executing query: {e}"
                    with self._lock:
                        self._errors.append(error_msg)
                    # Optionally re-raise or just break the loop
                    # raise # Re-raising might hide other errors
                    break  # Stop processing for this thread on error

                end_time = time.time()
                duration = round(end_time - start_time, 6)
                duration_str = format(duration, '.6f').rstrip('0').rstrip('.')

                record = {
                    "sent_at": timestamp_sent.isoformat(),
                    "duration": duration_str,
                    "duration_float": duration  # Keep float for calculations
                }
                results_local.append(record)

            # --- Store Results (Thread-Safe) ---
            if results_local:
                with self._lock:
                    for record in results_local:
                        self.execution_times.append(record["duration_float"])
                        self._run_timestamps.append({
                            "sent_at": record["sent_at"],
                            "duration": record["duration"]
                        })

        except Exception as e:
            # Catch errors during connection setup or other unexpected issues
            error_msg = f"Thread {threading.current_thread().name}: Worker error: {e}"
            with self._lock:
                self._errors.append(error_msg)
        finally:
            # --- Close Psycopg2 Connection ---
            if conn:
                try:
                    conn.close()
                except Exception as e:
                    # Log error during close if necessary
                    print(f"Warning: Error closing psycopg2 connection in thread: {e}")

    def run(self):
        """Executes the benchmark across multiple threads."""
        if not self.sql_query:
            raise ValueError("SQL query is not set. Use set_sql().")

        # Reset results from previous runs
        self.execution_times = []
        self._run_timestamps = []
        self._errors = []

        total_expected_runs = self.number_of_runs_per_thread * self.num_threads
        start_run_time = time.time()
        threads: List[threading.Thread] = []

        # Each thread gets assigned 'number_of_runs_per_thread'
        runs_for_each_thread = self.number_of_runs_per_thread
        if runs_for_each_thread == 0:
            return  # Nothing to do

        for i in range(self.num_threads):
            thread = threading.Thread(
                target=self._worker,
                args=(runs_for_each_thread,),  # Pass runs_per_thread to worker
                name=f"Worker-{i + 1}"
            )
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        end_run_time = time.time()
        total_duration = end_run_time - start_run_time

        if self._errors:
            print("\n--- Errors Occurred ---")
            for error in self._errors:
                print(error)
            print("-----------------------\n")
            # Decide if errors should halt further result processing
            # raise RuntimeError("Errors occurred during threaded execution. See logs.")

        # Verify run count against the total expected runs
        actual_runs_completed = len(self.execution_times)
        if actual_runs_completed != total_expected_runs and not self._errors:
            print(f"Warning: Expected {total_expected_runs} total results, but collected {actual_runs_completed}. "
                  f"This might happen if threads finished unexpectedly without errors.")
        elif actual_runs_completed == 0 and not self._errors and total_expected_runs > 0:
            print("Warning: No results collected and no errors reported.")

    def get_execution_results(self) -> Dict[str, Any]:
        """
        Calculates and returns summary statistics after the benchmark has run.

        :raises ValueError: If the benchmark hasn't run or produced no results.
        :return: Dictionary with min, max, average times, and run counts.
        """

        """ <--- If a rogue Thread is still running, getting results with a Lock, so that the output is not changed
        while calculating --->
        """
        with self._lock:
            if not self.execution_times:
                if self._errors:
                    raise ValueError("Benchmark ran with errors and produced no successful results.")
                else:
                    raise ValueError("Benchmark has not been run yet or produced no results.")

            actual_runs = len(self.execution_times)
            if actual_runs == 0:  # Should be caught above, but double check
                raise ValueError("No execution times recorded.")

            min_time = min(self.execution_times)
            max_time = max(self.execution_times)
            avg_time = sum(self.execution_times) / actual_runs
            total_expected_runs = self.number_of_runs_per_thread * self.num_threads

            return {
                "runs_per_thread": self.number_of_runs_per_thread,
                "num_threads": self.num_threads,
                "total_expected_runs": total_expected_runs,
                "actual_runs_completed": actual_runs,  # Number of successful runs recorded
                "min_time": format(min_time, '.6f').rstrip('0').rstrip('.'),
                "max_time": format(max_time, '.6f').rstrip('0').rstrip('.'),
                "avg_time": format(avg_time, '.6f').rstrip('0').rstrip('.'),
                "errors": len(self._errors),
            }

    def get_execution_timeseries(self) -> List[Dict[str, str]]:
        """
        Returns the detailed timestamp and duration for each successful execution.

        :raises ValueError: If the benchmark hasn't run or produced no results.
        :return: List of dictionaries, each containing 'sent_at' and 'duration'.
                 The order might not correspond to the absolute start time due
                 to threading, but reflects the order results were recorded.
        """
        with self._lock:
            if not self._run_timestamps:
                # Check if errors occurred, as that might be why there are no results
                if self._errors:
                    raise ValueError("Benchmark ran with errors and produced no successful results.")
                else:
                    raise ValueError("Benchmark has not been run yet or produced no results.")
            # Return a copy to prevent external modification
            return list(self._run_timestamps)
