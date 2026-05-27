from _common import reject_decision, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("sid")
parser.add_argument("--reason", default="")
args = parser.parse_args()
print(reject_decision(sid=args.sid, reason=args.reason))