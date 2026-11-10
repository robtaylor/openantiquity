"""HTTP routers, one module per domain.

`create_app()` imports every module in this package. A module that defines
`router` has it mounted under `/api/v1`, or at the root when the module also
sets `MOUNT_AT_ROOT = True` (tile endpoints do, so a CDN can cache them by
path). Modules without a `router`, such as `deps`, are left alone.

Routers stay thin: read the request, call a service, commit, shape the reply.
"""
