---
title: "release notes v0.20.0"
linkTitle: "release notes v0.20.0"
date: 2026-07-29
type: docs
---

# OpenShift Migration Advisor — release notes — `v0.20.0`

Compare: `v0.19.0` → `v0.20.0`

## Appliance changes

### Features
- Redesigned the Operating Systems card with a filterable table showing OS support tiers, VM counts, and upgrade recommendations
- Standardized empty states across the appliance UI with consistent messaging, icons, and layout

### API changes (not yet available in the UI)
- Added multi-collection architecture: each inventory run produces its own database, user data (labels, groups, settings) carries forward automatically, historical collections are browseable read-only, with full API support for VMs, groups, applications, rightsizing, deep inspection, and data export
- Added Excel (.xlsx) export format alongside existing CSV/ZIP export

### Fixes
- Fixed VM group creation being blocked while deep inspection is running
- Fixed Labels and Groups columns not supporting sorting in the Virtual Machines tab
- Fixed selected VMs remaining selected after applying a filter or changing search terms
- Fixed console connection status incorrectly showing as connected during transient server errors

## Console changes

### Features
- Redesigned cost estimation with updated input fields, a detailed 3-year VMware vs Red Hat breakdown table, and a copy-as-text option
- Redesigned the Operating Systems card with a filterable table showing OS support tiers, VM counts, and upgrade recommendations
- Added appliance version display and release documentation link to the environment setup form
