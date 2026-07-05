"""
sources
=======
One module per external data source. Every function here does exactly one
thing: call an API and return plain dicts/lists. No CSV logic, no CLI
logic, no cross-source orchestration lives in this package - that belongs
in `drug_pipeline/modules`.
"""
