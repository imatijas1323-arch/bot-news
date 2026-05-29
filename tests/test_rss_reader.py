from news_bot.rss_reader import extract_first_img_src, extract_image_url


def test_extract_first_img_src_from_html():
    html = '<p>Text</p><img src="https://example.com/image.jpg" alt="x">'

    assert extract_first_img_src(html) == "https://example.com/image.jpg"


def test_extract_image_url_from_summary_img():
    entry = {"summary": '<img src="https://example.com/summary.jpg">'}

    assert extract_image_url(entry) == "https://example.com/summary.jpg"
