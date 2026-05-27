from _common import check_conflict, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("summary")
parser.add_argument("--content", default="")
parser.add_argument("--topic-id", default="general")
args = parser.parse_args()
print(check_conflict(summary=args.summary, content=args.content, topic_id=args.topic_id))