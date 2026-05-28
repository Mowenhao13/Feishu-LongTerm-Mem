from _common import decision_children, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("sid")
args = parser.parse_args()
print(decision_children(sid=args.sid))