import multiprocessing
import os
import sys  # Import sys for flushing output
import time
from datetime import datetime, timezone
from queue import Empty  # Import Empty exception for queue
from typing import Dict, Any, Union, List, Callable, Optional, Iterator

# Try importing optional libraries
try:
    import psycopg2
except ImportError:
    psycopg2 = None

try:
    # Need create_engine and text for SQLAlchemy
    from sqlalchemy import create_engine, text as sqlalchemy_text
except ImportError:
    create_engine = None
    sqlalchemy_text = None

# Constants for queue item keys
IS_RESULT = "is_result"
WORKER_NAME = "worker_name"
SENT_AT = "sent_at"
DURATION = "duration"
DURATION_FLOAT = "duration_float"  # Keep float for calculation
ERROR = "error"
WORKER_DONE_SENTINEL = None  # Sentinel value to indicate worker completion


class ParallelBenchmark:
    """
    Runs SQL benchmarks concurrently using multiple processes with templated queries.

    Can be used with a blocking `run()` method or iterated over directly
    like a generator to get live results.

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
        if self._is_sqlalchemy_url and (create_engine is None or sqlalchemy_text is None):
            raise ImportError(
                "SQLAlchemy library (and its 'text' function) is required when providing a database URL string.")

        # State for iteration/running
        self._results_queue: Optional[multiprocessing.Queue] = None
        self._processes: List[multiprocessing.Process] = []
        self._completed_workers_count: int = 0
        self._is_running: bool = False  # Flag to indicate if benchmark is currently running/iterable
        self._benchmark_start_time: Optional[float] = None

        # Results storage - populated by the main process from the queue (either via run or iteration)
        self.execution_times: List[float] = []
        self._run_timestamps: List[Dict[str, str]] = []  # Stores formatted time string
        self._errors: List[str] = []
        self._total_run_duration: float = 0.0  # Duration measured from start to end of run() or iteration

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

        worker_name = f"{worker_id + 1}"

        try:
            # --- Establish Connection ---
            # connect_start_time = time.time() # Uncomment for connection time debug
            if is_sqlalchemy:
                if create_engine is None or sqlalchemy_text is None:
                    raise RuntimeError("SQLAlchemy not found in worker process.")
                engine = create_engine(connection_info)
            elif is_psycopg2:
                if psycopg2 is None:
                    raise RuntimeError("psycopg2 not found in worker process.")
                conn = psycopg2.connect(**connection_info)
            else:
                raise RuntimeError("Invalid database connection configuration.")
            # connect_duration = time.time() - connect_start_time
            # print(f"{worker_name}: Connection established in {connect_duration:.3f}s") # Optional debug info

            # --- Execute Queries ---
            for i in range(runs_for_this_process):
                start_time = time.time()
                timestamp_sent = datetime.now(timezone.utc)

                formatted_sql = sql_template
                try:
                    for placeholder, generator in sql_formatter.items():
                        value = generator()
                        formatted_sql = formatted_sql.replace(f"{{{{{placeholder}}}}}", str(value))

                    if engine:  # SQLAlchemy
                        sql_stmt = sqlalchemy_text(formatted_sql)
                        with engine.connect() as connection:
                            with connection.begin():
                                connection.execute(sql_stmt)
                    elif conn:  # psycopg2
                        with conn.cursor() as cursor:
                            cursor.execute(formatted_sql)
                        conn.commit()
                    else:
                        raise RuntimeError("No valid connection or engine available.")

                    # --- Success Case ---
                    end_time = time.time()
                    duration = end_time - start_time
                    duration_str = format(duration, '.6f').rstrip('0').rstrip('.')
                    result_data = {
                        IS_RESULT: True,
                        WORKER_NAME: worker_name,
                        SENT_AT: timestamp_sent.isoformat(),
                        DURATION: duration_str,
                        DURATION_FLOAT: duration
                    }
                    results_queue.put(result_data)

                except Exception as e:
                    # --- Error Case ---
                    # Capture error message and send it back
                    error_msg = f"{worker_name}: Run {i + 1}/{runs_for_this_process} failed. Error: {type(e).__name__}: {e}"
                    # Add SQL snippet if available and not too long
                    sql_snippet = formatted_sql[:200].replace('\n', ' ') + '...' if formatted_sql else 'N/A'
                    error_msg += f" SQL: '{sql_snippet}'"

                    error_data = {
                        IS_RESULT: False,
                        WORKER_NAME: worker_name,
                        ERROR: error_msg
                    }
                    results_queue.put(error_data)

                    # Assumes that if one error happened, worker is doomed, so it breaks
                    break

        except Exception as e:
            # Catch errors during connection setup or other unhandled issues before the run loop
            error_msg = f"{worker_name}: Worker initialization or unhandled error: {type(e).__name__}: {e}"
            error_data = {IS_RESULT: False, WORKER_NAME: worker_name, ERROR: error_msg}
            results_queue.put(error_data)

        finally:
            # --- Close Connection / Dispose Engine ---
            if conn:
                try:
                    conn.rollback()  # Rollback anything pending
                    conn.close()
                except Exception as e:
                    # Using print with stderr and flush is okay in a worker for warnings during shutdown
                    print(f"[Worker {worker_name}] Warning: Error closing psycopg2 connection: {type(e).__name__}: {e}",
                          file=sys.stderr)
                    sys.stderr.flush()
            if engine:
                try:
                    engine.dispose()
                except Exception as e:
                    print(f"[Worker {worker_name}] Warning: Error disposing SQLAlchemy engine: {type(e).__name__}: {e}",
                          file=sys.stderr)
                    sys.stderr.flush()

            # --- Signal Completion ---
            # Ensure the sentinel is sent
            results_queue.put(WORKER_DONE_SENTINEL)

    def __iter__(self):
        """
        Prepares and starts the benchmark processes for iteration.
        Returns the iterator object (self).
        """
        if self._is_running:
            raise RuntimeError("Benchmark is already running or being iterated over.")
        if not self.sql_query_template:
            raise ValueError("SQL query template is not set. Use set_sql().")

        # Reset state for a new run/iteration
        self.execution_times = []
        self._run_timestamps = []
        self._errors = []
        self._total_run_duration = 0.0
        self._completed_workers_count = 0
        self._processes = []  # Clear previous process list

        total_expected_runs = self.number_of_runs_per_process * self.num_processes
        print(f"[MainProcess] Starting benchmark for iteration with {self.num_processes} processes, "
              f"{self.number_of_runs_per_process} runs per process ({total_expected_runs} total runs expected)...")
        sys.stdout.flush()

        # Create the results Queue
        self._results_queue = multiprocessing.Queue()

        # --- Start Worker Processes ---
        runs_for_each_process = self.number_of_runs_per_process
        if runs_for_each_process <= 0:
            print("[MainProcess] Warning: number_of_runs_per_process is not positive, no work will be done.")
            sys.stdout.flush()
            self._is_running = False  # Not really running if no work
            return self  # Still return self, but __next__ will immediately stop

        for i in range(self.num_processes):
            process = multiprocessing.Process(
                target=self._worker_process,
                args=(
                    i,
                    self._sql_formatter,
                    self.sql_query_template,
                    self.db_connection_info,
                    runs_for_each_process,
                    self._results_queue
                ),
                name=f"Process-{i + 1}"
            )
            self._processes.append(process)
            process.start()

        self._is_running = True  # Set state to running/iterable
        self._benchmark_start_time = time.time()  # Start timing

        return self  # Return self as the iterator

    def __next__(self):
        """
        Fetches the next result or error item from the queue.
        Processes internal state and raises StopIteration when all workers are done.
        """
        if not self._is_running:
            # If not running, either iteration hasn't started or already finished
            if self._completed_workers_count >= self.num_processes:
                # If completed_workers matches total, it's properly finished
                raise StopIteration
            else:
                # Otherwise, iteration hasn't started or something went wrong before finishing
                raise RuntimeError("Benchmark iteration not started or is in an invalid state.")

        while self._completed_workers_count < self.num_processes:
            try:
                # Blocking get - waits for the next item from any worker
                item = self._results_queue.get()

                if item == WORKER_DONE_SENTINEL:
                    self._completed_workers_count += 1
                    # Check if ALL workers are now done *after* incrementing
                    if self._completed_workers_count == self.num_processes:
                        # All workers have sent their sentinel. Cleanup and stop iteration.
                        self._is_running = False  # Mark as not running
                        self._total_run_duration = time.time() - self._benchmark_start_time  # Final duration
                        print("[MainProcess] All workers finished. Joining processes...")
                        sys.stdout.flush()
                        # Join all processes to ensure they've exited
                        for p in self._processes:
                            p.join(timeout=5)  # Use a timeout in case process hangs
                            if p.is_alive():
                                print(f"[MainProcess] Warning: Process {p.name} did not join cleanly, terminating.",
                                      file=sys.stderr)
                                sys.stderr.flush()
                                p.terminate()  # Force terminate
                                p.join()  # Wait for termination
                        print("[MainProcess] Processes joined.")
                        sys.stdout.flush()
                        # Now raise StopIteration as there are no more items
                        raise StopIteration

                    # If it was just a sentinel and not the *last* one,
                    # continue the *internal* while loop to get the next actual item or sentinel.
                    continue

                elif isinstance(item, dict):
                    # This is a result or error item from a worker
                    if item.get(IS_RESULT):
                        # Store successful results for final stats/timeseries
                        self.execution_times.append(item[DURATION_FLOAT])
                        self._run_timestamps.append({
                            SENT_AT: item[SENT_AT],
                            DURATION: item[DURATION]
                        })
                    else:  # Error item
                        self._errors.append(item.get(ERROR, "Unknown error from worker"))

                    # Yield the item (either result or error dict) to the consumer (the for loop)
                    return item

                else:
                    # Unexpected item - handle like an error
                    error_msg = f"[MainProcess] Warning: Received unexpected item from queue: {item}"
                    print(error_msg, file=sys.stderr)
                    sys.stderr.flush()
                    self._errors.append(error_msg)
                    # Yield this as an error item
                    return {IS_RESULT: False, WORKER_NAME: "MainProcess", ERROR: error_msg}

            except Empty:
                # With a blocking get(), this should only happen if the queue is closed
                # or all workers are done before the main process checked (handled by sentinel).
                # It's unlikely to be reached in normal flow with blocking get() and active workers.
                # print("[MainProcess] Warning: Queue unexpectedly empty during get.", file=sys.stderr)
                # sys.stderr.flush()
                # time.sleep(0.01) # Small sleep to prevent tight loop if somehow reached
                pass  # With blocking get, this shouldn't be necessary

            except Exception as e:
                # Catch any unexpected errors during queue processing in the main thread
                error_msg = f"[MainProcess] Error processing queue item: {type(e).__name__}: {e}"
                print(error_msg, file=sys.stderr)
                sys.stderr.flush()
                self._errors.append(error_msg)
                # Yield this main process error
                return {IS_RESULT: False, WORKER_NAME: "MainProcess", ERROR: error_msg}

        # If the while loop finishes without raising StopIteration (e.g., logic error),
        # ensure iteration is stopped. This code should ideally not be reached.
        if self._completed_workers_count >= self.num_processes:
            raise StopIteration
        else:
            raise RuntimeError("Benchmark iterator finished unexpectedly before all workers signaled completion.")

    def iter_successful_results(self) -> Iterator[Dict[str, Any]]:
        """
        Iterates over the benchmark execution, yielding only the dictionaries
        for successful query executions as they complete. Errors are recorded
        internally but not yielded by this iterator.

        Yields:
            Dict[str, Any]: A dictionary containing details of a successful query execution.
        """
        # The 'for item in self:' loop implicitly calls self.__iter__() first
        # and then repeatedly calls self.__next__() until StopIteration.
        try:
            for item in self:
                if item.get(IS_RESULT):
                    # Only yield the item if it indicates a successful result
                    yield item
                else:
                    # Error items are processed by __next__ (added to _errors)
                    # but are not yielded by this specific helper method.
                    pass
        except StopIteration:
            # This is the normal exit when all workers have finished and __next__ raised StopIteration
            pass
        except Exception as e:
            # Catch any unexpected errors that might occur *during* this iteration process itself.
            # __next__ should handle most queue errors, but this is a safeguard.
            print(f"[MainProcess] Unexpected error during successful results iteration: {type(e).__name__}: {e}",
                  file=sys.stderr)
            sys.stderr.flush()
            # Decide whether to stop iteration or try to continue. Stopping is safer.
            raise StopIteration

    def run(self, live_reporting: bool = False):
        """
        Executes the benchmark across multiple processes, blocking until all runs complete.
        This method internally uses the iterator protocol.

        :param live_reporting: If True, print each successful query execution time as it completes.
        """
        print(f"[MainProcess] Running benchmark (blocking mode)...")
        sys.stdout.flush()

        # Call __iter__ to set up and start processes
        # Iterating over self implicitly calls __iter__
        try:
            # The for loop consumes items by repeatedly calling __next__()
            for item in self:
                if isinstance(item, dict):
                    if item.get(IS_RESULT):
                        # This is where live_reporting happens in the blocking mode
                        if live_reporting:
                            print(f"[{item[WORKER_NAME]}] Executed {item[SENT_AT]} UTC, took {item[DURATION]}s")
                            sys.stdout.flush()
                    else:  # Error item
                        # Errors are always reported live in blocking mode
                        print(f"[MainProcess] Worker Error: {item.get(ERROR, 'Unknown error from worker')}")
                        sys.stdout.flush()
                else:
                    # Unexpected items from queue (should be handled in __next__ yielding an error dict)
                    print(f"[MainProcess] Warning: Received unexpected item from queue during run(): {item}",
                          file=sys.stderr)
                    sys.stderr.flush()


        except StopIteration:
            # This is the normal way the loop finishes when __next__ raises StopIteration
            pass
        except Exception as e:
            # Catch unexpected exceptions during the consumption loop in run()
            error_msg = f"\nAn unexpected error occurred during benchmark run execution: {type(e).__name__}: {e}"
            print(error_msg, file=sys.stderr)
            sys.stderr.flush()
            self._errors.append(error_msg)  # Also record the error internally

        # __next__ handles joining processes and setting _total_run_duration when the last sentinel is received

        print(f"[MainProcess] Benchmark run finished in {self._total_run_duration:.3f} seconds.")
        sys.stdout.flush()

        # Final error summary if any errors were collected internally
        if self._errors:
            print("\n--- Errors Occurred During Run ---")
            sys.stdout.flush()
            for error in self._errors:
                print(error)
                sys.stdout.flush()
            print("-----------------------\n")
            sys.stdout.flush()

        # Final warnings based on collected results vs expected
        total_expected_runs = self.number_of_runs_per_process * self.num_processes
        actual_runs_completed = len(self.execution_times)
        if actual_runs_completed != total_expected_runs and not self._errors:
            print(
                f"[MainProcess] Warning: Expected {total_expected_runs} total results, but collected {actual_runs_completed}. Check for suppressed errors or unexpected worker exits.",
                file=sys.stderr)
            sys.stderr.flush()
        elif actual_runs_completed == 0 and not self._errors and total_expected_runs > 0:
            print("[MainProcess] Warning: No results collected and no errors reported, but runs were expected.",
                  file=sys.stderr)
            sys.stderr.flush()

    def get_execution_results(self) -> Dict[str, Any]:
        """
        Calculates and returns summary statistics after the benchmark has run
        (either via run() or by consuming the iterator).
        Must be called after the benchmark execution is complete.

        :raises ValueError: If the benchmark hasn't completed execution or produced no results.
        :return: Dictionary with min, max, average times, run counts, and throughput.
        """
        # Check if iteration/run has finished by looking at the flag or completed workers
        if self._is_running or self._completed_workers_count < self.num_processes:
            raise ValueError("Benchmark execution has not completed yet.")
        if not self.execution_times and not self._errors:
            raise ValueError("Benchmark completed but produced no results or errors.")

        actual_runs = len(self.execution_times)
        min_time = 0.0
        max_time = 0.0
        avg_time = 0.0
        throughput = 0.0

        if actual_runs > 0:
            min_time = min(self.execution_times)
            max_time = max(self.execution_times)
            avg_time = sum(self.execution_times) / actual_runs

            # Use the _total_run_duration measured during the main process consumption
            if self._total_run_duration > 0:
                throughput = actual_runs / self._total_run_duration
            else:
                throughput = 0.0

        # Format results consistently
        min_time_str = format(min_time, '.6f').rstrip('0').rstrip('.') if actual_runs > 0 else "N/A"
        max_time_str = format(max_time, '.6f').rstrip('0').rstrip('.') if actual_runs > 0 else "N/A"
        avg_time_str = format(avg_time, '.6f').rstrip('0').rstrip('.') if actual_runs > 0 else "N/A"
        throughput_str = f"{throughput:.2f}"

        return {
            "runs_per_process": self.number_of_runs_per_process,
            "num_processes": self.num_processes,
            "total_expected_runs": self.number_of_runs_per_process * self.num_processes,
            "actual_runs_completed": actual_runs,
            "total_run_duration_sec": round(self._total_run_duration, 3),
            "min_time_sec": min_time_str,
            "max_time_sec": max_time_str,
            "avg_time_sec": avg_time_str,
            "errors_count": len(self._errors),
            "throughput_runs_per_sec": throughput_str,
        }

    def get_execution_timeseries(self) -> List[Dict[str, str]]:
        """
        Returns the detailed timestamp (sent time) and duration for each successful execution.
        Must be called after the benchmark execution is complete.

        :raises ValueError: If the benchmark hasn't completed execution or produced no successful results.
        :return: List of dictionaries, each containing 'sent_at' (ISO format UTC) and 'duration' (formatted string).
        """
        if self._is_running or self._completed_workers_count < self.num_processes:
            raise ValueError("Benchmark execution has not completed yet.")
        if not self._run_timestamps:
            if self._errors:
                raise ValueError("Benchmark completed with errors and produced no successful results.")
            else:
                raise ValueError("Benchmark completed but produced no successful results.")
        return list(self._run_timestamps)
