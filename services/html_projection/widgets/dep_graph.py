"""Lemon-UI dependency graph widget.

Data contract:
  nodes: list[dict], required. Each item has id: str, label: str, and
    tone: str | None. Duplicate ids keep the first occurrence.
  edges: list[dict] | None, optional. Each item has from: str and to: str.
  direction: str | None, optional "down" or "right"; default "down".
  title: str | None, optional heading.

Degenerate-case policy:
  Empty/missing nodes render "no nodes". Missing node ids render a visible
  placeholder id derived from list index. Edges to unknown ids are dropped.
  At most 24 nodes and 36 valid edges render; extra entries are summarized
  with a visible "+N more" marker. Ranks are deterministic: Kahn traversal
  starts in node list order, ties stay in list order, and cycles fall into
  the next visible rank in list order. Layout numbers are deliberate SVG
  readability choices; colors and surface geometry come from LEMON_*.
"""

from __future__ import annotations

from services.html_projection import tokens
from services.html_projection.escape import escape_text

MAX_NODES = 24
MAX_EDGES = 36


def _tone_color(tone: object, root: bool) -> str:
    if tone == "accent":
        return tokens.LEMON_ACCENT
    if tone == "success":
        return tokens.LEMON_SUCCESS
    if tone == "warning":
        return tokens.LEMON_WARNING
    if tone == "danger":
        return tokens.LEMON_DANGER
    if tone == "info":
        return tokens.LEMON_INFO
    if tone == "neutral":
        return tokens.LEMON_NEUTRALS[1]
    return tokens.LEMON_ACCENT if root else tokens.LEMON_PRIMARY


