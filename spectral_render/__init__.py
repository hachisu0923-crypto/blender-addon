"""Spectral Render -- pseudo-spectral rendering for Cycles via band compositing.

The manifest (blender_manifest.toml) drives the Extension metadata; this module
only wires registration together.
"""

from . import properties
from .ops import inject, presets, render, restore
from .ui import panel

# Order matters: properties (PropertyGroup + Scene pointer) before anything that
# draws or uses them; operators before the panel that lists them.
_MODULES = (properties, inject, restore, render, presets, panel)


def register():
    for module in _MODULES:
        module.register()


def unregister():
    for module in reversed(_MODULES):
        module.unregister()
