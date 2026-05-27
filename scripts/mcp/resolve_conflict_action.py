from _common import resolve_conflict_action, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("sid_a")
parser.add_argument("sid_b")
args = parser.parse_args()
print(resolve_conflict_action(sid_a=args.sid_a, sid_b=args.sid_b))