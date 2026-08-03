import json
import os
from pathlib import Path
from typing import Dict, List, Set, Optional, Any
from src.config import config
from src.logger import logger

class CheckpointManager:
    def __init__(self):
        self.checkpoint_file = config.checkpoint_dir / "checkpoint.json"
        self.state: Dict[str, Any] = {
            "date": "",
            "completed_devices": [],
            "current_device": None,
            "downloaded_images": [],
            "failed_devices": {}
        }

    def load(self, target_date: str) -> Dict[str, Any]:
        """
        Loads the checkpoint state from disk.
        If the checkpoint is for a different date, resets the checkpoint for the new target date.
        """
        if not self.checkpoint_file.exists():
            self._reset(target_date)
            return self.state

        try:
            with open(self.checkpoint_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Check if checkpoint date matches current execution date
            if data.get("date") == target_date:
                self.state = data
                # Convert list to compatible format
                if "downloaded_images" not in self.state:
                    self.state["downloaded_images"] = []
                if "failed_devices" not in self.state:
                    self.state["failed_devices"] = {}
                logger.info(f"Loaded existing checkpoint. completed_devices={len(self.state['completed_devices'])}, current_device={self.state['current_device']}")
            else:
                logger.info(f"Checkpoint date '{data.get('date')}' does not match target date '{target_date}'. Resetting checkpoint.")
                self._reset(target_date)
        except Exception as e:
            logger.error(f"Error loading checkpoint file: {e}. Resetting to fresh state.")
            self._reset(target_date)

        return self.state

    def save(self):
        """Saves the current state to disk atomically using a temp file."""
        temp_file = self.checkpoint_file.with_suffix(".tmp")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=4)
            # Atomic swap
            os.replace(temp_file, self.checkpoint_file)
        except Exception as e:
            logger.error(f"Failed to write checkpoint file: {e}")

    def _reset(self, target_date: str):
        """Resets the state for a new date."""
        self.state = {
            "date": target_date,
            "completed_devices": [],
            "current_device": None,
            "downloaded_images": [],
            "failed_devices": {}
        }
        self.save()

    def mark_device_completed(self, device: str):
        """Adds a device to the completed list, clears current_device, and saves."""
        if device not in self.state["completed_devices"]:
            self.state["completed_devices"].append(device)
        self.state["current_device"] = None
        self.state["downloaded_images"] = []
        self.save()

    def set_current_device(self, device: str):
        """Sets the current device and saves."""
        self.state["current_device"] = device
        self.state["downloaded_images"] = []
        self.save()

    def add_downloaded_image(self, filename: str):
        """Records an image as downloaded for the current device."""
        if filename not in self.state["downloaded_images"]:
            self.state["downloaded_images"].append(filename)
            self.save()

    def mark_device_failed(self, device: str, reason: str):
        """Records a device failure with its reason, clears current_device, and saves."""
        self.state["failed_devices"][device] = reason
        self.state["current_device"] = None
        self.state["downloaded_images"] = []
        self.save()

    def clear(self):
        """Deletes the checkpoint file from disk and resets internal state."""
        if self.checkpoint_file.exists():
            try:
                self.checkpoint_file.unlink()
            except Exception as e:
                logger.error(f"Failed to delete checkpoint file: {e}")
        self._reset("")

# Instantiate global checkpoint manager
checkpoint_manager = CheckpointManager()
