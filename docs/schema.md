# Source Data Schemas

Converted from `Schema's.docx`. Each section lists the columns in source order.

## Schema summary

| Dataset | Column count | Primary use |
| :--- | :---: | :--- |
| ARM SERVICE NOW FILE | 46 | Application inventory, ownership, criticality, resiliency, and technology attributes |
| AXONIUS DEVICES | 84 | Device, CPU, OS, risk, location, and asset inventory |
| BA-AS-A-SERVER | 48 | Business application to service to server relationship |
| CMDB-CI-SERVER | 113 | Server configuration, compute, storage, ownership, lifecycle, and discovery attributes |
| VISUAL-GROUP | 27 | Visual grouping, dependency, application, and portfolio metadata |
| RV_TOOLS | 103 | VMware VM configuration, compute, storage, network, host, and cluster inventory |

## Recommended relationship for application and server assessment

```text
ARM SERVICE NOW FILE.Number
-> BA-AS-A-SERVER.u_business_application_1.number
-> BA-AS-A-SERVER.u_server_1.fqdn
-> CMDB-CI-SERVER.fqdn
-> CPU / RAM / disk / OS
```

> Use exact normalized FQDN as the preferred server join. Use hostname second and IP address only as a controlled fallback.

---

## ARM SERVICE NOW FILE

| # | Column |
| :-: | :--- |
| 1 | Number |
| 2 | Name |
| 3 | Application family |
| 4 | Description |
| 5 | Short name |
| 6 | Install Status |
| 7 | Company |
| 8 | Portfolio |
| 9 | Business criticality |
| 10 | Technology Recovery Time Objective (Technology RTO) |
| 11 | Technology Recovery Point Objective (Technology RPO) |
| 12 | Data classification |
| 13 | ICOFR |
| 14 | Application type |
| 15 | Architecture type |
| 16 | Install type |
| 17 | Internet accessible |
| 18 | Platform host |
| 19 | Support group |
| 20 | Business owner |
| 21 | IT Application owner |
| 22 | Application Assessor |
| 23 | Application Architect |
| 24 | Current Resiliency class |
| 25 | Target resiliency class |
| 26 | Resiliency Status |
| 27 | DR documentation |
| 28 | Billing code |
| 29 | Updated |
| 30 | Last updated by |
| 31 | Created |
| 32 | Created by |
| 33 | Serial number |
| 34 | Work notes |
| 35 | Application category |
| 36 | Portfolio manager |
| 37 | Model ID |
| 38 | Software model |
| 39 | Technology stack |
| 40 | Comments |
| 41 | DNS Domain |
| 42 | Environment |
| 43 | OT device details |
| 44 | Platform |
| 45 | Publisher |
| 46 | Business Unit |

---

## AXONIUS DEVICES

