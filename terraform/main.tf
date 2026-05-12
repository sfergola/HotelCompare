variable "availability_domain" {
  default = "SeHt:EU-FRANKFURT-1-AD-1"
}

# region esplicita richiesta per autenticazione InstancePrincipal in Oracle Resource Manager
provider "oci" {
  region = "eu-frankfurt-1"
}

resource "oci_core_instance" "generated_oci_core_instance" {
	agent_config {
		is_management_disabled = "false"
		is_monitoring_disabled = "false"
		plugins_config {
			desired_state = "DISABLED"
			name = "Vulnerability Scanning"
		}
		plugins_config {
			desired_state = "DISABLED"
			name = "OS Management Hub Agent"
		}
		plugins_config {
			desired_state = "DISABLED"
			name = "Management Agent"
		}
		plugins_config {
			desired_state = "ENABLED"
			name = "Custom Logs Monitoring"
		}
		plugins_config {
			desired_state = "DISABLED"
			name = "Compute RDMA GPU Monitoring"
		}
		plugins_config {
			desired_state = "ENABLED"
			name = "Compute Instance Monitoring"
		}
		plugins_config {
			desired_state = "DISABLED"
			name = "Compute HPC RDMA Auto-Configuration"
		}
		plugins_config {
			desired_state = "DISABLED"
			name = "Compute HPC RDMA Authentication"
		}
		plugins_config {
			desired_state = "ENABLED"
			name = "Cloud Guard Workload Protection"
		}
		plugins_config {
			desired_state = "DISABLED"
			name = "Block Volume Management"
		}
		plugins_config {
			desired_state = "DISABLED"
			name = "Bastion"
		}
	}
	availability_config {
		recovery_action = "RESTORE_INSTANCE"
	}
	availability_domain = var.availability_domain
	compartment_id = "ocid1.tenancy.oc1..aaaaaaaat5ynt5bb7s2iukk7q7jjfyufpz5qbkf7xf5phabcccsdm6z5fp7q"
	create_vnic_details {
		assign_ipv6ip = "false"
		assign_private_dns_record = "true"
		assign_public_ip = "true"
		subnet_id = "${oci_core_subnet.generated_oci_core_subnet.id}"
		nsg_ids    = ["${oci_core_network_security_group.hotelcompare_nsg.id}"]
	}
	display_name = "hotelcompare"
	instance_options {
		are_legacy_imds_endpoints_disabled = "true"
	}
	is_pv_encryption_in_transit_enabled = "true"
	metadata = {
		"ssh_authorized_keys" = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAID1OMAVqM0pelJWCeTZ9SI/GRMY32+blQj7B3F6fzcHv salvatore@salvatore-ThinkPad-X250"
	}
	shape = "VM.Standard.A1.Flex"
	shape_config {
		memory_in_gbs = "6"
		ocpus = "1"
	}
	source_details {
		source_id = "ocid1.image.oc1.eu-frankfurt-1.aaaaaaaab2msc7qxe4auh5mhnfqx746egseojithkvoe7fnqqzau67u7qhba"
		source_type = "image"
	}
}

resource "oci_core_vcn" "generated_oci_core_vcn" {
	cidr_block = "10.0.0.0/16"
	compartment_id = "ocid1.tenancy.oc1..aaaaaaaat5ynt5bb7s2iukk7q7jjfyufpz5qbkf7xf5phabcccsdm6z5fp7q"
	display_name = "vcn-20260510-1210"
	dns_label = "vcn05101213"
}

resource "oci_core_subnet" "generated_oci_core_subnet" {
	cidr_block = "10.0.0.0/24"
	compartment_id = "ocid1.tenancy.oc1..aaaaaaaat5ynt5bb7s2iukk7q7jjfyufpz5qbkf7xf5phabcccsdm6z5fp7q"
	display_name = "subnet-20260510-1210"
	dns_label = "subnet05101213"
	route_table_id = "${oci_core_vcn.generated_oci_core_vcn.default_route_table_id}"
	vcn_id = "${oci_core_vcn.generated_oci_core_vcn.id}"
}

resource "oci_core_internet_gateway" "generated_oci_core_internet_gateway" {
	compartment_id = "ocid1.tenancy.oc1..aaaaaaaat5ynt5bb7s2iukk7q7jjfyufpz5qbkf7xf5phabcccsdm6z5fp7q"
	display_name = "Internet Gateway vcn-20260510-1210"
	enabled = "true"
	vcn_id = "${oci_core_vcn.generated_oci_core_vcn.id}"
}

resource "oci_core_default_route_table" "generated_oci_core_default_route_table" {
	route_rules {
		destination = "0.0.0.0/0"
		destination_type = "CIDR_BLOCK"
		network_entity_id = "${oci_core_internet_gateway.generated_oci_core_internet_gateway.id}"
	}
	manage_default_resource_id = "${oci_core_vcn.generated_oci_core_vcn.default_route_table_id}"
}

# Network Security Group — unica porta aperta in ingresso: SSH (22)
# Tutto il traffico in uscita è permesso (necessario per scraping + push GitHub)
resource "oci_core_network_security_group" "hotelcompare_nsg" {
	compartment_id = "ocid1.tenancy.oc1..aaaaaaaat5ynt5bb7s2iukk7q7jjfyufpz5qbkf7xf5phabcccsdm6z5fp7q"
	vcn_id         = oci_core_vcn.generated_oci_core_vcn.id
	display_name   = "hotelcompare-nsg"
}

# Regola ingresso: SSH da qualsiasi IP
resource "oci_core_network_security_group_security_rule" "allow_ssh_ingress" {
	network_security_group_id = oci_core_network_security_group.hotelcompare_nsg.id
	direction                 = "INGRESS"
	protocol                  = "6"  # TCP
	source                    = "0.0.0.0/0"
	source_type               = "CIDR_BLOCK"
	tcp_options {
		destination_port_range {
			min = 22
			max = 22
		}
	}
}

# Regola uscita: tutto permesso (scraping Booking + push GitHub)
resource "oci_core_network_security_group_security_rule" "allow_all_egress" {
	network_security_group_id = oci_core_network_security_group.hotelcompare_nsg.id
	direction                 = "EGRESS"
	protocol                  = "all"
	destination               = "0.0.0.0/0"
	destination_type          = "CIDR_BLOCK"
}
