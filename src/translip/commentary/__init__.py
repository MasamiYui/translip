"""Commentary-script stage: generate an OST-interleaved movie-recap narration
script from a transcript (+ optional scene analysis) via a 3-stage LLM chain.

See :mod:`translip.commentary.chain` for the entry point
:func:`generate_commentary_script`. The atomic ``commentary-script`` tool is a
thin wrapper over it.
"""

from __future__ import annotations

from .chain import generate_commentary_script
from .inputs import StoryDocument, build_story_document, load_segments, load_visual_units
from .types import CommentaryItem, CommentaryOptions, CommentaryScript

__all__ = [
    "CommentaryItem",
    "CommentaryOptions",
    "CommentaryScript",
    "StoryDocument",
    "build_story_document",
    "generate_commentary_script",
    "load_segments",
    "load_visual_units",
]
