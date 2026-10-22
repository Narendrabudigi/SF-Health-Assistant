# Custom notebooks

Put the notebooks for the company's own standards here, as `.py` files that run on their own (`python notebook.py`).
`sf-pipeline` runs them when the custom standards file has values (see the README of the project).

- Start the file name with the module: `EC Notebook1.py`, `RCM_time_to_hire.py`. Its module is then skipped when the file has no value
  for that module.
- Read the standards from the file named by `CUSTOM_STANDARDS_FILE_PATH` in the bucket, and write the insights to
  `ML_Notebook_Custom_Insights`.
- Skip a metric whose benchmark cell is empty (write no row for it) instead of failing: a failing notebook stops the LLM step.
- The environment variable `PIPELINE_STANDARDS` is `custom` here and `industry` for the other notebooks.