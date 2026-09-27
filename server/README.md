# 博客端可选补丁

`99blog-cli` 的基础发布只需要 WordPress REST API 和应用密码。此目录中的 PHP 文件是 WordPress MU 插件，用于 99blog 的显示效果；`pip install` 不会把它们安装到 WordPress。

当前适配范围：

| 文件 | 用途 | 适配条件 |
| --- | --- | --- |
| `99blog-mermaid.php`、`assets/99blog-mermaid.js`、`assets/mermaid-11.17.2.min.js` | Mermaid 图表 | 样式和脚本选择器使用 `.single-content`；三个文件在 MU 插件目录中需位于同一级 |
| `99blog-katex-fix.php` | 数学公式 | 依赖 WP-Editor.md 安装路径和 KaTeX 资源 |
| `99blog-admonitions.php`、`99blog-diff.php` | 提示框和 diff 样式 | 样式选择器使用 `.single-content` |
| `99blog-article-lists.php`、`99blog-article-rules.php`、`99blog-article-html.php` | 列表、分割线和 HTML 元素样式 | 样式选择器使用 `.single-content`，列表补丁针对 Kizumi 主题 |
| `99blog-code-line-numbers.php` | 普通代码框行号 | 针对 Kizumi 的 `.post-single pre.prettyprint ol.linenums` 结构 |
| `99blog-content-safety.php` | 展示旧文章前再过滤 HTML | 使用 WordPress 核心 `wp_kses_post()`；请先确认旧文章是否依赖会被过滤的 HTML |

其他主题可把需要的文件放到 WordPress 的 `wp-content/mu-plugins/`，然后根据主题的文章容器调整 CSS/JS 选择器。PHP 文件在 MU 插件目录中会自动加载；请勿直接复制不需要的主题补丁。自行部署 Mermaid 时，保留 `assets/mermaid-11.17.2-LICENSE` 中的许可证文本。
