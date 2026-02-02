"""
Resource Aggregator

Aggregates low-level Terraform resources into high-level logical services
for cleaner architecture diagrams.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from .config_loader import ConfigLoader
from .parser import ParseResult, TerraformResource

if TYPE_CHECKING:
    from .variable_resolver import VariableResolver


# VPC Structure Data Models (Task 5)


@dataclass
class Subnet:
    """Represents a subnet within a VPC."""

    resource_id: str
    name: str
    subnet_type: str  # 'public', 'private', 'database', 'unknown'
    availability_zone: str
    cidr_block: Optional[str] = None


@dataclass
class AvailabilityZone:
    """Represents an availability zone containing subnets."""

    name: str
    short_name: str  # e.g., '1a', '1b'
    subnets: List[Subnet] = field(default_factory=list)


@dataclass
class VPCEndpoint:
    """Represents a VPC endpoint."""

    resource_id: str
    name: str
    endpoint_type: str  # 'gateway' or 'interface'
    service: str  # e.g., 's3', 'dynamodb', 'ecr.api'


@dataclass
class VPCStructure:
    """Represents the complete VPC structure with AZs and endpoints."""

    vpc_id: str
    name: str
    availability_zones: List[AvailabilityZone] = field(default_factory=list)
    endpoints: List[VPCEndpoint] = field(default_factory=list)


@dataclass
class LogicalService:
    """A high-level logical service aggregating multiple resources."""
    service_type: str  # e.g., 'alb', 'ecs', 's3', 'sqs'
    name: str
    icon_resource_type: str  # The Terraform type to use for the icon
    resources: List[TerraformResource] = field(default_factory=list)
    count: int = 1  # How many instances (e.g., 24 SQS queues)
    is_vpc_resource: bool = False
    attributes: Dict[str, str] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return f"{self.service_type}.{self.name}"


@dataclass
class LogicalConnection:
    """A connection between logical services."""
    source_id: str
    target_id: str
    label: Optional[str] = None
    connection_type: str = 'default'  # 'default', 'data_flow', 'trigger', 'encrypt'


@dataclass
class AggregatedResult:
    """Result of aggregating resources into logical services."""

    services: List[LogicalService] = field(default_factory=list)
    connections: List[LogicalConnection] = field(default_factory=list)
    vpc_services: List[LogicalService] = field(default_factory=list)
    global_services: List[LogicalService] = field(default_factory=list)
    vpc_structure: Optional[VPCStructure] = None


class ResourceAggregator:
    """Aggregates Terraform resources into logical services."""

    def __init__(self, config_loader: Optional[ConfigLoader] = None):
        self._config = config_loader or ConfigLoader()
        self._aggregation_rules = self._build_aggregation_rules()
        self._logical_connections = self._config.get_logical_connections()
        self._build_type_to_rule_map()

    def _build_aggregation_rules(self) -> Dict[str, Dict[str, Any]]:
        """Build aggregation rules dict from config."""
        flat_rules = self._config.get_flat_aggregation_rules()
        result = {}
        for service_name, config in flat_rules.items():
            # Map YAML format (primary/secondary/in_vpc) to internal format
            result[service_name] = {
                'primary': config.get("primary", []),
                'aggregate': config.get("secondary", []),  # secondary in YAML -> aggregate internally
                'icon': config.get("primary", [""])[0] if config.get("primary") else "",
                'display_name': service_name.replace("_", " ").title(),
                'is_vpc': config.get("in_vpc", False),
            }
        return result

    def _build_type_to_rule_map(self) -> None:
        """Build a mapping from resource type to aggregation rule."""
        self._type_to_rule: Dict[str, str] = {}
        for rule_name, rule in self._aggregation_rules.items():
            for res_type in rule['primary']:
                self._type_to_rule[res_type] = rule_name
            for res_type in rule['aggregate']:
                self._type_to_rule[res_type] = rule_name

    def aggregate(
        self,
        parse_result: ParseResult,
        terraform_dir: Optional[Union[str, Path]] = None,
    ) -> AggregatedResult:
        """Aggregate parsed resources into logical services.

        Args:
            parse_result: ParseResult containing Terraform resources
            terraform_dir: Optional path to Terraform directory for variable resolution

        Returns:
            AggregatedResult with logical services and optional VPC structure
        """
        result = AggregatedResult()

        # Group resources by aggregation rule
        rule_resources: Dict[str, List[TerraformResource]] = {}
        unmatched: List[TerraformResource] = []

        for resource in parse_result.resources:
            rule_name = self._type_to_rule.get(resource.resource_type)
            if rule_name:
                rule_resources.setdefault(rule_name, []).append(resource)
            else:
                unmatched.append(resource)

        # Create logical services from grouped resources
        for rule_name, resources in rule_resources.items():
            rule = self._aggregation_rules[rule_name]

            # Count primary resources
            primary_count = sum(1 for r in resources if r.resource_type in rule['primary'])
            if primary_count == 0:
                continue  # Skip if no primary resources

            service = LogicalService(
                service_type=rule_name,
                name=rule['display_name'],
                icon_resource_type=rule['icon'],
                resources=resources,
                count=primary_count,
                is_vpc_resource=rule['is_vpc'],
            )

            result.services.append(service)
            if service.is_vpc_resource:
                result.vpc_services.append(service)
            else:
                result.global_services.append(service)

        # Create logical connections based on which services exist
        existing_services = {s.service_type for s in result.services}
        for conn in self._logical_connections:
            source = conn.get("source", "")
            target = conn.get("target", "")
            if source in existing_services and target in existing_services:
                result.connections.append(LogicalConnection(
                    source_id=f"{source}.{self._aggregation_rules[source]['display_name']}",
                    target_id=f"{target}.{self._aggregation_rules[target]['display_name']}",
                    label=conn.get("label", ""),
                    connection_type=conn.get("type", "default"),
                ))

        # Build VPC structure if terraform_dir is provided
        if terraform_dir is not None:
            from .variable_resolver import VariableResolver

            resolver = VariableResolver(terraform_dir)
            vpc_builder = VPCStructureBuilder()
            result.vpc_structure = vpc_builder.build(
                parse_result.resources, resolver=resolver
            )

        return result


class VPCStructureBuilder:
    """Builds VPC structure from Terraform resources."""

    # Regex patterns for detecting AZ from resource names
    AZ_PATTERNS: List[tuple] = [
        # Pattern: name-a, name-b, name-c (single letter suffix)
        (r"[-_]([a-f])$", lambda m: m.group(1)),
        # Pattern: name-1a, name-1b, name-2a (number + letter suffix)
        (r"[-_](\d[a-f])$", lambda m: m.group(1)),
        # Pattern: name-az1, name-az2, name-az3 (az + number suffix)
        (r"[-_]az(\d)$", lambda m: m.group(1)),
        # Pattern: zone-a, zone-b in the middle of name
        (r"[-_]([a-f])[-_]", lambda m: m.group(1)),
    ]

    # Patterns for detecting subnet type from name/tags
    SUBNET_TYPE_PATTERNS: Dict[str, List[str]] = {
        "public": ["public", "pub", "external", "ext", "dmz"],
        "private": ["private", "priv", "internal", "int", "app"],
        "database": ["database", "db", "rds", "data", "storage"],
    }

    def __init__(self) -> None:
        """Initialize the VPCStructureBuilder."""
        pass

    def _detect_availability_zone(
        self, resource: TerraformResource
    ) -> Optional[str]:
        """Detect availability zone from resource attributes or name patterns.

        Args:
            resource: TerraformResource to analyze

        Returns:
            Detected AZ name or None if not detectable
        """
        # First check for explicit availability_zone attribute
        az = resource.attributes.get("availability_zone")
        if az and isinstance(az, str):
            return az

        # Try to detect from resource name
        name = resource.attributes.get("name", resource.resource_name)
        if not isinstance(name, str):
            return None

        name_lower = name.lower()

        for pattern, extractor in self.AZ_PATTERNS:
            match = re.search(pattern, name_lower)
            if match:
                suffix = extractor(match)
                # Return a placeholder AZ name with the detected suffix
                return f"detected-{suffix}"

        return None

    def _detect_subnet_type(self, resource: TerraformResource) -> str:
        """Detect subnet type from name or tags.

        Args:
            resource: TerraformResource to analyze

        Returns:
            Detected subnet type ('public', 'private', 'database', or 'unknown')
        """
        # Check resource name and name attribute
        names_to_check = [
            resource.resource_name,
            resource.attributes.get("name", ""),
        ]

        # Check tags
        tags = resource.attributes.get("tags", {})
        if isinstance(tags, dict):
            type_tag = tags.get("Type", tags.get("type", ""))
            if type_tag:
                type_tag_lower = type_tag.lower()
                for subnet_type, patterns in self.SUBNET_TYPE_PATTERNS.items():
                    if type_tag_lower in patterns:
                        return subnet_type

        # Check name patterns
        for name in names_to_check:
            if not isinstance(name, str):
                continue
            name_lower = name.lower()
            for subnet_type, patterns in self.SUBNET_TYPE_PATTERNS.items():
                for pattern in patterns:
                    if pattern in name_lower:
                        return subnet_type

        return "unknown"

    def _detect_endpoint_type(self, resource: TerraformResource) -> str:
        """Detect VPC endpoint type (gateway or interface).

        Args:
            resource: TerraformResource to analyze

        Returns:
            Endpoint type ('gateway' or 'interface')
        """
        endpoint_type = resource.attributes.get("vpc_endpoint_type", "")
        if isinstance(endpoint_type, str):
            endpoint_type_lower = endpoint_type.lower()
            if endpoint_type_lower == "gateway":
                return "gateway"
        return "interface"

    def _detect_endpoint_service(self, resource: TerraformResource) -> str:
        """Extract service name from VPC endpoint.

        Args:
            resource: TerraformResource to analyze

        Returns:
            Service name (e.g., 's3', 'dynamodb', 'ecr.api')
        """
        service_name = resource.attributes.get("service_name", "")
        if not isinstance(service_name, str):
            return "unknown"

        # Service name format: com.amazonaws.<region>.<service>
        # Example: com.amazonaws.us-east-1.s3
        parts = service_name.split(".")
        if len(parts) >= 4:
            # Join everything after the region (handles services like ecr.api)
            return ".".join(parts[3:])

        return "unknown"

    def _get_az_short_name(self, az_name: str) -> str:
        """Extract short name from AZ name.

        Args:
            az_name: Full AZ name (e.g., 'us-east-1a' or 'detected-1a')

        Returns:
            Short name (e.g., '1a', 'a')
        """
        # Handle detected AZs
        if az_name.startswith("detected-"):
            return az_name.replace("detected-", "")

        # Handle standard AWS AZ names like us-east-1a
        match = re.search(r"(\d[a-z])$", az_name)
        if match:
            return match.group(1)

        # Handle simple suffix like -a, -b
        if len(az_name) >= 1 and az_name[-1].isalpha():
            return az_name[-1]

        return az_name

    def build(
        self,
        resources: List[TerraformResource],
        resolver: Optional["VariableResolver"] = None,
    ) -> Optional[VPCStructure]:
        """Build VPCStructure from a list of Terraform resources.

        Args:
            resources: List of TerraformResource objects
            resolver: Optional VariableResolver for resolving interpolations

        Returns:
            VPCStructure or None if no VPC found
        """
        if not resources:
            return None

        # Find VPC resource
        vpc_resource = None
        for r in resources:
            if r.resource_type == "aws_vpc":
                vpc_resource = r
                break

        if not vpc_resource:
            return None

        # Get VPC name
        vpc_name = vpc_resource.attributes.get("name", vpc_resource.resource_name)
        if resolver and isinstance(vpc_name, str):
            vpc_name = resolver.resolve(vpc_name)

        # Collect subnets by AZ
        az_subnets: Dict[str, List[Subnet]] = {}
        for r in resources:
            if r.resource_type != "aws_subnet":
                continue

            az = self._detect_availability_zone(r)
            if not az:
                continue

            subnet_name = r.attributes.get("name", r.resource_name)
            if resolver and isinstance(subnet_name, str):
                subnet_name = resolver.resolve(subnet_name)

            subnet = Subnet(
                resource_id=r.full_id,
                name=subnet_name,
                subnet_type=self._detect_subnet_type(r),
                availability_zone=az,
                cidr_block=r.attributes.get("cidr_block"),
            )

            az_subnets.setdefault(az, []).append(subnet)

        # Build AvailabilityZone objects
        availability_zones = []
        for az_name, subnets in sorted(az_subnets.items()):
            az = AvailabilityZone(
                name=az_name,
                short_name=self._get_az_short_name(az_name),
                subnets=subnets,
            )
            availability_zones.append(az)

        # Collect VPC endpoints
        endpoints = []
        for r in resources:
            if r.resource_type != "aws_vpc_endpoint":
                continue

            endpoint_name = r.attributes.get("name", r.resource_name)
            if resolver and isinstance(endpoint_name, str):
                endpoint_name = resolver.resolve(endpoint_name)

            endpoint = VPCEndpoint(
                resource_id=r.full_id,
                name=endpoint_name,
                endpoint_type=self._detect_endpoint_type(r),
                service=self._detect_endpoint_service(r),
            )
            endpoints.append(endpoint)

        return VPCStructure(
            vpc_id=vpc_resource.full_id,
            name=vpc_name,
            availability_zones=availability_zones,
            endpoints=endpoints,
        )


def aggregate_resources(parse_result: ParseResult) -> AggregatedResult:
    """Convenience function to aggregate resources."""
    aggregator = ResourceAggregator()
    return aggregator.aggregate(parse_result)