| # | Column |
| :-: | :--- |
| 1 | Aggregated: Adapter Connections |
| 2 | Aggregated: Preferred Asset Name |
| 3 | Aggregated: Preferred Boot Time |
| 4 | Aggregated: Preferred Cloud Provider Account Name |
| 5 | Aggregated: Preferred Cloud Provider Account Name and Account ID |
| 6 | Aggregated: Preferred Company |
| 7 | Aggregated: Preferred Compliance Last Scan |
| 8 | Aggregated: Preferred Config Item ID |
| 9 | Aggregated: Preferred CPUs: Description |
| 10 | Aggregated: Preferred CPUs: Manufacturer |
| 11 | Aggregated: Preferred CPUs: Bitness |
| 12 | Aggregated: Preferred CPUs: Family |
| 13 | Aggregated: Preferred CPUs: Cores |
| 14 | Aggregated: Preferred CPUs: Logical Cores |
| 15 | Aggregated: Preferred CPUs: Threads in core |
| 16 | Aggregated: Preferred CPUs: Load Percentage |
| 17 | Aggregated: Preferred CPUs: Architecture |
| 18 | Aggregated: Preferred CPUs: Clockspeed (GHZ) |
| 19 | Aggregated: Preferred CS Sensor Update Policy: Applied |
| 20 | Aggregated: Preferred CPUs: Architecture |
| 21 | Aggregated: Preferred CPUs: Bitness |
| 22 | Aggregated: Preferred CPUs: Clockspeed (GHZ) |
| 23 | Aggregated: Preferred CPUs: Cores |
| 24 | Aggregated: Preferred CPUs: Description |
| 25 | Aggregated: Preferred CPUs: Family |
| 26 | Aggregated: Preferred CPUs: Load Percentage |
| 27 | Aggregated: Preferred CPUs: Logical Cores |
| 28 | Aggregated: Preferred CPUs: Manufacturer |
| 29 | Aggregated: Preferred CPUs: Threads in core |
| 30 | Aggregated: Preferred CUs Behind Latest |
| 31 | Aggregated: Preferred Device Manufacturer |
| 32 | Aggregated: Preferred Device Model |
| 33 | Aggregated: Preferred Device Type |
| 34 | Aggregated: Preferred Domain |
| 35 | Aggregated: Preferred Earliest First Seen |
| 36 | Aggregated: Preferred Earliest First Seen Adapter |
| 37 | Aggregated: Preferred Host Name |
| 38 | Aggregated: Preferred Host Name (FQDN) |
| 39 | Aggregated: Preferred Is Virtual |
| 40 | Aggregated: Preferred Last Vuln Scan |
| 41 | Aggregated: Preferred Latest Last Seen |
| 42 | Aggregated: Preferred Latest Last Seen (agents) |
| 43 | Aggregated: Preferred Latest Last Seen Adapter |
| 44 | Aggregated: Preferred Location Name |
| 45 | Aggregated: Preferred OS: Bitness |
| 46 | Aggregated: Preferred OS: Build |
| 47 | Aggregated: Preferred OS: Code Name |
| 48 | Aggregated: Preferred OS: Combined OS Fields |
| 49 | Aggregated: Preferred OS: Distribution |
| 50 | Aggregated: Preferred OS: Distribution Name |
| 51 | Aggregated: Preferred OS: Edition |
| 52 | Aggregated: Preferred OS: End of Extended Support |
| 53 | Aggregated: Preferred OS: End of Life |
| 54 | Aggregated: Preferred OS: End of Support |
| 55 | Aggregated: Preferred OS: Full String |
| 56 | Aggregated: Preferred OS: Is End of Extended Support |
| 57 | Aggregated: Preferred OS: Is End of Life |
| 58 | Aggregated: Preferred OS: Is End of Support |
| 59 | Aggregated: Preferred OS: Is Latest OS Version |
| 60 | Aggregated: Preferred OS: Is Supported OS Version |
| 61 | Aggregated: Preferred OS: Is Windows Server |
| 62 | Aggregated: Preferred OS: Kernel Version |
| 63 | Aggregated: Preferred OS: Latest OS Version |
| 64 | Aggregated: Preferred OS: Major |
| 65 | Aggregated: Preferred OS: Minor |
| 66 | Aggregated: Preferred OS: OS Version |
| 67 | Aggregated: Preferred OS: Patch |
| 68 | Aggregated: Preferred OS: Type |
| 69 | Aggregated: Preferred OS: Type and Distribution |
| 70 | Aggregated: Preferred OS: Windows Patch Version |
| 71 | Aggregated: Preferred OS: Windows Version |
| 72 | Aggregated: Preferred Physical Location |
| 73 | Aggregated: Preferred Risk Score |
| 74 | Aggregated: Preferred Serial Number |
| 75 | Aggregated: Preferred Serial Number (VMware formatted) |
| 76 | Aggregated: Preferred Site Code |
| 77 | Aggregated: Preferred Status |
| 78 | Aggregated: Preferred Total CPU Cores |
| 79 | Aggregated: Preferred Total Disk Space (GB) |
| 80 | Aggregated: Preferred Total Physical Processors |
| 81 | Aggregated: Preferred Total RAM (GB) |
| 82 | Aggregated: Preferred Uptime |
| 83 | Aggregated: Preferred User |
| 84 | Aggregated: Preferred User Manager |

---

## BA-AS-A-SERVER

| # | Column |
| :-: | :--- |
| 1 | u_business_application_1 |
| 2 | u_business_application_1.number |
| 3 | u_business_application_1.serial_number |
| 4 | u_business_application_1.portfolio |
| 5 | u_business_application_1.u_icofr |
| 6 | u_business_application_1.data_classification |
| 7 | u_business_application_1.u_recovery_time_objective_rto |
| 8 | u_business_application_1.u_recovery_point_objective_rpo |
| 9 | u_business_application_1.application_type |
| 10 | u_business_application_1.architecture_type |
| 11 | u_business_application_1.install_type |
| 12 | u_business_application_1.u_internet_accessible |
| 13 | u_business_application_1.gl_account |
| 14 | u_business_application_1.operational_status |
| 15 | u_business_application_1.install_status |
| 16 | u_business_application_1.it_application_owner |
| 17 | u_business_application_1.support_group |
| 18 | u_business_application_1.u_application_assessor |
| 19 | u_business_application_1.u_current_resiliency_class |
| 20 | u_business_application_1.u_resiliency_status |
| 21 | u_business_application_1.u_target_resiliency_class |
| 22 | u_business_application_1.short_description |
| 23 | u_business_application_1.category |
| 24 | u_business_application_1.subcategory |
| 25 | u_business_application_1.application_category |
| 26 | u_business_application_1.sys_class_name |
| 27 | u_rel_business_application_1_service_1.type |
| 28 | u_service_1 |
| 29 | u_service_1.number |
| 30 | u_service_1.serial_number |
| 31 | u_service_1.sys_class_name |
| 32 | u_rel_service_1_server_1.type |
| 33 | u_server_1 |
| 34 | u_server_1.serial_number |
| 35 | u_server_1.virtual |
| 36 | u_server_1.hardware_status |
| 37 | u_server_1.hardware_substatus |
| 38 | u_server_1.last_discovered |
| 39 | u_server_1.fqdn |
| 40 | u_server_1.environment |
| 41 | u_server_1.location |
| 42 | u_server_1.support_group |
| 43 | u_server_1.ip_address |
| 44 | u_server_1.ram |
| 45 | u_server_1.os |
| 46 | u_server_1.os_version |
| 47 | u_server_1.os_service_pack |
| 48 | u_server_1.sys_class_name |

