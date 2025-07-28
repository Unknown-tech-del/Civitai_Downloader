# Civitai Downloader

This repository contains a small Python script for downloading images from the [Civitai](https://civitai.com/) API. The script prompts for a username and retrieves all public images uploaded by that user. Downloads are performed asynchronously with retry logic and a progress bar.

## Requirements
- Python 3.9 or newer
- Packages listed in `requirements.txt`

Install the dependencies with:

```bash
pip install -r requirements.txt
```

## Usage
Run the downloader from the command line:

```bash
python simple_tags_downloader.py
```

You will be asked for the Civitai username. Images are saved into a folder named after that user. Existing files are skipped.

For authenticated requests, place your API key in a file named `civitai_api_key.txt` in the same directory. The script will read it automatically.

## License
This project is provided as-is under the MIT License.
