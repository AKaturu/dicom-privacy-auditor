"""Synthetic benchmark generation, execution, and evaluation."""

from .manifest import BenchmarkManifest, CaseRecord, Injection
from .synthetic import STRATA, generate_benchmark

__all__ = ["BenchmarkManifest", "CaseRecord", "Injection", "STRATA", "generate_benchmark"]
