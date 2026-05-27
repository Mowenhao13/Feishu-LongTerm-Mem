from _common import evaluate_dedup, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("sid_a")
parser.add_argument("sid_b")
args = parser.parse_args()
print(evaluate_dedup(sid_a=args.sid_a, sid_b=args.sid_b))