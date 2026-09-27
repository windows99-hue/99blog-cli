<?php
/**
 * Plugin Name: 99blog Article Rules
 * Description: Makes Markdown horizontal rules visible in article content.
 */

add_action('wp_head', function () {
    ?>
    <style id="99blog-article-rules">
    .single-content hr {
        height: 1px;
        margin: 1.5em 0;
        border: 0;
        background-color: currentColor;
        opacity: 0.35;
    }
    </style>
    <?php
}, 99);
