import shutil
import sys
import re
from pathlib import Path
from datetime import datetime
from src.config import config
from src.logger import logger

def _is_valid_gdrive_path(path: Path) -> bool:
    """Checks if the configured Google Drive sync directory is valid on the current OS."""
    if not path:
        return False
        
    path_str = str(path)
    
    # Check for Windows drive letter (e.g. G:\) on non-Windows platforms
    if sys.platform != "win32" and re.match(r"^[A-Za-z]:", path_str):
        logger.warning(
            f"Google Drive sync path '{path_str}' is a Windows drive path. "
            f"Skipping Drive sync on non-Windows platform ({sys.platform})."
        )
        return False

    # Check if parent or directory itself exists
    try:
        if path.exists() or path.parent.exists():
            return True
    except Exception as e:
        logger.warning(f"Error accessing Google Drive sync directory path '{path}': {e}")
        return False
        
    return False

def sync_to_gdrive(target_date_str: str = None) -> dict:
    """
    Resiliently synchronizes downloaded files from config.download_dir to config.gdrive_sync_dir.
    
    - Scans all date subdirectories (or target_date subfolder) in download_dir.
    - Copies each file individually using shutil.copy2 to handle transient locks.
    - Skips files that already exist at destination with matching file sizes.
    - Logs detailed sync progress and returns summary stats.
    """
    stats = {"synced": 0, "skipped": 0, "failed": 0, "folders_processed": 0}
    
    if not config.gdrive_sync_dir:
        logger.debug("Google Drive sync path not configured. Skipping sync.")
        return stats
        
    if not _is_valid_gdrive_path(config.gdrive_sync_dir):
        return stats

    download_root = config.download_dir
    if not download_root.exists():
        logger.debug(f"Download directory '{download_root}' does not exist. Nothing to sync.")
        return stats

    # Determine folders to sync
    folders_to_sync = []
    
    # Gather all subdirectories in download_root
    try:
        subdirs = [p for p in download_root.iterdir() if p.is_dir()]
    except Exception as e:
        logger.error(f"Failed to list subdirectories in '{download_root}': {e}")
        return stats

    if not subdirs:
        logger.debug(f"No subdirectories found in '{download_root}'. Nothing to sync.")
        return stats

    # Sort folders so latest date folders are processed first
    for subdir in sorted(subdirs, key=lambda p: p.name, reverse=True):
        folders_to_sync.append(subdir)

    logger.info(f"Starting Google Drive sync across {len(folders_to_sync)} download folder(s)...")

    for source_dir in folders_to_sync:
        stats["folders_processed"] += 1
        dest_dir = config.gdrive_sync_dir / source_dir.name
        
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
        except Exception as me:
            logger.error(f"Failed to create Google Drive destination folder '{dest_dir}': {me}")
            stats["failed"] += 1
            continue

        # Recursively walk through source_dir
        for source_file in source_dir.rglob("*"):
            if not source_file.is_file():
                continue

            rel_path = source_file.relative_to(source_dir)
            dest_file = dest_dir / rel_path

            try:
                # Ensure parent dir exists in destination
                dest_file.parent.mkdir(parents=True, exist_ok=True)

                # Check if file already exists at destination with same size
                if dest_file.exists():
                    try:
                        if dest_file.stat().st_size == source_file.stat().st_size:
                            stats["skipped"] += 1
                            continue
                    except Exception:
                        pass # Re-copy if size check fails

                # Copy file individually
                shutil.copy2(source_file, dest_file)
                stats["synced"] += 1
                logger.debug(f"Synced file to Google Drive: {dest_file.name}")
            except Exception as fe:
                stats["failed"] += 1
                logger.warning(f"Failed to sync '{source_file.name}' to Google Drive: {fe}")

    logger.info(
        f"Google Drive Sync Complete: {stats['synced']} new file(s) copied, "
        f"{stats['skipped']} skipped (already up to date), {stats['failed']} failed."
    )
    return stats