---

## CMDB-CI-SERVER

| # | Column |
| :-: | :--- |
| 1 | name |
| 2 | sys_created_on |
| 3 | install_status |
| 4 | ip_address |
| 5 | location |
| 6 | fqdn |
| 7 | manufacturer |
| 8 | model_id |
| 9 | os |
| 10 | os_version |
| 11 | short_description |
| 12 | sys_class_name |
| 13 | operational_status |
| 14 | owned_by |
| 15 | cpu_core_count |
| 16 | chassis_type |
| 17 | ram |
| 18 | internet_facing |
| 19 | disk_space |
| 20 | change_control |
| 21 | asset |
| 22 | asset_tag |
| 23 | attributes |
| 24 | u_bmc_cpu_core_count |
| 25 | u_bmc_cpu_count |
| 26 | business_unit |
| 27 | cd_rom |
| 28 | cd_speed |
| 29 | cpu_core_thread |
| 30 | cpu_count |
| 31 | cpu_manufacturer |
| 32 | cpu_name |
| 33 | cpu_speed |
| 34 | cpu_type |
| 35 | can_print |
| 36 | category |
| 37 | classification |
| 38 | cluster_id |
| 39 | cluster_name |
| 40 | comments |
| 41 | company |
| 42 | correlation_id |
| 43 | cost |
| 44 | cost_center |
| 45 | cost_cc |
| 46 | sys_created_by |
| 47 | dns_domain |
| 48 | default_gateway |
| 49 | department |
| 50 | dr_backup |
| 51 | discovery_source |
| 52 | sys_domain |
| 53 | sys_domain_path |
| 54 | due |
| 55 | due_in |
| 56 | duplicate_of |
| 57 | environment |
| 58 | fault_count |
| 59 | firewall_status |
| 60 | first_discovered |
| 61 | floppy |
| 62 | form_factor |
| 63 | frame_identification_code |
| 64 | gl_account |
| 65 | hardware_status |
| 66 | host_name |
| 67 | install_date |
| 68 | invoice_number |
| 69 | virtual |
| 70 | justification |
| 71 | u_last_logged_on_user |
| 72 | lease_id |
| 73 | life_cycle_stage |
| 74 | life_cycle_stage_status |
| 75 | mac_address |
| 76 | maintenance_schedule |
| 77 | managed_by_group |
| 78 | managed_by |
| 79 | model_number |
| 80 | monitor |
| 81 | most_frequent_user |
| 82 | os_address_width |
| 83 | os_domain |
| 84 | os_install |
| 85 | os_service_pack |
| 86 | cmdb_ot_entity |
| 87 | object_id |
| 88 | delivery_date |
| 89 | order_date |
| 90 | po_number |
| 91 | processor_name |
| 92 | product_instance_id |
| 93 | purchase_date |
| 94 | unverified |
| 95 | schedule |
| 96 | serial_number |
| 97 | service_tag |
| 98 | skip_sync |
| 99 | start_date |
| 100 | subcategory |
| 101 | hardware_substatus |
| 102 | support_group |
| 103 | supported_by |
| 104 | sys_class_path |
| 105 | x_avne2_addm_to_sn_td_key |
| 106 | sys_tags |
| 107 | sys_updated_on |
| 108 | sys_updated_by |
| 109 | sys_mod_count |
| 110 | used_for |
| 111 | vendor |
| 112 | cmdb_ci_vm_object |
| 113 | warranty_expiration |

---

## VISUAL-GROUP

