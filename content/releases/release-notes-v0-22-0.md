---
title: "release notes v0.22.0"
linkTitle: "release notes v0.22.0"
date: 2026-08-27
type: docs
---

# OpenShift Migration Advisor — release notes — `v0.22.0`

Compare: `v0.21.0` → `v0.22.0`

## Appliance changes

### Fixes
- Fixed VM details page not displaying inspection status
- Fixed dashboard card scrolling behavior and undefined metrics in forecaster results
- Fixed DRS configuration reporting to use correct RVTools data columns
- Fixed agent-collected inventory to include DRS enablement status and default VM behavior
- Fixed agent-collected inventory to include cluster HA enablement status
- Fixed cancel deep inspection button not stopping running inspections

## Console changes

### Features
- Added remove customer action to partner UI
- Added in-app notifications for assessment creation, sharing, and partnership events

### API changes (not yet available in the UI)
- Added average VMs per host metric to inventory API

### Fixes
- Fixed upload alert banners appearing in inconsistent positions
- Fixed DRS configuration reporting to use correct RVTools data columns
- Fixed inventory to include DRS enablement status and default VM behavior
