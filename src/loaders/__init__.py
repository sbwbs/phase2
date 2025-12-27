"""
Loaders package for specialized translation resource loading
"""

from .greencross_glossary_loader import GreenCrossGlossaryLoader
from .tmx_memory_loader import TMXMemoryLoader

__all__ = ["GreenCrossGlossaryLoader", "TMXMemoryLoader"]
