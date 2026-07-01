import json
from pathlib import Path


def inspect_manifest(manifest_path: Path):
    if not manifest_path.exists():
        print(f"Manifest not found at {manifest_path}")
        return
    with open(manifest_path) as f:
        data = json.load(f)

    print(f"Schema version: {data.get('metadata', {}).get('dbt_schema_version')}")

    sources = data.get("sources", {})
    print(f"\n--- Sources ({len(sources)}) ---")
    for _src_id, src in sources.items():
        name = f"{src['source_name']}.{src['name']}"
        desc = src.get("description", "No description")
        ext_loc = src.get("meta", {}).get("external_location", "N/A")
        columns = list(src.get("columns", {}).keys())
        print(f"Source: {name} | Cols: {len(columns)} | Ext: {ext_loc}")
        print(f"  Desc: {desc}")

    models = data.get("nodes", {})
    print("\n--- Models ---")
    for _node_id, node in models.items():
        if node.get("resource_type") == "model":
            name = node.get("name")
            config_mat = node.get("config", {}).get("materialized")
            desc = node.get("description", "No description")
            columns = list(node.get("columns", {}).keys())
            print(f"Model: {name} ({config_mat}) | Cols: {len(columns)}")
            print(f"  Desc: {desc}")


if __name__ == "__main__":
    manifest = (
        Path(__file__).resolve().parents[3] / "dbt" / "data_platform" / "target" / "manifest.json"
    )
    inspect_manifest(manifest)
