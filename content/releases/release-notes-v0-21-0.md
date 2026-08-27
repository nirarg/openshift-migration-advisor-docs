---
title: "release notes v0.21.0"
linkTitle: "release notes v0.21.0"
date: 2026-08-20
type: docs
---

# OpenShift Migration Advisor — release notes — `v0.21.0`

Compare: `v0.20.3` → `v0.21.0`

## Appliance changes

### Features
- Added RVTools upload mode for collecting inventory from uploaded Excel files instead of connecting to a live vCenter
- Added report comparison tool for comparing two collection runs, showing changes in VMs, clusters, and migration status over time
- Added "Run new report" action to trigger a fresh vSphere data collection and refresh the dashboard
- Added Excel (.xlsx) export format option alongside the existing ZIP export

### API changes (not yet available in the UI)
- Added vMotion and Storage vMotion capability flags to host inventory data
- Added created_at timestamp to inventory records for tracking when data was collected
- Added HA Enabled (High Availability) cluster feature to inventory data
- Migrated agent UI to v2 API endpoints with improved collection-based reporting
- Aligned v2 group API responses with v1 format for consistency
- Refactored filter package to remove project-specific dependencies for better reusability

### Fixes
- Fixed deep inspection showing misleading "disk encryption detected" error when user cancels inspection
- Fixed deep inspection failures incorrectly displayed as "Canceled" instead of "Error" in the UI
- Fixed storage offload estimator failures on multi-datacenter vCenter environments
- Fixed agent intermittently hanging on group and batch VM operations due to database deadlock
- Fixed VM selection not clearing after bulk label and group actions
- Fixed newly added labels and groups not displaying when Labels/Groups column is sorted
- Fixed filtering by deep inspection status causing other pages to appear empty
- Fixed export button not appearing when report is not shared with Red Hat
- Fixed export generation failing with 500 error when exporting all scopes
- Fixed chart legend text being too small and inconsistent across dashboard cards
- Fixed report comparison empty state button spacing
- Fixed generic error message when running a new report during deep inspection
- Fixed VDDK upload returning "internal server error" when a report is in progress
- Fixed out-of-memory error when retrieving VM detail endpoint
- Fixed "With issues breakdown" VM migration status loading slowly due to N+1 API calls
- Fixed container build installing RPMs without GPG signature verification and fetching remote artifacts without integrity checks
- Improved deep inspection status reporting by including inspection state in VM detail endpoint

## Console changes

### API changes (not yet available in the UI)
- Added assessment enhancement data endpoints for storing user-provided VMA data that cannot be auto-collected
- Added vMotion and Storage vMotion capability flags to host inventory data
- Added created_at timestamp to inventory records for tracking when data was collected
- Added HA Enabled (High Availability) cluster feature to inventory data

### Fixes
- Fixed environment status staying on "Uploaded manually" after agent switches to connected mode
- Improved appliance and assessment status displays with clearer labels and icons
- Fixed compact cluster sizing recommendation failing even when using recommended control plane resources
- Fixed storage I/O configuration returning null instead of actual values from vCenter
