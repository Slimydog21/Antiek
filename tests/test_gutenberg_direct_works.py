from acquisition.books.public_domain import gutenberg_direct_works


def test_gutenberg_direct_works_builds_cache_urls():
    works = gutenberg_direct_works([11, 1080])
    assert len(works) == 2
    assert works[0].download_url.endswith("/pg11.txt")
    assert works[0].download_format == "text"
    assert works[0].pd_basis and "11" in works[0].pd_basis
    assert works[0].source == "project_gutenberg"
    assert "Alice" in works[0].title
