<?php
/**
 * Plugin Name: 99blog Article HTML
 * Description: Styles safe HTML details and keyboard elements in articles.
 */

add_action('wp_head', function () {
    ?>
    <style id="99blog-article-html">
    .single-content details {
        margin: 1em 0;
        padding: 0.6em 0.9em;
        border: 1px solid currentColor;
        border-radius: 0.4em;
    }
    .single-content details > summary {
        cursor: pointer;
        font-weight: 600;
    }
    .single-content kbd {
        display: inline-block;
        padding: 0.1em 0.4em;
        border: 1px solid currentColor;
        border-radius: 0.25em;
        font-family: monospace;
        font-size: 0.9em;
        line-height: 1.3;
    }
    </style>
    <?php
}, 99);
