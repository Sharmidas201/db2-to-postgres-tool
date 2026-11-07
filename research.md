To determine an application’s hardware resources exactly, you need a minimum of 2 files (and practically 3 files for complete virtual and physical coverage).

The 6 files break down by necessity:

1. The Mandatory Mapping File

⚬ BA-AS-A-SERVER (Strictly Required)
  ⚬ Role: The relational join table.
  ⚬ Why it’s essential: It is the only dataset that connects the application identifier (u_business_application_1.number) to the underlying host/server infrastructure (u_server_1.fqdn / u_server_1.ip_address). Without this file, you cannot associate any server hardware with an application.

2. The Hardware Inventory Files (Pick based on your environment)

To get compute and storage specs, you need at least one hardware source:

⚬ RV_TOOLS (Required if servers are VMware VMs)
  ⚬ Role: Hypervisor ground truth.
  ⚬ Why it’s essential: CMDB discovery often reflects static configuration, whereas RV_TOOLS provides actual hypervisor allocation: vCPU count (CPUs), provisioned memory (Memory), and critically, both allocated storage (Total disk capacity MiB) and actual consumed storage (In Use MiB).
⚬ CMDB-CI-SERVER (Required if servers are Bare-Metal / Physical or Multi-Cloud)
  ⚬ Role: Enterprise configuration database.
  ⚬ Why it’s essential: RV_TOOLS only covers VMware vCenter. If your application runs on bare-metal physical servers, non-VMware hypervisors, or cloud instances, CMDB-CI-SERVER is required to capture cpu_core_count, ram, and disk_space.

3. Context & Validation Files (Recommended / Secondary)

⚬ ARM SERVICE NOW FILE (Recommended for scope & metadata)
  ⚬ Role: Application portfolio catalog.
  ⚬ Why use it: While BA-AS-A-SERVER links app numbers to servers, ARM SERVICE NOW FILE tells you if the application is currently active (Install Status), its environment (Environment), business criticality, and ownership. It allows you to filter out decommissioned apps or non-production environments before sizing.
⚬ AXONIUS DEVICES (Audit / Reconciliation Fallback)
  ⚬ Role: Cyber asset & multi-source reconciliation.
  ⚬ Why use it: Only needed as a tie-breaker if CMDB-CI-SERVER has stale discovery records or missing servers. It provides agent-verified RAM, CPU, and OS end-of-life data.
⚬ VISUAL-GROUP (Not Needed for sizing)
  ⚬ Role: Architectural diagramming and grouping relationships.
  ⚬ Why skip it: It contains visualization pointers and grouping containers (POID, Contains_Ref_List), not raw hardware allocation metrics.

Exact Combination Summary

Infrastructure Type	Minimum Files Needed	Primary Join Key
VMware-only Apps	BA-AS-A-SERVER + RV_TOOLS	u_server_1.fqdn → DNS Name
Physical / Non-VMware Apps	BA-AS-A-SERVER + CMDB-CI-SERVER	u_server_1.fqdn → fqdn
Enterprise Hybrid (Recommended standard)	ARM SERVICE NOW FILE (App scope)
BA-AS-A-SERVER (Relationship)
RV_TOOLS (VM specs)
CMDB-CI-SERVER (Physical specs fallback)	Number → u_business_application_1.number
then u_server_1.fqdn → DNS Name / fqdn