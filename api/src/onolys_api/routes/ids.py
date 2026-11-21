"""Path id type: every resource id is `uuid4().hex`; anything else is a 422 before storage."""

from typing import Annotated

from fastapi import Path

ResourceId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]
