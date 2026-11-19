from app.crawlers.html_parser import discover_page_links, parse_page
from app.services.platform_detection import detect_platform


def test_parser_extracts_visible_text_and_discovers_official_links():
    page = parse_page(
        """
        <html><head><title>Example Journal</title><style>hidden style</style></head>
        <body><h1>Example Journal</h1><script>hidden script</script>
        <a href="/authors/guide">Guide for Authors</a>
        <a href="https://submit.example.com/login">Submit Your Manuscript</a>
        <a href="/news">Latest news</a></body></html>
        """,
        "https://journal.example/home",
    )
    assert page.title == "Example Journal"
    assert "hidden script" not in page.text
    assert "hidden style" not in page.text
    links = discover_page_links(page)
    assert links.guideline_urls == ("https://journal.example/authors/guide",)
    assert links.submission_urls == ("https://submit.example.com/login",)


def test_parser_detects_login_and_captcha_without_bypassing():
    login = parse_page(
        '<form><input type="password"><button>Sign in</button></form>',
        "https://submit.example.com",
    )
    captcha = parse_page("<div>Verify you are human with CAPTCHA</div>", "https://x.example")
    assert login.requires_login is True
    assert captcha.has_captcha is True


def test_platform_detection_uses_url_and_page_evidence():
    editorial = detect_platform(
        "https://www.editorialmanager.com/example/default.aspx",
        "Editorial Manager",
        "Login",
    )
    scholarone = detect_platform(
        "https://mc.manuscriptcentral.com/example",
        "Manuscript Central",
        "Sign in",
    )
    ojs = detect_platform(
        "https://journal.example/index.php/example/about/submissions",
        "Submissions",
        "Open Journal Systems",
    )
    unknown = detect_platform("https://example.com", "Example", "No platform evidence")
    assert editorial.code == "EDITORIAL_MANAGER"
    assert editorial.confidence >= 0.95
    assert scholarone.code == "SCHOLARONE"
    assert ojs.code == "OJS"
    assert unknown.code == "UNKNOWN"
    assert unknown.confidence == 0
