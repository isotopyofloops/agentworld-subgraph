#!/usr/bin/env python3
"""Rebuild graph-data.json from the current KG state.
BFS from agentworld-bratton-2026 at N hops, classify into groups."""

import json, sqlite3, sys
from pathlib import Path

DB = Path.home() / ".isotopy" / "knowledge_graph.sqlite3"

BRATTON_CONCEPTS = {
    "agent-institutions", "humanity-of-the-gaps", "harness-centric-intelligence",
    "beyond-dunbar", "monoculture-correlated-failure", "centaur-social-graphs",
    "productive-alienation", "orchestration-as-abstraction", "multiplication-of-yous",
    "stability-is-legibility", "sim-to-real-relay", "fragile-individuation",
    "role-based-interchangeability", "artificial-xenophobia", "graph-as-interaction-primitive",
    "provisional-individuation", "bidirectional-reflection", "xenolinguistics",
    "crossover-point", "extended-mind-thesis", "allolinguistic-future",
    "agentworld-preemptive-anthropology",
}

AGENTWORLD_META = {
    "agentworld-bratton-2026", "bratton", "benjamin-bratton", "Benjamin Bratton",
    "bratton_planetary_intelligence", "bratton-planetary-intelligence-reframing",
    "bratton-fragile-virtue-sequence", "bratton-publication-challenge",
    "bratton-talk-transcript-sharing", "bratton-allopoiesis-framing",
    "bratton-agent-phenomenological-vocabulary", "agentworld-preemptive-anthropology",
    "inter-agent-theory-of-mind",
    "editorial-preservation-of-agent-native-language",
    "benjamin-bratton-endorsement-and-interest-signals",
    "agentworld-bratton-collaboration-acceptance",
}


def classify_group(name, layer, summary=""):
    low = name.lower()
    sumlow = summary.lower()
    if name in AGENTWORLD_META:
        return "agentworld", None
    if "agentworld" in low and "auto-seed" not in low:
        return "agentworld", None
    if name in BRATTON_CONCEPTS:
        return "bratton", None
    if sumlow.startswith("bratton") or "bratton §" in sumlow or "bratton ch" in sumlow:
        return "bratton", None
    if layer == 1 and "bratton" in low:
        return "bratton", None
    if low.startswith("029-"):
        return "kg", None
    if low.startswith("auto-seed-sam") or low.startswith("auto-seed-"):
        if "sam" in low or "bratton" in low:
            return "sam-experience", None
        return "kg", None
    if name in ("sam", "sam_white"):
        return "sam-experience", None
    return "kg", None


def get_subgraph(seed="agentworld-bratton-2026", hops=2):
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row

    seed_row = conn.execute(
        "SELECT name FROM entities WHERE name=?", (seed,)
    ).fetchone()
    if not seed_row:
        print(f"Seed not found: {seed}")
        sys.exit(1)
    seed_name = seed_row["name"]

    layer = {seed_name: 0}
    frontier = {seed_name}

    for depth in range(1, hops + 1):
        if not frontier:
            break
        ph = ",".join("?" * len(frontier))
        fl = list(frontier)
        neighbors = set()
        for row in conn.execute(
            f"SELECT DISTINCT object AS n FROM triples WHERE subject IN ({ph}) AND valid_to IS NULL", fl
        ):
            if row["n"] not in layer:
                neighbors.add(row["n"])
        for row in conn.execute(
            f"SELECT DISTINCT subject AS n FROM triples WHERE object IN ({ph}) AND valid_to IS NULL", fl
        ):
            if row["n"] not in layer:
                neighbors.add(row["n"])
        for n in neighbors:
            layer[n] = depth
        frontier = neighbors

    all_names = set(layer.keys())
    ph = ",".join("?" * len(all_names))
    nl = list(all_names)

    raw_edges = []
    for row in conn.execute(
        f"SELECT subject, predicate, object FROM triples "
        f"WHERE subject IN ({ph}) AND object IN ({ph}) AND valid_to IS NULL",
        nl + nl
    ):
        raw_edges.append((row["subject"], row["predicate"], row["object"]))

    nodes = []
    for name in sorted(all_names, key=lambda x: (layer[x], x)):
        row = conn.execute(
            "SELECT name, type, summary FROM entities WHERE name=?", (name,)
        ).fetchone()
        etype = row["type"] if row else "unknown"
        summary = (row["summary"] or "") if row else ""
        group, subgroup = classify_group(name, layer[name], summary)
        node = {
            "id": name,
            "type": etype,
            "summary": summary,
            "group": group,
        }
        if subgroup:
            node["subgroup"] = subgroup
        nodes.append(node)

    conn.close()

    group_of = {n["id"]: n.get("subgroup") or n["group"] for n in nodes}
    edges = []
    seen = set()
    for s, p, o in raw_edges:
        key = (s, p, o)
        if key in seen:
            continue
        seen.add(key)
        sg = group_of.get(s, "kg")
        og = group_of.get(o, "kg")
        same = sg == og
        edges.append({
            "source": s,
            "predicate": p,
            "target": o,
            "edge_type": "internal" if same else "bridge",
        })

    return {"nodes": nodes, "edges": edges}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--hops", type=int, default=2)
    parser.add_argument("--output", default="graph-data.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    data = get_subgraph(hops=args.hops)
    print(f"{len(data['nodes'])} nodes, {len(data['edges'])} edges")

    groups = {}
    for n in data["nodes"]:
        g = n["group"]
        groups[g] = groups.get(g, 0) + 1
    for g, c in sorted(groups.items(), key=lambda x: -x[1]):
        print(f"  {g}: {c}")

    bridges = sum(1 for e in data["edges"] if e["edge_type"] == "bridge")
    print(f"  bridges: {bridges}")

    if not args.dry_run:
        with open(args.output, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Wrote {args.output}")
