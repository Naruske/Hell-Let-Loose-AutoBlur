import subprocess
import sys
import json
import time
import pyautogui
import numpy as np
from mss import mss
from PIL import Image
from obsws_python import ReqClient
from typing import Tuple, Dict, Any, Optional
import logging

# Constants
CHECK_BLACK_INTERVAL = 4  # seconds
CHECK_COLOR_INTERVAL = 0.1  # seconds
COLOR_BLOCK_SIZE = 15  # pixels
COLOR_TOLERANCE = 17  # Euclidean distance tolerance
REVERT_DELAY = 20  # seconds
CONFIG_FILE = "obs_config.json"

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def install_libraries(libraries: list) -> None:
    """Install required libraries if missing."""
    for lib in libraries:
        try:
            __import__(lib.split("==")[0])
        except ImportError:
            logging.info(f"Installing {lib}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", lib])

def load_obs_config(filename: str = CONFIG_FILE) -> Optional[Dict[str, Any]]:
    """Load and validate configuration file."""
    try:
        with open(filename, 'r') as f:
            config = json.load(f)
        
        required_keys = ["host", "port", "password", "toggle_type", "scene", "source",
                        "coordinates", "color_block", "screen_resolution"]
        if missing := [k for k in required_keys if k not in config]:
            logging.error(f"Missing keys: {', '.join(missing)}")
            return None
        
        current_w, current_h = pyautogui.size()
        if (config["screen_resolution"]["width"] != current_w or
            config["screen_resolution"]["height"] != current_h):
            logging.warning("Screen resolution mismatch - coordinates may be inaccurate")
        
        return config
    except FileNotFoundError:
        logging.warning("Configuration file not found")
        return None
    except Exception as e:
        logging.error(f"Config error: {e}")
        return None

def save_obs_config(config: Dict[str, Any], filename: str = CONFIG_FILE) -> None:
    """Save configuration with type conversions."""
    try:
        # Convert numpy types and ensure serializability
        config["color_block"]["color"] = [int(c) for c in config["color_block"]["color"]]
        config["coordinates"] = {k: int(v) for k, v in config["coordinates"].items()}
        config["screen_resolution"] = {
            "width": int(pyautogui.size()[0]),
            "height": int(pyautogui.size()[1])
        }
        
        with open(filename, 'w') as f:
            json.dump(config, f, indent=4)
        logging.info(f"Configuration saved to {filename}")
    except Exception as e:
        logging.error(f"Error saving config: {e}")

def get_average_color(sct: mss, x: int, y: int, 
                     width: int = COLOR_BLOCK_SIZE, 
                     height: int = COLOR_BLOCK_SIZE) -> Tuple[int, int, int]:
    """Capture and average color from screen region."""
    monitor = {"top": y, "left": x, "width": width, "height": height}
    screenshot = sct.grab(monitor)
    img = Image.frombytes("RGB", (width, height), screenshot.rgb)
    return tuple(np.array(img).mean(axis=(0, 1)).astype(int))

def compare_colors(color1: Tuple[int, int, int], 
                  color2: Tuple[int, int, int], 
                  tolerance: int = COLOR_TOLERANCE) -> bool:
    """Compare colors using Euclidean distance."""
    return np.linalg.norm(np.array(color1) - np.array(color2)) <= tolerance

def toggle_filter(client: ReqClient, enable: bool, scene: str, source: str, 
                 filter_name: str, retries: int = 3) -> None:
    """Toggle filter with retry logic."""
    for _ in range(retries):
        try:
            current = client.get_source_filter(source, filter_name).filter_enabled
            if current != enable:
                client.set_source_filter_enabled(source, filter_name, enable)
                logging.info(f"Filter {'enabled' if enable else 'disabled'}")
            return
        except Exception as e:
            logging.warning(f"Filter toggle failed: {e}")
            time.sleep(1)
    logging.error("Failed to toggle filter after retries")

def toggle_source_visibility(client: ReqClient, scene: str, source: str, 
                            enable: bool, retries: int = 3) -> None:
    """Toggle source visibility with retry logic."""
    for _ in range(retries):
        try:
            item_id = client.get_scene_item_id(scene, source).scene_item_id
            current = client.get_scene_item_enabled(scene, item_id).scene_item_enabled
            if current != enable:
                client.set_scene_item_enabled(scene, item_id, enable)
                logging.info(f"Source {'visible' if enable else 'hidden'}")
            return
        except Exception as e:
            logging.warning(f"Visibility toggle failed: {e}")
            time.sleep(1)
    logging.error("Failed to toggle visibility after retries")

