from _common import decision_card, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("sid")
args = parser.parse_args()
print(decision_card(sid=args.sid))