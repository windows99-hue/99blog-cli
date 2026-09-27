<?php
/**
 * Plugin Name: 99blog Admonitions
 * Description: Styles Markdown admonitions and GitHub-style callouts in posts.
 */

add_action('wp_head', function () {
    ?>
    <style id="99blog-admonitions">
    .single-content .admonition {
        --admonition-color: #58a6ff;
        margin: 1.2em 0;
        padding: 0.75em 1em;
        border-left: 4px solid var(--admonition-color);
        border-radius: 0.35em;
        background: rgba(88, 166, 255, 0.1);
    }
    .single-content .admonition.tip {
        --admonition-color: #3fb950;
        background: rgba(63, 185, 80, 0.1);
    }
    .single-content .admonition.important {
        --admonition-color: #a371f7;
        background: rgba(163, 113, 247, 0.1);
    }
    .single-content .admonition.warning,
    .single-content .admonition.caution {
        --admonition-color: #d29922;
        background: rgba(210, 153, 34, 0.1);
    }
    .single-content .admonition.danger,
    .single-content .admonition.error {
        --admonition-color: #f85149;
        background: rgba(248, 81, 73, 0.1);
    }
    .single-content .admonition > .admonition-title {
        margin: 0 0 0.45em;
        color: var(--admonition-color);
        font-weight: 700;
    }
    .single-content .admonition > :last-child {
        margin-bottom: 0;
    }
    </style>
    <?php
}, 99);
