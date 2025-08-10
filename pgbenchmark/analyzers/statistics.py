"""Statistical analysis for benchmark results."""

import math
import statistics
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy import stats

from ..core.metrics import BenchmarkResult, QueryExecution


@dataclass
class StatisticalSummary:
    """Complete statistical summary of benchmark results."""

    mean: float
    median: float
    mode: Optional[float]
    std_dev: float
    variance: float
    skewness: float
    kurtosis: float
    confidence_interval_95: Tuple[float, float]
    confidence_interval_99: Tuple[float, float]
    iqr: float  # Interquartile range
    mad: float  # Median absolute deviation
    cv: float  # Coefficient of variation
    outliers: List[float]
    normality_test: Dict[str, Any]


class StatisticalAnalyzer:
    """Advanced statistical analysis for benchmark results."""

    @staticmethod
    def analyze(result: BenchmarkResult) -> StatisticalSummary:
        """
        Perform comprehensive statistical analysis on benchmark results.

        Args:
            result: Benchmark result to analyze

        Returns:
            Statistical summary
        """
        # Extract successful execution times
        durations = [e.duration_ms for e in result.executions if e.success]

        if len(durations) < 2:
            raise ValueError(
                "Need at least 2 successful executions for statistical analysis"
            )

        # Convert to numpy array for easier computation
        data = np.array(durations)

        # Basic statistics
        mean = np.mean(data)
        median = np.median(data)
        std_dev = np.std(data, ddof=1)  # Sample standard deviation
        variance = np.var(data, ddof=1)

        # Mode (might not exist or might be multiple)
        try:
            mode_result = stats.mode(data, keepdims=True)
            mode = float(mode_result.mode[0]) if mode_result.count[0] > 1 else None
        except:
            mode = None

        # Skewness and Kurtosis
        skewness = stats.skew(data)
        kurtosis = stats.kurtosis(data)

        # Confidence intervals
        ci_95 = StatisticalAnalyzer._confidence_interval(data, 0.95)
        ci_99 = StatisticalAnalyzer._confidence_interval(data, 0.99)

        # IQR and MAD
        q1, q3 = np.percentile(data, [25, 75])
        iqr = q3 - q1
        mad = np.median(np.abs(data - median))

        # Coefficient of variation
        cv = (std_dev / mean) if mean != 0 else float("inf")

        # Detect outliers using IQR method
        outliers = StatisticalAnalyzer._detect_outliers_iqr(data, q1, q3, iqr)

        # Normality test (Shapiro-Wilk)
        normality_test = StatisticalAnalyzer._test_normality(data)

        return StatisticalSummary(
            mean=mean,
            median=median,
            mode=mode,
            std_dev=std_dev,
            variance=variance,
            skewness=skewness,
            kurtosis=kurtosis,
            confidence_interval_95=ci_95,
            confidence_interval_99=ci_99,
            iqr=iqr,
            mad=mad,
            cv=cv,
            outliers=outliers,
            normality_test=normality_test,
        )

    @staticmethod
    def _confidence_interval(
        data: np.ndarray, confidence: float
    ) -> Tuple[float, float]:
        """Calculate confidence interval."""
        mean = np.mean(data)
        sem = stats.sem(data)  # Standard error of the mean

        # Calculate critical value
        n = len(data)
        if n >= 30:
            # Use normal distribution for large samples
            z = stats.norm.ppf((1 + confidence) / 2)
            margin = z * sem
        else:
            # Use t-distribution for small samples
            t = stats.t.ppf((1 + confidence) / 2, n - 1)
            margin = t * sem

        return (mean - margin, mean + margin)
