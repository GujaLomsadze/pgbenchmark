# pgbenchmark/visualizer/dashboard.py
import os


def get_dashboard_html():
    html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    with open(html_path, encoding="utf-8") as f:
        return f.read()
