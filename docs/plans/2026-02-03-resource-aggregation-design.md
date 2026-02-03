# Resource Aggregation with Interactive Toggle

## Problem

When a Terraform project has many resources of the same type (e.g., 12 SQS queues, 8 IAM roles), the graph becomes cluttered with too many nodes and connections, making it hard to read.

## Solution

Client-side JavaScript aggregation that groups resources of the same type into a single aggregate node, with interactive controls to toggle aggregation per resource type.

## Design Decisions

- **Client-side JS**: All aggregation logic runs in the browser. Python generates all individual nodes as before, JS groups them visually. No regeneration needed.
- **Threshold**: 3+ resources of the same `service_type` triggers default aggregation.
- **UI Controls**: Chip/tag toggles below the graph.

---

## 1. Python-side Changes (Minimal)

### 1.1 Data Attributes on SVG (renderer.py)

`_render_service()` already has `data-service-id`. Add:
- `data-service-type="sqs"` on each service group element

`_render_connection()` already has `data-source` and `data-target`. Add:
- `data-source-type="sqs"` and `data-target-type="lambda"` on each connection group

### 1.2 Aggregation Config JSON (renderer.py)

Inject a JSON object into the HTML template:

```javascript
const AGGREGATION_CONFIG = {
  threshold: 3,
  groups: {
    "sqs": { count: 12, label: "SQS", iconHtml: "<svg>...</svg>", defaultAggregated: true },
    "iam_role": { count: 8, label: "IAM Role", iconHtml: "<svg>...</svg>", defaultAggregated: true },
    "lambda": { count: 2, label: "Lambda", iconHtml: "<svg>...</svg>", defaultAggregated: false }
  }
};
```

`defaultAggregated = true` only when `count >= threshold`.

### 1.3 Aggregation Metadata (aggregator.py)

Add `get_aggregation_metadata()` method to `ResourceAggregator` that returns per-service-type counts and labels, consumed by the renderer to build `AGGREGATION_CONFIG`.

### No changes to:
- `parser.py`, `layout.py`, `icons.py`, `main.py`, config YAML files

---

## 2. Aggregate Node (JS)

When JS aggregates a group (e.g., SQS with 12 resources):

1. **Hide** all individual nodes of that group (`display: none`)
2. **Create a synthetic node** positioned at the centroid of hidden nodes:
   - Same AWS icon as the resource type
   - **Count badge** top-right (orange circle with number)
   - Label: "SQS (12)"
   - Dashed border to distinguish from individual nodes
3. **Redirect connections**: all connections to/from hidden nodes point to the aggregate node
4. **De-duplicate connections**: if multiple nodes in the group connect to the same external node, show one connection with multiplicity indicator ("x3") and thicker stroke
5. Aggregate node is **draggable** like any other node

### Click on Aggregate Node (Popover)

- Shows dropdown list of contained resources (icon + name per row)
- Click on a resource row: highlights only that resource's connections (others go semi-transparent)
- Click outside: closes popover

---

## 3. Chip Toggle Panel

Below the SVG, in the existing toolbar area:

```
Aggregation: [SQS (12) check] [IAM Role (8) check] [SNS (5) check] ...
```

- **Active chip** (aggregated): solid colored background (category color), white text, check icon
- **Inactive chip** (de-aggregated): transparent background, colored border, dark text
- Click toggles aggregation for that type
- Only types with count >= threshold appear
- Ordered by count descending

### Animations

- **De-aggregate**: fade-out aggregate node, fade-in individual nodes at original Python-calculated positions, redistribute connections (~300ms CSS transition)
- **Re-aggregate**: reverse animation

---

## 4. Connection Management (JS)

- Maintain a **map of original connections** read from SVG path elements and their data attributes
- When aggregating:
  - Connections where source/target is in the group get re-routed to aggregate node
  - Connections internal to the group are hidden
  - Duplicate connections to same external node are merged (show multiplicity)
- Connection paths recalculated using existing quadratic curve logic
- Thicker stroke for multiplied connections (1.5px base -> 2.5px for x3, 3.5px for x5+)

### Popover Resource Selection

- All aggregate connections go to `opacity: 0.15`
- Selected resource's original connections shown from aggregate node position to real targets
- Allows inspecting individual connections without de-aggregating

---

## 5. Persistence

Aggregation state (which groups are aggregated/de-aggregated) saved to `localStorage` alongside existing layout positions. Restored on page reload.