def _fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def render(data: dict) -> str:
    raw_nodes = data.get("nodes")
    node_items = raw_nodes if isinstance(raw_nodes, list) else []
    all_nodes: list[dict[str, object]] = []
    seen: list[str] = []
    for index, item in enumerate(node_items):
        if isinstance(item, dict):
            node_id = str(item.get("id") if item.get("id") is not None else f"node-{index + 1}")
            label = str(item.get("label") if item.get("label") is not None else node_id)
            tone = item.get("tone")
        else:
            node_id = f"node-{index + 1}"
            label = "—"
            tone = None
        if node_id in seen:
            continue
        seen.append(node_id)
        all_nodes.append({"id": node_id, "label": label, "tone": tone})
    # Cap for legible layout; hidden_nodes is the ACCURATE count of valid,
    # unique nodes omitted — never the raw input length (duplicates and
    # non-dict entries that never became nodes must not inflate "+N more").
    hidden_nodes = max(0, len(all_nodes) - MAX_NODES)
    nodes: list[dict[str, object]] = [
        {**node, "index": i} for i, node in enumerate(all_nodes[:MAX_NODES])
    ]
    title = data.get("title")
    heading = (
        f'<div style="font-weight:800;margin-bottom:{tokens.LEMON_SPACING[3]};">{escape_text(str(title))}</div>'
        if title is not None
        else ""
    )
    if not nodes:
        return (
            f'<div class="lemon lemon-card" style="border:{tokens.LEMON_BORDER};'
            f'border-radius:{tokens.LEMON_RADIUS};box-shadow:{tokens.LEMON_SHADOW};'
            f'background:{tokens.LEMON_SURFACE};padding:{tokens.LEMON_SPACING[4]};'
            f'color:{tokens.LEMON_NEUTRALS[3]};">{heading}no nodes</div>'
        )
    ids = [str(node["id"]) for node in nodes]
    raw_edges = data.get("edges")
    edge_items = raw_edges if isinstance(raw_edges, list) else []
    edges: list[tuple[str, str]] = []
    for item in edge_items:
        if not isinstance(item, dict):
            continue
        src = item.get("from")
        dst = item.get("to")
        if src is None or dst is None:
            continue
        src_s = str(src)
        dst_s = str(dst)
        # Edges to/from unknown or hidden node ids are dropped deterministically
        # (the referenced node isn't rendered); the node cap is the "+N more"
        # signal — edge drops are implied by it, not double-counted.
        if src_s in ids and dst_s in ids and len(edges) < MAX_EDGES:
            edges.append((src_s, dst_s))
    incoming: dict[str, int] = {node_id: 0 for node_id in ids}
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in ids}
    rank: dict[str, int] = {node_id: 0 for node_id in ids}
    for src, dst in edges:
        incoming[dst] += 1
        outgoing[src].append(dst)
    ready = [node_id for node_id in ids if incoming[node_id] == 0]
    processed: list[str] = []
    while ready:
        node_id = ready.pop(0)
        processed.append(node_id)
        for dst in outgoing[node_id]:
            rank[dst] = max(rank[dst], rank[node_id] + 1)
            incoming[dst] -= 1
            if incoming[dst] == 0:
                ready.append(dst)
    for node_id in ids:
        if node_id not in processed:
            rank[node_id] = max(rank.values(), default=0) + 1
    direction = "right" if data.get("direction") == "right" else "down"
    box_w = 126
    box_h = 46
    gap_x = 38
    gap_y = 34
    ranks = sorted({rank[node_id] for node_id in ids})
    positions: dict[str, tuple[float, float]] = {}
    for r_index, r_value in enumerate(ranks):
        rank_ids = [node_id for node_id in ids if rank[node_id] == r_value]
        for offset, node_id in enumerate(rank_ids):
            if direction == "right":
                x = 16 + r_index * (box_w + gap_x)
                y = 16 + offset * (box_h + gap_y)
            else:
                x = 16 + offset * (box_w + gap_x)
                y = 16 + r_index * (box_h + gap_y)
            positions[node_id] = (x, y)
    width = int(max((x + box_w + 20 for x, _ in positions.values()), default=180))
    height = int(max((y + box_h + 28 for _, y in positions.values()), default=100))
    marker_extra = hidden_nodes
    if marker_extra:
        height += 24
    edge_svg: list[str] = [
        f'<defs><marker id="lemon-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" '
        f'markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" '
        f'fill="{tokens.LEMON_INK}" /></marker></defs>'
    ]
    for src, dst in edges:
        x1, y1 = positions[src]
        x2, y2 = positions[dst]
        if direction == "right":
            start = (x1 + box_w, y1 + box_h / 2)
            end = (x2, y2 + box_h / 2)
        else:
            start = (x1 + box_w / 2, y1 + box_h)
            end = (x2 + box_w / 2, y2)
        edge_svg.append(
            f'<line x1="{_fmt(start[0])}" y1="{_fmt(start[1])}" x2="{_fmt(end[0])}" y2="{_fmt(end[1])}" '
            f'stroke="{tokens.LEMON_INK}" stroke-width="2" marker-end="url(#lemon-arrow)" />'
        )
    node_svg: list[str] = []
    for node in nodes:
        node_id = str(node["id"])
        x, y = positions[node_id]
        is_root = not any(dst == node_id for _, dst in edges)
        fill = _tone_color(node.get("tone"), is_root)
        label = str(node["label"])
        if len(label) > 18:
            label = label[:15] + "..."
        node_svg.append(
            f'<g><rect x="{_fmt(x + 4)}" y="{_fmt(y + 4)}" width="{box_w}" height="{box_h}" '
            f'fill="{tokens.LEMON_INK}" />'
            f'<rect x="{_fmt(x)}" y="{_fmt(y)}" width="{box_w}" height="{box_h}" rx="6" '
            f'fill="{fill}" stroke="{tokens.LEMON_INK}" stroke-width="2" />'
            f'<text x="{_fmt(x + box_w / 2)}" y="{_fmt(y + 28)}" text-anchor="middle" '
            f'fill="{tokens.LEMON_INK}" font-size="12" font-weight="800">{escape_text(label)}</text></g>'
        )
    more_svg = (
        f'<text x="16" y="{height - 8}" fill="{tokens.LEMON_NEUTRALS[3]}" font-size="12" '
        f'font-weight="700">+{marker_extra} more</text>'
        if marker_extra
        else ""
    )
    return (
        f'<div class="lemon lemon-card" style="border:{tokens.LEMON_BORDER};'
        f'border-radius:{tokens.LEMON_RADIUS};box-shadow:{tokens.LEMON_SHADOW};'
        f'background:{tokens.LEMON_SURFACE};padding:{tokens.LEMON_SPACING[4]};'
        f'color:{tokens.LEMON_INK};">{heading}'
        f'<svg role="img" viewBox="0 0 {width} {height}" width="100%" height="{height}">'
        f'{"".join(edge_svg)}{"".join(node_svg)}{more_svg}</svg></div>'
    )