| # | Column |
| :-: | :--- |
| 1 | CLASS |
| 2 | OID |
| 3 | POID |
| 4 | META_Ref |
| 5 | Latest_Ref |
| 6 | Older_Ref |
| 7 | Parents_Ref_List |
| 8 | Contains_Ref_List |
| 9 | Dependencies_Ref_List |
| 10 | Hostname |
| 11 | Details |
| 12 | Filters |
| 13 | DisplayName |
| 14 | Name |
| 15 | Environment |
| 16 | Out of scope |
| 17 | Description |
| 18 | Contains |
| 19 | Display as icon |
| 20 | Icon |
| 21 | Business Criticality |
| 22 | Portfolio |
| 23 | DNS Domain |
| 24 | Number |
| 25 | Architecture Type |
| 26 | IT Application owner |
| 27 | Resiliency Class |

---

## RV_TOOLS

| # | Column |
| :-: | :--- |
| 1 | VM |
| 2 | Powerstate |
| 3 | Template |
| 4 | SRM Placeholder |
| 5 | Config status |
| 6 | DNS Name |
| 7 | Connection state |
| 8 | Guest state |
| 9 | Heartbeat |
| 10 | Consolidation Needed |
| 11 | PowerOn |
| 12 | Suspended To Memory |
| 13 | Suspend time |
| 14 | Suspend Interval |
| 15 | Creation date |
| 16 | Change Version |
| 17 | CPUs |
| 18 | Overall Cpu Readiness |
| 19 | Memory |
| 20 | Active Memory |
| 21 | NICs |
| 22 | Disks |
| 23 | Total disk capacity MiB |
| 24 | Fixed Passthru HotPlug |
| 25 | min Required EVC Mode Key |
| 26 | Latency Sensitivity |
| 27 | Op Notification Timeout |
| 28 | EnableUUID |
| 29 | CBT |
| 30 | Primary IP Address |
| 31 | Network #1 |
| 32 | Network #2 |
| 33 | Network #3 |
| 34 | Network #4 |
| 35 | Network #5 |
| 36 | Network #6 |
| 37 | Network #7 |
| 38 | Network #8 |
| 39 | Num Monitors |
| 40 | Video Ram KiB |
| 41 | Resource pool |
| 42 | Folder ID |
| 43 | Folder |
| 44 | vApp |
| 45 | DAS protection |
| 46 | FT State |
| 47 | FT Role |
| 48 | FT Latency |
| 49 | FT Bandwidth |
| 50 | FT Sec. Latency |
| 51 | Vm Failover In Progress |
| 52 | Provisioned MiB |
| 53 | In Use MiB |
| 54 | Unshared MiB |
| 55 | HA Restart Priority |
| 56 | HA Isolation Response |
| 57 | HA VM Monitoring |
| 58 | Cluster rule(s) |
| 59 | Cluster rule name(s) |
| 60 | Boot Required |
| 61 | Boot delay |
| 62 | Boot retry delay |
| 63 | Boot retry enabled |
| 64 | Boot BIOS setup |
| 65 | Reboot PowerOff |
| 66 | EFI Secure boot |
| 67 | Firmware |
| 68 | HW version |
| 69 | HW upgrade status |
| 70 | HW upgrade policy |
| 71 | HW target |
| 72 | Path |
| 73 | Log directory |
| 74 | Snapshot directory |
| 75 | Suspend directory |
| 76 | Annotation |
| 77 | Build CRQ |
| 78 | CreatedBy |
| 79 | CreatedOn |
| 80 | Decom CRQ |
| 81 | Dell EMC vProxy Cleanup Descriptor |
| 82 | Dell EMC vProxy FLR Session |
| 83 | Dell EMC vProxy Session |
| 84 | EMC vProxy Cleanup Descriptor |
| 85 | EMC vProxy FLR Session |
| 86 | EMC vProxy Session |
| 87 | Last EMC vProxy Backup |
| 88 | SRM-com.vmware.vDr:::protected |
| 89 | WORKGROUP |
| 90 | XdConfig |
| 91 | Datacenter |
| 92 | Cluster |
| 93 | Host |
| 94 | OS according to the configuration file |
| 95 | OS according to the VMware Tools |
| 96 | Customization Info |
| 97 | Guest Detailed Data |
| 98 | VM ID |
| 99 | VM UUID |
| 100 | VI SDK Server type |
| 101 | VI SDK API Version |
| 102 | VI SDK Server |
| 103 | VI SDK UUID |

---

## Notes

* Column names are preserved from the source document, including capitalization, spaces, prefixes, and repeated names.
* Duplicate source columns are retained because downstream exports may contain them in that order.
* The document defines field availability only. It does not define data types, nullability, primary keys, foreign keys, or value quality.
* Validate units before calculations, especially `ram`, `disk_space`, Azure/VMware MiB values, CPU speed, and Axonius GB fields.
* For migration sizing, distinguish allocated server disk from actual database-used storage.


This is the Md file and I want to figure out the hardware resources of an application 