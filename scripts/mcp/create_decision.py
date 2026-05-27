from _common import create_decision, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("summary")
parser.add_argument("--content", default="")
parser.add_argument("--topic-id", default="general")
parser.add_argument("--impact-level", default="minor")
parser.add_argument("--tags", default="")
args = parser.parse_args()
print(create_decision(summary=args.summary, content=args.content, topic_id=args.topic_id, impact_level=args.impact_level, tags=args.tags))