"""Batch evaluation framework for the Build & Ship Pipeline.

Quick-start
-----------
1. Define test cases in eval/cases/sample_cases.yaml (or your own YAML).
2. Run a batch against a live server::

       python -m eval.runner --cases eval/cases/sample_cases.yaml \\
           --url http://localhost:8000 --token $TOKEN --out results_v1.json

3. After a code change, run again::

       python -m eval.runner --cases eval/cases/sample_cases.yaml \\
           --url http://localhost:8000 --token $TOKEN --out results_v2.json

4. Compare::

       python -m eval.compare results_v1.json results_v2.json

5. Generate a human-readable report::

       python -m eval.report results_v2.json --format html --out report.html
"""
