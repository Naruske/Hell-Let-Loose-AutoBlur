import subprocess
import sys

# List of required libraries
required_libraries = [
    'pyautogui',
    'numpy',
    'mss',
    'Pillow',
    'obsws-python',
]

# Function to install missing libraries
def install_libraries(libraries):
    for library in libraries:
        try:
            __import__(library)
        except ImportError:
            print(f"Installing {library}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", library])

# Install required libraries if they are not already installed
install_libraries(required_libraries)

import json
import time
import pyautogui
import numpy as np
from mss import mss
from PIL import Image
from obsws_python import ReqClient

CONFIG_FILE = "obs_config.json"

# Function to load OBS configuration from JSON
def load_obs_config(filename=CONFIG_FILE):
    try:
        with open(filename, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        print("Configuration file not found, please enter settings.")
        return None

# Function to save OBS configuration, including captured color block and coordinates, to JSON
def save_obs_config(config, filename=CONFIG_FILE):
    # Convert any numpy int64 to regular Python int
    if "color_block" in config:
        config["color_block"]["color"] = tuple(int(c) for c in config["color_block"]["color"])
    
    if "coordinates" in config:
        config["coordinates"]["x"] = int(config["coordinates"]["x"])
        config["coordinates"]["y"] = int(config["coordinates"]["y"])

    with open(filename, 'w') as file:
        json.dump(config, file, indent=4)

# Function to get average color of a block of pixels at a specific location
def get_average_color(x, y, width=15, height=15):
    with mss() as sct:
        # Define the capture region for the 15x15 block
        monitor = {"top": y, "left": x, "width": width, "height": height}
        screenshot = sct.grab(monitor)

        # Convert the screenshot to a PIL Image to access pixel data
        img = Image.frombytes('RGB', (width, height), screenshot.rgb)
        
        # Convert to numpy array to process the pixel data
        img_array = np.array(img)
        
        # Calculate the average color of the block (mean of all pixels)
        avg_color = np.mean(img_array, axis=(0, 1)).astype(int)  # Average over the block's width and height
        
    return tuple(avg_color)

# Function to compare two colors with a tolerance for small variations
def compare_colors(color1, color2, tolerance=10):
    diff = np.abs(np.array(color1) - np.array(color2))
    return np.all(diff <= tolerance)

# Function to toggle filter based on color change
def toggle_filter(client, enable, scene_name, source_name, filter_name):
    """Enable or disable the filter based on the captured color."""
    try:
        filter_response = client.get_source_filter(source_name, filter_name)

        # Check the current filter state
        current_state = filter_response.filter_enabled
        if current_state == enable:
            print(f"Filter is already {'enabled' if enable else 'disabled'}.")
            return

        # Toggle the filter state
        client.set_source_filter_enabled(source_name, filter_name, enable)
        print(f"Filter {'enabled' if enable else 'disabled'}.")
    except Exception as e:
        print(f"Error toggling filter: {e}")

# Function to toggle source visibility
def toggle_source_visibility(client, scene_name, source_name, enable):
    """Toggle the visibility of the source based on the enable flag."""
    try:
        # Get the scene item ID for the source
        response = client.get_scene_item_id(scene_name, source_name)

        # Access the correct attribute 'scene_item_id' (not 'sceneItemId')
        scene_item_id = response.scene_item_id

        # Get the current visibility state
        visibility_response = client.get_scene_item_enabled(scene_name, scene_item_id)

        # Access the correct attribute for visibility
        current_visibility = visibility_response.scene_item_enabled

        # Only toggle if the current state is different from the desired state
        if current_visibility != enable:
            client.set_scene_item_enabled(scene_name, scene_item_id, enable)
            print(f"Source '{source_name}' visibility toggled to {'visible' if enable else 'hidden'}.")
        else:
            print(f"Source '{source_name}' is already in the desired visibility state.")

    except Exception as e:
        print(f"Error toggling source visibility: {e}")

def main():
    # Load OBS configuration or prompt user for input
    obs_config = load_obs_config()
    if not obs_config:
        # Prompt for OBS WebSocket settings
        obs_config = {
            "host": input("Enter OBS WebSocket Host: "),
            "port": int(input("Enter OBS WebSocket Port: ")),
            "password": input("Enter OBS WebSocket Password: "),
        }
        
        # Ask user whether they want to toggle a filter or visibility
        toggle_choice = input("Choose (1) Filter or (2) Source Visibility: ")
        
        if toggle_choice == "1":
            obs_config["toggle_type"] = "filter"
            obs_config["scene"] = input("Enter the scene name: ")
            obs_config["source"] = input("Enter the source name (Your Hell Let Loose game): ")
            obs_config["filter"] = input("Enter the filter name to toggle: ")
        elif toggle_choice == "2":
            obs_config["toggle_type"] = "visibility"
            obs_config["scene"] = input("Enter the scene name: ")
            obs_config["source"] = input("Enter the source name of the image you want to toggle on and off: ")
        else:
            print("Invalid choice. Exiting...")
            return
        
        # Ask for the color block region to monitor
        input("Place your mouse on the beige color of the welcome screen in the bottom right of your deploy screen and press Enter to capture color block.")
        x, y = pyautogui.position()
        captured_color = get_average_color(x, y)
        obs_config["coordinates"] = {"x": x, "y": y}
        obs_config["color_block"] = {"color": captured_color, "width": 15, "height": 15}
        save_obs_config(obs_config)  # Save the updated configuration
        print(f"Captured color block at ({x}, {y}): {captured_color}")
    else:
        # Load previously saved settings
        x = obs_config["coordinates"]["x"]
        y = obs_config["coordinates"]["y"]
        captured_color = tuple(obs_config["color_block"]["color"])
        print(f"Using saved color block at ({x}, {y}): {captured_color}")

    # Color to search for (black screen)
    black_color = (0, 0, 0)
    captured_color_detected = False
    black_last_checked = time.time()
    color_lost_time = None

    # Initialize the ReqClient with the WebSocket configuration
    client = ReqClient(host=obs_config["host"], port=obs_config["port"], password=obs_config["password"])

    try:
        while True:
            current_time = time.time()

            # Step 1: Check for black every 4 seconds if not already in captured color mode
            if not captured_color_detected and current_time - black_last_checked >= 4:
                current_color = get_average_color(x, y)
                print(f"Checking for black... Current color: {current_color}")

                if compare_colors(current_color, black_color):
                    print("Black screen detected! Switching to captured color monitoring...")
                    captured_color_detected = True
                black_last_checked = current_time

            # Step 2: If black is detected, check for the captured color every 0.1 seconds
            if captured_color_detected:
                current_color = get_average_color(x, y)
                print(f"Checking for captured color... Current color: {current_color}")

                if compare_colors(current_color, captured_color):
                    # Captured color is still present
                    print("Captured color detected.")
                    color_lost_time = None
                    if obs_config["toggle_type"] == "filter":
                        toggle_filter(client, True, obs_config["scene"], obs_config["source"], obs_config["filter"])
                    elif obs_config["toggle_type"] == "visibility":
                        toggle_source_visibility(client, obs_config["scene"], obs_config["source"], True)
                else:
                    # Captured color is no longer present; disable the filter or visibility immediately
                    print("Captured color no longer found! Disabling...")
                    if obs_config["toggle_type"] == "filter":
                        toggle_filter(client, False, obs_config["scene"], obs_config["source"], obs_config["filter"])
                    elif obs_config["toggle_type"] == "visibility":
                        toggle_source_visibility(client, obs_config["scene"], obs_config["source"], False)

                    # Start the timer to revert to black detection
                    if color_lost_time is None:
                        color_lost_time = current_time
                    elif current_time - color_lost_time >= 20:
                        print("Captured color not found for 20 seconds. Reverting to black detection.")
                        captured_color_detected = False

                time.sleep(0.1)

            else:
                # Sleep briefly to avoid busy-waiting
                time.sleep(0.1)

    except KeyboardInterrupt:
        print("Exiting...")

if __name__ == "__main__":
    main()
