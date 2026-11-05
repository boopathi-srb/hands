"""HTTP API for the web UI (contract: docs/API.md), served by `hands serve`.

- `app`       create_api_app: routes, shared operator console at /console, built UI at /
- `runs`      RunManager: background discovery/replay runs, one at a time, plus runs found on disk
- `settings`  ApiSettings.from_env and seeding an empty data dir with the repo's artifacts
- `serve`     run the API and the CoreOne mock app as two uvicorn servers on one event loop
"""

from hands.api.app import ApiDependencies, create_api_app
from hands.api.settings import ApiSettings

__all__ = ["ApiDependencies", "ApiSettings", "create_api_app"]
