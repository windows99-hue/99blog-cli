<?php
/**
 * Plugin Name: 99blog Mermaid
 * Description: Renders Mermaid code fences in published Markdown posts.
 */

// Convert Mermaid fences before the theme's code highlighter rewrites <pre>.
add_filter('the_content', function ($content) {
    return preg_replace_callback('~<pre\b[^>]*>\s*<code\b([^>]*)>(.*?)</code>\s*</pre>~is', function ($match) {
        if (!preg_match('/\bclass\s*=\s*(["\'])(.*?)\1/i', $match[1], $classes)
            || !preg_match('/(?:^|\s)language-mermaid(?:\s|$)/i', $classes[2])) {
            return $match[0];
        }
        // WordPress texturizes plain text, which changes Mermaid arrows like -->.
        // Text inside <code> is left intact until the browser renderer reads it.
        return '<div class="blog-mermaid mermaid"><code class="mermaid-source">' . $match[2] . '</code></div>';
    }, $content);
}, 8);

add_action('wp_enqueue_scripts', function () {
    if (!is_singular()) return;
    $post = get_queried_object();
    if (!($post instanceof WP_Post) || strpos($post->post_content, 'language-mermaid') === false) return;

    $base = content_url('mu-plugins');
    wp_enqueue_script('99blog-mermaid-library', $base . '/mermaid-11.17.2.min.js', array(), '11.17.2', true);
    wp_enqueue_script('99blog-mermaid-render', $base . '/99blog-mermaid.js', array('99blog-mermaid-library'), (string) filemtime(__DIR__ . '/99blog-mermaid.js'), true);
});

add_action('wp_head', function () {
    if (!is_singular()) return;
    ?>
    <style id="99blog-mermaid-style">
    .single-content .blog-mermaid {
        max-width: 100%;
        margin: 1.2em 0;
        padding: 1em;
        overflow-x: auto;
        border-radius: 0.5em;
        background: #fff;
        color: #222;
    }
    .single-content .blog-mermaid svg {
        display: block;
        max-width: 100%;
        margin: auto;
    }
    </style>
    <?php
}, 99);
