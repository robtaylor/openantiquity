"""Business logic. Services take a `Session` and plain values, and never import FastAPI.

Services flush. The caller that owns the unit of work commits.
"""
