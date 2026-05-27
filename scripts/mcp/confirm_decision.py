from _common import confirm_decision, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("sid")
args = parser.parse_args()
print(confirm_decision(sid=args.sid))