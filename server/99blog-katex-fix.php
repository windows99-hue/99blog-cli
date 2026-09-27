<?php
/**
 * Plugin Name: 99blog KaTeX Footer Fix
 * Description: Renders WP-Editor.md math after its scripts finish loading.
 */

add_action('wp_enqueue_scripts', function () {
    wp_enqueue_style(
        '99blog-katex-local',
        content_url('plugins/wp-editormd/assets/KaTeX/katex.min.css'),
        array(),
        '10.2.1'
    );
});

add_action('wp_footer', function () {
    $fallback_url = content_url('plugins/wp-editormd/assets/KaTeX/katex.min.js');
    ?>
    <script>
    (function () {
        function renderMath() {
            if (!window.katex) {
                var script = document.createElement('script');
                script.src = <?php echo wp_json_encode($fallback_url); ?>;
                script.onload = renderMath;
                document.head.appendChild(script);
                return;
            }
            document.querySelectorAll('.katex.math.inline, .katex.math.multi-line').forEach(function (element) {
                if (element.querySelector('.katex-html')) return;
                var tex = element.textContent.trim();
                try {
                    window.katex.render(tex, element, {
                        displayMode: element.classList.contains('multi-line'),
                        throwOnError: false
                    });
                } catch (error) {
                    console.error('KaTeX rendering failed:', error);
                }
            });
        }
        if (document.readyState === 'complete') renderMath();
        else window.addEventListener('load', renderMath, {once: true});
    })();
    </script>
    <?php
}, 100);
