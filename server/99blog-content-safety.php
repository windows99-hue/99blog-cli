<?php
/**
 * Plugin Name: 99blog Content Safety
 * Description: Filters executable markup from rendered post content.
 */

// WP-Editor.md can decode HTML entities from code examples while saving.
// Filter after content plugins so older posts remain safe to view as well.
add_filter('the_content', function ($content) {
    return wp_kses_post($content);
}, PHP_INT_MAX);
