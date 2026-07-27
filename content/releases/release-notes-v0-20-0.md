---
title: "release notes v0.20.0"
linkTitle: "release notes v0.20.0"
date: 2026-07-27
type: docs
---

# OpenShift Migration Advisor — release notes — `v0.20.0`

Compare: `v0.19.0` → `v0.20.0`

## Appliance changes

### Features
- Redesigned the Operating Systems card with a filterable, sortable table showing OS name, support tier badges, and VM counts, replacing the previous bar chart; added help popovers explaining tier definitions and upgrade recommendations
- User data including VM labels, exclusions, migration settings, and groups is now automatically preserved when a new VMware collection runs
- Standardized empty states across all views with consistent messaging, icons, and loading indicators
- Collection runs and deep inspections are now mutually exclusive, preventing data conflicts

### API changes (not yet available in the UI)
- Introduced the V2 multi-collection API with collection-scoped endpoints for VM operations, groups, labels, rightsizing, deep inspection, VDDK management, and data export; historical collections are accessible in read-only mode with an optimized hot path for latest collection retrieval
- Added Excel (.xlsx) export format option to the inventory export API, producing a single workbook with one sheet per scope

### Fixes
- Fixed VM group creation being incorrectly blocked while deep inspection was running
- Fixed console connection status showing "Connected" during transient connection errors — status now accurately reflects live connection state
- Fixed VM selection not clearing when filters or search terms change
- Added sorting support for Labels and Groups columns in the VM table
- Stale collection data from interrupted runs is now automatically cleaned up on agent startup

## Console changes

### Features
- Redesigned the Operating Systems card with a filterable, sortable table showing OS name, support tier badges, and VM counts, replacing the previous bar chart; added help popovers explaining tier definitions and upgrade recommendations
- Added appliance version display and release documentation link to the environment setup modal

