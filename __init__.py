import logging

from .synctile_nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

__version__ = "5.4"
logging.getLogger("SyncTile").info("SyncTile H3 nodes v%s loaded (space x time regions, long video, stream decode)", __version__)
print(f"[bruxosdovfx • SyncTile] v{__version__} carregado")

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
