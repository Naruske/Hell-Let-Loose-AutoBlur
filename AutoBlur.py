import subprocess
import sys
import json
import time
import pyautogui
import numpy as np
from mss import mss
from PIL import Image
from obsws_python import ReqClient
from typing import Tuple, Dict, Any
import logging

# Constants
CHECK_BLACK_INTERVAL = 4  # seconds
CHECK_COLOR_INTERVAL = 0.1  # seconds
COLOR_BLOCK_SIZE = 15  # pixels
COLOR_TOLERANCE = 10
REVERT_DELAY = 20  # seconds
CONFIG_FILE = "obs_config.json"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def install_libraries(libraries: list) -> None:
    for library in libraries:
        try:
            __import__(library)
        except ImportError:
            logging.info(f"Installing {library}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", library])

# List of required libraries
required_libraries = [
    'pyautogui',
    'numpy',
    'mss',
    'Pillow',
    'obsws-python',
]

install_libraries(required_libraries)

def load_obs_config(filename: str = CONFIG_FILE) -> Dict[str, Any]:
    """Load OBS configuration from JSON file."""
    try:
        with open(filename, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        logging.warning("Configuration file not found, prompting user for settings.")
        return None

def save_obs_config(config: Dict[str, Any], filename: str = CONFIG_FILE) -> None:
    """Save OBS configuration to JSON file."""
    if "color_block" in config:
        config["color_block"]["color"] = tuple(int(c) for c in config["color_block"]["color"])
    
    if "coordinates" in config:
        config["coordinates"]["x"] = int(config["coordinates"]["x"])
        config["coordinates"]["y"] = int(config["coordinates"]["y"])

    with open(filename, 'w') as file:
        json.dump(config, file, indent=4)

def get_average_color(x: int, y: int, width: int = COLOR_BLOCK_SIZE, height: int = COLOR_BLOCK_SIZE) -> Tuple[int, int, int]:
    """Get average color of a block of pixels at a specific location."""
    with mss() as sct:
        monitor = {"top": y, "left": x, "width": width, "height": height}
        screenshot = sct.grab(monitor)
        img = Image.frombytes('RGB', (width, height), screenshot.rgb)
        img_array = np.array(img)
        avg_color = np.mean(img_array, axis=(0, 1)).astype(int)
    return tuple(avg_color)

def compare_colors(color1: Tuple[int, int, int], color2: Tuple[int, int, int], tolerance: int = COLOR_TOLERANCE) -> bool:
    """Compare two colors with a tolerance for small variations."""
    diff = np.abs(np.array(color1) - np.array(color2))
    return np.all(diff <= tolerance)

def toggle_filter(client: ReqClient, enable: bool, scene_name: str, source_name: str, filter_name: str) -> None:
    """Enable or disable the filter based on the captured color."""
    try:
        filter_response = client.get_source_filter(source_name, filter_name)
        current_state = filter_response.filter_enabled
        if current_state != enable:
            client.set_source_filter_enabled(source_name, filter_name, enable)
            logging.info(f"Filter {'enabled' if enable else 'disabled'}.")
        else:
            logging.info(f"Filter is already {'enabled' if enable else 'disabled'}.")
    except Exception as e:
        logging.error(f"Error toggling filter: {e}")

def toggle_source_visibility(client: ReqClient, scene_name: str, source_name: str, enable: bool) -> None:
    """Toggle the visibility of the source based on the enable flag."""
    try:
        response = client.get_scene_item_id(scene_name, source_name)
        scene_item_id = response.scene_item_id
        visibility_response = client.get_scene_item_enabled(scene_name, scene_item_id)
        current_visibility = visibility_response.scene_item_enabled

        if current_visibility != enable:
            client.set_scene_item_enabled(scene_name, scene_item_id, enable)
            logging.info(f"Source '{source_name}' visibility toggled to {'visible' if enable else 'hidden'}.")
        else:
            logging.info(f"Source '{source_name}' is already in the desired visibility state.")
    except Exception as e:
        logging.error(f"Error toggling source visibility: {e}")

def setup_config() -> Dict[str, Any]:
    """Set up OBS configuration interactively if not available."""
    config = {
        "host": input("Enter OBS WebSocket Host: "),
        "port": int(input("Enter OBS WebSocket Port: ")),
        "password": input("Enter OBS WebSocket Password: "),
    }
    
    toggle_choice = input("Choose (1) Filter or (2) Source Visibility: ")
    if toggle_choice == "1":
        config["toggle_type"] = "filter"
        config["scene"] = input("Enter the scene name: ")
        config["source"] = input("Enter the source name (Your Hell Let Loose game): ")
        config["filter"] = input("Enter the filter name to toggle: ")
    elif toggle_choice == "2":
        config["toggle_type"] = "visibility"
        config["scene"] = input("Enter the scene name: ")
        config["source"] = input("Enter the source name of the image you want to toggle on and off: ")
    else:
        logging.error("Invalid choice. Exiting...")
        sys.exit(1)
    
    input("Place your mouse on the beige color of the welcome screen in the bottom right of your deploy screen and press Enter to capture color block.")
    x, y = pyautogui.position()
    captured_color = get_average_color(x, y)
    config["coordinates"] = {"x": x, "y": y}
    config["color_block"] = {"color": captured_color, "width": COLOR_BLOCK_SIZE, "height": COLOR_BLOCK_SIZE}
    save_obs_config(config)
    logging.info(f"Captured color block at ({x}, {y}): {captured_color}")
    return config

def monitor_color(client: ReqClient, config: Dict[str, Any]) -> None:
    """Monitor screen color changes and react accordingly."""
    x, y = config["coordinates"]["x"], config["coordinates"]["y"]
    captured_color = tuple(config["color_block"]["color"])
    black_color = (0, 0, 0)
    captured_color_detected = False
    black_last_checked = time.time()
    color_lost_time = None

    try:
        while True:
            current_time = time.time()

            if not captured_color_detected:
                if current_time - black_last_checked >= CHECK_BLACK_INTERVAL:
                    current_color = get_average_color(x, y)
                    logging.info(f"Checking for black... Current color: {current_color}")
                    if compare_colors(current_color, black_color):
                        logging.info("Black screen detected! Switching to captured color monitoring...")
                        captured_color_detected = True
                    black_last_checked = current_time

                time.sleep(CHECK_COLOR_INTERVAL)
                continue

            if captured_color_detected:
                current_color = get_average_color(x, y)
                logging.info(f"Checking for captured color... Current color: {current_color}")
                if compare_colors(current_color, captured_color):
                    # Reset color_lost_time when color is detected again
                    color_lost_time = None
                    if config["toggle_type"] == "filter":
                        toggle_filter(client, True, config["scene"], config["source"], config["filter"])
                    elif config["toggle_type"] == "visibility":
                        toggle_source_visibility(client, config["scene"], config["source"], True)
                else:
                    if color_lost_time is None:
                        logging.info("Captured color no longer found! Disabling...")
                        if config["toggle_type"] == "filter":
                            toggle_filter(client, False, config["scene"], config["source"], config["filter"])
                        elif config["toggle_type"] == "visibility":
                            toggle_source_visibility(client, config["scene"], config["source"], False)
                        
                        color_lost_time = current_time  # Start or restart the 20-second countdown
                    else:
                        if current_time - color_lost_time >= REVERT_DELAY:
                            logging.info("Captured color not found for 20 seconds. Reverting to black detection.")
                            captured_color_detected = False
                            # Reset black_last_checked to ensure immediate check for black next cycle
                            black_last_checked = current_time
                            color_lost_time = None  # Reset for next cycle if black is detected again

                time.sleep(CHECK_COLOR_INTERVAL)

    except KeyboardInterrupt:
        logging.info("Exiting...")

def main():
    obs_config = load_obs_config()
    if not obs_config:
        obs_config = setup_config()
    else:
        logging.info(f"Using saved color block at ({obs_config['coordinates']['x']}, {obs_config['coordinates']['y']}): {tuple(obs_config['color_block']['color'])}")

    client = ReqClient(host=obs_config["host"], port=obs_config["port"], password=obs_config["password"])
    monitor_color(client, obs_config)

if __name__ == "__main__":
    main()