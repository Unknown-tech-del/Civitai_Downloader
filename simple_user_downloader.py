#!/usr/bin/env python
import httpx
import os
import asyncio
import aiofiles
from tqdm import tqdm
import sys
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# --- Constants ---
BASE_API_URL = "https://civitai.com/api/v1/images"
# Start with base headers
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}
CONCURRENT_DOWNLOADS = 5
RETRYABLE_EXCEPTIONS = (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
    reraise=True
)
async def fetch_api_page(client: httpx.AsyncClient, url: str) -> dict:
    """Fetches a single page from the API with automatic retries for network errors."""
    response = await client.get(url, timeout=30)
    if 500 <= response.status_code < 600:
        response.raise_for_status()
    return response.json()

async def fetch_image_list(client: httpx.AsyncClient, username: str) -> list:
    """Fetches the complete list of image data using cursor-based pagination."""
    all_images = []
    page_num = 1
    
    base_url = f"{BASE_API_URL}?username={username}&nsfw=X&sort=Newest&period=AllTime&limit=100"
    next_cursor = None

    while True: 
        current_url = f"{base_url}&cursor={next_cursor}" if next_cursor else base_url
            
        try:
            print(f"Fetching images (Batch {page_num})...")
            data = await fetch_api_page(client, current_url)
            
            items = data.get('items', [])
            if not items and page_num == 1:
                print(f"User '{username}' found, but they have no public images.")
                return []
            
            all_images.extend(items)
            
            next_cursor = data.get('metadata', {}).get('nextCursor')
            print(f"Found {len(all_images)} images so far...")

            if not next_cursor:
                break
                
            page_num += 1
            await asyncio.sleep(1) 

        except Exception as e:
            print(f"\nFailed to fetch image batch {page_num}: {e}. Stopping.")
            break
            
    print(f"Found a total of {len(all_images)} images for {username}.")
    return all_images

async def download_image(session: httpx.AsyncClient, image_data: dict, output_dir: str, semaphore: asyncio.Semaphore):
    """Downloads a single image into the specified directory."""
    image_url = image_data.get('url')
    image_id = image_data.get('id')

    if not image_url or not image_id: return

    file_extension = os.path.splitext(image_url.split('?')[0])[-1]
    if not file_extension or len(file_extension) > 5: file_extension = ".png"
    file_path = os.path.join(output_dir, f"{image_id}{file_extension}")

    if os.path.exists(file_path): return

    async with semaphore:
        try:
            @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS))
            async def do_download():
                async with session.stream("GET", image_url, follow_redirects=True, timeout=300.0) as response:
                    response.raise_for_status()
                    total_size = int(response.headers.get('content-length', 0))
                    
                    progress_bar = tqdm(total=total_size, unit='B', unit_scale=True, desc=f"Downloading {image_id}", leave=False)
                    async with aiofiles.open(file_path, "wb") as f:
                        async for chunk in response.aiter_bytes():
                            await f.write(chunk)
                            progress_bar.update(len(chunk))
                    progress_bar.close()
            await do_download()
        except Exception as e:
            print(f"\nFailed to download image {image_id} after multiple attempts: {e}")

async def main():
    """Main function to run the downloader."""
    username = input("Enter the Civitai username to download from: ").strip()
    if not username:
        print("Username cannot be empty.")
        return

    # Try to read API key from file
    api_key_file = "civitai_api_key.txt"
    api_key = None

    if os.path.exists(api_key_file):
        with open(api_key_file, "r", encoding="utf-8") as f:
            api_key = f.read().strip()
        if api_key:
            print(f"API Key loaded from '{api_key_file}'. Using authenticated requests.")
        else:
            print(f"'{api_key_file}' found but it is empty. Proceeding with public access.")
    else:
        print(f"API key file '{api_key_file}' not found. Proceeding with public access.")

    if api_key:
        DEFAULT_HEADERS['Authorization'] = f'Bearer {api_key}'

    output_dir = os.path.join(".", username)
    os.makedirs(output_dir, exist_ok=True)
    print(f"Images will be saved in: {os.path.abspath(output_dir)}")

    semaphore = asyncio.Semaphore(CONCURRENT_DOWNLOADS)

    async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=60.0) as client:
        images_to_download = await fetch_image_list(client, username)

        if not images_to_download:
            print("No images to download. Exiting.")
            return

        tasks_to_run = []
        for img in images_to_download:
            image_id = img.get('id')
            if not image_id:
                continue

            image_url = img.get('url', '')
            file_extension = os.path.splitext(image_url.split('?')[0])[-1]
            if not file_extension or len(file_extension) > 5:
                file_extension = ".png"

            file_path = os.path.join(output_dir, f"{image_id}{file_extension}")
            if not os.path.exists(file_path):
                tasks_to_run.append(download_image(client, img, output_dir, semaphore))

        print(f"\nQueueing {len(tasks_to_run)} new images for download...")
        await asyncio.gather(*tasks_to_run)

    print("\n\nDownload process complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProcess interrupted by user.")
    except Exception as e:
        print(f"\nA critical error occurred: {e}")