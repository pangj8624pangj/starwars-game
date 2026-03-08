"""
Scrape restaurant names from @nycbutglutenfree Instagram posts using Instaloader.

Usage:
    pip install instaloader
    python scrape_restaurants.py

Optional: Log in for better rate limits (avoids 401 errors on public profiles):
    python scrape_restaurants.py --username YOUR_USERNAME --password YOUR_PASSWORD

Output:
    restaurants.json - structured list of restaurants with post metadata
    restaurants.txt  - simple list of unique restaurant names
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime

try:
    import instaloader
except ImportError:
    print("Install instaloader first: pip install instaloader")
    sys.exit(1)


TARGET_ACCOUNT = "nycbutglutenfree"


def extract_restaurant_names(caption: str) -> list[str]:
    """
    Extract restaurant names from a post caption using common patterns.

    Instagram food bloggers typically mention restaurant names by:
    - Starting the caption with the restaurant name
    - Using @ mentions for the restaurant's own account
    - Patterns like "at <Name>", "from <Name>", "<Name> -", etc.
    """
    restaurants = []

    if not caption:
        return restaurants

    # Pattern 1: @ mentions (often the restaurant's own IG handle)
    # Exclude common non-restaurant mentions like @nycbutglutenfree itself
    mentions = re.findall(r"@(\w+)", caption)
    skip_accounts = {TARGET_ACCOUNT, "nycbutglutenfree"}
    for mention in mentions:
        if mention.lower() not in skip_accounts:
            # Convert handle to readable name: "joes_pizza_nyc" -> "joes pizza nyc"
            readable = mention.replace("_", " ").replace(".", " ").strip()
            restaurants.append({"name": readable, "instagram": f"@{mention}", "source": "mention"})

    # Pattern 2: First line of caption is often the restaurant name
    first_line = caption.split("\n")[0].strip()
    # Remove emojis and special chars, keep if it looks like a name (short, no hashtags)
    clean_first_line = re.sub(r"[^\w\s&''\-/]", "", first_line).strip()
    if clean_first_line and len(clean_first_line) < 60 and "#" not in first_line:
        restaurants.append({"name": clean_first_line, "instagram": None, "source": "caption_title"})

    # Pattern 3: Look for "at <Restaurant>" or "from <Restaurant>"
    at_patterns = re.findall(r"(?:^|\s)(?:at|from|@)\s+([A-Z][A-Za-z&'\s\-]{2,30})(?:[.,!?\n]|$)", caption)
    for match in at_patterns:
        name = match.strip()
        if len(name) > 2:
            restaurants.append({"name": name, "instagram": None, "source": "at_pattern"})

    return restaurants


def scrape_account(username: str | None = None, password: str | None = None, max_posts: int = 0):
    """Scrape posts from the target account and extract restaurant info."""
    loader = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
    )

    # Login if credentials provided (helps avoid rate limiting)
    if username and password:
        print(f"Logging in as {username}...")
        try:
            loader.login(username, password)
        except instaloader.exceptions.BadCredentialsException:
            print("Login failed: bad credentials")
            sys.exit(1)
        except instaloader.exceptions.TwoFactorAuthRequiredException:
            print("Login failed: 2FA required. Use session file approach instead.")
            print("  1. Run: instaloader --login YOUR_USERNAME")
            print("  2. Then run this script with just --username YOUR_USERNAME")
            sys.exit(1)

    print(f"Loading profile @{TARGET_ACCOUNT}...")
    try:
        profile = instaloader.Profile.from_username(loader.context, TARGET_ACCOUNT)
    except instaloader.exceptions.ProfileNotExistsException:
        print(f"Profile @{TARGET_ACCOUNT} not found")
        sys.exit(1)

    print(f"Found {profile.mediacount} posts. Scanning captions...")

    all_restaurants = []
    posts_processed = 0

    try:
        for post in profile.get_posts():
            if max_posts and posts_processed >= max_posts:
                break

            caption = post.caption or ""
            location = post.location.name if post.location else None
            restaurants = extract_restaurant_names(caption)

            # Add location as a potential restaurant name
            if location:
                restaurants.append({"name": location, "instagram": None, "source": "geotag"})

            for r in restaurants:
                r["post_date"] = post.date_utc.isoformat()
                r["post_url"] = f"https://www.instagram.com/p/{post.shortcode}/"
                r["caption_preview"] = caption[:150].replace("\n", " ")

            all_restaurants.extend(restaurants)
            posts_processed += 1

            if posts_processed % 25 == 0:
                print(f"  Processed {posts_processed} posts, found {len(all_restaurants)} restaurant mentions...")

    except instaloader.exceptions.QueryReturnedNotFoundException:
        print("Rate limited or profile became private. Try again later or log in.")
    except KeyboardInterrupt:
        print(f"\nStopped early after {posts_processed} posts.")

    print(f"\nDone! Processed {posts_processed} posts, found {len(all_restaurants)} total mentions.")
    return all_restaurants


def deduplicate(restaurants: list[dict]) -> list[dict]:
    """Deduplicate restaurants by normalized name."""
    seen = {}
    for r in restaurants:
        key = r["name"].lower().strip()
        if key not in seen or r["source"] == "geotag":  # prefer geotag names
            seen[key] = r
    return sorted(seen.values(), key=lambda x: x["name"].lower())


def main():
    parser = argparse.ArgumentParser(description="Scrape restaurant recommendations from @nycbutglutenfree")
    parser.add_argument("--username", "-u", help="Instagram username for login (optional, helps with rate limits)")
    parser.add_argument("--password", "-p", help="Instagram password")
    parser.add_argument("--max-posts", "-n", type=int, default=0, help="Max posts to scan (0 = all)")
    args = parser.parse_args()

    restaurants = scrape_account(args.username, args.password, args.max_posts)
    unique = deduplicate(restaurants)

    # Save detailed JSON
    with open("restaurants.json", "w") as f:
        json.dump(unique, f, indent=2)
    print(f"\nSaved {len(unique)} unique restaurants to restaurants.json")

    # Save simple text list
    with open("restaurants.txt", "w") as f:
        for r in unique:
            ig = f" ({r['instagram']})" if r["instagram"] else ""
            f.write(f"{r['name']}{ig}\n")
    print(f"Saved simple list to restaurants.txt")


if __name__ == "__main__":
    main()
