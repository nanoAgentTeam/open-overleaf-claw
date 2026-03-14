"""
一次性脚本：将所有本地 workspace 链接并同步到 Overleaf。

逻辑：
1. 列出 Overleaf 上已有的 project（按名字建立 map）
2. 遍历 workspace/ 下所有 E2E 项目：
   - 已在 Overleaf → 直接 LINK（补写 project_id + 真实 root_folder_id）
   - 不在 Overleaf → CREATE 新 project
3. 写入正确的 .overleaf.json（files 置空，确保全量上传）
4. Sync 上传所有本地文件
"""

import json
import re
import sys
from pathlib import Path

# 确保项目路径在 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent.tools.overleaf import OverleafTool

WORKSPACE_ROOT = PROJECT_ROOT / "workspace"
SKIP_DIRS = {"test_debug", ".bot_data"}


def main():
    # 用任意一个现有 workspace 初始化 tool（只用于鉴权）
    tool = OverleafTool(workspace=WORKSPACE_ROOT / "E2E_Test_W01")
    api = tool._get_api()
    if not api:
        print("[ERROR] No Overleaf auth cookie found.")
        return

    # 列出 Overleaf 现有 projects
    projects = api.get_projects()
    overleaf_map = {p.name: p.id for p in projects}
    print(f"Overleaf 现有 projects: {len(overleaf_map)} 个")
    print()

    results = []

    for ws_dir in sorted(WORKSPACE_ROOT.iterdir()):
        if not ws_dir.is_dir() or ws_dir.name in SKIP_DIRS:
            continue

        name = ws_dir.name
        core_dir = ws_dir / name
        if not core_dir.is_dir():
            print(f"  SKIP {name}: core dir not found")
            continue

        overleaf_json = core_dir / ".overleaf.json"

        # 如果已有 project_id，跳过
        if overleaf_json.exists():
            try:
                meta = json.loads(overleaf_json.read_text())
                if meta.get("project_id"):
                    print(f"  SKIP {name}: already linked to {meta['project_id']}")
                    continue
            except Exception:
                pass

        # 找到或创建 Overleaf project
        if name in overleaf_map:
            project_id = overleaf_map[name]
            action = "LINK"
        else:
            print(f"  CREATE {name}: creating new Overleaf project...")
            result = tool.execute(action="create_project", project_name=name)
            match = re.search(r"ID: ([a-f0-9]+)", result)
            if not match:
                print(f"  ERROR {name}: create failed — {result}")
                results.append(("ERROR", name, result))
                continue
            project_id = match.group(1)
            action = "CREATE"

        print(f"  {action} {name} → project_id={project_id}")

        # 获取真实 root_folder_id
        try:
            root_folder = api.project_get_files(project_id)
            root_folder_id = root_folder.id
        except Exception as e:
            print(f"  ERROR {name}: could not get root_folder_id — {e}")
            results.append(("ERROR", name, str(e)))
            continue

        # 写入 .overleaf.json（files 置空，让 sync 全量上传）
        meta = {
            "project_id": project_id,
            "project_name": name,
            "root_folder_id": root_folder_id,
            "files": {},
        }
        overleaf_json.write_text(json.dumps(meta, indent=2))

        # Sync 上传所有本地文件
        try:
            sync_result = tool._sync_project_by_folder(api, core_dir, is_absolute=True)
            last_line = sync_result.strip().splitlines()[-1]
            print(f"    → {last_line}")
            results.append((action, name, last_line))
        except Exception as e:
            print(f"  ERROR {name}: sync failed — {e}")
            results.append(("ERROR", name, str(e)))

    print()
    print("=" * 60)
    print("汇总：")
    for action, name, msg in results:
        print(f"  [{action:6s}] {name}: {msg}")


if __name__ == "__main__":
    main()
