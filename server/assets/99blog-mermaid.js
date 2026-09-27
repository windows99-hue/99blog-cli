(function () {
    if (!window.mermaid) return;

    // Mermaid registers its own load handler. Disable it before that handler
    // can process our source <code> elements as diagram syntax.
    window.mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        htmlLabels: false,
        theme: 'default'
    });

    function renderDiagrams() {
        var diagrams = Array.from(document.querySelectorAll('.single-content .blog-mermaid.mermaid'));
        diagrams.forEach(function (diagram) {
            var source = diagram.querySelector('code.mermaid-source');
            if (source) diagram.textContent = source.textContent;
        });
        var codes = document.querySelectorAll('.single-content pre code.language-mermaid');
        codes.forEach(function (code) {
            var pre = code.closest('pre');
            if (!pre) return;

            var diagram = document.createElement('div');
            diagram.className = 'blog-mermaid mermaid';
            diagram.textContent = code.textContent.trim();
            pre.replaceWith(diagram);
            diagrams.push(diagram);
        });

        if (!diagrams.length) return;

        window.mermaid.run({nodes: diagrams, suppressErrors: true}).catch(function (error) {
            console.error('Mermaid rendering failed:', error);
        });
    }

    if (document.readyState === 'complete') renderDiagrams();
    else window.addEventListener('load', renderDiagrams, {once: true});
})();
