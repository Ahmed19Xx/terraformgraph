# Resource Aggregation - Implementation Plan

Reference: [Design Document](2026-02-03-resource-aggregation-design.md)

---

## Step 1: Add data attributes to SVG elements (Python)

**File:** `terraformgraph/renderer.py`

### 1a. `_render_service()` (~line 378-400)
- Add `data-service-type="{service.service_type}"` to both the icon and fallback `<g>` elements
- The `data-service-id` is already present

### 1b. `_render_connection()` (~line 485-488)
- Add `data-source-type` and `data-target-type` attributes
- These require looking up the service_type for each source/target ID
- Pass a `service_type_map: Dict[str, str]` (service_id -> service_type) to the render method
- Build this map in the parent render method from the services list

### Verification
- Generate a diagram, inspect SVG to confirm new attributes are present on all nodes and connections

---

## Step 2: Add aggregation metadata method (Python)

**File:** `terraformgraph/aggregator.py`

### 2a. Add `get_aggregation_metadata()` to `ResourceAggregator`
- After `aggregate()` method (~line 379)
- Takes `AggregatedResult` as input
- Returns `Dict[str, Dict]` mapping service_type -> { count, label, icon_resource_type }
- Counts services per service_type from result.services
- Label derived from service_type (title case, underscores to spaces)

### Verification
- Unit test: aggregate a sample set of resources, verify metadata counts match

---

## Step 3: Inject AGGREGATION_CONFIG into HTML template (Python)

**File:** `terraformgraph/renderer.py`

### 3a. In `HTMLRenderer.render()` or `generate_html()`
- Call `aggregator.get_aggregation_metadata()` to get the metadata
- For each group, include the icon SVG HTML (from IconMapper) so JS can render aggregate nodes
- Serialize as JSON and inject into template as `<script>const AGGREGATION_CONFIG = {...};</script>`
- Place before the main JS block

### 3b. Pass metadata through the pipeline
- `main.py` or wherever HTMLRenderer is called: pass the aggregation metadata to the renderer
- May need to pass IconMapper instance or pre-render icons for each service_type

### Verification
- Generate HTML, open in browser, check `AGGREGATION_CONFIG` is accessible in console

---

## Step 4: CSS for aggregation UI (Python/HTML template)

**File:** `terraformgraph/renderer.py` (CSS section of HTML_TEMPLATE, ~lines 505-867)

### 4a. Chip styles
```css
.aggregation-panel { ... }        /* Container below diagram */
.aggregation-chip { ... }         /* Individual chip */
.aggregation-chip.active { ... }  /* Aggregated state - filled */
.aggregation-chip.inactive { ... } /* De-aggregated state - outlined */
```

### 4b. Aggregate node styles
```css
.aggregate-node { ... }           /* Synthetic group node */
.aggregate-badge { ... }          /* Count badge top-right */
.aggregate-node .service-border { stroke-dasharray: 4,4; } /* Dashed border */
```

### 4c. Popover styles
```css
.aggregate-popover { ... }        /* Dropdown container */
.aggregate-popover-item { ... }   /* Individual resource row */
.aggregate-popover-item:hover { ... }
.aggregate-popover-item.selected { ... }
```

### 4d. Transition styles
```css
.service.aggregating { transition: opacity 0.3s, transform 0.3s; }
.connection path { transition: d 0.3s, opacity 0.3s; }
```

### Verification
- Visual check: chips render correctly, aggregate nodes have dashed borders

---

## Step 5: Core aggregation JS engine

**File:** `terraformgraph/renderer.py` (JS section of HTML_TEMPLATE, ~lines 990-1530)

### 5a. State management
```javascript
// Aggregation state
const aggregationState = {};     // { serviceType: boolean (true=aggregated) }
const originalConnections = [];  // Snapshot of all connections from DOM
const aggregateNodes = {};       // { serviceType: SVGElement }
```

### 5b. `initAggregation()` - called in DOMContentLoaded
- Read `AGGREGATION_CONFIG`
- Initialize `aggregationState` from config defaults (or localStorage if saved)
- Snapshot all connections into `originalConnections` array
- For each group with `defaultAggregated: true`, call `aggregateGroup(serviceType)`
- Render chip panel

### 5c. `snapshotConnections()`
- Iterate all `.connection` elements
- Store: { element, sourceId, targetId, sourceType, targetType, label, connType }
- This is the source of truth for re-routing connections

### 5d. `aggregateGroup(serviceType)`
- Find all `.service[data-service-type="{serviceType}"]` nodes
- Calculate centroid position
- Hide individual nodes (`display: none`)
- Create aggregate SVG node (clone icon from AGGREGATION_CONFIG.iconHtml)
- Add count badge
- Insert into SVG
- Call `rerouteConnections(serviceType)`
- Register aggregate node for drag-and-drop

### 5e. `deaggregateGroup(serviceType)`
- Remove aggregate SVG node
- Show individual nodes (`display: ""`)
- Restore original connections for this group
- Close popover if open

