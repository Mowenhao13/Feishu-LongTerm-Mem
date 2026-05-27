from _common import resolve_conflict, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("decision_a")
parser.add_argument("decision_b")
parser.add_argument("resolution")
args = parser.parse_args()
print(resolve_conflict(decision_a=args.decision_a, decision_b=args.decision_b, resolution=args.resolution))