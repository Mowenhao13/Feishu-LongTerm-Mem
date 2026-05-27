from _common import git_blame, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("sid")
parser.add_argument("--topic-id", default="")
args = parser.parse_args()
print(git_blame(sid=args.sid, topic_id=args.topic_id))