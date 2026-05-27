from _common import update_decision, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("sid")
parser.add_argument("--summary", default="")
parser.add_argument("--content", default="")
parser.add_argument("--status", default="")
parser.add_argument("--impact-level", default="")
args = parser.parse_args()
print(update_decision(sid=args.sid, summary=args.summary, content=args.content, status=args.status, impact_level=args.impact_level))