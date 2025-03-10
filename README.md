# Hell Let Loose AutoBlur Map on Death

This script automatically applies a blur filter to the map in OBS when the player dies in the game *Hell Let Loose*, using the OBS WebSocket API. It monitors the player's screen for the appearance of a death screen (black screen) and then applies a blur effect or toggles the visibility of a source based on the user’s preference to cover the map.

Before running the script, make sure you have Python installed. If not, you can download it from [python.org](https://www.python.org/downloads/).

## How to run
Place the .py somewhere (Like your desktop in a folder)
Open a command prompt and navigate to the location (for ex., in CMD: cd c:\Users\Jan\Desktop\Autoblur)
Run the script by typing autoblur.py

## How it works
When the script starts it prompts you for the required OBS Websocket details and your preference of hiding the map (either by toggling an image source or a filter on your display or game capture).
It will ask you to place your mouse on the beige colour that is present in the Welcome box on the Deploy screen.
It will now save your preferences in a json file, where the script is located, so it can quickly start again without doing the configuration again.

Every 4 seconds it will check if the selected region is pitch black (RGB 0,0,0) and make sure the image source or filter is disabled (in case you manually turned it on and forgot to turn it off)
If the selected region is pitch black (death screen is detected) it will now check every 0.1 seconds if the color is detected that was configured at the beginning of the script.
If the color is detected it will toggle either the image source or the filter on your game source so the map is not visible or blurred.
If the color is not detected anymore it will remain in a state of checking every 0.1 seconds (in case you're changing loadout) before swapping back to checking for black every 4 seconds.

If you wish to reconfigure the script you can safely delete the obs_config.json.

## Requirements

- Python 3.7 or higher
- OBS Studio with the OBS WebSocket plugin installed
- An image source that perfectly covers the map or a filter ([I use pixelate from Composite Blur for performance](https://obsproject.com/forum/resources/composite-blur.1780/))
- Required Python libraries (the script will attempt to download these manually):
    - `obsws_python`
    - `pyautogui`
    - `numpy`
    - `mss`
    - `Pillow`

![Example](https://i.imgur.com/0DDzZ4B.png)

## Known issues
- Issue with screen region coordinates if there is display scaling active on the monitor where OBS is displayed.
- Issue if you move the OBS window after the script is running. It won't check the correct region anymore.
- No idea what the performance impact is
- The script is literally made with ChatGPT so I have no idea if it's best practice
- If you're changing your loadout for longer than 10 seconds it will return to scanning for black and thus not toggle the image source or filter
  You can change the time it scans for the captured color by editing this line:
                      elif current_time - color_lost_time >= **20**:
