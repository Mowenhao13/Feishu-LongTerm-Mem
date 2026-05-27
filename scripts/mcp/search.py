from _common import search, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("query")
parser.add_argument("--topic", default="")
parser.add_argument("--top-k", type=int, default=10)
args = parser.parse_args()
print(search(query=args.query, topic=args.topic, top_k=args.top_k))