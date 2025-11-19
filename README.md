
---
# Offline Mesh Analysis Plotter
---

**A Pygame-based Meshtastic / LoRa node visualizer** built for **offline SIGINT and field research**.

**OMAP** reads live serial data from a Meshtastic node (over `/dev/ttyACM*`) and turns it into a spatial network map showing GPS positions, mesh links, and signal reach in real time.

If you want to _see_ what your LoRa mesh is doing with positioning data strictly at the RF level, this is the tool. 

---
### Functions
---

- **Serial-only operation.** Reads directly from a connected Meshtastic device over USB.
    
- Designed for **offline telemetry, SIGINT work, and topology research** without dashboards that rely on the internet.
    
- Renders **GPS positions, link paths, hop counts, and packet ages** in a live map.
    
- Fully interactive **Pygame interface** for exploration and analysis.
	
- **NOTE** :  Nodes with the device role (CLIENT_HIDDEN) may still appear on the map. OMAP detects nodes based on the parameters for (REBROADCASTING) to be set to (ALL), or (LOCAL ONLY) if within the radius of a mesh network.

---
### Project Images
---

- **Visualized Node Data**

<img width="665" height="80" alt="image" src="https://github.com/user-attachments/assets/17b8bb5b-cbf1-419b-8f7c-595f8c8d9279" />

- **Mesh Topology**

<img width="966" height="841" alt="image" src="https://github.com/user-attachments/assets/e35a5af2-46f0-413f-b327-8463f14e2489" />

- **Node Callsigns**

<img width="601" height="456" alt="image" src="https://github.com/user-attachments/assets/8659b7ce-03a3-42b7-a41c-ecbf75c50205" />

- **Coordinate Tracker**

<img width="601" height="456" alt="image" src="https://github.com/user-attachments/assets/5bc26d6b-d7b9-41b8-9297-14f494c8417f" />

---
### Requirements
---

- Python 3.10+
    
- Pygame / Pyserial
	
- Meshtastic Node
	
- Meshtastic CLI 

Install all dependencies: 

---
### Install Dependencies
---

- **Debian or Ubuntu (Dependencies)**

		 sudo apt install pip && python3

- **Fedora or RHEL (Dependencies)**

		 sudo dnf install pip && python3

- **Install Pygame** 

		python3 -m pip install -U pygame --user

- **Meshtastic CLI**

	- There are several ways to download Meshtastic CLI depending on which OS you are currently using. You can find all steps here [Meshtastic CLI (Python Installation)](https://meshtastic.org/docs/software/python/cli/installation/)
--- 
### Launching the script
---

- **Add user to dialout group**

		sudo usermod -aG dialout "$USER"

		newgrp dialout

- **Run script with python**

		python3 OMAP-Radar.py

- **Suggestions**

	- For easier use in your CLI, make a bash script that runs (**OMAP-Radar.py**), then move it to **/bin/** so you can use the command (**omap**) anywhere throughout your CLI.

---
### Making a script for easier use (OPTIONAL)
---

 - **Create a new bash script** 

		sudo nano omap-radar.sh

- **Paste this skeleton script**

			#!/bin/bash
			cd /home/user/yourgitdirectory/omap-radar
			OMAP-Radar.py

- **Replace /home/user/yourgitdirectory/omap-radar**

	- In your current directory (where you cloned this repo), type **pwd**, then replace the parameters in the skeleton script above with your new script.

- **Make the script executable**

		sudo chmod +x omap-radar.sh
		

- **Now test the script to make sure it works**

		./omap-radar.sh

- **Move the script to bin**

		sudo mv omap-radar.sh /bin/omap

- **Now you should be able to use the command "omap" anywhere throughout your CLI**

---
### Controls
---

- **WASD / Arrows**   → pan map  
								
- **Left Click**             -> move around
								
- **Mouse wheel**      → zoom in/out  
								
- **L**                           → toggle labels  
								
- **F**                           → hide stale  
								
- **Shift+E**                 → toggle flow 
								
- **R**                           → toggle target  
								
- **ESC**                      → quit  
								

---
### Related Projects
---

For a robust **offline Meshtastic messenger**, check out [**meshtastic_terminal** by richstokes](https://github.com/richstokes/meshtastic_terminal)

---
