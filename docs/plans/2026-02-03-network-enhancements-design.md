# Network Enhancements - Design Document

## Scope

Four enhancements to network visualization:

1. CIDR blocks in subnet labels
2. Network flow connections (IGW, NAT Gateway)
3. Security group-to-security group connections
4. Route table associations in subnet labels

---

## 1. CIDR Block in Subnet Labels

**Change**: In `_render_subnet()`, replace the right-side type text with `cidr_block` when available. The subnet type is already communicated by border color (green=public, blue=private, yellow=database).

**Before**: `public_a | public`
**After**: `public_a | 10.0.1.0/24`

Fallback to subnet type if `cidr_block` is None.

**Files**: `renderer.py` only.

---

## 2. Network Flow Connections

**New connection type**: `network_flow` — green (`#0d7c3f`), thin solid line (1px), dedicated arrowhead.

**Connections created**:
- `internet_gateway -> subnet` for each public subnet, label "Internet"
- `subnet -> nat_gateway` for each private subnet, label "NAT"

**Where**: Post-aggregation in `aggregator.py`. After `VPCStructureBuilder.build()` completes and services exist, create `LogicalConnection` objects by matching:
- IGW service + public subnets (from VPC structure)
- NAT GW service + private subnets (from VPC structure)

The NAT GW -> IGW connection is implicit (NAT is in a public subnet which already has IGW connection).

**Subnet targeting**: Network flow connections target the subnet itself. But subnets are secondary resources (not rendered as service nodes). So connections target the **services inside** the subnet, or alternatively target the IGW/NAT service nodes. Best approach: connect IGW to each service that has `is_vpc_resource=True` and is in a public subnet? No — too many connections.

**Simpler approach**: These connections go between the IGW/NAT service nodes only:
- `IGW -> NAT Gateway` with label "Public Route"
- No subnet-level connections (subnets aren't service nodes)

Actually, the most useful approach: connect based on route table analysis (see Section 4). Since route tables link subnets to gateways, we create:
- For each route table with route `0.0.0.0/0 -> igw_id`: the associated subnets are "public" — connect `IGW -> services in those subnets`

This is too complex for a first iteration. **Pragmatic approach**:
- `IGW -> NAT Gateway` with label "Public Route" (NAT is in a public subnet)
- No direct subnet connections — the VPC structure already shows which subnets are public/private

**Files**: `aggregator.py`, `renderer.py` (add style), `renderer.py` JS (add to CONNECTION_TYPES).

---

## 3. Security Group-to-Security Group Connections

**Goal**: When SG "web" has an ingress rule with `source_security_group_id = sg "alb"`, show a connection between the services that USE these security groups.

### Parser changes (`parser.py`)

Add a new method `_extract_sg_connections()` called from `_extract_relationships()`:

1. For each `aws_security_group` resource, iterate `ingress` blocks looking for references to other security groups (pattern: `aws_security_group.*.id` in any value).
2. For each `aws_security_group_rule` with `type = "ingress"`, check `source_security_group_id`.
3. For each `aws_vpc_security_group_ingress_rule`, check `referenced_security_group_id`.
4. Store as a new relationship type: `sg_allows_from`.

### Aggregator changes (`aggregator.py`)

After creating services and before returning result:

1. Build map: `security_group_id -> [service_ids that use it]` (from `uses_security_group` relationships)
2. For each `sg_allows_from` relationship (sg_target allows traffic from sg_source):
   - Find services using sg_source -> these are the "source services"
   - Find services using sg_target -> these are the "target services"
   - Create `LogicalConnection(source, target, label="TCP/port", type="security_rule")`
3. Extract port info from the rule's `from_port`/`to_port` for the label.

### Renderer changes

New connection style `security_rule`: orange (`#d97706`), dotted line (`2,4`), dedicated arrowhead.
Add to JS `CONNECTION_TYPES` array and legend.

**Files**: `parser.py`, `aggregator.py`, `renderer.py`.

---

## 4. Route Table Associations in Subnet Labels

**Goal**: Show the associated route table name as small text in the subnet box.

### Aggregator changes

In `VPCStructureBuilder.build()`, after building subnets:

1. Find all `aws_route_table_association` resources
2. Extract `subnet_id` and `route_table_id` references
3. Map each subnet to its route table name
4. Store in `Subnet` dataclass as new field `route_table_name: Optional[str]`

### Renderer changes

In `_render_subnet()`, if `subnet_info.route_table_name` is set, add a third text element below the existing ones, smaller font (9px), gray color, showing "RT: {name}".

**Files**: `aggregator.py` (Subnet dataclass + builder), `renderer.py` (_render_subnet).

---

## New Connection Types Summary

| Type | Color | Style | Arrowhead | Use |
|------|-------|-------|-----------|-----|
| `network_flow` | `#0d7c3f` | solid, 1px | arrowhead-network | IGW/NAT traffic |
| `security_rule` | `#d97706` | dotted `2,4` | arrowhead-security | SG rule connections |

Both added to: Python renderer styles dict, JS CONNECTION_TYPES, legend SVG lines, connection filter chips.
