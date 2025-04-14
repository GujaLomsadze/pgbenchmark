import multiprocessing
import os
import time
from datetime import datetime, timezone
from queue import Empty  # To handle queue timeout if needed, though blocking get is simpler
from typing import List, Dict, Any, Union, Optional, Callable  # Added Optional

try:
    import psycopg2
    # Cannot type hint Psycopg2Connection as it's not passed
except ImportError:
    psycopg2 = None

try:
    from sqlalchemy import create_engine, text as sqlalchemy_text
    from sqlalchemy.engine import Engine as SQLAlchemyEngine  # Keep for type hint clarity
except ImportError:
    create_engine = None
    sqlalchemy_text = None
    SQLAlchemyEngine = None  # Define for type hint

# Result dictionary keys for the queue
SENT_AT = "sent_at"
DURATION = "duration"
DURATION_FLOAT = "duration_float"
ERROR = "error"
WORKER_NAME = "worker_name"
IS_RESULT = "is_result"  # Flag to distinguish results from errors/sentinels

# Sentinel value to signal worker completion
WORKER_DONE_SENTINEL = None


# Note: shared_benchmark concept doesn't really work across processes
# shared_benchmark = None

class ParallelBenchmark:
    """
    Runs SQL benchmarks concurrently using multiple processes with templated queries.

    Requires pickleable connection information (psycopg2 params dict or SQLAlchemy URL string).
    """

    def __init__(
            self,
            num_processes: int,
            number_of_runs: int,  # Runs PER PROCESS
            # MUST be pickleable: dict for psycopg2, str (URL) for SQLAlchemy recommended
            db_connection_info: Union[Dict[str, Any], str],
    ):
        """
        :param num_processes: The number of concurrent processes to use.
        :param number_of_runs: Number of times to run the SQL query PER PROCESS.
        :param db_connection_info: EITHER a dictionary of parameters for
            psycopg2.connect() OR a database URL string for SQLAlchemy.
            Cannot be a live connection or Engine object.
        """
        if num_processes <= 0:
            raise ValueError("Number of processes must be positive.")
        if number_of_runs <= 0:
            raise ValueError("Number of runs per process must be positive.")

        self.sql_query_template: Optional[str] = None
        self._sql_formatter: Dict[str, Callable[[], Any]] = {}
        self.num_processes = num_processes
        self.number_of_runs_per_process = number_of_runs
        self.db_connection_info = db_connection_info

        # Determine connection type based on input type
        self._is_sqlalchemy_url = isinstance(db_connection_info, str)
        self._is_psycopg2_params = isinstance(db_connection_info, dict)

        # Validate connection info type and library presence
        if not self._is_sqlalchemy_url and not self._is_psycopg2_params:
            raise TypeError("db_connection_info must be a dict (for psycopg2 params) or a str (for SQLAlchemy URL).")
        if self._is_psycopg2_params and psycopg2 is None:
            raise ImportError("psycopg2 library is required when providing connection parameters as dict.")
        if self._is_sqlalchemy_url and create_engine is None:
            raise ImportError("SQLAlchemy library is required when providing a database URL string.")

        # Results storage - populated by the main process from the queue
        self.execution_times: List[float] = []
        self._run_timestamps: List[Dict[str, str]] = []
        self._errors: List[str] = []
        self._total_run_duration: float = 0.0  # <--- Initialize total duration

    def set_sql(self, query: str):
        """Sets the SQL query template, reading from a file if `query` is a valid path."""
        if os.path.isfile(query):
            with open(query, "r", encoding="utf-8") as f:
                self.sql_query_template = f.read().strip()
        else:
            self.sql_query_template = query.strip()

    def get_sql_template(self) -> Optional[str]:
        """Returns the currently set SQL query template."""
        return self.sql_query_template

    def set_sql_formatter(self, for_placeholder: str, generator: Callable[[], Any]):
        """
        Sets a generator function for a specific placeholder in the SQL query template.

        :param for_placeholder: The name of the placeholder (e.g., 'value' for '{{value}}').
        :param generator: A callable (function or lambda) that returns the value to be inserted.
        """
        if not callable(generator):
            raise TypeError("Generator must be a callable function.")
        self._sql_formatter[for_placeholder] = generator

    @staticmethod
    def _worker_process(
            worker_id: int,
            sql_formatter: Dict[str, Callable[[], Any]],
            sql_template: str,
            connection_info: Union[Dict[str, Any], str],
            runs_for_this_process: int,
            results_queue: multiprocessing.Queue
    ):
        """Target function for each worker process."""
        conn = None  # psycopg2 connection
        engine = None  # SQLAlchemy engine
        is_sqlalchemy = isinstance(connection_info, str)
        is_psycopg2 = isinstance(connection_info, dict)
        worker_name = f"Process-{worker_id + 1}"

        try:
            # --- Establish Connection ---
            connect_start_time = time.time()
            if is_sqlalchemy:
                if create_engine is None or sqlalchemy_text is None:
                    raise RuntimeError("SQLAlchemy not found in worker process.")
                # Create engine specific to this process
                engine = create_engine(connection_info)  # Add pool options if needed
            elif is_psycopg2:
                if psycopg2 is None:
                    raise RuntimeError("psycopg2 not found in worker process.")
                # Create connection specific to this process
                conn = psycopg2.connect(**connection_info)
            else:
                # Should not happen based on __init__ checks
                raise RuntimeError("Invalid database connection configuration.")
            connect_duration = time.time() - connect_start_time
            # print(f"{worker_name}: Connection established in {connect_duration:.3f}s") # Optional debug info

            # --- Execute Queries ---
            for i in range(runs_for_this_process):
                start_time = time.time()
                timestamp_sent = datetime.now(timezone.utc)
                result_data = {}  # Store result/error for queue
                formatted_sql = sql_template
                for placeholder, generator in sql_formatter.items():
                    value = generator()
                    formatted_sql = formatted_sql.replace(f"{{{{{placeholder}}}}}", str(value))

                try:
                    if engine:  # SQLAlchemy
                        sql_stmt = sqlalchemy_text(formatted_sql)
                        with engine.connect() as connection:
                            with connection.begin():  # Transaction
                                connection.execute(sql_stmt)
                    elif conn:  # psycopg2
                        with conn.cursor() as cursor:
                            cursor.execute(formatted_sql)
                        conn.commit()
                    else:
                        # Should not happen
                        raise RuntimeError("No connection or engine available in loop.")

                    # --- Success Case ---
                    end_time = time.time()
                    duration = round(end_time - start_time, 6)
                    duration_str = format(duration, '.6f').rstrip('0').rstrip('.')
                    result_data = {
                        IS_RESULT: True,
                        WORKER_NAME: worker_name,
                        SENT_AT: timestamp_sent.isoformat(),
                        DURATION: duration_str,
                        DURATION_FLOAT: duration
                    }

                except Exception as e:
                    # --- Error Case ---
                    error_msg = f"{worker_name}: Run {i + 1}/{runs_for_this_process} failed: {e}"
                    result_data = {
                        IS_RESULT: False,
                        WORKER_NAME: worker_name,
                        ERROR: error_msg
                    }
                    results_queue.put(result_data)
                    # Stop this worker on error
                    break
                finally:
                    # Put result/error data on the queue
                    # Check if result_data was populated (it should be unless unknown exception before try block end)
                    if result_data:
                        results_queue.put(result_data)
                    else:
                        # Handle unexpected case where result_data is empty
                        results_queue.put({
                            IS_RESULT: False,
                            WORKER_NAME: worker_name,
                            ERROR: f"{worker_name}: Run {i + 1}/{runs_for_this_process} ended unexpectedly without result/error."
                        })


        except Exception as e:
            # Catch errors during connection setup or other unexpected issues
            error_msg = f"{worker_name}: Worker initialization or unhandled error: {e}"
            results_queue.put({IS_RESULT: False, WORKER_NAME: worker_name, ERROR: error_msg})

        finally:
            # --- Close Connection / Dispose Engine ---
            if conn:  # psycopg2
                try:
                    conn.close()
                except Exception as e:
                    print(f"Warning: Error closing psycopg2 connection in {worker_name}: {e}")
            if engine:  # SQLAlchemy
                try:
                    engine.dispose()  # Release pool resources
                except Exception as e:
                    print(f"Warning: Error disposing SQLAlchemy engine in {worker_name}: {e}")

            # --- Signal Completion ---
            results_queue.put(WORKER_DONE_SENTINEL)  # Put None (or sentinel) to signal worker finished

    def run(self):
        """Executes the benchmark across multiple processes with formatted SQL."""
        if not self.sql_query_template:
            raise ValueError("SQL query template is not set. Use set_sql().")

        # Reset results from previous runs
        self.execution_times = []
        self._run_timestamps = []
        self._errors = []
        self._total_run_duration = 0.0  # <--- Reset total duration

        total_expected_runs = self.number_of_runs_per_process * self.num_processes
        start_run_time = time.time()  # <--- Start timing here
        print(f"[MainProcess] Starting benchmark with {self.num_processes} processes, "
              f"{self.number_of_runs_per_process} runs per process ({total_expected_runs} total runs expected)...")

        # Create the results Queue
        results_queue = multiprocessing.Queue()
        processes: List[multiprocessing.Process] = []

        # --- Start Worker Processes ---
        runs_for_each_process = self.number_of_runs_per_process
        if runs_for_each_process == 0:
            print("[MainProcess] Warning: number_of_runs_per_process is 0, no work will be done.")
            # Store duration even if no work done
            end_run_time_no_work = time.time()
            self._total_run_duration = end_run_time_no_work - start_run_time
            return

        for i in range(self.num_processes):
            process = multiprocessing.Process(
                target=self._worker_process,
                args=(
                    i,
                    self._sql_formatter,
                    self.sql_query_template,
                    self.db_connection_info,
                    runs_for_each_process,
                    results_queue
                ),
                name=f"Process-{i + 1}"
            )
            processes.append(process)
            process.start()

        # --- Collect Results from Queue ---
        print("[MainProcess] Waiting for results from worker processes...")
        completed_workers = 0
        processed_results = 0
        processed_errors = 0

        while completed_workers < self.num_processes:
            try:
                item = results_queue.get()
                if item == WORKER_DONE_SENTINEL:
                    completed_workers += 1
                elif isinstance(item, dict):
                    if item.get(IS_RESULT):
                        self.execution_times.append(item[DURATION_FLOAT])
                        self._run_timestamps.append({
                            SENT_AT: item[SENT_AT],
                            DURATION: item[DURATION]
                        })
                        processed_results += 1
                    else:
                        self._errors.append(item.get(ERROR, "Unknown error from worker"))
                        processed_errors += 1
                else:
                    print(f"[MainProcess] Warning: Received unexpected item from queue: {item}")
                    self._errors.append(f"Unexpected item from queue: {item}")
                    processed_errors += 1
            except Empty:
                pass  # Should not happen with blocking get
            except Exception as e:
                print(f"[MainProcess] Error processing result queue: {e}")
                self._errors.append(f"Main process error handling queue: {e}")
                processed_errors += 1

        print(
            f"[MainProcess] All workers signaled completion. Processed {processed_results} results, {processed_errors} errors.")

        # --- Join Worker Processes ---
        print("[MainProcess] Joining worker processes...")
        for i, process in enumerate(processes):
            try:
                process.join(timeout=10)
                if process.is_alive():
                    print(
                        f"[MainProcess] Warning: Process {process.name} did not terminate after join timeout. Terminating.")
                    process.terminate()
                    process.join()
            except Exception as e:
                print(f"[MainProcess] Error joining process {process.name}: {e}")

        end_run_time = time.time()  # <--- Stop timing here
        total_duration = end_run_time - start_run_time
        self._total_run_duration = total_duration  # <--- Store total duration

        print(f"[MainProcess] Benchmark finished in {self._total_run_duration:.3f} seconds.")

        # (Error reporting and final verification remain the same)
        if self._errors:
            print("\n--- Errors Occurred ---")
            for error in self._errors:
                print(error)
            print("-----------------------\n")

        actual_runs_completed = len(self.execution_times)
        if actual_runs_completed != total_expected_runs and not self._errors:
            print(
                f"[MainProcess] Warning: Expected {total_expected_runs} total results, but collected {actual_runs_completed}. Check worker logs/errors if any were suppressed.")
        elif actual_runs_completed == 0 and not self._errors and total_expected_runs > 0:
            print("[MainProcess] Warning: No results collected and no errors reported.")

    def get_execution_results(self) -> Dict[str, Any]:
        """
        Calculates and returns summary statistics after the benchmark has run.
        Must be called after run() completes.

        :raises ValueError: If the benchmark hasn't run or produced no results.
        :return: Dictionary with min, max, average times, run counts, and throughput.
        """
        if not self.execution_times:
            if self._errors:
                raise ValueError("Benchmark ran with errors and produced no successful results.")
            # Check if run() completed by looking at the duration flag
            elif self._total_run_duration <= 0:
                raise ValueError("Benchmark has not been run yet.")
            else:  # No errors, run completed, but zero results (e.g., all runs failed quickly)
                # Allow returning results like counts and errors, but throughput will be 0
                pass

        actual_runs = len(self.execution_times)
        min_time = 0.0
        max_time = 0.0
        avg_time = 0.0
        throughput = 0.0  # Default to 0

        if actual_runs > 0:
            min_time = min(self.execution_times)
            max_time = max(self.execution_times)
            avg_time = sum(self.execution_times) / actual_runs

            # Calculate throughput: successful runs / total duration
            if self._total_run_duration > 0:
                throughput = actual_runs / self._total_run_duration
            else:
                # Avoid division by zero if benchmark was instantaneous (unlikely but possible)
                # Or if only failed runs occurred very quickly before duration was stored properly
                throughput = 0.0  # Or perhaps float('inf') if actual_runs > 0? Let's stick to 0.

        total_expected_runs = self.number_of_runs_per_process * self.num_processes

        # Format results consistently
        min_time_str = format(min_time, '.6f').rstrip('0').rstrip('.') if actual_runs > 0 else "N/A"
        max_time_str = format(max_time, '.6f').rstrip('0').rstrip('.') if actual_runs > 0 else "N/A"
        avg_time_str = format(avg_time, '.6f').rstrip('0').rstrip('.') if actual_runs > 0 else "N/A"
        throughput_str = f"{throughput:.2f}"  # Format throughput to 2 decimal places

        return {
            "runs_per_process": self.number_of_runs_per_process,
            "num_processes": self.num_processes,
            "total_expected_runs": total_expected_runs,
            "actual_runs_completed": actual_runs,
            "total_run_duration_sec": round(self._total_run_duration, 3),  # Add total time
            "min_time": min_time_str,
            "max_time": max_time_str,
            "avg_time": avg_time_str,
            "errors": len(self._errors),
            "throughput_runs_per_sec": throughput_str,  # <--- Added throughput
        }

    def get_execution_timeseries(self) -> List[Dict[str, str]]:
        """
        Returns the detailed timestamp and duration for each successful execution.
        Must be called after run() completes.

        :raises ValueError: If the benchmark hasn't run or produced no results.
        :return: List of dictionaries, each containing 'sent_at' and 'duration'.
        """
        # No lock needed here
        if not self._run_timestamps:
            if self._errors:
                raise ValueError("Benchmark ran with errors and produced no successful results.")
            else:
                raise ValueError("Benchmark has not been run yet or produced no results.")
        # Return a copy
        return list(self._run_timestamps)
