from _common import decision_history, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("sid")
parser.add_argument("--topic-id", default="")
args = parser.parse_args()
print(decision_history(sid=args.sid, topic_id=args.topic_id))