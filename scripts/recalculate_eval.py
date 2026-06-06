
"""重新计算评估指标，使用过滤后的 expected.jsonl"""
import json
from pathlib import Path

from src.eval.comparator import EvalComparator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPECTED_PATH = PROJECT_ROOT / "eval_dataset/argusbot_multi_v2/expected.jsonl"
DECISIONS_PATH = PROJECT_ROOT / "eval_dataset/argusbot_multi_v2/decisions.jsonl"

# 1. 读取 actual decisions
print("Loading actual decisions...")
actual = []
with open(DECISIONS_PATH, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            d = json.loads(line)
            actual.append({
                "sid": d.get("sid", ""),
                "topic_id": d.get("topic_id", ""),
                "summary": d.get("summary", ""),
                "status": d.get("status", ""),
                "impact": d.get("impact", ""),
                "chat_id": d.get("chat_id", ""),
                "is_suggestion": d.get("is_suggestion", False),
            })
print(f"Loaded {len(actual)} actual decisions")

# 2. 运行 comparator
print("\nRunning comparison...")
comparator = EvalComparator(str(EXPECTED_PATH), embedding_provider=None)
comparator.match(actual)
report = comparator.to_dict()

# 3. 打印结果
print()
print("=" * 62)
print("  重新计算后的精度评估报告")
print("=" * 62)
print(f"  预期:          {report['total_expected']}")
print(f"  实际检测:      {report['total_detected']}")
print(f"  TP:            {report['true_positives']}")
print(f"  FP:            {report['false_positives']}")
print(f"  FN:            {report['false_negatives']}")
p, r, f = report["precision"], report["recall"], report["f1"]
print(f"\n  Precision:  {p:.1%}   Recall:  {r:.1%}   F1:  {f:.1%}")

# 决策/建议分类统计
dm = report.get("decision_metrics", {})
if dm:
    print(f"\n  决策与建议分类")
    print(f"    决策:  TP={dm.get('decision_tp', 0)}  FN={dm.get('decision_fn', 0)}  Recall={dm.get('decision_recall', 0):.1%}")
    print(f"    建议:  TP={dm.get('suggestion_tp', 0)}  FN={dm.get('suggestion_fn', 0)}  Recall={dm.get('suggestion_recall', 0):.1%}")

if report.get("by_topic"):
    print(f"\n  按话题:")
    for t, v in report["by_topic"].items():
        print(f"    {t:&lt;12}  P={v['precision']:.1%}  R={v['recall']:.1%}  F1={v['f1']:.1%}")

if report.get("by_chat"):
    iso = report["by_chat"].get("_isolation", {})
    if iso:
        print(f"\n  跨群隔离:  score={iso.get('score', 1.0):.1%}  issues={iso.get('issues', 0)}")

print("\n" + "=" * 62)

# 4. 保存报告
report_path = PROJECT_ROOT / "eval_results/eval_v2_recalculated.json"
with open(report_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print(f"\n报告已保存到: {report_path}")

