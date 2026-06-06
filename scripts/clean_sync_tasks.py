"""清理旧任务并重新同步到飞书任务清单"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.view.task_syncer import TaskViewSyncer

syncer = TaskViewSyncer()

# 1. 获取当前 tasklist GUID
tasklist_guid = None
try:
    tasklist_guid = syncer._ensure_tasklist()
    print(f"Found tasklist: {tasklist_guid}")
except Exception as e:
    print(f"Failed to get tasklist: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 2. 获取 tasklist 内的所有任务（使用正确的端点）
print("Listing all tasks in tasklist...")
all_tasks = []
page_token = ""
while True:
    path = f"/task/v2/tasklists/{tasklist_guid}/tasks"
    params = {"page_size": "50"}
    if page_token:
        params["page_token"] = page_token
    result = syncer._api_request("GET", path, params=params)
    if not result:
        print("  No result from API, breaking")
        break
    items = result.get("data", {}).get("items", [])
    all_tasks.extend(items)
    print(f"  Got {len(items)} items, total so far: {len(all_tasks)}")
    if not result.get("data", {}).get("has_more"):
        break
    page_token = result.get("data", {}).get("page_token", "")

print(f"Found {len(all_tasks)} tasks to delete")

# 3. 删除所有任务
deleted = 0
for task in all_tasks:
    guid = task.get("guid") or task.get("id")
    if guid:
        syncer._api_request("DELETE", f"/task/v2/tasks/{guid}")
        deleted += 1
        if deleted % 10 == 0:
            print(f"  Deleted {deleted}/{len(all_tasks)} tasks")

print(f"Deleted {deleted} tasks")

# 4. 清除 meta 中的 synced_tasks
syncer._synced_tasks.clear()
syncer._meta["synced_tasks"] = {}
syncer._save_meta()
print("Cleared local meta")

# 5. 直接从 MemoryGraph + GitStorage 加载决策
print("\nLoading decisions from local storage...")
try:
    from src.graph.memory_graph import MemoryGraph
    from src.storage.git_storage import GitStorage, GitStorageConfig
    from src.config import get_storage_path
    work_dir = get_storage_path()
    storage = GitStorage(config=GitStorageConfig(work_dir=work_dir))
    graph = MemoryGraph()
    graph.load_from_git(storage, "feishu-mem")
    decisions = graph.get_all_decisions()
    print(f"Loaded {len(decisions)} decisions")
except Exception as e:
    print(f"Failed to load decisions: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 6. 重新同步
print("\nStarting full sync...")
stats = syncer.full_sync(decisions)
print(f"Sync complete: created={stats['created']}, updated={stats['updated']}, deleted={stats['deleted']}")
