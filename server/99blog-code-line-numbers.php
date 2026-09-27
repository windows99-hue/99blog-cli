<?php
/**
 * Plugin Name: 99blog Code Line Numbers
 * Description: Aligns line numbers inside the gutter of regular code blocks.
 */

add_action('wp_head', function () {
    if (!is_singular()) return;
    ?>
    <style id="99blog-code-line-numbers">
    .post-single pre.prettyprint ol.linenums {
        counter-reset: blog-code-line;
    }
    .post-single pre.prettyprint ol.linenums > li {
        position: relative;
        list-style: none !important;
        counter-increment: blog-code-line;
    }
    .post-single pre.prettyprint ol.linenums > li::before {
        content: counter(blog-code-line);
        position: absolute;
        top: 0;
        right: calc(100% + 1.2em);
        width: 2.2em;
        color: var(--code-line-number);
        line-height: inherit;
        text-align: right;
        user-select: none;
    }
    </style>
    <?php
}, 99);
