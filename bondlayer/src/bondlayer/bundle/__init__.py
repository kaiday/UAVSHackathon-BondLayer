"""Dynamic bundling: composing matched proposals into sets.

The seam is ``bondlayer.types.Bundler``. See ``compose.py`` for what this does
and, more importantly, for what it refuses to do -- it never re-matches, and it
never crosses a merchant boundary.
"""

from bondlayer.bundle.compose import (
    RECIPES,
    CategoryBundler,
    Recipe,
    Slot,
    bundle_payload,
    compose,
    role_of,
)

__all__ = [
    "RECIPES",
    "CategoryBundler",
    "Recipe",
    "Slot",
    "bundle_payload",
    "compose",
    "role_of",
]
