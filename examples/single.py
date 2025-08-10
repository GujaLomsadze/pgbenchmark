from pgbenchmark import BenchmarkConfig, ConnectionManager, SingleThreadBenchmark

# 1. Setup database connection parameters
connection_params = {
    "host": "localhost",
    "port": "5432",
    "dbname": "postgres",
    "user": "postgres",
    "password": "asdASD123",
}

config = BenchmarkConfig(
    number_of_runs=100,  # Run the query 100 times
    warmup_runs=10,  # Do 10 warmup runs first
    timeout=5.0,  # 5 second timeout per query
    collect_explain=True,  # Don't collect EXPLAIN plans (faster)
    retry_on_error=1,  # Retry once on error
)

# 3. Create connection manager and benchmark
conn_manager = ConnectionManager(connection_params)
benchmark = SingleThreadBenchmark(conn_manager, config)

# 4. Set the SQL query to benchmark
benchmark.set_sql("SELECT COUNT(*) FROM pg_tables")

# 5. Run the benchmark
print("Starting benchmark...")
result = benchmark.run()

print(result.get_summary())
exit()
# 6. Display results
print("\n=== Benchmark Results ===")
print(f"Total runs: {result.total_runs}")
print(f"Successful: {result.successful_runs}")
print(f"Failed: {result.failed_runs}")
print(f"\n=== Performance Metrics ===")
print(f"Min time: {result.min_time_ms:.2f} ms")
print(f"Max time: {result.max_time_ms:.2f} ms")
print(f"Average: {result.avg_time_ms:.2f} ms")
print(f"Median: {result.median_time_ms:.2f} ms")
print(f"Std Dev: {result.stddev_time_ms:.2f} ms")

print(f"Explain Plans: {result.expl}")

print(f"\n=== Throughput ===")
print(f"Queries/second: {result.throughput_qps:.2f}")

# 7. Cleanup
conn_manager.close()
print("\nBenchmark complete!")