### Verification
- Generate diagram with 5+ SQS queues
- Verify they aggregate into single node on load
- Verify de-aggregation restores individual nodes

---

## Step 6: Connection re-routing JS

**File:** `terraformgraph/renderer.py` (JS section)

### 6a. `rerouteConnections(serviceType)`
- For each connection in `originalConnections`:
  - If source or target is in the aggregated group:
    - Hide original connection element
    - Create/update aggregate connection from/to aggregate node
  - If both source AND target are in same group: hide entirely
- De-duplicate: group aggregate connections by external endpoint
  - Merge duplicates: show multiplicity label ("x3"), increase stroke-width
- Use existing `updateConnection()` path calculation logic

### 6b. `restoreConnections(serviceType)`
- Remove all aggregate connections for this group
- Show original connections that were hidden

### 6c. `recalculateAggregatePath(sourcePos, targetPos)`
- Reuse existing quadratic curve logic from `updateConnection()`
- Generate SVG path string

### Verification
- Aggregate SQS: verify connections from Lambda->SQS are re-routed to aggregate node
- Verify de-duplication: if 3 connections go to same target, show "x3"
- De-aggregate: verify original connections restore correctly

---

## Step 7: Chip panel UI

**File:** `terraformgraph/renderer.py` (HTML + JS sections)

### 7a. HTML structure
- Add `<div class="aggregation-panel">` after `.diagram-wrapper`
- Label: "Aggregation:"
- Chips rendered dynamically by JS from AGGREGATION_CONFIG

### 7b. `renderChipPanel()`
- Create chips for each group where count >= threshold
- Sort by count descending
- Each chip shows: "{Label} ({count})" + check icon if active
- Color based on category (use existing connection type colors or define per-category)
- Attach click handler to toggle

### 7c. `toggleAggregation(serviceType)`
- Flip `aggregationState[serviceType]`
- Call `aggregateGroup()` or `deaggregateGroup()` accordingly
- Update chip visual state
- Save state to localStorage

### Verification
- Chips appear for all groups with 3+ resources
- Click toggles aggregation visually
- State persists across page reload

---

## Step 8: Popover for aggregate node inspection

**File:** `terraformgraph/renderer.py` (JS + CSS sections)

### 8a. Click handler on aggregate nodes
- On click: show popover positioned below/beside the node
- Popover contains scrollable list of resources in the group

### 8b. `showAggregatePopover(serviceType, position)`
- Create/show popover element
- List all resources: small icon + resource name
- Each item clickable

### 8c. `selectResourceInPopover(resourceId, serviceType)`
- Dim all aggregate connections to `opacity: 0.15`
- Show only the selected resource's original connections
- Draw these connections from the aggregate node position (not original hidden position) to real targets
- Highlight the selected resource row in popover

### 8d. Click outside handler
- Close popover
- Restore all aggregate connections to normal opacity

### Verification
- Click aggregate node: popover appears with correct resource list
- Click resource in popover: only its connections highlighted
- Click outside: popover closes, connections restore

---

## Step 9: Drag-and-drop integration

**File:** `terraformgraph/renderer.py` (JS section)

### 9a. Register aggregate nodes with existing drag system
- Aggregate nodes need `class="service draggable"` attributes
- On drag: update aggregate node position + all re-routed connections
- Use existing `updateConnectionsFor()` logic

### 9b. Update connections on aggregate node drag
- All aggregate connections must update their paths when the node is dragged
- Reuse existing quadratic curve recalculation

### Verification
- Drag aggregate node: connections follow smoothly
- Save/load layout includes aggregate node positions

---

## Step 10: Persistence integration

**File:** `terraformgraph/renderer.py` (JS section)

### 10a. Save aggregation state
- In existing `savePositions()`: also save `aggregationState` to localStorage
- In existing `loadPositions()`: also load `aggregationState` and apply
- In existing `resetPositions()`: reset aggregation to defaults from AGGREGATION_CONFIG

### 10b. Save aggregate node positions
- When user drags an aggregate node, save its position
- On reload, if group is still aggregated, restore aggregate node position

### Verification
- Toggle some aggregations, save, reload: state restored
- Drag aggregate node, save, reload: position restored
- Reset: returns to default aggregation state

---

## Step 11: Testing and edge cases

### Edge cases to handle:
1. **Group with exactly threshold resources** (3): aggregates correctly
2. **Group with 1-2 resources**: no aggregation chip shown
3. **All connections internal** to a group: aggregate node has no visible connections
4. **Multiple aggregated groups connected to each other**: aggregate-to-aggregate connections
5. **VPC resources aggregation**: aggregate node should respect VPC boundary constraints
6. **Empty groups after filtering**: handle gracefully
7. **Export (PNG/JPG)**: aggregate view should export correctly (html2canvas captures current DOM)

### Manual testing:
- Generate diagram from example Terraform project
- Verify all aggregation/de-aggregation flows
- Test with varying resource counts (small project vs large project)
- Test export in both aggregated and de-aggregated states
- Test localStorage persistence
