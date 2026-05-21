from src.llm.client import LLMClient
from src.eval.evaluator import run_extraction_eval
client = LLMClient()

# scenarios choices:
# 01-technical-selection
# 02-task-assignment
# 03-parameter-lock
# 04-implicit-consensus
# 05-conflict-decisions
# 06-rejection-override
# 07-pure-discussion
# 08-status-update
# 09-suggestion-only
# 10-small-talk
# 11-mixed-scenario
# 12-boundary-case

report = run_extraction_eval(client, enable_storage=True)
print(report.to_dict())