def toggle_obs_element(client: ReqClient, config: Dict[str, Any], enable: bool) -> None:
    """Toggle OBS element based on config."""
    try:
        if config["toggle_type"] == "filter":
            toggle_filter(client, enable, config["scene"], 
                         config["source"], config["filter"])
        else:
            toggle_source_visibility(client, config["scene"], 
                                    config["source"], enable)
    except KeyError as e:
        logging.error(f"Invalid config: Missing {e}")

def setup_config() -> Dict[str, Any]:
    """Interactive configuration setup."""
    config = {}
    print("\n--- OBS Configuration Setup ---")
    
    config["host"] = input("OBS WebSocket Host [localhost]: ") or "localhost"
    
    while True:
        port = input("OBS WebSocket Port [4455]: ") or "4455"
        if port.isdigit():
            config["port"] = int(port)
            break
        print("Invalid port number")
    
    config["password"] = input("OBS WebSocket Password: ")
    
    print("\nChoose element to toggle:")
    choice = input("1. Filter\n2. Source Visibility\nChoice: ")
    config["toggle_type"] = "filter" if choice == "1" else "visibility"
    
    config["scene"] = input("Scene name: ")
    config["source"] = input("Source name (If choice was filter, choose the Hell Let Loose Source,. If choice was source visibility, type the image source you wish to toggle: ")
    
    if config["toggle_type"] == "filter":
        config["filter"] = input("Filter name: ")
    
    input("\nPosition mouse on target color and press Enter...")
    x, y = pyautogui.position()
    
    with mss() as sct:
        color = get_average_color(sct, x, y)
        config["color_block"] = {
            "color": [int(c) for c in color],
            "width": COLOR_BLOCK_SIZE,
            "height": COLOR_BLOCK_SIZE
        }
    
    config["coordinates"] = {"x": x, "y": y}
    save_obs_config(config)
    logging.info(f"Captured color at ({x}, {y}): {config['color_block']['color']}")
    return config

def monitor_color(client: ReqClient, config: Dict[str, Any]) -> None:
    """Main monitoring loop."""
    x = config["coordinates"]["x"]
    y = config["coordinates"]["y"]
    target_color = tuple(config["color_block"]["color"])
    
    state = "detecting_black"
    color_lost_time = None
    filter_enabled = False  # Track filter state
    
    try:
        with mss() as sct:
            while True:
                current_color = get_average_color(sct, x, y)
                
                if state == "detecting_black":
                    if compare_colors(current_color, (0, 0, 0)):
                        logging.info("Black detected - monitoring color")
                        state = "monitoring_color"
                        filter_enabled = True
                        toggle_obs_element(client, config, True)
                    time.sleep(CHECK_BLACK_INTERVAL)
                
                elif state == "monitoring_color":
                    if compare_colors(current_color, target_color):
                        if not filter_enabled:
                            logging.info("Target color detected - enabling filter")
                            toggle_obs_element(client, config, True)
                            filter_enabled = True
                        color_lost_time = None
                    else:
                        if color_lost_time is None:
                            logging.info("Color lost - starting timer")
                            toggle_obs_element(client, config, False)
                            filter_enabled = False
                            color_lost_time = time.time()
                        elif time.time() - color_lost_time >= REVERT_DELAY:
                            logging.info("Reverting to black detection")
                            state = "detecting_black"
                            color_lost_time = None
                        else:
                            remaining = REVERT_DELAY - (time.time() - color_lost_time)
                            logging.debug(f"Color still missing ({remaining:.1f}s remaining)")
                    time.sleep(CHECK_COLOR_INTERVAL)
    
    except KeyboardInterrupt:
        logging.info("Monitoring stopped")

def main():
    """Main application flow."""
    install_libraries([
        "pyautogui",
        "numpy",
        "mss",
        "Pillow",
        "obsws-python"
    ])
    
    if not (config := load_obs_config()):
        config = setup_config()
    
    try:
        client = ReqClient(
            host=config["host"],
            port=config["port"],
            password=config["password"]
        )
        client.get_version()  # Test connection
    except Exception as e:
        logging.error(f"OBS connection failed: {e}")
        if input("Reconfigure? (y/n): ").lower() == 'y':
            config = setup_config()
            client = ReqClient(**{k: config[k] for k in ["host", "port", "password"]})
        else:
            sys.exit(1)
    
    try:
        monitor_color(client, config)
    except KeyboardInterrupt:
        logging.info("Exiting...")
    finally:
        client.disconnect()

if __name__ == "__main__":
    main()