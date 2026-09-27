"""99blog command-line entry point."""

import argparse
from pathlib import Path
from typing import Optional, Sequence

import output
from config import ConfigError, configure, load_config
from images import find_local_images, replace_with_wordpress_urls
from post import Post, PostError, read_post
from wordpress import WordPressError, publish_post, resolve_categories


def ask_metadata(post: Post) -> tuple:
    try:
        title = input(f"Title [{post.title}]: ").strip() or post.title
        while True:
            status = input(f"Status (draft/publish) [{post.status}]: ").strip().lower() or post.status
            if status in ("draft", "publish"):
                break
            output.warning("Status must be draft or publish")
        default_categories = ", ".join(post.categories)
        default_label = default_categories or ("keep WordPress categories" if post.wp_id else "WordPress default")
        while True:
            entered = input(f"Categories (comma-separated; - to clear) [{default_label}]: ").strip()
            if not entered:
                categories = post.categories
                break
            if entered == "-":
                categories = []
                break
            categories = [name.strip() for name in entered.split(",") if name.strip()]
            if categories:
                break
            output.warning("Enter a category name, press Enter to keep, or use - to clear")
        return title, status, list(dict.fromkeys(categories))
    except EOFError as exc:
        raise PostError("Interactive input is required to confirm title, status, and categories") from exc


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="99blog", description="Publish a local Markdown post to WordPress")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("configure", help="Save WordPress credentials for this computer")
    publish = commands.add_parser("publish", help="Create or update a WordPress post")
    publish.add_argument("file", type=Path, help="Markdown source file")
    publish.add_argument("--dry-run", action="store_true", help="Preview without contacting WordPress or changing the file")
    args = parser.parse_args(argv)

    try:
        if args.command == "configure":
            path = configure()
            output.good(f"WordPress configuration saved to {path}")
            return 0
        output.status(f"Reading {args.file.name}...")
        post = read_post(args.file)
        html = post.html
        local_images = find_local_images(post, html)
        output.good("Markdown parsed")
        title, status, categories = ask_metadata(post)
        action = "Updating" if post.wp_id is not None else "Creating"
        if post.wp_id is not None:
            output.warning(f"Existing WordPress post #{post.wp_id}")
        if args.dry_run:
            output.status(f"Dry run: {action.lower()} '{title}' (status: {status}; categories: {', '.join(categories) or 'WordPress default'})")
            output.status(f"Local images: {len({image.key for image in local_images.values()})}")
            output.good(f"Generated {len(html)} HTML characters; no network or file changes")
            return 0

        config = load_config()
        category_ids = [] if categories != post.categories and not categories else None
        if categories:
            output.status(f"Resolving categories: {', '.join(categories)}...")
            category_ids = resolve_categories(config, categories)
            output.good("Categories: " + ", ".join(f"{name} (#{term_id})" for name, term_id in zip(categories, category_ids)))
        media_cache = post.wp_media
        if local_images:
            output.status("Uploading local images to WordPress...")
            html, media_cache, uploaded = replace_with_wordpress_urls(config, html, local_images, post.wp_media)
            output.good(f"Images: {uploaded} uploaded, {len({image.key for image in local_images.values()}) - uploaded} reused")
        output.status(f"{action} post on {config.url}...")
        returned_id, link = publish_post(config, title, html, status, post.wp_id, categories=category_ids)
        if post.wp_id is None or title != post.title or status != post.status or categories != post.categories or media_cache != post.wp_media:
            try:
                post.write_metadata(returned_id, title, status, categories, media_cache)
            except PostError:
                output.warning(f"WordPress accepted post #{returned_id}, but local metadata could not be saved. Add 'wp_id: {returned_id}' manually before retrying to avoid a duplicate.")
                raise
        output.good(f"{'Updated' if post.wp_id is not None else 'Published'} successfully")
        output.good(f"Post ID: {returned_id}")
        if link:
            output.good(f"URL: {link}")
        return 0
    except (PostError, ConfigError, WordPressError) as exc:
        output.error(str(exc))
        return 1
    except KeyboardInterrupt:
        output.warning("Cancelled")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
