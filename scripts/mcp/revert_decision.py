from _common import revert_decision, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("sid")
parser.add_argument("commit_hash")
parser.add_argument("--topic-id", default="")
args = parser.parse_args()
print(revert_decision(sid=args.sid, commit_hash=args.commit_hash, topic_id=args.topic_id))