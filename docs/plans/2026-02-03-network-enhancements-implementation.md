# Network Enhancements - Implementation Plan

Reference: [Design Document](2026-02-03-network-enhancements-design.md)

---

## Step 1: CIDR blocks in subnet labels

**File**: `terraformgraph/renderer.py`

### 1a. Modify `_render_subnet()` (~line 237-241)

Replace the right-side text content:
- Current: `{subnet_info.subnet_type}`
- New: `{subnet_info.cidr_block}` if available, else `{subnet_info.subnet_type}`

### Verification
- Generate diagram, inspect subnet boxes — should show CIDR when available, type as fallback.

---

## Step 2: Add `route_table_name` to Subnet dataclass

**File**: `terraformgraph/aggregator.py`

### 2a. Update `Subnet` dataclass (~line 24-33)
- Add field: `route_table_name: Optional[str] = None`

### 2b. In `VPCStructureBuilder.build()`, after subnet creation
- Find all `aws_route_table_association` resources in the input
- For each, extract `subnet_id` reference and `route_table_id` reference
- Resolve to actual resource IDs using `_find_referenced_resources` pattern
- Map subnet resource_id -> route table name
- Set `subnet.route_table_name` for each matched subnet

### Verification
- Unit test: create resources with route table associations, verify Subnet objects have correct route_table_name.

---

## Step 3: Show route table name in subnet boxes

**File**: `terraformgraph/renderer.py`

### 3a. Modify `_render_subnet()` (~line 237-241)
- After the CIDR/type text, if `subnet_info.route_table_name` is set, add a third `<text>` element:
  - Position: right-aligned, below existing text (y offset +12)
  - Font: 9px, gray (#999), opacity 0.6
  - Content: `RT: {route_table_name}`

Note: this may require adjusting the subnet box height. Check `layout.py` for minimum subnet heights.

### Verification
- Generate diagram with route table associations, verify RT label appears in subnet boxes.

---

## Step 4: Add `network_flow` connection type

**File**: `terraformgraph/renderer.py`

### 4a. Add arrowhead marker (~line 139-151, SVG defs)
- Add `<marker id="arrowhead-network">` with green fill (#0d7c3f)

### 4b. Add to Python styles dict (~line 456-461)
- Add: `"network_flow": ("#0d7c3f", "", "url(#arrowhead-network)")`

### 4c. Add to JS CONNECTION_TYPES array (~line 1759-1764)
- Add: `{ id: 'network_flow', label: 'Network Flow', color: '#0d7c3f' }`

### 4d. Add to JS styles objects in `recalculateAllAggregateConnections` and `selectResourceInPopover`
- Add network_flow entry to the inline `styles` dicts

### 4e. Add to legend
- Add SVG line entry for Network Flow (green solid line with arrowhead)

### Verification
- Visually confirm new connection type renders correctly.

---

## Step 5: Create network flow connections

**File**: `terraformgraph/aggregator.py`

### 5a. Add method `_create_network_flow_connections()` to `ResourceAggregator`

After standard logical connections are created (~line 367), call this method:

1. Check `result.vpc_structure` exists
2. Find IGW service(s) in `result.services` where `service_type == "internet_gateway"`
3. Find NAT GW service(s) in `result.services` where `service_type == "nat_gateway"`
4. If both IGW and NAT GW exist, create `LogicalConnection`:
   - `source_id=igw.id, target_id=nat_gw.id, label="Public Route", connection_type="network_flow"`
5. If multiple NAT GWs, connect IGW to each

### Verification
- Generate diagram with IGW and NAT GW, verify green connection appears.

---

## Step 6: Add `security_rule` connection type

**File**: `terraformgraph/renderer.py`

### 6a. Add arrowhead marker
- Add `<marker id="arrowhead-security">` with orange fill (#d97706)

### 6b. Add to Python styles dict
- Add: `"security_rule": ("#d97706", "2,4", "url(#arrowhead-security)")`

### 6c. Add to JS CONNECTION_TYPES array
- Add: `{ id: 'security_rule', label: 'Security Rule', color: '#d97706' }`

### 6d. Add to JS styles objects in recalculate/popover functions

### 6e. Add to legend
- Add SVG line entry for Security Rule (orange dotted line)

### Verification
- Visually confirm new connection type renders correctly.

---

## Step 7: Parse security group cross-references

**File**: `terraformgraph/parser.py`

### 7a. Add `_extract_sg_connections()` method

Called from `_extract_relationships()` after standard extraction:

1. For each `aws_security_group` resource:
   - Get `ingress` attribute (list of rule blocks)
   - For each rule, search all values recursively for patterns matching `aws_security_group.*.id`
   - If found: create `ResourceRelationship(source_id=referenced_sg, target_id=this_sg, relationship_type="sg_allows_from")`
   - Also extract `from_port`/`to_port` and `protocol` for label

2. For each `aws_security_group_rule` resource with `type == "ingress"`:
   - Check `source_security_group_id` attribute
   - If references another SG: create relationship
   - Extract `security_group_id` (the SG this rule belongs to) as target

3. For each `aws_vpc_security_group_ingress_rule` resource:
   - Check `referenced_security_group_id` attribute
   - Extract `security_group_id` as target

### 7b. Store port info in relationship
- Add optional `metadata: Dict` field to `ResourceRelationship` dataclass, or encode port info in relationship_type string (e.g., `"sg_allows_from:tcp/80"`)

### Verification
- Unit test: parse a terraform file with SG cross-references, verify relationships are extracted.

---

## Step 8: Create security rule connections from SG relationships

**File**: `terraformgraph/aggregator.py`

### 8a. Add method `_create_sg_connections()` to `ResourceAggregator`

Called after `_create_network_flow_connections()`:

1. Build map: `sg_resource_id -> [service_ids that use it]`
   - From relationships where `relationship_type == "uses_security_group"`
   - Each service's resource list may contain the SG, or the service has a `security_group_ids` reference

2. For each `sg_allows_from` relationship:
   - source_sg -> find services using source_sg -> "source services"
   - target_sg -> find services using target_sg -> "target services"
   - Create `LogicalConnection` for each source-target pair
   - Label: port info from relationship metadata (e.g., "TCP/80")
   - Type: `"security_rule"`

3. Deduplicate: if a `data_flow` or `trigger` connection already exists between the same services, still create the `security_rule` connection (different layer of information).

### Verification
- Generate diagram with SG cross-references, verify orange dotted connections appear.

---

## Step 9: Update connection filter and legend

**Files**: `terraformgraph/renderer.py`

### 9a. Verify both new types appear in filter chips
- `initConnectionTypeFilter()` reads from `CONNECTION_TYPES` array, so new types appear automatically.

### 9b. Update legend
- Already handled in Steps 4e and 6e.

### Verification
- Full integration test: generate diagram, verify all 6 connection types visible, filterable, and in legend.

---

## Step 10: Testing and edge cases

### Edge cases:
1. **No CIDR block**: subnet falls back to showing type — verify
2. **No route table associations**: subnet shows no RT label — verify
3. **No IGW or NAT GW**: no network_flow connections created — verify no errors
4. **No SG cross-references**: no security_rule connections — verify no errors
5. **SG references via variables**: may not resolve — handle gracefully (skip)
6. **Multiple VPCs**: each VPC has its own IGW/NAT — connections should be per-VPC
7. **Self-referencing SG**: SG allows traffic from itself — skip (no useful visual)
8. **Aggregated services**: security_rule connections should work with aggregation system

### Run existing test suite
- All 128 tests must pass.
