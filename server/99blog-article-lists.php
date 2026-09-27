<?php
/**
 * Plugin Name: 99blog Article List Styles
 * Description: Restores list markers in article content under the Kizumi theme.
 */

add_action('wp_head', function () {
    ?>
    <style id="99blog-article-lists">
    .single-content ul:not(.list-unstyled):not(.linenums),
    .single-content ol:not(.ol):not(.linenums) {
        padding-left: 1.6em;
        margin: 0.6em 0 1em;
    }
    .single-content ul:not(.list-unstyled):not(.linenums) > li {
        list-style-type: disc;
        list-style-position: outside;
    }
    .single-content ul:not(.list-unstyled):not(.linenums) ul > li {
        list-style-type: circle;
    }
    .single-content ul:not(.list-unstyled):not(.linenums) ul ul > li {
        list-style-type: square;
    }
    .single-content ol:not(.ol):not(.linenums) > li {
        list-style-type: decimal;
        list-style-position: outside;
    }
    </style>
    <?php
}, 99);
