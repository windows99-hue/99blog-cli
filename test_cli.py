import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import Mock, patch

import main
from config import Config, load_config
from images import find_local_images, replace_with_wordpress_urls
from post import PostError, read_post
from sanitize import sanitize_html
from wordpress import WordPressError, publish_post, resolve_categories, upload_media


SOURCE = b'---\r\ntitle: "Test"\r\nstatus: draft\r\ntags:\r\n  - Python\r\nwp_id: # keep\r\n---\r\n\r\n# Heading\r\n\r\n```python\r\nprint(1)\r\n```\r\n'


class CliTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "post.md"
        self.path.write_bytes(SOURCE)

    def tearDown(self):
        self.directory.cleanup()

    def test_configure_can_be_used_outside_project_directory(self):
        settings = Path(self.directory.name) / "settings" / "config.env"
        other_directory = Path(self.directory.name) / "writing"
        other_directory.mkdir()
        with patch("config.user_config_path", return_value=settings), \
             patch("config.Path.cwd", return_value=other_directory), \
             patch.dict(os.environ, {}, clear=True), \
             patch("builtins.input", side_effect=["https://example.org/blog/", "writer"]), \
             patch("config.getpass", return_value="secret app password"):
            self.assertEqual(main.main(["configure"]), 0)
            self.assertEqual(
                load_config(),
                Config("https://example.org/blog", "writer", "secret app password"),
            )
        self.assertTrue(settings.is_file())
        self.assertIn('WORDPRESS_APP_PASSWORD="secret app password"', settings.read_text(encoding="utf-8"))

    def test_dry_run_does_not_use_network_or_modify_file(self):
        with patch("builtins.input", side_effect=["", "", ""]), patch("main.load_config") as config, patch("main.publish_post") as publish:
            self.assertEqual(main.main(["publish", str(self.path), "--dry-run"]), 0)
        config.assert_not_called()
        publish.assert_not_called()
        self.assertEqual(self.path.read_bytes(), SOURCE)
        self.assertIn('<code class="language-python">', read_post(self.path).html)

    def test_typora_math_becomes_katex_markup_without_touching_code(self):
        source = r"""正文 $E=mc^2$，还有 \(a+b\)。

$$
\frac{a}{b}
$$

\[
x<y
\]

\begin{align}
x &= 1
\end{align}

`$not_math$` 和 \$5。

```python
print("$not_math$")
```
"""
        self.path.write_text(source, encoding="utf-8")
        html = read_post(self.path).html
        self.assertIn('<span class="katex math inline">E=mc^2</span>', html)
        self.assertIn('<span class="katex math inline">a+b</span>', html)
        self.assertIn('<div class="katex math multi-line">', html)
        self.assertIn(r"\frac{a}{b}", html)
        self.assertIn("x&lt;y", html)
        self.assertIn(r"\begin{align}", html)
        self.assertEqual(html.count('class="katex math multi-line"'), 3)
        self.assertIn("<code>$not_math$</code>", html)
        self.assertIn('print(&quot;$not_math$&quot;)', html)
        self.assertEqual(html.count('class="katex math inline"'), 2)

    def test_text_styles_include_strikethrough_and_nested_emphasis(self):
        self.path.write_text(
            "***bold italic***\n\n~~deleted~~\n\n**bold *with italic***\n\n~~**deleted bold**~~\n\n`inline`\n",
            encoding="utf-8",
        )
        html = read_post(self.path).html
        self.assertIn("<strong><em>bold italic</em></strong>", html)
        self.assertIn("<del>deleted</del>", html)
        self.assertIn("<strong>bold <em>with italic</em></strong>", html)
        self.assertIn("<del><strong>deleted bold</strong></del>", html)
        self.assertIn("<code>inline</code>", html)

    def test_admonitions_and_github_callouts_survive_sanitization(self):
        self.path.write_text(
            '!!! note "Read me"\n    A **bold** note.\n\n'
            '> [!WARNING]\n> Be careful with `code`.\n\n'
            '> Ordinary quotation.\n',
            encoding="utf-8",
        )
        html = sanitize_html(read_post(self.path).html)
        self.assertIn('<div class="admonition note">', html)
        self.assertIn('<p class="admonition-title">Read me</p>', html)
        self.assertIn('<strong>bold</strong>', html)
        self.assertIn('<div class="admonition warning">', html)
        self.assertIn('<code>code</code>', html)
        self.assertIn('<blockquote>\n<p>Ordinary quotation.</p>\n</blockquote>', html)

    def test_safe_html_details_and_keyboard_tags_survive_publish(self):
        self.path.write_text(
            '<details markdown="1">\n<summary>Open</summary>\n\n- **Bold**\n\n</details>\n\n'
            '<div style="padding: 10px; border: 1px solid currentColor; background-image: url(javascript:alert(1))">Box</div>\n\n'
            'Press <kbd>Ctrl</kbd> + <kbd>C</kbd>\n',
            encoding="utf-8",
        )
        html = sanitize_html(read_post(self.path).html)
        self.assertIn('<details>', html)
        self.assertIn('<summary>Open</summary>', html)
        self.assertIn('<li><strong>Bold</strong></li>', html)
        self.assertIn('<kbd>Ctrl</kbd>', html)
        self.assertIn('padding: 10px; border: 1px solid currentColor;', html)
        self.assertNotIn('background-image', html)
        self.assertNotIn('javascript:', html)

    def test_math_block_next_to_text_is_separated_but_fenced_code_is_not(self):
        source = "文字紧贴公式\n$$\na = \\frac{qU}{md}\n$$\n后续文字\n\n~~~text\n$$\nnot math\n$$\n~~~\n"
        self.path.write_text(source, encoding="utf-8")
        html = read_post(self.path).html
        self.assertIn('<div class="katex math multi-line">', html)
        self.assertIn(r"a = \frac{qU}{md}", html)
        self.assertEqual(html.count('class="katex math multi-line"'), 1)
        self.assertIn('class="language-text">$$\nnot math\n$$', html)
        self.assertEqual(self.path.read_text(encoding="utf-8"), source)

    def test_first_publish_writes_id_then_updates_same_post(self):
        with patch("main.load_config", return_value=Config("https://example.com/blog", "user", "password")):
            with patch("main.publish_post", return_value=(123, "https://example.com/blog/test")) as publish:
                with patch("builtins.input", side_effect=["", "", "", "", "", ""]):
                    self.assertEqual(main.main(["publish", str(self.path)]), 0)
                    self.assertEqual(main.main(["publish", str(self.path)]), 0)
        self.assertEqual([call.args[-1] for call in publish.call_args_list], [None, 123])
        self.assertNotIn("title:", publish.call_args_list[0].args[2])
        self.assertNotIn("wp_id:", publish.call_args_list[0].args[2])
        result = self.path.read_bytes()
        self.assertIn(b"wp_id: 123", result)
        self.assertEqual(read_post(self.path).metadata["tags"], ["Python"])
        self.assertTrue(result.endswith(SOURCE.split(b"---\r\n", 2)[-1]))

    def test_plain_markdown_prompts_and_never_sends_yaml_as_content(self):
        source = b"# Heading\n\nHello **World**.\n"
        self.path.write_bytes(source)
        with patch("builtins.input", side_effect=["My title", "publish", ""]):
            with patch("main.load_config", return_value=Config("https://example.com/blog", "user", "password")):
                with patch("main.publish_post", return_value=(456, "https://example.com/blog/my-title")) as publish:
                    self.assertEqual(main.main(["publish", str(self.path)]), 0)
        self.assertEqual(publish.call_args.args[1], "My title")
        self.assertEqual(publish.call_args.args[3], "publish")
        self.assertNotIn("---", publish.call_args.args[2])
        self.assertNotIn("title:", publish.call_args.args[2])
        self.assertEqual(read_post(self.path).wp_id, 456)
        self.assertTrue(self.path.read_bytes().endswith(source))

    def test_changed_prompt_values_are_saved_after_update(self):
        self.path.write_bytes(b"---\ntitle: Old\nstatus: draft\nwp_id: 123\n---\nBody\n")
        with patch("builtins.input", side_effect=["New", "publish", ""]):
            with patch("main.load_config", return_value=Config("https://example.com/blog", "user", "password")):
                with patch("main.publish_post", return_value=(123, "")) as publish:
                    self.assertEqual(main.main(["publish", str(self.path)]), 0)
        self.assertEqual(publish.call_args.args[1:4], ("New", "<p>Body</p>", "publish"))
        self.assertEqual(read_post(self.path).title, "New")
        self.assertEqual(read_post(self.path).status, "publish")

    def test_failed_publish_keeps_source(self):
        with patch("builtins.input", side_effect=["", "", ""]), patch("main.load_config", return_value=Config("https://example.com/blog", "user", "password")):
            with patch("main.publish_post", side_effect=WordPressError("WordPress returned HTTP 401")):
                self.assertEqual(main.main(["publish", str(self.path)]), 1)
        self.assertEqual(self.path.read_bytes(), SOURCE)

    def test_changed_source_is_not_overwritten(self):
        post = read_post(self.path)
        self.path.write_bytes(SOURCE + b"changed")
        with self.assertRaises(PostError):
            post.write_metadata(123, "Test", "draft")
        self.assertEqual(self.path.read_bytes(), SOURCE + b"changed")

    def test_invalid_front_matter_is_rejected(self):
        for source, message in (
            (b"---\ntitle: Test\nBody\n", "closing"),
            (b"---\ntitle: Test\nstatus: private\n---\nBody\n", "status"),
        ):
            with self.subTest(message=message):
                self.path.write_bytes(source)
                with self.assertRaisesRegex(PostError, message):
                    read_post(self.path)

    def test_wordpress_http_and_json_errors(self):
        config = Config("https://example.com/blog", "user", "password")
        with patch("wordpress.requests.post") as request:
            response = request.return_value
            response.ok = False
            response.status_code = 404
            response.headers = {"Content-Type": "application/json"}
            response.json.return_value = {"message": "Not found"}
            with self.assertRaisesRegex(WordPressError, "post #123 was not found"):
                publish_post(config, "Test", "<p>x</p>", "draft", 123)
            response.ok = True
            response.json.side_effect = ValueError("bad JSON")
            with self.assertRaisesRegex(WordPressError, "invalid JSON"):
                publish_post(config, "Test", "<p>x</p>", "draft")

    def test_html_404_falls_back_to_query_rest_route(self):
        config = Config("https://example.com/blog", "user", "password")
        with patch("wordpress.requests.post") as request:
            request.side_effect = [
                type("Response", (), {"status_code": 404, "headers": {"Content-Type": "text/html"}})(),
                type("Response", (), {"status_code": 201, "ok": True, "json": lambda self: {"id": 123, "link": "https://example.com/blog/test"}})(),
            ]
            self.assertEqual(publish_post(config, "Test", "<p>x</p>", "draft", categories=[8]), (123, "https://example.com/blog/test"))
            self.assertEqual(request.call_args.args[0], "https://example.com/blog/index.php")
            self.assertEqual(request.call_args.kwargs["params"], {"rest_route": "/wp/v2/posts"})
            self.assertEqual(request.call_args.kwargs["json"]["categories"], [8])

    def test_publish_uses_configured_wordpress_subdirectory(self):
        config = Config("https://example.org/journal", "author", "app-password")
        created = Mock(ok=True, status_code=201, headers={})
        created.json.return_value = {"id": 42, "link": "https://example.org/journal/?p=42"}
        with patch("wordpress.requests.post", return_value=created) as request:
            self.assertEqual(
                publish_post(config, "Hello", "<p>World</p>", "draft"),
                (42, "https://example.org/journal/?p=42"),
            )
        self.assertEqual(request.call_args.args[0], "https://example.org/journal/wp-json/wp/v2/posts")
        self.assertEqual(request.call_args.kwargs["auth"], ("author", "app-password"))

    def test_publish_sanitizes_html_and_prevents_second_markdown_pass(self):
        config = Config("https://example.com/blog", "user", "password")
        created = Mock(ok=True, status_code=201, headers={})
        created.json.return_value = {"id": 146, "link": "https://example.com/blog/?p=146"}
        missing = Mock(status_code=404, headers={"Content-Type": "text/html"})
        content = (
            '<pre><code>&lt;script&gt;alert("Hello")&lt;/script&gt;</code></pre>'
            '<script>alert("raw")</script>'
            '<img src="https://example.com/a.png" onerror="alert(1)">'
            '<a href="javascript:alert(2)">bad link</a>'
            '<span class="katex math inline">E=mc^2</span>'
        )
        with patch("wordpress.requests.post", side_effect=[missing, created]) as request:
            publish_post(config, "Test", content, "publish")
        sent = request.call_args.kwargs["json"]["content"]
        self.assertTrue(sent.startswith("<!-- wp:html -->\n"))
        self.assertTrue(sent.endswith("\n<!-- /wp:html -->"))
        self.assertIn('&lt;script&gt;alert("Hello")&lt;/script&gt;', sent)
        self.assertNotIn("<script>", sent)
        self.assertNotIn("onerror=", sent)
        self.assertNotIn("javascript:", sent)
        self.assertIn('class="katex math inline"', sent)

    def test_sanitizer_keeps_markdown_tables_lists_and_images(self):
        safe = sanitize_html(
            '<ol start="3"><li>third</li></ol>'
            '<table><thead><tr><th scope="col">A</th></tr></thead></table>'
            '<img src="https://example.com/photo.png" alt="photo">'
            '<svg onload="alert(1)"></svg>'
        )
        self.assertIn('<ol start="3"><li>third</li></ol>', safe)
        self.assertIn('<th scope="col">A</th>', safe)
        self.assertIn('src="https://example.com/photo.png"', safe)
        self.assertNotIn("<svg", safe)
        self.assertIn('&lt;svg onload="alert(1)"&gt;', safe)

    def test_media_upload_uses_binary_body_and_wordpress_source_url(self):
        config = Config("https://example.com/blog", "user", "password")
        missing = Mock(status_code=404, headers={"Content-Type": "text/html"})
        created = Mock(ok=True, status_code=201, headers={"Content-Type": "application/json"})
        created.json.return_value = {"id": 77, "source_url": "https://example.com/blog/wp-content/uploads/photo.png"}
        with patch("wordpress.requests.post", side_effect=[missing, created]) as request:
            self.assertEqual(upload_media(config, b"image bytes", "image/png", "99blog-test.png"),
                             (77, "https://example.com/blog/wp-content/uploads/photo.png"))
        self.assertEqual(request.call_args.args[0], "https://example.com/blog/index.php")
        self.assertEqual(request.call_args.kwargs["params"], {"rest_route": "/wp/v2/media"})
        self.assertEqual(request.call_args.kwargs["data"], b"image bytes")
        self.assertEqual(request.call_args.kwargs["headers"]["Content-Type"], "image/png")

    def test_categories_reuse_exact_name_and_create_missing_name(self):
        config = Config("https://example.com/blog", "user", "password")
        existing = Mock(ok=True, status_code=200, headers={})
        existing.json.return_value = [{"id": 8, "name": "Python"}, {"id": 9, "name": "Python Tips"}]
        missing = Mock(ok=True, status_code=200, headers={})
        missing.json.return_value = []
        created = Mock(ok=True, status_code=201, headers={})
        created.json.return_value = {"id": 27, "name": "技术"}
        with patch("wordpress.requests.get", side_effect=[existing, missing]) as get:
            with patch("wordpress.requests.post", return_value=created) as post:
                self.assertEqual(resolve_categories(config, ["Python", "技术"]), [8, 27])
        self.assertEqual(get.call_count, 2)
        post.assert_called_once()
        self.assertEqual(post.call_args.kwargs["json"], {"name": "技术"})

    def test_publish_sends_category_ids_and_saves_names(self):
        with patch("builtins.input", side_effect=["", "", "技术, Python"]):
            with patch("main.load_config", return_value=Config("https://example.com/blog", "user", "password")):
                with patch("main.resolve_categories", return_value=[27, 8]) as resolve:
                    with patch("main.publish_post", return_value=(123, "")) as publish:
                        self.assertEqual(main.main(["publish", str(self.path)]), 0)
        resolve.assert_called_once()
        self.assertEqual(publish.call_args.kwargs["categories"], [27, 8])
        self.assertEqual(read_post(self.path).categories, ["技术", "Python"])

    def test_clear_categories_sends_empty_list(self):
        self.path.write_bytes(b"---\ntitle: Test\nstatus: publish\nwp_id: 123\ncategories:\n- Python\n---\nBody\n")
        with patch("builtins.input", side_effect=["", "", "-"]):
            with patch("main.load_config", return_value=Config("https://example.com/blog", "user", "password")):
                with patch("main.resolve_categories") as resolve:
                    with patch("main.publish_post", return_value=(123, "")) as publish:
                        self.assertEqual(main.main(["publish", str(self.path)]), 0)
        resolve.assert_not_called()
        self.assertEqual(publish.call_args.kwargs["categories"], [])
        self.assertEqual(read_post(self.path).categories, [])

    def test_local_image_is_uploaded_once_and_html_uses_wordpress_url(self):
        source = b"# Photo\n\n![local](assets/photo.png)\n\n![again](assets/photo.png)\n\n![remote](https://example.com/other.png)\n"
        self.path.write_bytes(source)
        asset = self.path.parent / "assets" / "photo.png"
        asset.parent.mkdir()
        asset.write_bytes(b"\x89PNG\r\n\x1a\nfirst image")
        config = Config("https://example.com/blog", "user", "password")
        post = read_post(self.path)
        images = find_local_images(post, post.html)
        with patch("images.upload_media", return_value=(77, "https://example.com/blog/wp-content/uploads/photo.png")) as upload:
            html, cache, count = replace_with_wordpress_urls(config, post.html, images, {})
            self.assertEqual(count, 1)
            self.assertEqual(upload.call_count, 1)
            self.assertEqual(html.count('src="https://example.com/blog/wp-content/uploads/photo.png"'), 2)
            self.assertIn('src="https://example.com/other.png"', html)
            _, again, count = replace_with_wordpress_urls(config, post.html, images, cache)
            self.assertEqual(count, 0)
            self.assertEqual(again, cache)
            self.assertEqual(upload.call_count, 1)
        self.assertEqual(self.path.read_bytes(), source)

    def test_image_on_another_windows_drive_can_be_uploaded_and_reused(self):
        self.path.write_text("![photo](photo.png)\n", encoding="utf-8")
        asset = self.path.parent / "photo.png"
        asset.write_bytes(b"image bytes")
        post = read_post(self.path)
        with patch("images.os.path.relpath", side_effect=ValueError("different drives")):
            images = find_local_images(post, post.html)
        self.assertEqual(images["photo.png"].key, asset.resolve().as_posix())
        config = Config("https://example.com/blog", "user", "password")
        remote = "https://example.com/blog/wp-content/uploads/photo.png"
        with patch("images.upload_media", return_value=(77, remote)) as upload:
            html, cache, uploaded = replace_with_wordpress_urls(config, post.html, images, {})
            self.assertEqual(uploaded, 1)
            self.assertIn(f'src="{remote}"', html)
            _, _, uploaded = replace_with_wordpress_urls(config, post.html, images, cache)
            self.assertEqual(uploaded, 0)
            upload.assert_called_once()

    def test_changed_image_uploads_again(self):
        self.path.write_text("![local](photo.png)\n", encoding="utf-8")
        asset = self.path.parent / "photo.png"
        asset.write_bytes(b"first")
        config = Config("https://example.com/blog", "user", "password")
        post = read_post(self.path)
        with patch("images.upload_media", side_effect=[(77, "https://example.com/old.png"), (78, "https://example.com/new.png")]) as upload:
            _, cache, _ = replace_with_wordpress_urls(config, post.html, find_local_images(post, post.html), {})
            asset.write_bytes(b"changed")
            html, cache, count = replace_with_wordpress_urls(config, post.html, find_local_images(post, post.html), cache)
        self.assertEqual(count, 1)
        self.assertEqual(upload.call_count, 2)
        self.assertIn("https://example.com/new.png", html)

    def test_cli_saves_media_cache_and_reuses_it_on_update(self):
        source = b"# Photo\n\n![local](photo.png)\n"
        self.path.write_bytes(source)
        (self.path.parent / "photo.png").write_bytes(b"image bytes")
        remote = "https://example.com/blog/wp-content/uploads/photo.png"
        with patch("builtins.input", side_effect=["", "", "", "", "", ""]):
            with patch("main.load_config", return_value=Config("https://example.com/blog", "user", "password")):
                with patch("images.upload_media", return_value=(77, remote)) as upload:
                    with patch("main.publish_post", return_value=(456, "")) as publish:
                        self.assertEqual(main.main(["publish", str(self.path)]), 0)
                        self.assertEqual(main.main(["publish", str(self.path)]), 0)
        self.assertEqual(upload.call_count, 1)
        self.assertIn(remote, publish.call_args_list[0].args[2])
        self.assertIn(remote, publish.call_args_list[1].args[2])
        self.assertEqual(read_post(self.path).wp_media["photo.png"]["id"], 77)
        self.assertTrue(self.path.read_bytes().endswith(source))

    def test_missing_local_image_stops_before_network(self):
        self.path.write_text("![missing](assets/missing.png)\n", encoding="utf-8")
        with patch("main.load_config") as config, patch("main.publish_post") as publish:
            self.assertEqual(main.main(["publish", str(self.path)]), 1)
        config.assert_not_called()
        publish.assert_not_called()

    def test_media_upload_failure_does_not_publish_or_write_metadata(self):
        source = b"![local](photo.png)\n"
        self.path.write_bytes(source)
        (self.path.parent / "photo.png").write_bytes(b"image bytes")
        with patch("builtins.input", side_effect=["", "", ""]):
            with patch("main.load_config", return_value=Config("https://example.com/blog", "user", "password")):
                with patch("images.upload_media", side_effect=WordPressError("WordPress returned HTTP 403")):
                    with patch("main.publish_post") as publish:
                        self.assertEqual(main.main(["publish", str(self.path)]), 1)
        publish.assert_not_called()
        self.assertEqual(self.path.read_bytes(), source)


if __name__ == "__main__":
    unittest.main()
