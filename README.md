Gallery Builder
Built with the assistance of ChatGPT

## Features

Gallery Builder will take images, videos or a mix of images and videos and create and html based gallery view of the files. 

	-Browse to the folder of images, videos or combination of images and videos.
	-Input a Page Title. Defaults to Photo Gallery.
	-Input an Output HTML name. Defaults to index.html.
	-Click Build Photo Gallery, Build Video Gallery, or Build Mixed Gallery and the report will generate inside of the parent folder.

The generated HTML reveals a gallery view and video files can be played in the browser. Each file can be opened in a new tab with the "open in new tab" link.

Note: Some video file formats cannot be played inline in most browsers. In the gallery they appear with a poster image, but when clicked they will download to be opened in an external player.

## Requirements

-OS: Windows 10/11 (works on macOS/Linux too, but paths/buttons are written with Windows in mind).
-Python: CPython 3.9 – 3.12 installed and on PATH (python --version).
-Tkinter: Comes with standard Windows Python. (On Linux/mac, install the OS tk package if missing.)
-Web browser: Any modern browser (Chrome/Edge/Firefox/Safari) to open the generated HTML.

## Dependencies

-Standard library only for the GUI and HTML writing.
-Optional: Pillow (for image thumbnails).
		
	pip install -r requirements.txt

## External Tools

-FFmpeg (for video posters/thumbnails).
	Needed only if you check “Generate posters (ffmpeg)” in the Videos/Mixed tabs.
	Must be installed and on PATH so ffmpeg is found (ffmpeg -version).
	If missing, the app still works—posters are just skipped.


## Compile to executable

Windows OS

To create GalleryBuilder.exe run:
	py -m PyInstaller GalleryBuilderGUI.py --onefile --noconsole --name GalleryBuilder


## Usage

-GUI
	python GalleryBuilderGUI.py

