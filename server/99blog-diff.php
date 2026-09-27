<?php
/**
 * Plugin Name: 99blog Diff Blocks
 * Description: Gives Markdown diff code fences readable line-by-line styling.
 */

// Run before the theme rewrites <pre> blocks for syntax highlighting.
add_filter('the_content', function ($content) {
    return preg_replace_callback('~<pre\b[^>]*>\s*<code\b([^>]*)>(.*?)</code>\s*</pre>~is', function ($match) {
        if (!preg_match('/\bclass\s*=\s*(["\'])(.*?)\1/i', $match[1], $classes)
            || !preg_match('/(?:^|\s)language-(?:diff|patch)(?:\s|$)/i', $classes[2])) {
            return $match[0];
        }

        $lines = preg_split('/\r\n|\r|\n/', $match[2]);
        if (end($lines) === '') array_pop($lines);
        $rendered = '<div class="blog-diff">';
        foreach ($lines as $line) {
            if (preg_match('/^(?:diff --git\b|index\s|---\s|\+\+\+\s)/', $line)) {
                $type = 'file';
            } elseif (strncmp($line, '@@', 2) === 0) {
                $type = 'hunk';
            } elseif (strncmp($line, '+', 1) === 0) {
                $type = 'added';
            } elseif (strncmp($line, '-', 1) === 0) {
                $type = 'removed';
            } else {
                $type = 'context';
            }
            $rendered .= '<div class="blog-diff-line ' . $type . '"><code>' . $line . '</code></div>';
        }
        return $rendered . '</div>';
    }, $content);
}, 8);

add_action('wp_head', function () {
    if (!is_singular()) return;
    ?>
    <style id="99blog-diff-style">
    .single-content .blog-diff {
        margin: 1.2em 0;
        padding: 0.45em 0;
        overflow-x: auto;
        border: 1px solid rgba(128, 128, 128, 0.3);
        border-radius: 0.5em;
        background: rgba(128, 128, 128, 0.06);
        counter-reset: diff-line;
    }
    .single-content .blog-diff-line {
        display: flex;
        min-width: max-content;
        margin: 0;
        padding: 0.12em 1em 0.12em 0;
        line-height: 1.55;
        counter-increment: diff-line;
    }
    .single-content .blog-diff-line::before {
        content: counter(diff-line);
        flex: 0 0 3.5em;
        padding-right: 1em;
        color: inherit;
        text-align: right;
        opacity: 0.45;
        user-select: none;
    }
    .single-content .blog-diff-line > code {
        padding: 0;
        border: 0;
        background: transparent;
        color: inherit;
        font: inherit;
        font-family: ui-monospace, SFMono-Regular, Consolas, 'Liberation Mono', monospace;
        white-space: pre;
    }
    .single-content .blog-diff-line.added {
        color: #54c87a;
        background: rgba(63, 185, 80, 0.13);
    }
    .single-content .blog-diff-line.removed {
        color: #f47b78;
        background: rgba(248, 81, 73, 0.13);
    }
    .single-content .blog-diff-line.hunk {
        color: #9d9af7;
        background: rgba(120, 110, 240, 0.11);
    }
    .single-content .blog-diff-line.file {
        color: #8bbfff;
        font-weight: 600;
    }
    </style>
    <?php
}, 99);
